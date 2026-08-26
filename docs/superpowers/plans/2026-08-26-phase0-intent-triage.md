# Phase 0 设计意图采集 + 相似插件分流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 tshock-plugin-dev skill 的 Phase 0 需求采集为三段式（设计意图采集 → 相似插件检索与分流 → 细化问卷），并新增 MCP 工具 `search_plugin_library` 检索 UnrealMultiple/TShockPlugin 插件库。

**Architecture:** 在现有 `references/00-需求采集.md` 基础上重构 Phase 0 流程；扩展 `mcp-server/tools/github_access.py`（复用其 `_probe_version`/`_match_version` 版本校验逻辑，重构支持子目录参数）；`server.py` 注册第 13 个工具；借鉴分支新增版本升级检查硬性规则。Skill 未装 MCP 时优雅降级为手动检索。

**Tech Stack:** Python 3（stdlib `unittest` + `unittest.mock` 测试，`requests` 调 GitHub REST/raw API），Markdown 文档，TShock 6.0.0+ / net9.0 版本门禁。

**设计文档：** `docs/superpowers/specs/2026-08-26-phase0-intent-triage-design.md`

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `mcp-server/tools/github_access.py` | 新增 `search_plugin_library` + 重构 `_probe_version` 支持 subdir + CLI `library` 模式 |
| `mcp-server/tests/__init__.py` | 测试包标记（空文件） |
| `mcp-server/tests/test_github_access.py` | `_probe_version` 子目录 / `search_plugin_library` 的单元测试（mock 网络） |
| `mcp-server/server.py` | 注册第 13 个工具 `search_plugin_library` |
| `mcp-server/README.md` | 工具清单 12→13、自测命令、设计说明 |
| `references/00-需求采集.md` | 重构为三段式流程 |
| `SKILL.md` | Phase 0 描述、硬性规则"借鉴须版本升级检查"、Phase 2 参考源说明 |

---

### Task 1: 重构 `_probe_version` 支持子目录参数

**Files:**
- Create: `mcp-server/tests/__init__.py`
- Create: `mcp-server/tests/test_github_access.py`
- Modify: `mcp-server/tools/github_access.py:28-69`

- [ ] **Step 1: 建测试包与失败测试**

创建 `mcp-server/tests/__init__.py`（空文件）。

创建 `mcp-server/tests/test_github_access.py`：

```python
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
        mock_raw.side_effect = [mock.Mock(status_code=404)]

        result = github_access.search_plugin_library("spam", "UnrealMultiple/TShockPlugin")
        names = [p["name"] for p in result.get("plugins", [])]
        self.assertIn("SpamKiller", names)   # 目录名含关键词"spam"

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
```

- [ ] **Step 2: 运行测试确认失败（函数尚未存在）**

Run: `cd mcp-server && python -m unittest tests.test_github_access -v`
Expected: FAIL — `AttributeError: module 'tools.github_access' has no attribute 'search_plugin_library'`

- [ ] **Step 3: 重构 `_probe_version` 支持 subdir**

修改 `mcp-server/tools/github_access.py:28-69`，把签名改为 `_probe_version(repo: str, subdir: str = "")`，候选路径加子目录前缀：

```python
def _probe_version(repo: str, subdir: str = "") -> dict:
    """探测仓库/插件适配的 TShock / Terraria 版本（读 README + csproj 线索）。

    subdir 非空时探测插件子目录（如 UnrealMultiple/TShockPlugin 里的单个插件）。
    返回 version_hint（如 "TShock 6.1.0 / net9.0"）与 evidence（依据来源）。
    """
    prefix = f"{subdir}/" if subdir else ""
    hint_parts, evidence = [], []
    candidates = [
        f"{prefix}README.md", f"{prefix}README_cn.md", f"{prefix}README_CN.md", f"{prefix}readme.md",
        f"{prefix}src/Plugin.csproj", f"{prefix}Plugin.csproj", f"{prefix}src/TShock.Plugin.csproj",
        f"{prefix}TShock.Plugin.csproj", f"{prefix}src/*.csproj",
    ]
    for cand in candidates[:5]:  # 最多探测 5 个路径，避免 API 消耗过大
        url = f"{RAW}/{repo}/HEAD/{cand}"
        if "*" in cand:
            continue
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code != 200:
                continue
            text = resp.text
            evidence.append(cand)
            # README 中的版本字样
            for pat, label in [
                (r"TShock\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)", "TShock"),
                (r"Terraria\s*([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)", "Terraria"),
                (r"1\.4\.5\.\d", "Terraria"),
            ]:
                m = re.search(pat, text, re.IGNORECASE)
                if m and label not in hint_parts:
                    val = m.group(1) if m.lastindex else m.group(0)
                    hint_parts.append(f"{label} {val}")
            # csproj 中的 TFM / 包版本
            tfm = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", text)
            if tfm:
                hint_parts.append(tfm.group(1))
            pkg = re.search(r"PackageReference\s+Include=\"TShock\"\s+Version=\"([^\"]+)\"", text)
            if pkg:
                hint_parts.append(f"TShock {pkg.group(1)}")
        except requests.RequestException:
            continue

    return {"version_hint": " / ".join(dict.fromkeys(hint_parts)) if hint_parts else "", "evidence": evidence}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd mcp-server && python -m unittest tests.test_github_access -v`
Expected: `ProbeVersionSubdirTest` PASS（此时 `search_plugin_library` 仍未定义，后两个测试类仍 FAIL——Task 2 补齐）

- [ ] **Step 5: Commit**

```bash
git add mcp-server/tools/github_access.py mcp-server/tests/__init__.py mcp-server/tests/test_github_access.py
git commit -m "refactor: _probe_version 支持插件子目录探测 + 新增测试骨架"
```

---

### Task 2: 新增 `search_plugin_library` 函数 + CLI `library` 模式

**Files:**
- Modify: `mcp-server/tools/github_access.py`（在 `search_repos` 后追加函数；CLI 加 `library` 分支）

- [ ] **Step 1: 实现 `search_plugin_library`**

在 `mcp-server/tools/github_access.py` 的 `search_code` 函数之后（`if __name__` 之前）追加：

```python
# 插件库检索的扫描上限：匿名限速 60 次/小时，读树 2 次 + README 若干次须留余量
MAX_README_SCAN = 30
MAX_RESULTS = 6


def search_plugin_library(query: str, repo: str = "UnrealMultiple/TShockPlugin",
                          target_tshock: str = "", target_terraria: str = "") -> dict:
    """在插件库仓库内检索相似插件（Phase 0 步骤 0.2）。

    参数：
        query: 关键词（如 "签到 礼包"，中英文均可）
        repo: 插件库仓库（默认 UnrealMultiple/TShockPlugin）
        target_tshock: 目标 TShock 版本（如 6.1.0），版本匹配校验
        target_terraria: 目标 Terraria 版本（如 1.4.5.6）

    返回 JSON：repo/stars/plugins[{name/description/version_hint/version_match}]。
    version_match: match（可参考）/ mismatch（需升级改造）/ unknown（自行核对）。
    """
    if not query:
        return {"error": "缺少参数 query"}
    try:
        info = _get(f"{API}/repos/{repo}")
        default_branch = info.get("default_branch", "HEAD")
        stars = info.get("stargazers_count", 0)

        tree = _get(f"{API}/repos/{repo}/git/trees/{default_branch}", {"recursive": "1"})
        # 顶层插件子目录：type=tree 且路径不含 '/'
        dirs = [i["path"] for i in tree.get("tree", [])
                if i.get("type") == "tree" and "/" not in i["path"]]
        if len(dirs) > MAX_README_SCAN:
            dirs = dirs[:MAX_README_SCAN]

        tokens = [t for t in re.split(r"[\s,，、/_\-]+", query.lower()) if t]

        plugins = []
        for d in dirs:
            readme_url = f"{RAW}/{repo}/HEAD/{d}/README.md"
            try:
                resp = requests.get(readme_url, timeout=8)
                text = resp.text if resp.status_code == 200 else ""
            except requests.RequestException:
                text = ""
            dirname_hit = any(t in d.lower() for t in tokens)
            readme_hit = any(t in text.lower()[:800] for t in tokens)
            if not (dirname_hit or readme_hit):
                continue
            desc = _readme_summary(text) or d
            probe = _probe_version(repo, subdir=d)
            plugins.append({
                "name": d,
                "description": desc[:120],
                "version_hint": probe["version_hint"],
                "version_match": _match_version(probe["version_hint"], target_tshock, target_terraria),
            })
            if len(plugins) >= MAX_RESULTS:
                break
        return {
            "repo": repo, "stars": stars,
            "plugins": plugins,
            "hint": ("匹配基于插件目录名与 README 摘要；version_match=match 可参考，"
                     "mismatch 借鉴需升级改造，unknown 需自行核对。未找到时可用 search_repos 搜全 GitHub 兜底。"),
        }
    except requests.RequestException as e:
        return {"error": f"GitHub API 请求失败：{e}。可设置 GITHUB_TOKEN 提升速率限制。"}


def _readme_summary(text: str) -> str:
    """提取 README 第一段有效文字作摘要（去标题/空行/图片行）。"""
    for line in text.splitlines():
        line = line.strip(" #*\t")
        if not line or line.startswith("!"):
            continue
        return line
    return ""
```

在 `__main__` CLI 中追加 `library` 分支（紧跟 `elif mode == "code":` 之后）：

```python
    elif mode == "library":
        r = sys.argv[3] if len(sys.argv) > 3 else "UnrealMultiple/TShockPlugin"
        t2 = sys.argv[4] if len(sys.argv) > 4 else ""
        t3 = sys.argv[5] if len(sys.argv) > 5 else ""
        print(json.dumps(search_plugin_library(q, r, t2, t3), ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 运行测试验证通过**

Run: `cd mcp-server && python -m unittest tests.test_github_access -v`
Expected: 3 个测试类全部 PASS（`ProbeVersionSubdirTest` + 2 个 `SearchPluginLibraryTest` + 1 个 empty 用例）

- [ ] **Step 3: CLI 冒烟测试（mock 场景已覆盖，这里验证语法/入口）**

Run: `cd mcp-server && python -c "from tools.github_access import search_plugin_library; print(search_plugin_library('')['error'])"`
Expected: `缺少参数 query`（参数校验路径可用，不发网络请求）

- [ ] **Step 4: Commit**

```bash
git add mcp-server/tools/github_access.py
git commit -m "feat: 新增 search_plugin_library 插件库检索工具 + CLI library 模式"
```

---

### Task 3: server.py 注册第 13 个工具

**Files:**
- Modify: `mcp-server/server.py`

- [ ] **Step 1: 注册 `search_plugin_library` 工具**

在 `server.py` 的 `search_repos` 工具（约 90 行）之后追加：

```python
@server.tool()
def search_plugin_library(query: str, repo: str = "UnrealMultiple/TShockPlugin",
                          target_tshock: str = "", target_terraria: str = "") -> str:
    """在 TShock 插件库仓库内检索相似插件（Phase 0 步骤 0.2）。

    参数：
        query: 关键词（如 "签到 礼包"，中英文均可）
        repo: 插件库仓库（默认 UnrealMultiple/TShockPlugin）
        target_tshock: 目标 TShock 版本（可选，版本匹配校验）
        target_terraria: 目标 Terraria 版本（可选）

    返回 JSON：repo/stars/plugins[{name/description/version_hint/version_match}]。
    """
    import json

    return json.dumps(github_access.search_plugin_library(query, repo, target_tshock, target_terraria), ensure_ascii=False)
```

- [ ] **Step 2: 验证工具数 = 13**

Run: `cd mcp-server && (Select-String -Path server.py -Pattern "@server.tool()").Count`
Expected: `13`

Run: `python -c "import sys; sys.path.insert(0, '.'); from tools import github_access; print(callable(github_access.search_plugin_library))"`
Expected: `True`（导入无误）

- [ ] **Step 3: Commit**

```bash
git add mcp-server/server.py
git commit -m "feat: MCP server 注册 search_plugin_library（第 13 个工具）"
```

---

### Task 4: 更新 mcp-server/README.md

**Files:**
- Modify: `mcp-server/README.md`

- [ ] **Step 1: 更新工具清单与自测命令**

把第 5 行 `## 工具清单（12 个）` 改为 `## 工具清单（13 个）`；在「GitHub 访问」表格中追加一行：

```markdown
| `search_plugin_library` | Phase 0 | 在 UnrealMultiple/TShockPlugin 插件库内检索相似插件（目录名+README 匹配，含版本校验） |
```

把第 64 行 `工具列表出现 12 个工具即成功` 改为 `工具列表出现 13 个工具即成功`；在自测命令列表中（`search_code` 那行之后）追加：

```bash
python tools/github_access.py library "签到" UnrealMultiple/TShockPlugin 6.1.0 1.4.5.6  # 插件库内检索相似插件
```

- [ ] **Step 2: 更新设计说明**

在设计说明列表追加一条：

```markdown
- `search_plugin_library` 读取插件库仓库递归树 + 各插件 README（扫描上限 30 个目录），目录名或 README 命中关键词即入选；复用 `_probe_version`/`_match_version` 对每个入选插件做版本匹配校验。未设 `GITHUB_TOKEN` 时可用（匿名限速 60 次/小时）
```

- [ ] **Step 3: Commit**

```bash
git add mcp-server/README.md
git commit -m "docs: mcp-server README 工具清单 12→13 并补充 search_plugin_library"
```

---

### Task 5: 重构 references/00-需求采集.md 为三段式 + 更新 SKILL.md

**Files:**
- Modify: `references/00-需求采集.md`（整文件重写）
- Modify: `SKILL.md`

- [ ] **Step 1: 重写 `references/00-需求采集.md`**

整体替换为以下内容（保留原必答问卷/可选信息/确认话术/需求变更，前置两段新流程）：

```markdown
# 00 需求采集（必答问卷）

开发前必须完成需求采集。以聊天问答形式逐项确认，**禁止跳过**。

流程分三步：**0.1 设计意图采集 → 0.2 相似插件检索与分流 → 0.3 细化问卷**。先弄清「为什么做」，再决定「怎么做 / 做不做」。

## 步骤 0.1 设计意图采集（必答，新增）

开放式一问一答（参照 brainstorming 风格：一次一问、给选项），目的是彻底弄清真实需求，避免开发中犯迷糊。

**提问脚本（一次只问一个）**：

1. **目的**：想通过这个插件解决什么问题 / 达成什么效果？（例：防止玩家卡 BUG 刷物品、给玩家每日签到奖励）
2. **场景**：谁用（管理员/玩家/全员）？什么时候用？怎么触发（聊天命令/进服事件/定时任务）？
3. **方向**：功能全面还是精简够用？高性能还是易上手？是否要与现有某插件配合？
4. **强度**：不做这个插件会怎样？（若用户答「无所谓/就是想要」，主动提示存在放弃选项）

产出「设计意图摘要」（2-3 句），并入下方需求摘要。

## 步骤 0.2 相似插件检索与分流（必答，新增决策门）

1. 从意图摘要提取检索关键词（中文 + 英文，如「签到 礼包 checkin」）
2. 检索顺序：
   - **MCP 可用**：`search_plugin_library` 查 `UnrealMultiple/TShockPlugin` 插件库 → 无结果或需扩大范围时用 `search_repos` 搜全 GitHub 兜底
   - **MCP 不可用**：按 `references/03-参考源码获取.md` 手动 GitHub 检索
3. 向用户呈现候选表：仓库/插件名、描述、Star、**版本匹配（match/mismatch/unknown）**
4. 问用户三选一：

> 库/GitHub 上有相似插件：<名称>（版本匹配：match/mismatch/unknown）。你想怎么处理？
> 1. **借鉴改进**：下载源码以它为底座改造（版本不匹配会先做升级检查，交付兼容 TShock 6.0.0+）
> 2. **自研**：不下载，独立实现（相似插件仍作 Phase 2 参考源看思路）
> 3. **放弃**：不需要了，结束本次开发

5. 分流结果处理：
   - **借鉴** → 记录参考仓库 full_name 与版本匹配结论；进入步骤 0.3 时版本问题优先参考该插件；下载动作在 Phase 2 执行（先征得同意）
   - **自研** → 正常进入步骤 0.3；候选插件记入参考源列表（Phase 2 L2）
   - **放弃** → 复述意图摘要确认后结束会话，不进入后续阶段
   - 版本匹配为 **mismatch** 时提示：该插件为旧版本，借鉴需升级改造（TFM→net9.0、TShock 包版本、API 变更用 Phase 2 参考源核对）

## 步骤 0.3 细化问卷（按分流结果裁剪）

> 分流裁剪规则：**借鉴**分支的「目标版本」改为「参考插件版本 + 升级检查」；**自研**分支问卷照常；**放弃**分支不进入本步骤。

### 必答项（不可省略）

### 1. 目标版本（最关键，**必须先提问，禁止直接自动探测**）

**提问纪律**：逐条向用户提问，一次一问、给出选项；**只有**用户明确表示「不知道 / 用最新 / 给你服务器文件夹」时，才进入 Phase 1 自动探测，且探测结果必须回显给用户确认。

**提问脚本（服务端版本）**：
> 你的服务端 TShock 版本是？选一个：
> 1. 我知道版本号（如 6.1.0）
> 2. 给你服务器文件夹路径，你自己探测
> 3. 用最新稳定版
> 4. 不清楚（由你探测）

> 借鉴分支：可直接问「参考插件适配的版本行不行？」（不匹配则进入升级检查）。

**提问脚本（客户端版本）**：
> 玩家的 Terraria 客户端版本是？（需与服务端支持的版本匹配；不确定可选「与服务器一致」或「最新」）

- 客户端与服务端必须匹配：Terraria 客户端只能连接同版本的 Terraria 服务端
- 用户答「最新 / 不知道」→ 记为「未知，需在线解析」，进入 Phase 1 查询，结果回显确认
- 用户给服务器文件夹 → Phase 1 从文件夹探测（`ServerPlugins/TShockAPI.dll` 版本、启动横幅）

> 若客户端版本过新（TShock 尚未跟进、无对应 NuGet 包），触发版本门禁：除非用户提供本地跟进源码，否则**明确告知无法为该版本编写插件**。

### 2. 插件基本信息
- 插件名称（英文，用作命名空间/程序集名，如 `MyPlugin`）
- 作者
- 版本（默认 1.0.0）
- 描述（一句话）

### 3. 功能需求（自由描述）
- 核心功能：插件要做什么
- 触发方式：命令 / 玩家事件 / 定时 / 服务器事件
- 边界条件：适用于哪些玩家（全员/指定组/管理员）、哪些状态（登录后/游戏中）

### 4. 命令与权限
- 需要哪些聊天命令（`/xxx` 语法）
- 每条命令对应的权限名（如 `myplugin.admin`）
- 默认哪些用户组可使用

### 5. 配置与数据
- 是否需要配置文件（JSON）与缓存/数据文件
- 配置文件里要放哪些可调项

## 可选信息（按用户掌握程度，小白可留空）

| 信息 | 用途 | 留空时的处理 |
|---|---|---|
| 本地版本化源码夹路径（TShock源码+OTAPI+Terraria反编译） | L1 参考源，API 行为最权威依据 | 跳过 L1，走 L3/L4 |
| 本地插件收集仓库路径 | L2 参考源，找相似插件 | 跳过 L2 |
| **其他可参考的 GitHub 仓库或本地源码**（社区插件、同类实现、工具源码等） | 补充参考源，纳入 Phase 2 一并读取 | 跳过 |
| 本地测试服务器目录 | Phase 7 加载验证 | 自动下载官方发布包作测试服务器 |
| 是否安装 .NET SDK | 编译环境 | 自动安装（征得同意） |
| 是否提供自有插件模板 | 代码组织规范 | 用内置 templates/ |

> **提问提醒**：需求采集阶段主动问一句「还有其他可参考的 GitHub 仓库或本地源码吗？」，防止用户有现成参考源却没说。

## 采集完成后的确认话术

向用户复述一遍需求摘要，确认无误后再进入 Phase 1：

```
需求摘要：
- 设计意图：<2-3 句>
- 分流决策：借鉴改进/自研/放弃（参考插件：<名称>，版本匹配：<match/mismatch/unknown>）
- 目标：TShock <版本> / Terraria <版本>
- 插件：<名称> by <作者> v<版本>
- 功能：<要点>
- 命令：<列表>
- 权限：<列表>
- 配置：<是/否>
```

## 需求变更（任何阶段适用）

开发中用户提出新增/修改需求时，**禁止不更新摘要直接改代码**。按以下流程：

1. 更新需求摘要（上面的格式，标记变更处）
2. 说明本次变更影响哪些阶段，明确重跑路径：
   - 改目标版本（TShock/Terraria/.NET）→ 重跑 Phase 1 版本解析 → Phase 3+
   - 改配置项/新增配置 → Phase 3（脚手架）→ Phase 4/6
   - 改命令/权限/逻辑 → Phase 4（TDD）→ Phase 6
   - 改部署方式/边界条件 → Phase 4/7
   - **改设计意图 / 切换分流决策**（如自研改借鉴）→ 重跑 Phase 0 → Phase 2+
3. 与用户确认后，从对应阶段重新推进

变更不重跑已完成的、不受影响阶段的验证结论（如只改命令不改配置，Phase 3 无需重做）。
```

- [ ] **Step 2: 更新 SKILL.md**

修改 Phase 0 章节（第 20-32 行区域），在其开头插入三段式说明：

```markdown
**流程（三段式）**：先按「步骤 0.1 设计意图采集」开放式问清目的/场景/方向/强度；再按「步骤 0.2 相似插件检索与分流」检索 UnrealMultiple/TShockPlugin 插件库与全 GitHub（MCP 可用时优先 `search_plugin_library` + `search_repos`），呈现候选后由用户三选一（借鉴改进/自研/放弃）；最后按「步骤 0.3 细化问卷」裁剪提问。放弃 → 确认后终止开发流程。
```

在「硬性规则」列表追加第 7 条：

```markdown
7. **借鉴须版本升级检查**：以社区插件源码为底座改造时，先探测其 TFM/TShock 版本（`check_csproj` 或读 csproj）；低于 TShock 6.0 / 非 net9.0 必须列出升级改造点（TFM、包版本、API 变更），交付物兼容 TShock 6.0.0+
```

在 Phase 2 参考源码获取章节，把 L2 描述补充为：

```markdown
- **L2 本地插件收集仓库** → 按需求搜索相似插件源码作参考；**Phase 0 分流为「借鉴」时，下载的插件源码在此作为改造底座**
```

- [ ] **Step 3: Commit**

```bash
git add references/00-需求采集.md SKILL.md
git commit -m "feat: Phase 0 重构为三段式（设计意图采集 + 相似插件分流）+ 借鉴版本升级检查"
```

---

### Task 6: 实网验证 + 推送

**Files:** 无新增（验证用）

- [ ] **Step 1: 实网验证 search_plugin_library**

Run: `cd mcp-server && python tools/github_access.py library "签到" UnrealMultiple/TShockPlugin 6.1.0 1.4.5.6`
Expected: 返回 JSON，`plugins` 数组包含 README/目录名命中「签到」的插件，或 `{"plugins": [], ...}` + hint 提示用 search_repos 兜底；网络失败则返回 `{"error": ...}`（工具优雅降级，不算失败）

- [ ] **Step 2: 全量测试回归**

Run: `cd mcp-server && python -m unittest tests.test_github_access -v`
Expected: 全部 PASS

- [ ] **Step 3: 语法/导入冒烟（确认 13 个工具可加载）**

Run: `cd mcp-server && python -c "import sys; sys.path.insert(0,'.'); import server"`（如 mcp 环境不可用则跳过此步，改用 `python -c "from tools import github_access"`）
Expected: 无异常

- [ ] **Step 4: Commit + Push**

```bash
git add -A
git commit -m "feat: Phase 0 设计意图采集 + 相似插件分流（search_plugin_library 第 13 工具）"
git push origin main
```

Expected: push 成功（`main` 前进若干 commit）。推送后提示用户重启 TRAE 刷新 MCP 工具列表为 13 个。

---

## Self-Review 记录

- **Spec coverage**：设计文档四节全部有对应任务——三段式（Task 5）、search_plugin_library（Task 2/3/4）、借鉴版本升级检查（Task 5 SKILL.md）、文件清单（Task 1-6）。
- **Placeholder scan**：所有步骤含完整代码/命令与期望输出，无 TBD/TODO。
- **Type consistency**：`search_plugin_library(query, repo, target_tshock, target_terraria)` 在 github_access.py、server.py 注册、CLI、README 自测命令四处签名一致；`_probe_version(repo, subdir="")` 向后兼容 search_repos 现有调用。
