# mcp-server/tests/test_gh_comments.py
"""gh_comments 工具测试：URL 解析 / 输入归一化 / 评论读取（mock _gh_api）。"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import gh_comments


def _make_item(is_pr: bool = True, body: str = "PR body") -> dict:
    item = {
        "id": 10,
        "user": {"login": "owner"},
        "author_association": "OWNER",
        "title": "Add feature",
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "body": body,
    }
    if is_pr:
        item["pull_request"] = {}
    return item


def _make_conversation(i: int) -> dict:
    return {
        "id": i,
        "user": {"login": f"user{i}"},
        "author_association": "MEMBER",
        "created_at": f"2026-01-0{i + 1}T00:00:00Z",
        "updated_at": f"2026-01-0{i + 1}T00:00:00Z",
        "body": f"conversation {i}",
    }


def _make_review(i: int) -> dict:
    return {
        "id": 100 + i,
        "user": {"login": "reviewer"},
        "state": "approved",
        "submitted_at": f"2026-01-0{i + 2}T00:00:00Z",
        "body": f"review {i}",
        "commit_id": "abc123",
    }


def _make_code(i: int) -> dict:
    return {
        "id": 200 + i,
        "user": {"login": "coder"},
        "created_at": f"2026-01-0{i + 3}T00:00:00Z",
        "body": f"code {i}",
        "path": "src/Plugin.cs",
        "line": 10 + i,
        "side": "RIGHT",
        "in_reply_to_id": None,
        "commit_id": "abc123",
        "html_url": f"https://github.com/o/r/pull/1#discussion_r{200 + i}",
    }


class _FakeGhApi:
    """模拟 _gh_api：按 endpoint 返回构造数据。is_pr 控制本体是否含 pull_request。"""

    def __init__(self, is_pr: bool = True):
        self.is_pr = is_pr
        self.calls = []

    def __call__(self, repo, endpoint, paginate=False):
        self.calls.append((repo, endpoint, paginate))
        if endpoint == "issues/5":
            return _make_item(is_pr=self.is_pr)
        if endpoint == "issues/5/comments":
            return [_make_conversation(1), _make_conversation(2)]
        if endpoint == "pulls/5/reviews":
            return [_make_review(1)]
        if endpoint == "pulls/5/comments":
            return [_make_code(1)]
        raise AssertionError(f"unexpected endpoint: {endpoint}")


class TestFindGh(unittest.TestCase):
    def test_find_gh_returns_path_or_none(self):
        result = gh_comments._find_gh()
        self.assertTrue(result is None or isinstance(result, str))


class TestParseUrl(unittest.TestCase):
    def test_issue_url(self):
        parsed = gh_comments._parse_url("https://github.com/owner/repo/issues/42")
        self.assertEqual(parsed["owner"], "owner")
        self.assertEqual(parsed["repo"], "repo")
        self.assertEqual(parsed["number"], "42")
        self.assertEqual(parsed["kind"], "issue")

    def test_pull_url(self):
        parsed = gh_comments._parse_url("https://github.com/owner/repo/pull/5")
        self.assertEqual(parsed["kind"], "pr")

    def test_pulls_url(self):
        parsed = gh_comments._parse_url("https://github.com/owner/repo/pulls/5")
        self.assertEqual(parsed["kind"], "pr")

    def test_query_and_trailing_slash(self):
        parsed = gh_comments._parse_url(
            "https://github.com/owner/repo/issues/42?tab=comments#issuecomment-1")
        self.assertEqual(parsed["number"], "42")

    def test_www_and_http(self):
        parsed = gh_comments._parse_url("http://www.github.com/owner/repo/pull/1")
        self.assertEqual(parsed["kind"], "pr")

    def test_invalid_url(self):
        self.assertIsNone(gh_comments._parse_url("https://example.com/owner/repo/issues/1"))
        self.assertIsNone(gh_comments._parse_url("https://github.com/owner/repo/"))
        self.assertIsNone(gh_comments._parse_url("not a url"))


class TestResolveInputs(unittest.TestCase):
    def test_repo_number(self):
        self.assertEqual(gh_comments._resolve_inputs("owner/repo", "5", ""),
                         ("owner/repo", "5", ""))

    def test_repo_with_git_suffix(self):
        self.assertEqual(gh_comments._resolve_inputs("owner/repo.git", "5", ""),
                         ("owner/repo", "5", ""))

    def test_repo_full_url(self):
        self.assertEqual(
            gh_comments._resolve_inputs("https://github.com/owner/repo", "5", ""),
            ("owner/repo", "5", ""))

    def test_url_priority(self):
        self.assertEqual(
            gh_comments._resolve_inputs("owner/repo", "5",
                                        "https://github.com/a/b/pull/9"),
            ("a/b", "9", "pr"))

    def test_invalid_number(self):
        self.assertEqual(gh_comments._resolve_inputs("owner/repo", "abc", ""),
                         (None, None, None))
        self.assertEqual(gh_comments._resolve_inputs("owner/repo", "0", ""),
                         (None, None, None))

    def test_missing_all(self):
        self.assertEqual(gh_comments._resolve_inputs("", "", ""), (None, None, None))


class TestReadComments(unittest.TestCase):
    def test_all_types_aggregated_and_sorted(self):
        fake = _FakeGhApi(is_pr=True)
        with mock.patch.object(gh_comments, "_gh_api", fake):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5)
        self.assertIsNone(result.get("error"))
        self.assertEqual(result["kind"], "pr")
        self.assertEqual(result["total"], 5)  # description + 2 conv + 1 review + 1 code
        types = [c["type"] for c in result["comments"]]
        self.assertEqual(types, ["description", "conversation", "conversation",
                                 "review", "code"])
        # 时间升序
        times = [c.get("created_at") or c.get("submitted_at") for c in result["comments"]]
        self.assertEqual(times, sorted(times))

    def test_kind_issue_when_no_pull_request(self):
        fake = _FakeGhApi(is_pr=False)
        with mock.patch.object(gh_comments, "_gh_api", fake):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5)
        self.assertEqual(result["kind"], "issue")
        self.assertEqual(result["total"], 3)  # description + 2 conv（issue 无 review/code）

    def test_issue_skips_pulls_endpoints(self):
        fake = _FakeGhApi(is_pr=False)
        with mock.patch.object(gh_comments, "_gh_api", fake):
            gh_comments.read_github_comments(repo="owner/repo", number=5)
        pulls_calls = [c for c in fake.calls if c[1].startswith("pulls/")]
        self.assertEqual(pulls_calls, [], "issue 不应调用 pulls 端点")

    def test_comment_type_filter_code(self):
        fake = _FakeGhApi(is_pr=True)
        with mock.patch.object(gh_comments, "_gh_api", fake):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5,
                                                      comment_type="code")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["comments"][0]["type"], "code")
        self.assertEqual(result["comments"][0]["path"], "src/Plugin.cs")

    def test_comment_type_filter_review(self):
        fake = _FakeGhApi(is_pr=True)
        with mock.patch.object(gh_comments, "_gh_api", fake):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5,
                                                      comment_type="review")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["comments"][0]["state"], "approved")

    def test_url_input_and_priority(self):
        fake = _FakeGhApi(is_pr=True)
        with mock.patch.object(gh_comments, "_gh_api", fake):
            result = gh_comments.read_github_comments(
                repo="wrong/repo", number=1,
                url="https://github.com/owner/repo/pull/5")
        self.assertEqual(result["repo"], "owner/repo")
        self.assertEqual(result["number"], "5")

    def test_missing_args_error(self):
        result = gh_comments.read_github_comments()
        self.assertIn("error", result)
        self.assertIn("参数不足", result["error"])

    def test_invalid_comment_type(self):
        result = gh_comments.read_github_comments(repo="owner/repo", number=5,
                                                  comment_type="bogus")
        self.assertIn("error", result)
        self.assertIn("comment_type", result["error"])

    def test_gh_missing_error(self):
        with mock.patch.object(gh_comments, "_find_gh", return_value=None):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5)
        self.assertIn("error", result)
        self.assertIn("gh", result["error"])

    def test_404_error(self):
        def boom(repo, endpoint, paginate=False):
            raise RuntimeError("HTTP 404: Not Found (https://api.github.com/...)")

        with mock.patch.object(gh_comments, "_gh_api", boom):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5)
        self.assertIn("error", result)
        self.assertIn("404", result["error"])

    def test_invalid_json_error(self):
        def fake_run(*args, timeout=60):
            return 0, "this is not json", ""

        with mock.patch.object(gh_comments, "_run_gh", fake_run):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5)
        self.assertIn("error", result)
        self.assertIn("JSON", result["error"])

    def test_auth_error_hint(self):
        def fake_run(*args, timeout=60):
            return 1, "", "HTTP 401: Bad credentials (https://api.github.com/...)"

        with mock.patch.object(gh_comments, "_run_gh", fake_run):
            result = gh_comments.read_github_comments(repo="owner/repo", number=5)
        self.assertIn("error", result)
        self.assertIn("认证", result["hint"])


if __name__ == "__main__":
    unittest.main()
