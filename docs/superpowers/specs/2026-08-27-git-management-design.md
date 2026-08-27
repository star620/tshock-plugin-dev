# 设计文档：tshock-plugin-dev skill 增加 git 管理能力

- 日期：2026-08-27
- 状态：已批准（三段逐节确认）
- 关联 skill：`tshock-plugin-dev`

## 1. 背景与目标

现有 `tshock-plugin-dev` skill 的十阶段流程完全没有 git 环节：插件开发完成后的交付物只有本地 DLL/源码，用户需要自行管理版本、推送远程。本设计为 skill 增加一套**贯穿全流程、仅首尾提交**的 git 管理能力，支持两类目标仓库场景：

- **个人私有仓库**：用户自己的插件仓库，git init / commit / push 全自动，默认创建私有仓库
- **社区 CI 仓库**：目标仓库配置了 GitHub Actions 构建工作流（如 `UnrealMultiple/TShockPlugin`、`Zykor-Club/TShockServerPlugin`），推送会触发自动构建 + Release——此类默认走 **fork + PR** 流程

## 2. 流程接入（贯穿全流程，仅首尾提交）

### Phase 0 需求采集（新增第 4 问）

在现有三段式问卷（设计意图采集 / 相似插件检索与分流 / 细化问卷）之后新增 1 个问题：

> **git 管理**：是否需要 git 管理？远程仓库 URL（可留空）？私有/公开？

- 需要 + 有 URL → `git_required=true`，记录 `repo_url`、`visibility`
- 需要 + 无 URL → `git_required=true`，`repo_url=""`，交付时按需创建私有仓库
- 不需要 → `git_required=false`，跳过整个 git 流程

### Phase 3 项目脚手架（git 初始化 + 首次提交）

脚手架生成完成后：

1. 调 `git_status(project_dir)` 检测：
   - 已存在 `.git/` → **复用**（不 init、不覆盖，追加提交）
   - 不存在 → `git init` + 写 `.gitignore`（排除 `bin/`、`obj/`、`*.dll`、`*.pdb`、`ServerPlugins/`、`.vs/`、`*.user`）+ 首次提交 `chore: 项目脚手架初始化`
2. 若 Phase 0 设了 `git_required=false` → 跳过

### Phase 9 交付（最终提交 + 推送）

1. 调 `git_commit(project_dir, message=最终交付信息)` 做最终提交（无变化则 skip）
2. 调 `git_push(project_dir, repo_url, visibility)` 推送：
   - 无远程 → 创建仓库（默认 private）+ push
   - 有远程 → 先 CI 检测，再按结果走推送或 fork+PR
3. 向用户简报：commit hash / 远程 URL / 分支 / CI 情况

### 已有 git 仓库

Phase 3 检测到 `.git/` 即视为已有仓库，只追加提交、不重复初始化、不覆盖任何内容。远程 URL 以已有 origin 为准，用户未显式提供新 URL 时不改动。

## 3. MCP 工具设计（新增 3 个工具）

新增 `mcp-server/tools/git_manage.py`，在 `server.py` 注册 3 个工具。全部通过子进程调用本机 git。

### 工具 1 `git_status(project_dir)`

只读检测。返回 JSON：

```
is_git_repo / remote_url / branch / dirty / untracked_files / git_available / git_path
```

- 检测 `project_dir/.git/` 是否存在
- `git remote get-url origin` 读远程
- `git status --porcelain` 判断 dirty 与未跟踪文件
- git 不可用或路径探测失败 → `git_available=false` + hint（提示装 git 或配 `GIT_EXECUTABLE`）

### 工具 2 `git_commit(project_dir, message, init_if_needed=false)`

提交。返回 JSON：

```
action(init/commit/skip) / commit_hash / changed_files / message
```

- 已 init → `git add -A` + commit
- 未 init 且 `init_if_needed=true` → 先 init + 写 `.gitignore` + commit
- 无变化 → `skip`（不产生空提交）
- `init_if_needed=false` 且未 init → 返回错误 + 提示先走 Phase 3
- user.name/email 未配置 → 明确错误 + 提示 `git config` 命令

### 工具 3 `git_push(project_dir, repo_url="", visibility="private")`

推送 + CI 检测。返回 JSON：

```
pushed / repo_url / branch / ci_detected / ci_files[] / recommended_flow / notes
```

**CI 检测（核心）**：

1. 探测目标仓库 `.github/workflows/*.yml`：
   - 本地已 clone → 读本地
   - 否则用 GitHub API `GET /repos/{owner}/{repo}/contents/.github/workflows`
2. 识别到 `build.yml` 等构建工作流 → `ci_detected=true` + `ci_files[]`
3. **ci_detected=true 时默认推荐 fork + PR 流程**（`recommended_flow="fork_pr"`）：
   - fork 上游仓库 → 本地开发分支 → push 到 fork → 开 PR 到上游
   - 避免直接推 master/main 触发不必要的构建 + Release
   - 若用户坚持直接推上游，必须征得同意并明确告知会触发 CI 构建 + 自动 Release
4. ci_detected=false → 正常 push（`recommended_flow="direct_push"`）

**远程创建**：本地无 origin 时，用 `repo_url` + GitHub API（GH_TOKEN）创建私有仓库（默认 private）→ `git remote add origin` → push。

**失败处理**：push 403 / 认证失败 → 返回错误 + hint「生成 GitHub token 配到凭据 / GIT_TOKEN」。

**参考实现**：yeet skill 的混合模式——本地 git 做 add/commit/push，GitHub API 只做仓库创建与 CI 探测。

## 4. git 路径探测（关键技术点）

MCP 工具运行于 Python 子进程，本机 git 不在 PATH（如 `D:\Git\bin\git.exe`）。`git_manage.py` 必须内置路径探测，顺序：

1. 环境变量 `GIT_EXECUTABLE`
2. 常见安装路径（`C:\Program Files\Git\bin\git.exe`、`D:\Git\bin\git.exe` 等）
3. `shutil.which("git")`

探测失败 → `git_available=false` + 明确 hint。

## 5. references/12-git管理.md 文档

新增参考文档，结构：

1. **git 命令速查**：init / add / commit / remote / push 的 PowerShell 命令 + 常见错误解决（403、身份未配置、路径含中文）
2. **`.gitignore` 模板**：排除 `bin/`、`obj/`、`*.dll`、`*.pdb`、`ServerPlugins/`、`.vs/`、`*.user`
3. **MCP 工具调用对照**：`git_status` / `git_commit` / `git_push` 对应流程阶段、时机、参数示例
4. **CI 仓库专项**：
   - 识别：目标仓库 `.github/workflows/` 存在 build.yml → CI 仓库
   - 行为：push 到 master/main 自动构建 + 自动发 Release + 更新 tag（UnrealMultiple 还同步 ApmApi/论坛/Crowdin）
   - 注意：这类仓库通常要求插件放 `src/<插件名>/`、不能提交 DLL/PDB、可能要求 `manifest.json`/`README`/`template.targets`（Zykor-Club 的 Lint 会校验）——推送前必须用 `check_csproj`/目录结构核对，否则 CI 会挂
   - 建议流程：**fork → 分支开发 → 提 PR**，而非直接推 master；用户坚持直接推必须征得同意
5. **安全提醒**：token 不入库、`.gitignore` 排除敏感文件、推送前确认远程 URL

## 6. SKILL.md 同步修改

- Phase 0 增加第 4 问（git 管理/远程仓库/私有公开）
- Phase 3 增加「git init + .gitignore + 首次提交」
- Phase 9 增加「git commit + push（含 CI 检测）」
- 参考文档索引表加 `references/12-git管理.md`

## 7. 测试

新增 `mcp-server/tests/test_git_manage.py`：

- git_status：非仓库目录 / 空仓库 / 有远程仓库
- git_commit：init + 首次提交 / 重复提交 / 无变化 skip
- git_push：CI 探测 mock（有 build.yml → fork_pr 推荐；无 → 正常 push）

跑通现有全部测试：`python -m pytest mcp-server/tests`。

## 8. 涉及文件清单

| 文件 | 动作 |
|---|---|
| `mcp-server/tools/git_manage.py` | 新增（3 工具实现 + git 路径探测） |
| `mcp-server/server.py` | 修改（注册 3 个新工具） |
| `mcp-server/tests/test_git_manage.py` | 新增 |
| `references/12-git管理.md` | 新增 |
| `SKILL.md` | 修改（Phase 0/3/9 + 索引表） |
