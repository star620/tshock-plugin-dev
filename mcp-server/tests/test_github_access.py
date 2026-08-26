# github_access 工具单元测试（mock 网络，不连真实 GitHub）
import unittest
from unittest import mock

from tools import github_access


class ProbeVersionSubdirTest(unittest.TestCase):
    """_probe_version 支持 subdir 后，应探测插件子目录内的 README/csproj。"""

    @mock.patch("tools.github_access.requests.get")
    def test_subdir_probes_plugin_files(self, mock_get):
        def fake_get(url, timeout=8, **kw):
            resp = mock.Mock()
            resp.status_code = 200
            if url.endswith("/CheckIn/README.md"):
                resp.text = "# CheckIn\n签到插件，适配 TShock 6.1.0 / Terraria 1.4.5.6"
            elif url.endswith("/CheckIn/Plugin.csproj"):
                resp.text = ("<Project><PropertyGroup>"
                             "<TargetFramework>net9.0</TargetFramework>"
                             "</PropertyGroup></Project>")
            else:
                resp.status_code = 404
            return resp
        mock_get.side_effect = fake_get

        result = github_access._probe_version("UnrealMultiple/TShockPlugin", subdir="CheckIn")
        self.assertIn("TShock 6.1.0", result["version_hint"])
        self.assertIn("net9.0", result["version_hint"])
        self.assertIn("CheckIn/README.md", result["evidence"])


class SearchPluginLibraryTest(unittest.TestCase):
    """search_plugin_library 目录名匹配 + README 匹配 + 版本校验。"""

    @mock.patch("tools.github_access.requests.get")
    @mock.patch("tools.github_access._get")
    def test_readme_keyword_match(self, mock_get, mock_raw):
        # repo 信息 + 递归树（mock _get）
        mock_get.side_effect = [
            {"default_branch": "master", "stargazers_count": 100},
            {"tree": [
                {"type": "tree", "path": "CheckIn"},
                {"type": "tree", "path": "SpamKiller"},
                {"type": "blob", "path": "CheckIn/README.md"},
                {"type": "blob", "path": "CheckIn/Plugin.csproj"},
                {"type": "blob", "path": "SpamKiller/README.md"},
            ]},
        ]

        def fake_raw(url, timeout=8, **kw):
            resp = mock.Mock()
            resp.status_code = 200
            if "CheckIn/README.md" in url:
                resp.text = "# CheckIn\n签到插件，玩家每日打卡领奖励"
            else:
                resp.status_code = 404
            return resp
        mock_raw.side_effect = fake_raw

        result = github_access.search_plugin_library("签到", "UnrealMultiple/TShockPlugin")
        names = [p["name"] for p in result.get("plugins", [])]
        self.assertIn("CheckIn", names)      # README 含关键词"签到"
        self.assertNotIn("SpamKiller", names)
        self.assertEqual(result["stars"], 100)
        self.assertIn("签到", result["plugins"][0]["match_context"])  # 命中上下文取自 README 命中行

    @mock.patch("tools.github_access.requests.get")
    @mock.patch("tools.github_access._get")
    def test_dirname_keyword_match(self, mock_get, mock_raw):
        mock_get.side_effect = [
            {"default_branch": "master", "stargazers_count": 100},
            {"tree": [
                {"type": "tree", "path": "SpamKiller"},
                {"type": "blob", "path": "SpamKiller/README.md"},
            ]},
        ]
        # 所有 requests.get 均返回 404（README 无、版本探测无），避免 side_effect 耗尽抛 StopIteration
        mock_raw.return_value = mock.Mock(status_code=404)

        result = github_access.search_plugin_library("spam", "UnrealMultiple/TShockPlugin")
        names = [p["name"] for p in result.get("plugins", [])]
        self.assertIn("SpamKiller", names)   # 目录名含关键词"spam"

    @mock.patch("tools.github_access.requests.get")
    @mock.patch("tools.github_access._get")
    def test_src_layout_detection(self, mock_get, mock_raw):
        """UnrealMultiple/TShockPlugin 使用 src/<插件> 布局，应识别 src/ 下的插件目录。"""
        mock_get.side_effect = [
            {"default_branch": "master", "stargazers_count": 100},
            {"tree": [
                {"type": "tree", "path": "src/SignInSign"},
                {"type": "tree", "path": "src/WorldEdit"},
                {"type": "tree", "path": ".github"},
                {"type": "blob", "path": "src/SignInSign/README.md"},
                {"type": "blob", "path": "src/WorldEdit/README.md"},
            ]},
        ]

        def fake_raw(url, timeout=8, **kw):
            resp = mock.Mock()
            resp.status_code = 200
            if "src/SignInSign/README.md" in url:
                resp.text = "# SignInSign\n签到签到签到，玩家每日签到"
            else:
                resp.status_code = 404
            return resp
        mock_raw.side_effect = fake_raw

        result = github_access.search_plugin_library("签到", "UnrealMultiple/TShockPlugin")
        names = [p["name"] for p in result.get("plugins", [])]
        self.assertIn("SignInSign", names)   # src/ 布局下应只显示插件名，且命中 README
        self.assertNotIn("WorldEdit", names)
        self.assertIn("签到", result["plugins"][0]["match_context"])

    @mock.patch("tools.github_access._get")
    def test_no_keyword_returns_empty(self, mock_get):
        mock_get.side_effect = [
            {"default_branch": "master", "stargazers_count": 0},
            {"tree": [{"type": "tree", "path": "CheckIn"},
                      {"type": "blob", "path": "CheckIn/README.md"}]},
        ]
        result = github_access.search_plugin_library("zzz", "UnrealMultiple/TShockPlugin")
        self.assertEqual(result["plugins"], [])


if __name__ == "__main__":
    unittest.main()
