# TShock 插件开发 Skill 配套 MCP Server

为 [tshock-plugin-dev](../SKILL.md) skill 提供高频操作的自动化工具。AI 在对应阶段直接调用工具，减少手动命令与猜错；**未安装时 skill 流程照常工作（优雅降级）**。

## 工具清单（13 个）

### 核心工具

| 工具 | 对应阶段 | 作用 |
|---|---|---|
| `resolve_version` | Phase 1 | 解析 Terraria ↔ TShock ↔ TFM ↔ NuGet 四元组 + 门禁判断 |
| `check_build` | Phase 6 | 编译插件 + 解析错误码（CS0012/CS0234/NU1101…）给出修复建议 |
| `check_load_log` | Phase 7 | 读取服务器日志，按特征表判断插件加载成败 |
| `fetch_source` | Phase 2 L4 | 下载指定版本 TShock 源码 + 可选定位 API 符号定义 |

### GitHub 访问（Phase 2 参考源）

| 工具 | 作用 |
|---|---|
| `search_repos` | 搜索相似插件仓库，**自动校验其适配版本与目标版本是否匹配**（match/mismatch/unknown） |
| `read_remote_file` | 直接读取 GitHub 上某文件内容（不下载整包，省流量） |
| `search_code` | 跨仓库代码搜索找 API 用法（需 `GITHUB_TOKEN` 环境变量） |
| `search_plugin_library` | 在 UnrealMultiple/TShockPlugin 插件库内检索相似插件（目录名+README 匹配，含版本校验，Phase 0） |

### 源码/资源获取（Phase 2 L4）

| 工具 | 作用 |
|---|---|
| `fetch_terrariaapi` | 下载 TerrariaServerAPI 子模块源码（CS0117 报错根源常在） |
| `fetch_release_asset` | 下载 TShock 官方发布包 zip（自动准备测试服务器） |
| `list_submodules` | 解析 TShock 源码 `.gitmodules` 列出子模块仓库 |

### 项目辅助（Phase 1/3）

| 工具 | 作用 |
|---|---|
| `check_csproj` | 检查 csproj 的 TFM 与 TShock 包版本是否正确 |
| `find_test_server` | 探测本地测试服务器目录 |

## 安装

```bash
pip install -r requirements.txt
```

## 在 TRAE 中注册（本地 stdio）

1. 打开 TRAE 的 MCP 设置 → 添加本地 MCP server
2. 配置（JSON 形式）：

```json
{
  "mcpServers": {
    "tshock-plugin-dev": {
      "type": "stdio",
      "command": "python",
      "args": ["C:\\Users\\星梦\\Desktop\\插件开发\\[文档]插件开发\\TShock插件开发Skill-分发版\\tshock-plugin-dev\\mcp-server\\server.py"]
    }
  }
}
```

> `command` 换成你本机 `python` 的实际路径（`where python` 查看）；`args` 指向本仓库 `mcp-server/server.py` 的绝对路径。

3. 保存后确认 server 状态为「已连接」，工具列表出现 13 个工具即成功。

> 若使用 `search_code`，还需给 MCP server 进程设置 `GITHUB_TOKEN` 环境变量（代码搜索 API 强制认证）。

## 命令行自测（不经过 MCP）

每个工具都可独立运行：

```bash
python tools/version_resolver.py 1.4.5.6          # 解析指定 Terraria 版本
python tools/build_check.py "路径\MyPlugin.csproj" --test
python tools/load_log_check.py "路径\server_out.log" MyPlugin
python tools/fetch_tshock_source.py 6.1.0 PacketTypes
python tools/github_access.py search "tshock plugin" 6.1.0 1.4.5.6  # 搜索仓库并校验版本匹配
python tools/github_access.py read Pryaxis/TShock TShockAPI/Commands.cs
python tools/github_access.py code "PacketTypes language:C#"          # 需 GITHUB_TOKEN
python tools/github_access.py library "签到" UnrealMultiple/TShockPlugin 6.1.0 1.4.5.6  # 插件库内检索相似插件
python tools/source_fetch.py terrariaapi 6.1.0                        # 下载 TerrariaServerAPI
python tools/source_fetch.py release 6.1.0                            # 下载发布包
python tools/source_fetch.py submodules "路径\tshock源码目录"          # 列出子模块
python tools/project_util.py csproj "路径\MyPlugin.csproj"            # 检查 csproj
python tools/project_util.py server                                   # 探测测试服务器
```

## 设计说明

- 所有工具返回 **JSON 字符串**，便于 AI 解析
- 工具层兜底：网络失败/文件缺失返回 `{"error": ...}`，不崩溃
- `fetch_source` / `fetch_terrariaapi` / `fetch_release_asset` 属联网下载，AI 调用前须按 skill 硬性规则征得用户同意
- `search_repos` 会对每个结果仓库做**版本匹配校验**（读 README/csproj 提取 TShock/Terraria 版本线索），返回 match / mismatch / unknown，避免参考错误版本的代码
- `search_code` 需要 `GITHUB_TOKEN` 环境变量；`search_repos` / `read_remote_file` 无 token 也能用（有速率限制）
- `search_plugin_library` 读取插件库仓库递归树 + 各插件 README（自动识别 `src/<插件>` 或顶层布局；有 `GITHUB_TOKEN` 全扫、无 token 限 50 个目录），目录名或 README 命中关键词即入选，每个结果带 `match_context`（README 命中行或功能描述）便于判断语义相关性；复用 `_probe_version`/`_match_version` 对每个入选插件做版本匹配校验。未设 `GITHUB_TOKEN` 时可用（匿名限速 60 次/小时）
- 错误码速查表 / 加载特征表 / TFM 映射分别与 `references/10-排错手册.md`、`references/09-编译部署加载验证.md`、`references/02-版本解析与兼容性.md` 保持一致
