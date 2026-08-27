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


def _detect_ci_local(project_dir: str) -> dict:
    """探测本地仓库 .github/workflows/ 下的工作流文件。返回 ci_detected/ci_files。"""
    wf_dir = os.path.join(project_dir, ".github", "workflows")
    if not os.path.isdir(wf_dir):
        return {"ci_detected": False, "ci_files": []}
    files = sorted(f for f in os.listdir(wf_dir)
                   if f.endswith((".yml", ".yaml")) and os.path.isfile(os.path.join(wf_dir, f)))
    return {"ci_detected": bool(files), "ci_files": files}


def _detect_ci_remote(repo_full_name: str) -> dict:
    """用 GitHub API 探测远程仓库 .github/workflows/ 下的工作流（本地未 clone 时）。"""
    try:
        url = f"{API}/repos/{repo_full_name}/contents/.github/workflows"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 404:
            return {"ci_detected": False, "ci_files": []}
        resp.raise_for_status()
        files = [i["name"] for i in resp.json()
                 if i.get("type") == "file" and i["name"].endswith((".yml", ".yaml"))]
        return {"ci_detected": bool(files), "ci_files": files}
    except requests.RequestException as e:
        return {"ci_detected": False, "ci_files": [],
                "hint": f"CI 检测失败（{e}），按无 CI 处理，但建议人工确认目标仓库是否配置了构建工作流。"}


def _create_private_repo(repo_name: str) -> dict:
    """用 GitHub API 创建私有仓库。返回 (ok, repo_url, err_hint)。"""
    if not TOKEN:
        return False, "", "缺少 GITHUB_TOKEN/GH_TOKEN 环境变量，无法自动创建远程仓库。"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", repo_name):
        return False, "", f"仓库名不合法：{repo_name}（仅允许字母数字 . _ -）"
    try:
        resp = requests.post(
            f"{API}/user/repos",
            headers=HEADERS,
            json={"name": repo_name, "private": True, "auto_init": False},
            timeout=TIMEOUT,
        )
        if resp.status_code in (200, 201):
            return True, f"https://github.com/{resp.json().get('full_name')}.git", ""
        body = resp.json().get("message", resp.text)
        return False, "", f"创建仓库失败（HTTP {resp.status_code}）：{body}"
    except requests.RequestException as e:
        return False, "", f"创建仓库请求失败：{e}"


def git_push(project_dir: str, repo_url: str = "", visibility: str = "private") -> dict:
    """推送本地提交到远程，并检测目标仓库是否配置 CI（Phase 9）。

    参数：
        project_dir: 项目目录绝对路径
        repo_url: 目标远程仓库 URL（可带 .git 后缀）；留空时若本地无 origin 则按项目名创建私有仓库
        visibility: 仅创建新仓库时生效（private/public，默认 private）

    返回 JSON：pushed/repo_url/branch/ci_detected/ci_files/recommended_flow/notes。
    """
    if not project_dir:
        return _err("缺少参数 project_dir", "用法：git_push(project_dir, repo_url, visibility)", "")
    if not os.path.isdir(project_dir):
        return _err(f"目录不存在：{project_dir}", "确认项目目录路径正确", "")
    if visibility not in ("private", "public"):
        return _err("visibility 仅支持 private/public", "用法：git_push(project_dir, repo_url, visibility)", "")
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return _err(
            "目录不是 git 仓库，且尚未初始化",
            "Phase 3 需先 git_commit(init_if_needed=true)；Phase 9 前应已完成至少一次提交",
            "",
        )

    try:
        # 1) 确定远程 URL：优先 repo_url 参数；否则读本地 origin；否则创建私有仓库
        remote_url = repo_url
        created_repo = False
        if not remote_url:
            rc, out, _ = _run_git(project_dir, "remote", "get-url", "origin")
            if rc == 0 and out:
                remote_url = out
        if not remote_url:
            repo_name = os.path.basename(os.path.abspath(project_dir))
            ok, new_url, hint = _create_private_repo(repo_name)
            if not ok:
                return _err(
                    "本地无远程仓库且自动创建失败",
                    hint,
                    "可手动在 GitHub 建仓后：git remote add origin <url> && git push -u origin <branch>",
                )
            remote_url = new_url
            created_repo = True

        # 2) 解析 owner/repo 用于 CI 检测
        m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s#]+?)(?:\.git)?$", remote_url)
        repo_full = f"{m.group(1)}/{m.group(2)}" if m else ""
        ci = {"ci_detected": False, "ci_files": []}
        if repo_full:
            # 本地已有 .github/workflows 则优先读本地；否则 API 探测
            local_ci = _detect_ci_local(project_dir)
            ci = local_ci if local_ci["ci_detected"] else _detect_ci_remote(repo_full)

        # 3) CI 检测到 → 默认推荐 fork+PR，不直接推上游
        if ci["ci_detected"]:
            return {
                "pushed": False,
                "repo_url": remote_url,
                "branch": "",
                "ci_detected": True,
                "ci_files": ci["ci_files"],
                "recommended_flow": "fork_pr",
                "notes": (
                    f"目标仓库 {repo_full} 配置了构建工作流 {ci['ci_files']}。"
                    "直接 push 到 master/main 会触发自动构建并可能自动发 Release（如 UnrealMultiple/TShockPlugin、"
                    "Zykor-Club/TShockServerPlugin）。默认推荐：fork 上游 → 本地分支开发 → push 到 fork → 提 PR。"
                    "若你坚持直接推上游，请明确确认，我会先核对仓库结构要求（src/<插件>/、manifest.json、"
                    "不得提交 DLL）后再推送。"
                ),
            }

        # 4) 无 CI → 直接推送
        rc, out, _ = _run_git(project_dir, "branch", "--show-current")
        branch = out if rc == 0 else ""
        if not branch:
            rc, out, _ = _run_git(project_dir, "rev-parse", "--abbrev-ref", "HEAD")
            branch = out if rc == 0 else "HEAD"

        if created_repo or not _remote_exists(project_dir):
            rc, _, err = _run_git(project_dir, "remote", "add", "origin", remote_url)
            if rc != 0:
                # 已存在 origin 但 URL 不同则更新
                _run_git(project_dir, "remote", "set-url", "origin", remote_url)

        rc, _, err = _run_git(project_dir, "push", "-u", "origin", branch)
        if rc != 0:
            hint = ("推送失败。若是 403/认证错误：生成 GitHub Personal Access Token（需 repo 权限），"
                    "设置 GITHUB_TOKEN/GH_TOKEN 环境变量，或用 git config 配置凭据后重试。")
            return _err(f"git push 失败：{err}", hint, "")

        return {
            "pushed": True,
            "repo_url": remote_url,
            "branch": branch,
            "ci_detected": False,
            "ci_files": [],
            "recommended_flow": "direct_push",
            "notes": f"已推送到 {remote_url}（分支 {branch}）。" + ("已自动创建私有仓库。" if created_repo else ""),
        }
    except RuntimeError as e:
        return _err(str(e), "安装 Git 或设置 GIT_EXECUTABLE 后重试", "")
    except subprocess.TimeoutExpired:
        return _err("git 命令超时", "检查 git 是否卡住（如等待凭据输入）", "")


def _remote_exists(project_dir: str) -> bool:
    """判断本地是否已配置 origin 远程。"""
    try:
        rc, _, _ = _run_git(project_dir, "remote")
        return rc == 0
    except RuntimeError:
        return False


if __name__ == "__main__":
    # 调试：python git_manage.py status <目录> | commit <目录> <消息> [init]
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    d = sys.argv[2] if len(sys.argv) > 2 else ""
    if mode == "status":
        print(json.dumps(git_status(d), ensure_ascii=False, indent=2))
    elif mode == "commit":
        msg = sys.argv[3] if len(sys.argv) > 3 else "update"
        init = len(sys.argv) > 4 and sys.argv[4] == "init"
        print(json.dumps(git_commit(d, msg, init), ensure_ascii=False, indent=2))
    elif mode == "push":
        url = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(git_push(d, url), ensure_ascii=False, indent=2))
