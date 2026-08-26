# MCP server 入口：注册 4 个工具，供 AI 在 skill 各阶段调用。
# 运行：python server.py（默认 stdio 传输，供 TRAE/其他 MCP 客户端本地注册）
# 依赖 mcp>=2.0：mcp 2.x 中 FastMCP 已改名为 MCPServer。
from mcp.server.mcpserver import MCPServer

from tools import build_check, fetch_tshock_source, load_log_check, version_resolver

server = MCPServer("tshock-plugin-dev")


@server.tool()
def resolve_version(terraria_version: str = "") -> str:
    """解析 Terraria ↔ TShock ↔ TFM ↔ NuGet 版本四元组并做门禁判断（Phase 1）。

    参数：
        terraria_version: 目标 Terraria 版本（如 1.4.5.6）；留空取最新稳定版。

    返回 JSON：terraria/tshock/tfm/nuget_version/gate_status/experimental_notes。
    """
    import json

    return json.dumps(version_resolver.resolve(terraria_version), ensure_ascii=False)


@server.tool()
def check_build(csproj_path: str, run_tests: bool = False) -> str:
    """编译插件工程并解析错误码给出修复建议（Phase 6）。

    参数：
        csproj_path: 插件工程 csproj 绝对路径
        run_tests: 是否同时跑 dotnet test

    返回 JSON：success/exit_code/errors/warnings/test/output_tail。
    """
    import json

    return json.dumps(build_check.check(csproj_path, run_tests), ensure_ascii=False)


@server.tool()
def check_load_log(log_path: str, plugin_name: str = "") -> str:
    """检查服务器日志判断插件加载成败（Phase 7）。

    参数：
        log_path: server_out.log 或 ServerLog.txt 绝对路径
        plugin_name: 插件名（可选，精确匹配）

    返回 JSON：status（loaded/failed/not_found/crashed）/matched/suggestions。
    """
    import json

    return json.dumps(load_log_check.check(log_path, plugin_name), ensure_ascii=False)


@server.tool()
def fetch_source(version: str, api_symbol: str = "") -> str:
    """下载指定版本 TShock 源码并可选定位 API 符号定义（Phase 2 L4）。

    注意：属于联网下载操作，调用前必须征得用户同意。

    参数：
        version: TShock 版本（如 6.1.0）
        api_symbol: 要定位的符号名（可选，如 PacketTypes）

    返回 JSON：version/source_dir/downloaded/matched_symbols。
    """
    import json

    return json.dumps(fetch_tshock_source.fetch(version, api_symbol), ensure_ascii=False)


if __name__ == "__main__":
    server.run()  # 默认 stdio 传输
