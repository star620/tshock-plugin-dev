# git 管理功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 tshock-plugin-dev skill 增加贯穿全流程、仅首尾提交的 git 管理能力：git init/commit/push + CI 仓库检测（默认 fork+PR 建议），配套 3 个 MCP 工具与 1 份参考文档。

**Architecture:** 新增 `mcp-server/tools/git_manage.py` 实现 3 个工具（git_status / git_commit / git_push），通过子进程调用本机 git，GitHub API 只做仓库创建与 CI 探测（复用 github_access.py 的 TOKEN/API/_err 模式）。流程接入：Phase 0 新增第 4 问、Phase 3 init+首次提交、Phase 9 最终提交+推送。新增 `references/12-git管理.md` 文档。

**Tech Stack:** Python 3（标准库 subprocess/os/shutil + requests），MCP server（mcp>=2.0），git 命令行，pytest。

**Spec:** `docs/superpowers/specs/2026-08-27-git-management-design.md`（已批准）

---

### Task 1: git_manage.py 骨架 + git 路径探测 + git_status

**Files:**
- Create: `mcp-server/tools/git_manage.py`
- Test: `mcp-server/tests/test_git_manage.py`

- [ ] **Step 1: 编写失败测试**（git 路径探测 + git_status）

```python
# mcp-server/tests/test_git_manage.py
"""git_manage 工具测试：路径探测 / status / commit / push（CI 探测 mock）。"""
import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import git_manage

GIT = git_manage._find_git() or "git"  # 本机无 git 时测试仍可跑（用例会跳过/降级）


def _git(repo_dir, *args):
    subprocess.run([GIT, "-C", repo_dir] + list(args), check=True,
                   capture_output=True, text=True)


class TestFindGit(unittest.TestCase):
    def test_find_git_returns_path_or_none(self):
        # 只要不抛异常、返回 str 或 None 即可；不依赖本机是否装 git
        result = git_manage._find_git()
        self.assertTrue(result is None or isinstance(result, str))


class TestGitStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gitmgmt_")
        self.empty_dir = os.path.join(self.tmp, "empty")
        os.makedirs(self.empty_dir, exist_ok=True)
        self.repo_dir = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo_dir, exist_ok=True)
        if GIT != "git":
            _git(self.repo_dir, "init")
            _git(self.repo_dir, "config", "user.name", "Test")
            _git(self.repo_dir, "config", "user.email", "t@t.t")
            with open(os.path.join(self.repo_dir, "a.txt"), "w", encoding="utf-8") as f:
                f.write("hello")
            _git(self.repo_dir, "add", ".")
            _git(self.repo_dir, "commit", "-m", "init")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_non_repo(self):
        result = git_manage.git_status(self.empty_dir)
        self.assertFalse(result["is_git_repo"])

    def test_status_repo(self):
        if GIT == "git":
            self.skipTest("本机无 git，跳过仓库用例")
        result = git_manage.git_status(self.repo_dir)
        self.assertTrue(result["is_git_repo"])
        self.assertFalse(result["dirty"])
        self.assertIn("git_available", result)

    def test_status_missing_dir(self):
        result = git_manage.git_status(os.path.join(self.tmp, "nope"))
        self.assertEqual(result["error"], "目录不存在：nope".replace("nope", os.path.join(self.tmp, "nope")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest mcp-server/tests/test_git_manage.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'git_manage'`

- [ ] **Step 3: 实现 git_manage.py 骨架、路径探测、git_status**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest mcp-server/tests/test_git_manage.py -v`
Expected: PASS（3 个用例；本机无 git 时仓库用例 skip）

- [ ] **Step 5: 提交**

```bash
git add mcp-server/tools/git_manage.py mcp-server/tests/test_git_manage.py
git commit -m "feat: 新增 git_manage 工具骨架与 git_status 检测"
```

---

### Task 2: git_commit（init + 首次提交 / 增量提交 / 无变化 skip）

**Files:**
- Modify: `mcp-server/tools/git_manage.py`
- Test: `mcp-server/tests/test_git_manage.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 test_git_manage.py 的 TestGitStatus 类之后
class TestGitCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gitcommit_")
        self.dir_ = os.path.join(self.tmp, "proj")
        os.makedirs(self.dir_, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_commit_init_if_needed(self):
        if GIT == "git":
            self.skipTest("本机无 git，跳过仓库用例")
        result = git_manage.git_commit(self.dir_, "chore: 项目脚手架初始化", init_if_needed=True)
        self.assertEqual(result["action"], "init")
        self.assertTrue(os.path.isdir(os.path.join(self.dir_, ".git")))
        # .gitignore 已写入
        self.assertTrue(os.path.isfile(os.path.join(self.dir_, ".gitignore")))

    def test_commit_no_changes_skip(self):
        if GIT == "git":
            self.skipTest("本机无 git，跳过仓库用例")
        git_manage.git_commit(self.dir_, "chore: init", init_if_needed=True)
        result = git_manage.git_commit(self.dir_, "chore: again")
        self.assertEqual(result["action"], "skip")

    def test_commit_requires_init(self):
        if GIT == "git":
            self.skipTest("本机无 git，跳过仓库用例")
        result = git_manage.git_commit(self.dir_, "msg", init_if_needed=False)
        self.assertIn("error", result)

    def test_commit_missing_dir(self):
        result = git_manage.git_commit(os.path.join(self.tmp, "nope"), "msg")
        self.assertIn("error", result)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest mcp-server/tests/test_git_manage.py::TestGitCommit -v`
Expected: FAIL —— `AttributeError: module 'git_manage' has no attribute 'git_commit'`

- [ ] **Step 3: 实现 git_commit**

```python
# 追加到 git_manage.py 的 git_status 之后
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest mcp-server/tests/test_git_manage.py::TestGitCommit -v`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add mcp-server/tools/git_manage.py mcp-server/tests/test_git_manage.py
git commit -m "feat: git_commit 支持 init/增量提交/无变化跳过"
```

---

### Task 3: git_push（推送 + CI 检测 + 按需创建私有仓库）

**Files:**
- Modify: `mcp-server/tools/git_manage.py`
- Test: `mcp-server/tests/test_git_manage.py`

- [ ] **Step 1: 追加失败测试**（CI 检测用 mock，不真正联网推送）

```python
# 追加到 test_git_manage.py 的 TestGitCommit 类之后
class TestCiDetect(unittest.TestCase):
    def test_detect_ci_with_build_yml(self):
        # 本地仓库含 .github/workflows/build.yml → ci_detected=true
        tmp = tempfile.mkdtemp(prefix="gicit_")
        try:
            if GIT == "git":
                self.skipTest("本机无 git，跳过仓库用例")
            repo = os.path.join(tmp, "r")
            os.makedirs(os.path.join(repo, ".github", "workflows"), exist_ok=True)
            _git(repo, "init")
            with open(os.path.join(repo, ".github", "workflows", "build.yml"), "w", encoding="utf-8") as f:
                f.write("name: build\n")
            result = git_manage._detect_ci_local(repo)
            self.assertTrue(result["ci_detected"])
            self.assertIn("build.yml", result["ci_files"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_detect_ci_no_workflows(self):
        tmp = tempfile.mkdtemp(prefix="gicit_")
        try:
            if GIT == "git":
                self.skipTest("本机无 git，跳过仓库用例")
            repo = os.path.join(tmp, "r")
            os.makedirs(repo, exist_ok=True)
            _git(repo, "init")
            result = git_manage._detect_ci_local(repo)
            self.assertFalse(result["ci_detected"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_detect_ci_remote_api(self):
        # 无本地 clone 时走 GitHub API：mock requests 返回含 build.yml
        with mock.patch("git_manage.requests.get") as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [
                {"name": "build.yml", "type": "file"},
                {"name": "release.yml", "type": "file"},
            ]
            mock_get.return_value = mock_resp
            result = git_manage._detect_ci_remote("owner/repo")
            self.assertTrue(result["ci_detected"])
            self.assertIn("build.yml", result["ci_files"])

    def test_push_detects_ci_recommends_fork_pr(self):
        # 整链路：本地仓库无远程、repo_url 指向上游 CI 仓库 → 不直接推，推荐 fork+PR
        tmp = tempfile.mkdtemp(prefix="gipush_")
        try:
            if GIT == "git":
                self.skipTest("本机无 git，跳过仓库用例")
            repo = os.path.join(tmp, "r")
            os.makedirs(os.path.join(repo, ".github", "workflows"), exist_ok=True)
            _git(repo, "init")
            _git(repo, "config", "user.name", "Test")
            _git(repo, "config", "user.email", "t@t.t")
            with open(os.path.join(repo, ".github", "workflows", "build.yml"), "w", encoding="utf-8") as f:
                f.write("name: build\n")
            with open(os.path.join(repo, "a.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "init")
            # mock GitHub API（检测上游 CI 用），不真正联网
            with mock.patch("git_manage.requests.get") as mock_get:
                mock_resp = mock.MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = [{"name": "build.yml", "type": "file"}]
                mock_get.return_value = mock_resp
                result = git_manage.git_push(repo, repo_url="https://github.com/owner/repo.git")
            self.assertTrue(result["ci_detected"])
            self.assertEqual(result["recommended_flow"], "fork_pr")
            self.assertIn("fork", result["notes"].lower())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest mcp-server/tests/test_git_manage.py::TestCiDetect -v`
Expected: FAIL —— `AttributeError: module 'git_manage' has no attribute '_detect_ci_local'`

- [ ] **Step 3: 实现 git_push + CI 检测辅助函数**

```python
# 追加到 git_manage.py 的 git_commit 之后
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
                    "设置 GIT_TOKEN/GITHUB_TOKEN 环境变量，或用 git config 配置凭据后重试。")
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest mcp-server/tests/test_git_manage.py -v`
Expected: PASS（git_status 3 + git_commit 4 + CI 检测 4 = 11 个用例）

- [ ] **Step 5: 提交**

```bash
git add mcp-server/tools/git_manage.py mcp-server/tests/test_git_manage.py
git commit -m "feat: git_push 支持 CI 检测与按需创建私有仓库"
```

---

### Task 4: server.py 注册 3 个新工具

**Files:**
- Modify: `mcp-server/server.py`

- [ ] **Step 1: 修改 import 与注册**

在 server.py 顶部 import 中加入 `git_manage`：

```python
from tools import (build_check, fetch_tshock_source, git_manage, github_access,
                   load_log_check, project_util, source_fetch, version_resolver)
```

在文件末尾（`if __name__` 之前）追加 3 个工具注册：

```python
# ---------- 扩展工具：git 管理（Phase 0/3/9） ----------


@server.tool()
def git_status(project_dir: str) -> str:
    """检测目录的 git 状态（Phase 3 脚手架，判断是否需 init/复用）。

    参数：
        project_dir: 项目目录绝对路径

    返回 JSON：is_git_repo/remote_url/branch/dirty/untracked_files/git_available。
    """
    import json

    return json.dumps(git_manage.git_status(project_dir), ensure_ascii=False)


@server.tool()
def git_commit(project_dir: str, message: str, init_if_needed: bool = False) -> str:
    """提交项目改动；目录未初始化时可自动 git init + 写 .gitignore（Phase 3/9）。

    参数：
        project_dir: 项目目录绝对路径
        message: 提交信息（如 "chore: 项目脚手架初始化"）
        init_if_needed: 未 init 时是否自动初始化（Phase 3 用 true）

    返回 JSON：action(init/commit/skip)/commit_hash/changed_files/message。
    """
    import json

    return json.dumps(git_manage.git_commit(project_dir, message, init_if_needed), ensure_ascii=False)


@server.tool()
def git_push(project_dir: str, repo_url: str = "", visibility: str = "private") -> str:
    """推送本地提交到远程；检测目标仓库 CI，默认建议 fork+PR；可自动创建私有仓库（Phase 9）。

    参数：
        project_dir: 项目目录绝对路径
        repo_url: 目标远程 URL；留空且无 origin 时按项目名创建私有仓库
        visibility: 创建新仓库时生效（private/public，默认 private）

    返回 JSON：pushed/repo_url/branch/ci_detected/ci_files/recommended_flow/notes。
    """
    import json

    return json.dumps(git_manage.git_push(project_dir, repo_url, visibility), ensure_ascii=False)
```

- [ ] **Step 2: 语法检查**

Run: `python -m py_compile mcp-server/server.py mcp-server/tools/git_manage.py`
Expected: 无输出（编译通过）

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest mcp-server/tests -v`
Expected: PASS（原 13 工具测试 + 新增 git_manage 11 个用例全部通过）

- [ ] **Step 4: 提交**

```bash
git add mcp-server/server.py
git commit -m "feat: server.py 注册 git_status/git_commit/git_push 工具"
```

---

### Task 5: references/12-git管理.md 参考文档

**Files:**
- Create: `references/12-git管理.md`

- [ ] **Step 1: 编写文档**

```markdown
# 12 git 管理（Phase 0/3/9）

目的：插件开发全流程的 git 版本管理（init / commit / push），支持个人私有仓库与社区 CI 仓库两类场景。
与 `references/03` 一致，本文档是 AI 执行 git 操作时的行为依据；MCP 可用时优先调用 `git_status` / `git_commit` / `git_push` 工具。

## 1. 流程接入（贯穿全流程，仅首尾提交）

| 阶段 | 动作 | 工具/命令 |
|---|---|---|
| Phase 0 | 询问「是否需要 git 管理？远程仓库 URL（可留空）？私有/公开？」；不需要 → 全程跳过 | — |
| Phase 3 | 检测 `.git/`；无 → `git init` + 写 `.gitignore` + 首次提交 `chore: 项目脚手架初始化`；有 → 复用不覆盖 | `git_status` → `git_commit(init_if_needed=true)` |
| Phase 9 | 最终提交（无变化 skip）+ 推送；CI 仓库默认 fork+PR | `git_commit` → `git_push` |

**已有仓库**：检测到 `.git/` 即复用，只追加提交，不重复初始化。远程 URL 以已有 origin 为准，用户未提供新 URL 时不改动。

## 2. git 命令速查（MCP 不可用时的兜底）

```powershell
# 初始化（PowerShell）
git init
# 写 .gitignore 后（模板见下），首次提交
git add .
git commit -m "chore: 项目脚手架初始化"
# 绑定远程并推送
git remote add origin <URL>
git push -u origin main
# 查看状态
git status
```

**常见错误**：
| 现象 | 原因 | 解决 |
|---|---|---|
| `403 denied to <user>` | 凭据/token 权限不足 | 生成带 repo 权限的 PAT，配到 Windows 凭据管理器或 GIT_TOKEN/GITHUB_TOKEN |
| `Author identity unknown` | 未配置 user.name/email | `git config --global user.name "名字"`、`git config --global user.email "邮箱"` |
| 路径含中文报错 | 编码/引号问题 | 用绝对路径并加引号，避免 `cd` 拼接 |
| `LF will be replaced by CRLF` | 行尾符警告（非错误） | 可忽略；或配置 `core.autocrlf` |

## 3. .gitignore 模板

```gitignore
# 构建产物
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
```

## 4. MCP 工具调用对照

| 工具 | 阶段 | 参数 | 返回关键字段 |
|---|---|---|---|
| `git_status` | Phase 3 | `project_dir` | is_git_repo / remote_url / branch / dirty / git_available |
| `git_commit` | Phase 3/9 | `project_dir` `message` `init_if_needed` | action(init/commit/skip) / commit_hash / changed_files |
| `git_push` | Phase 9 | `project_dir` `repo_url` `visibility` | pushed / repo_url / branch / ci_detected / recommended_flow / notes |

## 5. CI 仓库专项（重要）

**识别**：目标仓库 `.github/workflows/` 存在 `build.yml` 等 → 判定为 CI 仓库（`git_push` 返回 `ci_detected=true`）。

**行为**：push 到 `master`/`main` 会自动触发构建；构建成功可能**自动发 Release + 更新 tag**（UnrealMultiple/TShockPlugin 还会同步 ApmApi/论坛/Crowdin；Zykor-Club 的 Lint 会校验插件结构）。

**注意**：这类仓库通常要求：
- 插件放 `src/<插件名>/` 目录
- **不能提交 DLL/PDB**（构建产物）
- 可能要求 `manifest.json` / `README` / `template.targets`（Zykor-Club Lint 会校验）

推送前必须用 `check_csproj` 或目录结构核对，否则 CI 会挂。

**建议流程（`git_push` 检测到 CI 时的默认推荐）**：
1. fork 上游仓库
2. 本地在分支上开发（不改 master/main）
3. push 到 fork
4. 开 PR 到上游

若用户坚持直接推上游，必须征得同意并明确告知会触发 CI 构建 + 自动 Release。

## 6. 安全提醒

- **token 不入库**：不要把 GITHUB_TOKEN/GH_TOKEN 写进代码、`.gitignore` 之外的任何文件
- `.gitignore` 必须排除敏感文件（配置里的密钥、凭据）
- 推送前确认远程 URL 是预期目标（避免推到错误仓库）
```

- [ ] **Step 2: 检查文档与 spec 一致性**

核对：文档第 5 节 CI 专项与 spec 第 5 节一致；第 4 节工具对照与 git_manage.py 实现签名一致（project_dir/message/init_if_needed/repo_url/visibility）。
Expected: 一致，无遗漏

- [ ] **Step 3: 提交**

```bash
git add "references/12-git管理.md"
git commit -m "docs: 新增 references/12-git管理.md 参考文档"
```

---

### Task 6: SKILL.md 流程接入（Phase 0/3/9 + 索引表）

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Phase 0 新增第 4 问**

在 Phase 0 的「3. **其他参考源**」之后追加：

```markdown
4. **git 管理**：问「是否需要 git 管理？远程仓库 URL（可留空）？私有/公开？」——不需要则全程跳过 git 流程（Phase 3/9 均跳过）；需要则记录 `git_required=true`、`repo_url`、`visibility`（默认 private）。详见 `references/12-git管理.md`。
```

- [ ] **Step 2: Phase 3 增加 git 初始化**

在 Phase 3 的「解决方案 sln、测试项目（若存在可测逻辑）」之后追加：

```markdown
- **git 初始化**（Phase 0 设 `git_required=true` 时）：MCP 可用时调 `git_status` 检测 → 无 `.git/` 则 `git_commit(project_dir, "chore: 项目脚手架初始化", init_if_needed=true)`（自动 init + 写 .gitignore + 首次提交）；已有 `.git/` 则复用不覆盖。详见 `references/12-git管理.md`
```

- [ ] **Step 3: Phase 9 增加最终提交 + 推送**

将 Phase 9 内容替换为：

```markdown
### Phase 9 交付

- 输出：插件 DLL、README（命令表/权限表/配置说明）、单测报告、审查结论、本次使用的版本四元组
- **git 收尾**（Phase 0 设 `git_required=true` 时）：MCP 可用时调 `git_commit` 做最终提交（无变化 skip）→ `git_push` 推送（`repo_url`、`visibility` 来自 Phase 0）；目标仓库检测到 CI 时默认走 fork+PR 流程（见 `references/12-git管理.md`），用户坚持直接推上游须征得同意并告知会触发构建+Release。向用户简报 commit hash / 远程 URL / 分支 / CI 情况
- 明确告知用户：剩余功能测试由用户自行完成
```

- [ ] **Step 4: 参考文档索引表补一行**

在索引表 `references/11-终审代码审查.md` 行之后追加：

```markdown
| `references/12-git管理.md` | git 初始化/提交/推送、CI 仓库 fork+PR 流程、.gitignore 模板 |
```

- [ ] **Step 5: 核对全文一致性**

核对：SKILL.md 三处改动（Phase 0/3/9）均引用 `references/12-git管理.md`；索引表新增行与文件名一致；git 相关 MCP 工具名（`git_status`/`git_commit`/`git_push`）与 server.py 注册名一致。
Expected: 一致

- [ ] **Step 6: 提交**

```bash
git add SKILL.md
git commit -m "feat: SKILL.md 接入 git 管理流程（Phase 0/3/9 + 索引表）"
```

---

### Task 7: mcp-server/README.md 更新 + 全量回归 + 推送

**Files:**
- Modify: `mcp-server/README.md`

- [ ] **Step 1: README 工具数更新**

将「## 工具清单（13 个）」改为「## 工具清单（16 个）」；在「### 项目辅助（Phase 1/3）」表后追加一节：

```markdown
### git 管理（Phase 0/3/9）

| 工具 | 作用 |
|---|---|
| `git_status` | 检测目录 git 状态（是否仓库/远程/分支/脏），判断 init 还是复用 |
| `git_commit` | git init（可选）+ 写 .gitignore + 提交；无变化自动 skip |
| `git_push` | 推送 + 检测目标仓库 CI（默认推荐 fork+PR）+ 按需创建私有仓库 |

`git_push` 检测到目标仓库 `.github/workflows/` 含构建工作流（如 UnrealMultiple/TShockPlugin、Zykor-Club/TShockServerPlugin）时，默认返回 `recommended_flow=fork_pr` 并建议 fork→分支→PR，避免直接推 master/main 触发自动构建 + Release；用户坚持直接推上游须先征得同意。创建新仓库默认 private。
```

同时把注册数量「工具列表出现 13 个工具即成功」改为 16 个；命令行自测节追加：

```bash
python tools/git_manage.py status "路径\项目目录"          # 检测 git 状态
python tools/git_manage.py commit "路径\项目目录" "chore: init" init   # init + 首次提交
python tools/git_manage.py push "路径\项目目录" "https://github.com/owner/repo.git"  # 推送（含 CI 检测）
```

- [ ] **Step 2: 全量回归测试**

Run: `python -m pytest mcp-server/tests -v`
Expected: 全部 PASS（原 13 工具测试 + 新 11 个 git_manage 用例）

Run: `python -m py_compile mcp-server/server.py mcp-server/tools/git_manage.py`
Expected: 无输出（编译通过）

- [ ] **Step 3: 提交并推送**

```bash
git add mcp-server/README.md
git commit -m "docs: README 更新 git 管理工具清单"
# 推送全部到远程
git push origin main
```

Expected: push 成功，远程 main 更新

---

## 自审记录（writing-plans 要求）

**1. Spec 覆盖核对**：
- Phase 0 第 4 问 → Task 6 Step 1 ✅
- Phase 3 init+首次提交 → Task 6 Step 2 + Task 1/2 ✅
- Phase 9 提交+推送 → Task 6 Step 3 + Task 3 ✅
- 已有仓库复用 → git_status 检测 + git_commit 不覆盖（Task 1/2）+ Task 5 第 1 节 ✅
- 3 个 MCP 工具 → Task 1/2/3 + Task 4 注册 ✅
- git 路径探测 → Task 1 `_find_git` ✅
- references/12-git管理.md → Task 5 ✅
- SKILL.md 修改 → Task 6 ✅
- 测试 → Task 1/2/3 的 TDD 步骤 + Task 7 全量回归 ✅
- CI 仓库 fork+PR 默认推荐 → Task 3 `git_push` + Task 5 第 5 节 ✅

**2. 占位符扫描**：全部步骤含完整代码与命令，无 TBD/TODO/「写测试」「类似 Task N」等占位 ✅

**3. 类型一致性**：
- `git_status(project_dir)` / `git_commit(project_dir, message, init_if_needed)` / `git_push(project_dir, repo_url, visibility)` 三个签名在 git_manage.py、server.py、references/12、README 各处一致 ✅
- `_detect_ci_local` / `_detect_ci_remote` / `_create_private_repo` / `_remote_exists` 辅助函数命名前后一致 ✅
- 返回字段 `ci_detected/ci_files/recommended_flow/notes` 在 git_push 实现、测试断言、docs 各处一致 ✅
- `_find_git()` 在 git_status 与测试 setUp 中用法一致 ✅
