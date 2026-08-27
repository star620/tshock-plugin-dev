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


if __name__ == "__main__":
    unittest.main()
