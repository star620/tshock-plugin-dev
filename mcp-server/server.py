# MCP server 入口：注册 17 个工具，供 AI 在 skill 各阶段调用。
# 运行：python server.py（默认 stdio 传输，供 TRAE/其他 MCP 客户端本地注册）
# 依赖 mcp>=2.0：mcp 2.x 中 FastMCP 已改名为 MCPServer。
from mcp.server.mcpserver import MCPServer

from tools import (build_check, fetch_tshock_source, gh_comments, git_manage,
                   github_access, load_log_check, project_util, source_fetch,
                   version_resolver)

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


# ---------- 扩展工具：GitHub 访问（Phase 2 参考源） ----------


@server.tool()
def search_repos(query: str, target_tshock: str = "", target_terraria: str = "") -> str:
    """搜索 GitHub 相似插件仓库，并校验其适配版本与当前目标版本是否匹配（Phase 2 L2）。

    参数：
        query: 搜索关键词（如 "tshock plugin 签到"）
        target_tshock: 目标 TShock 版本（如 6.1.0），用于版本匹配校验
        target_terraria: 目标 Terraria 版本（如 1.4.5.6）

    返回 JSON：repositories[{full_name/description/stars/version_hint/version_match}]。
    version_match: match（可参考）/ mismatch（版本不符，只看思路）/ unknown（需自行核对）。
    """
    import json

    return json.dumps(github_access.search_repos(query, target_tshock, target_terraria), ensure_ascii=False)


@server.tool()
def search_plugin_library(query: str, repo: str = "UnrealMultiple/TShockPlugin",
                          target_tshock: str = "", target_terraria: str = "") -> str:
    """在 TShock 插件库仓库内检索相似插件（Phase 0 步骤 0.2）。

    参数：
        query: 关键词（如 "签到 礼包"，中英文均可）
        repo: 插件库仓库（默认 UnrealMultiple/TShockPlugin）
        target_tshock: 目标 TShock 版本（可选，版本匹配校验）
        target_terraria: 目标 Terraria 版本（可选）

    返回 JSON：repo/stars/plugins[{name/description/match_context/version_hint/version_match}]。
    match_context 为命中依据，供判断语义是否真相关。
    """
    import json

    return json.dumps(github_access.search_plugin_library(query, repo, target_tshock, target_terraria), ensure_ascii=False)


@server.tool()
def read_remote_file(repo: str, path: str, ref: str = "HEAD") -> str:
    """读取 GitHub 仓库中某个文件的内容（不下载整包，省流量）（Phase 2）。

    参数：
        repo: 仓库 full_name（如 Pryaxis/TShock）
        path: 文件路径（如 TShockAPI/Commands.cs）
        ref: 分支/tag（默认 HEAD）

    返回 JSON：content（前 4000 字符）/truncated。
    """
    import json

    return json.dumps(github_access.read_remote_file(repo, path, ref), ensure_ascii=False)


@server.tool()
def search_code(query: str) -> str:
    """GitHub 代码搜索，跨仓库找 API 用法示例（Phase 2）。

    注意：需要设置 GITHUB_TOKEN 环境变量后重启 MCP server 才能用。

    参数：
        query: 搜索语句（如 "PacketTypes language:C#"）

    返回 JSON：results[{repository/path/html_url}]。
    """
    import json

    return json.dumps(github_access.search_code(query), ensure_ascii=False)


# ---------- 扩展工具：源码/资源获取（Phase 2 L4） ----------


@server.tool()
def fetch_terrariaapi(version: str = "") -> str:
    """下载 TerrariaServerAPI 子模块源码（CS0117 报错的根源常在此，Phase 2 L4）。

    注意：属于联网下载操作，调用前必须征得用户同意。

    参数：
        version: 目标 TShock 版本（可选，用于对应 tag；留空取默认分支）

    返回 JSON：version/source_dir/downloaded。
    """
    import json

    return json.dumps(source_fetch.fetch_terrariaapi(version), ensure_ascii=False)


@server.tool()
def fetch_release_asset(version: str = "", platform: str = "win-x64") -> str:
    """下载 TShock 官方发布包 zip（测试服务器用，Phase 1/7）。

    注意：属于联网下载操作，调用前必须征得用户同意。

    参数：
        version: TShock 版本（如 6.1.0）；留空取最新稳定版
        platform: win-x64 / linux-x64 / osx-x64

    返回 JSON：version/asset_name/save_path/size_mb。
    """
    import json

    return json.dumps(source_fetch.fetch_release_asset(version, platform), ensure_ascii=False)


@server.tool()
def list_submodules(source_dir: str) -> str:
    """解析 TShock 源码的 .gitmodules 列出子模块仓库（Phase 2）。

    参数：
        source_dir: TShock 源码目录（fetch_source 的 source_dir）

    返回 JSON：submodules[{path/url}]。
    """
    import json

    return json.dumps(source_fetch.list_submodules(source_dir), ensure_ascii=False)


# ---------- 扩展工具：项目辅助（Phase 1/3） ----------


@server.tool()
def check_csproj(csproj_path: str) -> str:
    """检查插件工程 csproj 的 TFM 与 TShock 包版本是否正确（Phase 3）。

    参数：
        csproj_path: 插件工程 csproj 绝对路径

    返回 JSON：target_framework/tshock_package/issues。
    """
    import json

    return json.dumps(project_util.check_csproj(csproj_path), ensure_ascii=False)


@server.tool()
def find_test_server(search_root: str = "") -> str:
    """探测本地测试服务器目录（Phase 1）。

    参数：
        search_root: 搜索根目录；留空则探测常见位置

    返回 JSON：found/server_dir/plugins_dir。
    """
    import json

    return json.dumps(project_util.find_test_server(search_root), ensure_ascii=False)


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


# ---------- 扩展工具：GitHub 评论读取（gh CLI 封装，独立可用） ----------


@server.tool()
def read_github_comments(repo: str = "", number: str = "", url: str = "",
                         comment_type: str = "all") -> str:
    """读取 GitHub issue/PR 的评论（对话 / Review 总结 / 代码行评论），封装 gh CLI。

    独立可用：即使没有插件开发需求，也可直接调用做评论审核、查看、分析。

    参数：
        repo: 仓库 full_name（如 owner/repo）；与 number 配对，与 url 二选一
        number: issue/PR 编号（正整数）
        url: 评论页 URL（如 https://github.com/owner/repo/pull/5）；优先于 repo+number
        comment_type: all/description/conversation/review/code（默认 all 全部）

    返回 JSON：repo/number/kind/total/comments[{id/type/author/created_at/body/path/line/state}]。
    """
    import json

    return json.dumps(gh_comments.read_github_comments(repo, number, url, comment_type),
                      ensure_ascii=False)


if __name__ == "__main__":
    server.run()  # 默认 stdio 传输
