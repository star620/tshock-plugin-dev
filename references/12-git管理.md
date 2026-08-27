# 12 git 管理（Phase 0/3/9）

目的：插件开发全流程的 git 版本管理（init / commit / push），支持个人私有仓库与社区 CI 仓库两类场景。
与 `references/03` 一致，本文档是 AI 执行 git 操作时的行为依据；MCP 可用时优先调用 `git_status` / `git_commit` / `git_push` 工具。

## 1. 流程接入（贯穿全流程，仅首尾提交）

| 阶段 | 动作 | 工具/命令 |
|---|---|---|
| Phase 0 | 询问「是否需要 git 管理？远程仓库 URL（可留空）？私有/公开？」；不需要 → 全程跳过 | — |
| Phase 3 | 检测 `.git/`；无 → `git init` + 写 `.gitignore` + 首次提交 `chore: 项目脚手架初始化`；有 → 复用不覆盖 | `git_status` → `git_commit(init_if_needed=true)` |
| Phase 9 | 最终提交（无变化 skip）+ 推送；CI 仓库默认 fork+PR | `git_commit` → `git_push` |

**已有仓库**：检测到 `.git/` 即复用，只追加提交，不重复初始化。远程 URL 以已有 origin 为准，用户未提供新 URL 时不改动。

## 2. git 命令速查（MCP 不可用时的兜底）

```powershell
# 初始化（PowerShell）
git init
# 写 .gitignore 后（模板见下），首次提交
git add .
git commit -m "chore: 项目脚手架初始化"
# 绑定远程并推送
git remote add origin <URL>
git push -u origin main
# 查看状态
git status
```

**常见错误**：
| 现象 | 原因 | 解决 |
|---|---|---|
| `403 denied to <user>` | 凭据/token 权限不足 | 生成带 repo 权限的 PAT，配到 Windows 凭据管理器或 GIT_TOKEN/GITHUB_TOKEN |
| `Author identity unknown` | 未配置 user.name/email | `git config --global user.name "名字"`、`git config --global user.email "邮箱"` |
| 路径含中文报错 | 编码/引号问题 | 用绝对路径并加引号，避免 `cd` 拼接 |
| `LF will be replaced by CRLF` | 行尾符警告（非错误） | 可忽略；或配置 `core.autocrlf` |

## 3. .gitignore 模板

```gitignore
# 构建产物
bin/
obj/
*.dll
*.pdb
*.exe
# 测试服务器目录
ServerPlugins/
# IDE / 系统
.vs/
*.user
.DS_Store
```

## 4. MCP 工具调用对照

| 工具 | 阶段 | 参数 | 返回关键字段 |
|---|---|---|---|
| `git_status` | Phase 3 | `project_dir` | is_git_repo / remote_url / branch / dirty / git_available |
| `git_commit` | Phase 3/9 | `project_dir` `message` `init_if_needed` | action(init/commit/skip) / commit_hash / changed_files |
| `git_push` | Phase 9 | `project_dir` `repo_url` `visibility` | pushed / repo_url / branch / ci_detected / recommended_flow / notes |

## 5. CI 仓库专项（重要）

**识别**：目标仓库 `.github/workflows/` 存在 `build.yml` 等 → 判定为 CI 仓库（`git_push` 返回 `ci_detected=true`）。

**行为**：push 到 `master`/`main` 会自动触发构建；构建成功可能**自动发 Release + 更新 tag**（UnrealMultiple/TShockPlugin 还会同步 ApmApi/论坛/Crowdin；Zykor-Club 的 Lint 会校验插件结构）。

**注意**：这类仓库通常要求：
- 插件放 `src/<插件名>/` 目录
- **不能提交 DLL/PDB**（构建产物）
- 可能要求 `manifest.json` / `README` / `template.targets`（Zykor-Club Lint 会校验）

推送前必须用 `check_csproj` 或目录结构核对，否则 CI 会挂。

**建议流程（`git_push` 检测到 CI 时的默认推荐）**：
1. fork 上游仓库
2. 本地在分支上开发（不改 master/main）
3. push 到 fork
4. 开 PR 到上游

若用户坚持直接推上游，必须征得同意并明确告知会触发 CI 构建 + 自动 Release。

## 6. 安全提醒

- **token 不入库**：不要把 GITHUB_TOKEN/GH_TOKEN 写进代码、`.gitignore` 之外的任何文件
- `.gitignore` 必须排除敏感文件（配置里的密钥、凭据）
- 推送前确认远程 URL 是预期目标（避免推到错误仓库）
