# mcp-server/tools/gh_comments.py
# GitHub 评论读取工具（封装 gh CLI）
# 作用：
#   read_github_comments —— 读取 GitHub 上 issue/PR 的各类评论：
#     - description  （issue/PR 标题 + 正文 + 状态）
#     - conversation（issue/PR 下的对话回复）
#     - review       （整体审查意见，含 approved / changes_requested 状态）
#     - code         （代码行评论 inline review comments，含文件路径与行号）
# 设计：全部通过子进程调用本机 gh CLI（gh api REST 端点，--paginate 自动翻页）。
# 独立可用：即使没有插件开发需求，也可以直接调用本工具做评论审核、查看、分析。
import json
import os
import re
import shutil
import subprocess
import sys

# 允许的 comment_type
ALLOWED_TYPES = ("all", "description", "conversation", "review", "code")

# 匹配 GitHub 评论页 URL：owner/repo + issues|pull|pulls + 编号
_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?]+)"
    r"/(?P<kind>issues|pull|pulls)/(?P<number>\d+)",
    re.IGNORECASE,
)

# 规范化 repo 参数时提取 owner/repo（兼容 https://github.com/owner/repo 形式）
_REPO_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s#?]+)/([^/\s#?]+)")


def _err(message: str, hint: str = "", fallback: str = "") -> dict:
    """统一错误格式：error 表示出错，hint 为排查建议，fallback 为降级路径。"""
    return {"error": message, "hint": hint, "fallback": fallback}


def _find_gh() -> str:
    """探测 gh 可执行文件路径：GH_EXECUTABLE > 常见安装路径 > PATH。找不到返回 None。"""
    candidates = []
    env_gh = os.environ.get("GH_EXECUTABLE", "")
    if env_gh:
        candidates.append(env_gh)
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates.append(os.path.join(local, "Programs", "gh", "bin", "gh.exe"))
        candidates.append(os.path.join(local, "Programs", "gh-cli", "bin", "gh.exe"))
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    if pf:
        candidates.append(os.path.join(pf, "GitHub CLI", "gh.exe"))
    if pf86:
        candidates.append(os.path.join(pf86, "GitHub CLI", "gh.exe"))
    candidates += [
        r"C:\Program Files\GitHub CLI\gh.exe",
        r"C:\Program Files (x86)\GitHub CLI\gh.exe",
        r"D:\GitHub CLI\gh.exe",
        "/usr/local/bin/gh",
        "/opt/homebrew/bin/gh",
        "/usr/bin/gh",
    ]
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return cand
    which = shutil.which("gh")
    return which


def _run_gh(*args: str, timeout: int = 60) -> tuple:
    """运行 gh 命令，返回 (returncode, stdout, stderr)。gh 不可用抛 RuntimeError。"""
    gh = _find_gh()
    if not gh:
        raise RuntimeError(
            "未找到 gh。请安装 GitHub CLI 或设置环境变量 GH_EXECUTABLE 指向 gh 可执行文件"
        )
    proc = subprocess.run(
        [gh] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _gh_api(repo_full: str, endpoint: str, paginate: bool = False):
    """gh api GET 单对象或数组（--paginate 自动翻页）。出错抛 RuntimeError。"""
    args = ["api", f"repos/{repo_full}/{endpoint}"]
    if paginate:
        args.append("--paginate")
    rc, out, err = _run_gh(*args)
    if rc != 0:
        raise RuntimeError(err or f"gh api 请求失败（exit {rc}）")
    return json.loads(out)


def _parse_url(url: str) -> dict:
    """解析 GitHub 评论页 URL → {owner, repo, number, kind}。解析失败返回 None。"""
    m = _URL_RE.match((url or "").strip())
    if not m:
        return None
    return {
        "owner": m.group("owner"),
        "repo": m.group("repo"),
        "number": m.group("number"),
        "kind": "pr" if m.group("kind") != "issues" else "issue",
    }


def _resolve_inputs(repo: str, number: str, url: str) -> tuple:
    """把 repo+number 或 url 归一化为 (repo_full, number, kind)。

    kind 在能由 URL 推断时给出；仅 repo+number 时为 ""（由调用方探测 issue 本体确定）。
    参数无效返回 (None, None, None)。
    """
    if url:
        parsed = _parse_url(url)
        if not parsed:
            return None, None, None
        return f"{parsed['owner']}/{parsed['repo']}", parsed["number"], parsed["kind"]
    if repo and number:
        repo_full = (repo or "").strip().strip("/")
        if repo_full.startswith("http"):
            m = _REPO_URL_RE.match(repo_full)
            if m:
                repo_full = f"{m.group(1)}/{m.group(2)}"
        repo_full = repo_full.rstrip(".git")
        num = str(number).strip()
        if repo_full and num.isdigit() and int(num) > 0:
            return repo_full, num, ""
    return None, None, None


def _norm_description(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "type": "description",
        "author": (item.get("user") or {}).get("login", ""),
        "author_association": item.get("author_association", ""),
        "title": item.get("title", ""),
        "state": item.get("state", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "body": item.get("body", ""),
    }


def _norm_conversation(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "type": "conversation",
        "author": (c.get("user") or {}).get("login", ""),
        "author_association": c.get("author_association", ""),
        "created_at": c.get("created_at", ""),
        "updated_at": c.get("updated_at", ""),
        "body": c.get("body", ""),
    }


def _norm_review(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "type": "review",
        "author": (r.get("user") or {}).get("login", ""),
        "state": r.get("state", ""),  # approved / changes_requested / commented / dismissed
        "submitted_at": r.get("submitted_at", ""),
        "body": r.get("body", ""),
        "commit_id": r.get("commit_id", ""),
    }


def _norm_code(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "type": "code",
        "author": (c.get("user") or {}).get("login", ""),
        "created_at": c.get("created_at", ""),
        "body": c.get("body", ""),
        "path": c.get("path", ""),
        "line": c.get("line"),
        "original_line": c.get("original_line"),
        "side": c.get("side", ""),
        "in_reply_to_id": c.get("in_reply_to_id"),
        "commit_id": c.get("commit_id", ""),
        "url": c.get("html_url", ""),
    }


def _auth_hint(msg: str) -> str:
    """根据 gh 报错给出认证/网络排查建议。"""
    if "401" in msg or "Bad credentials" in msg or "Unauthorized" in msg:
        return ("gh 认证失败。请运行 gh auth login 或设置 GH_TOKEN 环境变量后重试；"
                "可用 gh auth status 检查当前状态")
    if "403" in msg or "rate limit" in msg.lower():
        return ("API 限流或权限不足。稍后重试；或确认 token 具备仓库读取权限")
    return ("gh 调用失败。检查：1) gh 是否安装并认证（gh auth status）；"
            "2) 仓库/编号是否正确；3) 网络是否可达 api.github.com")


def read_github_comments(repo: str = "", number: str = "", url: str = "",
                         comment_type: str = "all") -> dict:
    """读取 GitHub issue/PR 的评论（封装 gh CLI）。

    支持对话评论 / Review 总结 / 代码行评论 / issue 正文描述。
    独立可用：即使没有插件开发需求，也可以直接调用做评论审核、查看、分析。

    参数：
        repo: 仓库 full_name（如 owner/repo）；与 number 配对使用，与 url 二选一
        number: issue/PR 编号（正整数）
        url: 评论页 URL（如 https://github.com/owner/repo/pull/5）；优先于 repo+number
        comment_type: all/description/conversation/review/code（默认 all 全部）

    返回 JSON：repo/number/kind/total/comment_type/comments[{id/type/author/...}]。
    """
    repo_full, num, kind = _resolve_inputs(repo, number, url)
    if not repo_full or not num:
        return _err(
            "参数不足",
            "用法一：read_github_comments(url=\"https://github.com/owner/repo/pull/5\")；"
            "用法二：read_github_comments(repo=\"owner/repo\", number=5)",
            "",
        )

    ct = (comment_type or "all").strip().lower()
    if ct not in ALLOWED_TYPES:
        return _err(
            f"comment_type 仅支持 {list(ALLOWED_TYPES)}",
            "用法：read_github_comments(url=..., comment_type=\"all\")",
            "",
        )

    try:
        # 1) 取 issue/PR 本体：PR 也是 issue，含 pull_request 字段 → 判定 kind
        item = _gh_api(repo_full, f"issues/{num}")
        if not isinstance(item, dict):
            return _err("读取 issue/PR 本体失败，返回格式异常", "", "")
        if "pull_request" in item:
            kind = "pr"
        else:
            kind = "issue"

        comments = []
        if ct in ("all", "description"):
            comments.append(_norm_description(item))
        if ct in ("all", "conversation"):
            for c in _gh_api(repo_full, f"issues/{num}/comments", paginate=True):
                comments.append(_norm_conversation(c))
        if kind == "pr":  # 只有 PR 才有 review 总结与代码行评论（issue 调 pulls 端点会 404）
            if ct in ("all", "review"):
                for r in _gh_api(repo_full, f"pulls/{num}/reviews", paginate=True):
                    comments.append(_norm_review(r))
            if ct in ("all", "code"):
                for c in _gh_api(repo_full, f"pulls/{num}/comments", paginate=True):
                    comments.append(_norm_code(c))

        # 按时间升序排序（review 用 submitted_at，其余用 created_at；无时间戳置前）
        def _ts(c):
            return c.get("created_at") or c.get("submitted_at") or ""

        comments.sort(key=_ts)

        return {
            "repo": repo_full,
            "number": num,
            "kind": kind,
            "total": len(comments),
            "comment_type": ct,
            "comments": comments,
            "note": "由 gh CLI 封装读取；如需逐条回复/处理，请用对应 gh 命令或浏览器操作。",
        }
    except RuntimeError as e:
        msg = str(e)
        if "404" in msg or "Not Found" in msg:
            return _err(f"未找到 {repo_full} 的 issue/PR #{num}（404）",
                        "确认仓库名与编号是否正确，或该编号是 issue 还是 PR", "")
        return _err(msg, _auth_hint(msg), "")
    except json.JSONDecodeError:
        return _err("gh api 返回内容不是合法 JSON",
                    "检查 gh 是否已认证：gh auth status；或手动运行 gh api 看原始输出", "")
    except subprocess.TimeoutExpired:
        return _err("gh 命令超时", "网络较慢时可重试；或检查 gh 是否卡在等待认证输入", "")


if __name__ == "__main__":
    # 调试：python gh_comments.py <url|repo> [number]
    if len(sys.argv) >= 2:
        if sys.argv[1].startswith("http"):
            arg_url = sys.argv[1]
            print(json.dumps(read_github_comments(url=arg_url), ensure_ascii=False, indent=2))
        else:
            num = sys.argv[2] if len(sys.argv) > 2 else ""
            print(json.dumps(read_github_comments(repo=sys.argv[1], number=num),
                             ensure_ascii=False, indent=2))
    else:
        print(json.dumps(read_github_comments(), ensure_ascii=False, indent=2))
