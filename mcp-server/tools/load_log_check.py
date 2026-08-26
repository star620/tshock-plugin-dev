# 加载日志检查工具（对应 skill Phase 7）
# 作用：读取服务器日志（server_out.log / ServerLog.txt），按特征表判断插件加载成败。
# 特征表与 references/09-编译部署加载验证.md「加载结果特征」一致。
import json
import re
import sys
from pathlib import Path

# 加载结果特征表（按优先级匹配，中英双语：TShock 中文版日志用"插件已加载"，英文版用 loaded）
SUCCESS_PATTERNS = [
    re.compile(r"插件已加载", re.IGNORECASE),
    re.compile(r"已加载", re.IGNORECASE),
    re.compile(r"Plugin\s+[\"']?(?P<name>\w+)[\"']?\s+loaded", re.IGNORECASE),
    re.compile(r"(?P<name>\w+)\s+loaded\s+successfully", re.IGNORECASE),
]

# 进入运行状态标志（TShock 中文版 banner；英文版为 is running）
RUNNING_MARKERS = [
    re.compile(r"TShock\s+[\d.]+\s*正在运行", re.IGNORECASE),
    re.compile(r"欢迎使用泰拉瑞亚TShock服务器", re.IGNORECASE),
    re.compile(r"is running", re.IGNORECASE),
]

# 启动阶段失败标志（REST 端口冲突等，出现在进入运行之前）
STARTUP_FAIL_MARKERS = [
    re.compile(r"Rest: ERROR: 启动时发生致命错误", re.IGNORECASE),
    re.compile(r"SocketException", re.IGNORECASE),
    re.compile(r"Fatal error", re.IGNORECASE),
]

FAIL_PATTERNS = [
    # (正则, 标签, 处理建议)
    (re.compile(r"has thrown an exception during initialization", re.IGNORECASE),
     "initialize_exception", "Initialize 阶段异常：检查空引用/配置路径/事件注册（回退 Phase 5）"),
    (re.compile(r"failed to load", re.IGNORECASE),
     "failed_to_load", "插件加载失败：检查 Initialize 与静态初始化（回退 Phase 5）"),
    (re.compile(r"System\.MissingMethodException", re.IGNORECASE),
     "missing_method", "用了比服务端更新的 API：对照服务端实际版本换兼容写法（回退 Phase 4）"),
    (re.compile(r"System\.TypeLoadException", re.IGNORECASE),
     "type_load", "依赖 DLL 缺失或版本不匹配：检查 csproj 引用与 ServerPlugins 内 DLL（回退 Phase 3/6）"),
    (re.compile(r"System\.TypeInitializationException", re.IGNORECASE),
     "type_initialization", "静态构造失败：检查静态字段初始化顺序与目录可写（回退 Phase 5）"),
    (re.compile(r"System\.FileNotFoundException", re.IGNORECASE),
     "file_not_found", "依赖文件缺失：确认 ServerPlugins/TShockAPI.dll 存在（最常见，见 10-排错手册）"),
]

# 服务器是否存活（进程检查）
CRASH_MARKERS = [
    re.compile(r"Unhandled exception", re.IGNORECASE),
    re.compile(r"Fatal error", re.IGNORECASE),
    re.compile(r"Shutting down", re.IGNORECASE),
]


def _err(message: str, hint: str = "", fallback: str = "") -> dict:
    """统一错误格式：error 表示出错，hint 为排查建议，fallback 为降级路径。"""
    return {"error": message, "hint": hint, "fallback": fallback}


# 服务器日志常见文件名（目录探测用）
LOG_CANDIDATES = ["server_out.log", "ServerLog.txt"]


def find_log_file(log_path: str) -> str:
    """log_path 为目录时探测常见日志位置；为文件则原样返回；找不到返回空串。"""
    p = Path(log_path)
    if p.is_file():
        return str(p)
    if p.is_dir():
        for cand in LOG_CANDIDATES:
            f = p / cand
            if f.is_file():
                return str(f)
        logs_dir = p / "logs"
        if logs_dir.is_dir():
            logs = sorted(logs_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
            if logs:
                return str(logs[0])
    return ""


def _read_log(path: str) -> str:
    """读取日志，兼容 utf-8 与 gbk 编码。"""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="replace") as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="latin-1", errors="replace") as f:
        return f.read()


def check(log_path: str, plugin_name: str = "") -> dict:
    """检查插件加载结果。

    参数：
        log_path: 日志文件绝对路径（server_out.log 或 ServerLog.txt）
        plugin_name: 插件名（用于精确匹配；留空则匹配通用加载行）

    返回：
        JSON 字符串，含 status/matched/suggestions/crash_markers/log_tail。
    """
    if not log_path:
        return _err("缺少参数 log_path", "用法：check_load_log(log_path, plugin_name)", "")
    resolved = find_log_file(log_path)
    if not resolved:
        return _err(
            f"找不到日志文件：{log_path}",
            "确认服务器已启动并重定向输出；或传入 server_out.log / ServerLog.txt 的具体路径",
            "按 references/09-编译部署加载验证.md 检查服务器日志位置",
        )
    log_path = resolved

    try:
        text = _read_log(log_path)
    except FileNotFoundError:
        return _err(f"日志文件不存在：{log_path}", "文件可能被服务器占用/删除，重启服务器后重试", "")
    except Exception as e:  # noqa: BLE001 —— 工具层兜底
        return _err(f"读取日志失败：{e}", "确认日志路径正确且可读", "")

    name_pat = re.compile(re.escape(plugin_name), re.IGNORECASE) if plugin_name else None

    # 1. 匹配成功/失败特征
    matched, suggestions = [], []
    for pat in SUCCESS_PATTERNS:
        if pat.search(text) and (name_pat is None or name_pat.search(text)):
            matched.append("loaded")
            break
    if "loaded" not in matched:
        for pat, label, tip in FAIL_PATTERNS:
            if pat.search(text):
                matched.append(label)
                suggestions.append(tip)

    # 2. 崩溃标志（返回匹配到的实际文本，正则对象无法 JSON 序列化）
    crash_markers = []
    for m in CRASH_MARKERS:
        match = m.search(text)
        if match:
            crash_markers.append(match.group(0))

    # 3. 状态判定
    if crash_markers:
        status = "crashed"
    elif "loaded" in matched:
        status = "loaded"
    elif matched:
        status = "failed"
    else:
        status = "not_found"

    # 4. 日志尾部（最近 15 行，供人工判断）
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    log_tail = lines[-15:]

    # 5. 启动诊断（TShock 是否进入运行、已加载插件、ERROR 行汇总）
    running = any(m.search(text) for m in RUNNING_MARKERS)
    startup_fail = [m.pattern.split(":")[-1].strip() for m in STARTUP_FAIL_MARKERS if m.search(text)]
    loaded_plugins = []
    for line in text.splitlines():
        if ("已加载" in line or re.search(r"Loaded", line, re.IGNORECASE)) and "ERROR" not in line:
            m = re.search(r"\[([^\]]+)\]", line)
            if m:
                name = m.group(1).strip()
                if name and name not in loaded_plugins:
                    loaded_plugins.append(name)
    error_lines = []
    for line in text.splitlines():
        if "ERROR:" in line:
            line = line.strip()
            if line and line not in error_lines:
                error_lines.append(line)
        if len(error_lines) >= 5:
            break
    startup = {
        "tshock_running": running,
        "startup_fail": startup_fail,
        "loaded_plugins": loaded_plugins[:20],
        "error_lines": error_lines,
    }

    return {
        "status": status,
        "matched": matched,
        "suggestions": suggestions,
        "crash_markers": crash_markers,
        "plugin_name": plugin_name,
        "startup": startup,
        "log_tail": log_tail,
        "hint": ("status=loaded 为插件加载通过；failed/crashed 按 suggestions 回退对应阶段。"
                 "startup.tshock_running 表示 TShock 是否进入运行（false 且 startup_fail 非空时定位到启动阶段失败）；"
                 "startup.loaded_plugins 为已加载插件，startup.error_lines 为日志中的 ERROR 行。"),
    }


if __name__ == "__main__":
    # 命令行调试：python load_log_check.py <日志路径> [插件名]
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    name = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(check(path, name), ensure_ascii=False, indent=2))
