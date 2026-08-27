# mcp-server/tools/git_manage.py
# git 管理工具（对应 skill Phase 0/3/9）
# 作用：
#   git_status  —— 只读检测目录是否为 git 仓库、远程、分支、脏状态（Phase 3）
#   git_commit  —— init + 首次提交 / 增量提交（Phase 3/9）
#   git_push    —— 推送 + CI 仓库检测（默认 fork+PR）+ 按需创建私有远程仓库（Phase 9）
# 设计：全部通过子进程调用本机 git；GitHub API 只做仓库创建与 CI 探测。
import json
import os
import re
import shutil
import subprocess
import sys

import requests

# 与 github_access.py 一致的 GitHub 访问配置
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
HEADERS = {"Authorization": f"token {TOKEN}"} if TOKEN else {}
TIMEOUT = 15
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# .gitignore 模板（Phase 3 init 时写入；排除构建产物与本地工具文件）
GITIGNORE_TEMPLATE = """# 构建产物
bin/
obj/
*.dll
*.pdb
*.exe
# 测试服务器目录
ServerPlugins/
# IDE / 系统
.vs/
*.user
.DS_Store
"""


def _err(message: str, hint: str = "", fallback: str = "") -> dict:
    """统一错误格式：error 表示出错，hint 为排查建议，fallback 为降级路径。"""
    return {"error": message, "hint": hint, "fallback": fallback}


def _find_git() -> str:
    """探测 git 可执行文件路径：GIT_EXECUTABLE > 常见安装路径 > PATH。找不到返回 None。"""
    candidates = []
    env_git = os.environ.get("GIT_EXECUTABLE", "")
    if env_git:
        candidates.append(env_git)
    candidates += [
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe",
        r"D:\Git\bin\git.exe",
        "/usr/bin/git",
        "/usr/local/bin/git",
    ]
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return cand
    which = shutil.which("git")
    return which


def _run_git(project_dir: str, *args: str) -> tuple:
    """在 project_dir 运行 git 命令，返回 (returncode, stdout, stderr)。git 不可用抛 RuntimeError。"""
    git = _find_git()
    if not git:
        raise RuntimeError(
            "未找到 git。请安装 Git 或设置环境变量 GIT_EXECUTABLE 指向 git.exe"
        )
    proc = subprocess.run(
        [git, "-C", project_dir] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def git_status(project_dir: str) -> dict:
    """只读检测目录的 git 状态（Phase 3 脚手架 / Phase 9 交付前）。

    参数：
        project_dir: 项目目录绝对路径

    返回 JSON：is_git_repo/remote_url/branch/dirty/untracked_files/git_available/git_path。
    """
    if not project_dir:
        return _err("缺少参数 project_dir", "用法：git_status(project_dir)", "")
    if not os.path.isdir(project_dir):
        return _err(f"目录不存在：{project_dir}", "确认项目目录路径正确", "")

    git = _find_git()
    if not git:
        return {
            "is_git_repo": os.path.isdir(os.path.join(project_dir, ".git")),
            "git_available": False,
            "git_path": "",
            "remote_url": "", "branch": "", "dirty": False, "untracked_files": [],
            "hint": "未找到 git。请安装 Git 或设置 GIT_EXECUTABLE 后重试。",
        }

    is_repo = os.path.isdir(os.path.join(project_dir, ".git"))
    if not is_repo:
        return {
            "is_git_repo": False, "git_available": True, "git_path": git,
            "remote_url": "", "branch": "", "dirty": False, "untracked_files": [],
            "hint": "不是 git 仓库。Phase 3 可调 git_commit(init_if_needed=true) 初始化。",
        }

    remote_url, branch, dirty = "", "", False
    untracked = []
    try:
        rc, out, _ = _run_git(project_dir, "remote", "get-url", "origin")
        if rc == 0:
            remote_url = out
    except RuntimeError:
        pass
    try:
        rc, out, _ = _run_git(project_dir, "branch", "--show-current")
        if rc == 0:
            branch = out
    except RuntimeError:
        pass
    try:
        rc, out, _ = _run_git(project_dir, "status", "--porcelain")
        if rc == 0 and out:
            lines = [ln for ln in out.splitlines() if ln.strip()]
            untracked = [ln[3:] for ln in lines if ln.startswith("??")]
            dirty = len(lines) > 0
    except RuntimeError:
        pass

    return {
        "is_git_repo": True, "git_available": True, "git_path": git,
        "remote_url": remote_url, "branch": branch, "dirty": dirty,
        "untracked_files": untracked,
    }


def git_commit(project_dir: str, message: str, init_if_needed: bool = False) -> dict:
    """提交项目改动（Phase 3 首次提交 / Phase 9 最终提交）。

    参数：
        project_dir: 项目目录绝对路径
        message: 提交信息（如 "chore: 项目脚手架初始化"）
        init_if_needed: 目录未 init 时是否自动 git init + 写 .gitignore（Phase 3 用 true）

    返回 JSON：action(init/commit/skip)/commit_hash/changed_files/message。
    """
    if not project_dir:
        return _err("缺少参数 project_dir", "用法：git_commit(project_dir, message, init_if_needed)", "")
    if not message:
        return _err("缺少参数 message", "用法：git_commit(project_dir, message, init_if_needed)", "")
    if not os.path.isdir(project_dir):
        return _err(f"目录不存在：{project_dir}", "确认项目目录路径正确", "")

    try:
        is_repo = os.path.isdir(os.path.join(project_dir, ".git"))
        if not is_repo:
            if not init_if_needed:
                return _err(
                    "目录不是 git 仓库",
                    "Phase 3 需先初始化：调 git_commit(project_dir, message, init_if_needed=true)",
                    "",
                )
            rc, _, err = _run_git(project_dir, "init")
            if rc != 0:
                return _err(f"git init 失败：{err}", "检查 git 安装与目录权限", "")
            # 写 .gitignore（已存在则不覆盖）
            gi_path = os.path.join(project_dir, ".gitignore")
            if not os.path.isfile(gi_path):
                with open(gi_path, "w", encoding="utf-8") as f:
                    f.write(GITIGNORE_TEMPLATE)
            rc, _, err = _run_git(project_dir, "add", ".gitignore")
            if rc != 0:
                return _err(f"git add .gitignore 失败：{err}", "", "")

        rc, out, _ = _run_git(project_dir, "status", "--porcelain")
        if rc == 0 and not out.strip():
            return {"action": "skip", "commit_hash": "", "changed_files": [],
                    "message": message, "hint": "无改动，未产生空提交。"}

        rc, _, err = _run_git(project_dir, "add", "-A")
        if rc != 0:
            return _err(f"git add -A 失败：{err}", "检查是否有权限变更的冲突文件", "")

        rc, _, err = _run_git(project_dir, "commit", "-m", message)
        if rc != 0:
            hint = ("可能是 git 未配置 user.name/user.email。"
                    "请运行：git config --global user.name \"你的名字\" 和 "
                    "git config --global user.email \"你的邮箱\" 后重试")
            return _err(f"git commit 失败：{err}", hint, "")

        # 取最近提交 hash（短 7 位）
        hash_ = ""
        rc, out, _ = _run_git(project_dir, "rev-parse", "--short", "HEAD")
        if rc == 0:
            hash_ = out

        # changed_files：本次提交涉及的文件数
        rc, out, _ = _run_git(project_dir, "diff", "--name-only", "HEAD~1", "HEAD")
        changed = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []
        action = "init" if not is_repo else "commit"
        return {"action": action, "commit_hash": hash_, "changed_files": changed,
                "message": message}
    except RuntimeError as e:
        return _err(str(e), "安装 Git 或设置 GIT_EXECUTABLE 后重试", "")
    except subprocess.TimeoutExpired:
        return _err("git 命令超时", "检查 git 是否卡住（如等待凭据输入）", "")
