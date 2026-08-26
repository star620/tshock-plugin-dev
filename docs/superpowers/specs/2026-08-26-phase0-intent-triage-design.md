# Phase 0 重构：设计意图采集 + 相似插件分流

- 日期：2026-08-26
- 状态：已确认
- 影响范围：tshock-plugin-dev skill 的 Phase 0 需求采集流程、MCP 工具

## 背景与目标

现有 Phase 0 需求采集只问"事实型"问题（版本/功能/命令/权限/配置），缺少对**设计意图、设计方向、真实需求**的挖掘，导致开发中容易"犯迷糊"——需求理解错位后返工。另外，开发前不会主动检索社区是否已有相似插件，导致重复造轮子。

本次改动目标：

1. 开发前先彻底弄清用户的设计意图与真实需求（参照 brainstorming 的一问一答风格）
2. 依据意图在 UnrealMultiple/TShockPlugin 插件库及全 GitHub 检索相似插件
3. 检索到相似插件后，由用户分流决策：**借鉴改进 / 自研 / 放弃**
4. 借鉴分支必须做版本升级检查，交付物兼容 TShock 6.0.0+

## 设计

### 一、Phase 0 重构为三段式（references/00-需求采集.md + SKILL.md）

#### 步骤 0.1 设计意图采集（新增）

开放式一问一答，一次一问、给选项，参照 brainstorming 风格：

1. **目的**：想通过这个插件解决什么问题 / 达成什么效果？（"为什么需要"）
2. **场景**：谁用（管理员/玩家）、什么时候用、怎么触发（命令/事件/定时）？
3. **方向**：功能全面 vs 精简够用；高性能 vs 易上手；是否要与现有插件配合？
4. **强度**：不做这个插件会怎样？（需求真实度判断——若"无所谓"则主动提示可放弃）

产出"设计意图摘要"，并入需求摘要。

#### 步骤 0.2 相似插件检索与分流（新增决策门）

1. 从意图摘要提取检索关键词
2. MCP 可用时：`search_plugin_library` 查 UnrealMultiple/TShockPlugin 库 → `search_repos` 全站兜底；不可用时按 references/03 手动 GitHub 检索
3. 向用户呈现候选表：仓库名 / 描述 / Star / **版本匹配（match/mismatch/unknown）**
4. 用户三选一：
   - **借鉴改进** → 征得同意后下载源码为底座改造（须过版本升级检查）
   - **自研** → 独立实现（候选插件仍作 Phase 2 参考源）
   - **放弃** → 确认后终止开发流程，结束会话
5. 版本匹配为 mismatch 时：提示"该插件为旧版本，借鉴需升级改造"

#### 步骤 0.3 现有细化问卷（按分流结果裁剪）

- 借鉴分支：版本问题参考插件定，命令/权限/配置问卷照常
- 自研分支：问卷照常
- 放弃分支：不进入问卷
- 版本门禁保持（Terraria 版本无对应 TShock NuGet 包 → 明确告知无法编写）

### 二、新增 MCP 工具 search_plugin_library（第 13 个工具）

- 文件：`mcp-server/tools/github_access.py` 新增函数 + `server.py` 注册
- 入参：`query`（关键词，可多个）+ 可选 `repo`（默认 `UnrealMultiple/TShockPlugin`）
- 逻辑：
  1. GitHub API 递归获取仓库 git tree
  2. 过滤顶层插件子目录
  3. 关键词匹配目录名 / README 内容
  4. 读匹配目录 README 前若干行作摘要
  5. **复用现有 `_probe_version` / `_match_version` 校验版本线索**
- 返回 JSON：`plugins[{name/description/stars/version_hint/version_match}]`（`stars` 为插件库仓库总 Star，子目录无独立 Star，用作参考热度）
- 无 token 可用（匿名限速 60 次/小时，读 tree + 少量 README 足够）
- 更新 `mcp-server/README.md`：工具清单 12→13、自测命令、设计说明

### 三、借鉴分支版本升级检查（SKILL.md 硬性规则新增）

1. 下载源码后先探测其目标 TFM / TShock 版本（`check_csproj` 或读 csproj）
2. 若低于 TShock 6.0 / 非 net9.0 → 明确列出升级改造点：
   - TFM 升级（net9.0）
   - TShock NuGet 包版本更新
   - API 变更点（用 Phase 2 参考源核对）
3. **交付物必须是 TShock 6.0.0+ 兼容**

### 四、文件改动清单

| 文件 | 改动 |
|---|---|
| `references/00-需求采集.md` | 重构为三段式 + 意图提问脚本 + 分流决策话术 |
| `SKILL.md` | Phase 0 描述更新、硬性规则加"借鉴须版本升级检查"、参考文档索引 |
| `mcp-server/tools/github_access.py` | 新增 `search_plugin_library` |
| `mcp-server/server.py` | 注册第 13 个工具 |
| `mcp-server/README.md` | 工具清单 12→13 + 自测命令 + 设计说明 |

## 不在本次范围

- 不改动 Phase 1~9 流程主体
- 不新增其他 MCP 工具
- 不重写现有版本/命令/权限问卷，只做顺序与裁剪调整
