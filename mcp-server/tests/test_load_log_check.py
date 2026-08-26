# load_log_check 工具单元测试（真实日志特征：TShock 6.1.0 中文版）
import json
import tempfile
import unittest

from tools import load_log_check


def _check_with_text(text: str, plugin_name: str = "") -> dict:
    """把日志文本写入临时文件后调用 check()。"""
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    try:
        return load_log_check.check(path, plugin_name)
    finally:
        import os
        os.unlink(path)


class LoadLogCheckTest(unittest.TestCase):

    def test_chinese_success(self):
        """中文日志：插件已加载 + TShock 正在运行 → loaded，startup 诊断正确。"""
        log = (
            "2026-08-26 15:59:38 - TShock: INFO: TShock 6.1.0.0 (Profoundly Collaborative (3.11)) 正在运行。\n"
            "2026-08-26 15:59:38 - TShock: INFO: 欢迎使用泰拉瑞亚TShock服务器！\n"
            "2026-08-26 15:59:38 - Plugin: INFO: [粒子文字] 插件已加载，命令: /ptext\n"
            "2026-08-26 15:59:38 - BuffDisablerPlugin: INFO: [BuffDisabler] Loaded.\n"
        )
        r = _check_with_text(log)
        self.assertEqual(r["status"], "loaded")
        self.assertTrue(r["startup"]["tshock_running"])
        self.assertIn("粒子文字", r["startup"]["loaded_plugins"])
        self.assertIn("BuffDisabler", r["startup"]["loaded_plugins"])
        self.assertEqual(r["startup"]["error_lines"], [])

    def test_english_success(self):
        """英文日志：loaded 模式仍可用（向后兼容）。"""
        log = "12:00:00 - Plugin: INFO: [SpamKiller] Plugin loaded successfully\n"
        r = _check_with_text(log)
        self.assertEqual(r["status"], "loaded")

    def test_rest_port_conflict(self):
        """REST 端口冲突：未进入运行，startup_fail 非空。"""
        log = (
            "2026-08-26 13:00:12 - TShock: INFO: TShock 6.1.0.0 (Profoundly Collaborative (3.11)) 正在运行。\n"
            "2026-08-26 13:00:12 - Rest: ERROR: 启动时发生致命错误\n"
            "2026-08-26 13:00:12 - Rest: ERROR: System.Net.Sockets.SocketException (10048): 通常每个套接字地址只允许使用一次。\n"
        )
        r = _check_with_text(log)
        self.assertNotEqual(r["status"], "loaded")
        self.assertTrue(r["startup"]["startup_fail"])
        self.assertTrue(r["startup"]["error_lines"])

    def test_no_match(self):
        """无加载特征：not_found，且返回可 JSON 序列化。"""
        r = _check_with_text("2026-08-26 10:00:00 - TShock: INFO: 一些无关日志\n")
        self.assertEqual(r["status"], "not_found")
        json.dumps(r)  # 不应抛 TypeError

    def test_json_serializable(self):
        """完整结果必须可 JSON 序列化（回归 crash_markers 那类 bug）。"""
        log = (
            "2026-08-26 15:59:38 - Plugin: INFO: [粒子文字] 插件已加载\n"
            "2026-08-26 15:59:38 - Plugin: ERROR: System.NullReferenceException: Object reference not set\n"
        )
        r = _check_with_text(log)
        json.dumps(r)


if __name__ == "__main__":
    unittest.main()
