# 设计文档：tshock-plugin-dev skill 增加 GitHub 评论读取能力（gh 封装）

- 日期：2026-08-28
- 状态：已批准（工具形态 + 输入方式确认）
- 关联 skill：`tshock-plugin-dev`

## 1. 背景与目标

合作开发者在 issue / PR / 代码行上留下的评论，AI 之前无法直接读取（需要用户手动粘贴）。本设计为 skill/mcp 增加**读取 GitHub 评论**的能力，封装本机已安装并认证的 `gh` CLI，让 AI 能直接读取、审核、分析他人评论。

**独立可用**：该工具不依赖插件开发流程，即使没有开发插件的需求，也可以单独调用做评论审核、查看、分析等通用工作。

## 2. 支持的评论类型

| 类型 | 端点 | 说明 |
|---|---|---|
| 描述（issue/PR 正文） | `/repos/{o}/{r}/issues/{n}` | 标题 + 正文 + 状态，作为首条上下文 |
| 对话评论 | `/repos/{o}/{r}/issues/{n}/comments` | issue/PR 下的对话回复（PR 也是 issue） |
| Review 总结 | `/repos/{o}/{r}/pulls/{n}/reviews` | 整体审查意见，含 state（approved / changes_requested / commented） |
| 代码行评论 | `/repos/{o}/{r}/pulls/{n}/comments` | inline code comments，含 path / line / side / in_reply_to_id |

## 3. 工具设计（单个统一工具）

新增 `mcp-server/tools/gh_comments.py`，在 `server.py` 注册 1 个工具。

### `read_github_comments(repo="", number="", url="", comment_type="all")`

**输入（二选一）**：
- `url`：完整评论页 URL（`https://github.com/owner/repo/pull/5`、`.../issues/5`），自动解析 kind
- `repo` + `number`：`repo="owner/repo"`、`number=5`，通过探测 issue 本体自动判断 issue/pr

**comment_type**：`all`（默认）/ `description` / `conversation` / `review` / `code`

**返回 JSON**：

```
repo / number / kind(issue|pr) / total / comment_type
comments: [{ id / type(description|conversation|review|code)
             author / author_association / created_at / updated_at / submitted_at
             body / title / state
             path / line / original_line / side / in_reply_to_id / commit_id }]
```

- 全部按时间升序排序，description 置顶
- `gh api` 一律带 `--paginate` 自动翻页
- gh 未安装 / 未认证 / 404 / 限流 → 返回 `error` + 明确 `hint`

**gh 路径探测**（沿用 git_manage 风格）：`GH_EXECUTABLE` 环境变量 > 常见安装路径（`%LOCALAPPDATA%\Programs\gh\bin\gh.exe`、`%LOCALAPPDATA%\Programs\gh-cli\bin\gh.exe`、`C:\Program Files\GitHub CLI\gh.exe`、macOS/Linux 常见路径）> `shutil.which("gh")`。

**认证**：gh 用 GH_TOKEN / gh auth login 的凭据，`gh auth status` 可验证。

## 4. references/13-评论读取.md 文档

新增参考文档，结构：
1. **目的与独立可用性**：无需插件开发场景，可直接做评论审核/查看/分析
2. **支持场景与评论类型对照**
3. **gh 安装与认证**：安装命令、`gh auth login`、`gh auth status`
4. **MCP 工具调用对照**：`read_github_comments` 参数、返回字段、示例
5. **gh 命令速查（兜底）**：`gh pr view --comments`、`gh issue view --comments`、`gh api` 各端点
6. **常见错误**：gh 未装 / 未认证 / 404 / 限流 / 中文路径

## 5. SKILL.md 同步修改

- 参考文档索引表加 `references/13-评论读取.md`
- Phase 9（交付/收尾）：收到合作者 review comment 或 PR 未通过时，先 `read_github_comments` 读取全部评论再逐条处理
- README 工具列表更新

## 6. 测试

新增 `mcp-server/tests/test_gh_comments.py`（mock `_gh_api` / `_find_gh`）：
- URL 解析：issue / pull / pulls / 带查询参数 / 非法 URL
- repo+number 输入与 URL 优先级
- kind 探测（item 含 pull_request 字段 → pr）
- 全类型聚合 + 排序；comment_type 过滤
- 错误：参数不足 / gh 未装 / comment_type 非法 / JSON 解析失败

跑通现有全部测试：`python -m unittest discover mcp-server/tests`。

## 7. 涉及文件清单

| 文件 | 动作 |
|---|---|
| `docs/superpowers/specs/2026-08-28-gh-comments-design.md` | 新增（本文档） |
| `mcp-server/tools/gh_comments.py` | 新增（工具实现 + gh 路径探测） |
| `mcp-server/server.py` | 修改（注册 `read_github_comments`） |
| `mcp-server/tests/test_gh_comments.py` | 新增 |
| `references/13-评论读取.md` | 新增 |
| `SKILL.md` | 修改（Phase 9 + 索引表） |
| `README.md` | 修改（工具列表） |
