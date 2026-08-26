# GitHub 访问工具（对应 skill Phase 2 参考源获取）
# 作用：
#   search_repos    —— 搜索相似插件仓库，并校验其适配版本与当前目标版本是否匹配
#   read_remote_file—— 直接读取 GitHub 上某个文件的内容（不下载整包）
#   search_code     —— GitHub 代码搜索（需要 GITHUB_TOKEN 环境变量）
# 设计约束：所有仓库结果必须做「版本匹配校验」，避免参考了错误版本的代码。
import json
import os
import re
import sys

import requests

# 未提供 token 时无认证请求有速率限制（约 60 次/小时）；提供后提升到 5000/小时
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
HEADERS = {"Authorization": f"token {TOKEN}"} if TOKEN else {}
TIMEOUT = 15
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


def _get(url: str, params: dict = None) -> dict:
    resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


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
    for cand in candidates[:6]:  # 最多探测 6 个路径，避免 API 消耗过大
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


def _match_version(hint: str, target_tshock: str, target_terraria: str) -> str:
    """判断仓库版本提示与目标版本是否匹配。"""
    if not hint:
        return "unknown"  # 没读到版本信息，无法判断
    hint_low = hint.lower()
    verdicts = []
    if target_tshock:
        t = target_tshock.split(".")
        # 匹配主版本号（如目标 6.1.0，提示含 TShock 6.0 / 6.1 都算同主系列）
        major = t[0]
        if re.search(rf"tshock\s*{major}(\.| |$)", hint_low):
            verdicts.append("match")
        elif re.search(r"tshock\s*\d+", hint_low):
            verdicts.append("mismatch")
    if target_terraria:
        if target_terraria in hint_low:
            verdicts.append("match")
        elif re.search(r"1\.4\.5\.\d", hint_low):
            verdicts.append("mismatch")
    if not verdicts:
        return "unknown"
    return "match" if "mismatch" not in verdicts else "mismatch"


def search_repos(query: str, target_tshock: str = "", target_terraria: str = "") -> dict:
    """搜索 GitHub 相似插件仓库并校验版本匹配度（Phase 2 L2）。

    参数：
        query: 搜索关键词（如 "tshock plugin 签到"）
        target_tshock: 目标 TShock 版本（如 6.1.0），用于版本匹配校验
        target_terraria: 目标 Terraria 版本（如 1.4.5.6），用于版本匹配校验

    返回 JSON：repositories[{full_name/description/stars/version_hint/version_match}]。
    version_match: match（版本匹配）/ mismatch（版本不符，勿参考）/ unknown（无法判断）。
    """
    if not query:
        return {"error": "缺少参数 query"}
    try:
        data = _get(f"{API}/search/repositories", {"q": query, "sort": "stars", "per_page": 6})
        repos = []
        for item in data.get("items", [])[:6]:
            full = item["full_name"]
            probe = _probe_version(full)
            repos.append({
                "full_name": full,
                "description": (item.get("description") or "")[:120],
                "stars": item.get("stargazers_count", 0),
                "html_url": item["html_url"],
                "version_hint": probe["version_hint"],
                "version_match": _match_version(probe["version_hint"], target_tshock, target_terraria),
            })
        return {
            "repositories": repos,
            "hint": "优先参考 version_match=match 的仓库；mismatch 的仓库 API 已变，仅可看思路；unknown 需自行核对版本。",
        }
    except requests.RequestException as e:
        return {"error": f"GitHub API 请求失败：{e}。可设置 GITHUB_TOKEN 环境变量提升速率限制。"}


def read_remote_file(repo: str, path: str, ref: str = "HEAD") -> dict:
    """读取 GitHub 仓库中某个文件的内容（不下载整包，省流量）。

    参数：
        repo: 仓库 full_name（如 Pryaxis/TShock）
        path: 文件路径（如 TShockAPI/Commands.cs）
        ref: 分支/tag（默认 HEAD）

    返回 JSON：repo/path/ref/content（前 4000 字符）/truncated。
    """
    if not repo or not path:
        return {"error": "缺少参数 repo 或 path"}
    try:
        url = f"{RAW}/{repo}/{ref}/{path}"
        resp = requests.get(url, timeout=TIMEOUT)
        if resp.status_code == 404:
            return {"error": f"文件不存在：{repo}@{ref} 的 {path}（可能路径或 ref 错误）"}
        resp.raise_for_status()
        content = resp.text
        return {
            "repo": repo, "path": path, "ref": ref,
            "content": content[:4000], "truncated": len(content) > 4000,
        }
    except requests.RequestException as e:
        return {"error": f"读取失败：{e}"}


def search_code(query: str) -> dict:
    """GitHub 代码搜索（跨仓库找 API 用法示例）。

    注意：代码搜索 API 必须提供 GITHUB_TOKEN 环境变量，否则报错。

    参数：
        query: 搜索语句（如 "PacketTypes language:C#"）

    返回 JSON：results[{repository/path/url}]。
    """
    if not TOKEN:
        return {"error": "代码搜索需要认证：请设置 GITHUB_TOKEN 环境变量后重启 MCP server。"}
    if not query:
        return {"error": "缺少参数 query"}
    try:
        data = _get(f"{API}/search/code", {"q": query, "per_page": 8})
        results = [
            {"repository": item["repository"]["full_name"], "path": item["path"], "html_url": item["html_url"]}
            for item in data.get("items", [])[:8]
        ]
        return {"results": results, "hint": "结果里的文件可用 read_remote_file 读取内容。"}
    except requests.RequestException as e:
        return {"error": f"代码搜索失败：{e}"}


# 插件库检索的扫描上限：有 token 全扫（5000/h 限速充裕）；无 token 受匿名限速(60/h)约束取 50
MAX_README_SCAN = 500 if TOKEN else 50
MAX_RESULTS = 6


def search_plugin_library(query: str, repo: str = "UnrealMultiple/TShockPlugin",
                          target_tshock: str = "", target_terraria: str = "") -> dict:
    """在插件库仓库内检索相似插件（Phase 0 步骤 0.2）。

    参数：
        query: 关键词（如 "签到 礼包"，中英文均可）
        repo: 插件库仓库（默认 UnrealMultiple/TShockPlugin）
        target_tshock: 目标 TShock 版本（如 6.1.0），版本匹配校验
        target_terraria: 目标 Terraria 版本（如 1.4.5.6）

    返回 JSON：repo/stars/plugins[{name/description/match_context/version_hint/version_match}]。
    match_context 为命中依据（README 命中行或功能描述），供判断语义是否真相关。
    version_match: match（可参考）/ mismatch（需升级改造）/ unknown（自行核对）。
    """
    if not query:
        return {"error": "缺少参数 query"}
    try:
        info = _get(f"{API}/repos/{repo}")
        default_branch = info.get("default_branch", "HEAD")
        stars = info.get("stargazers_count", 0)

        tree = _get(f"{API}/repos/{repo}/git/trees/{default_branch}", {"recursive": "1"})
        items = tree.get("tree", [])
        # 插件目录：优先 src/<插件> 布局（UnrealMultiple/TShockPlugin 惯例），无 src 时回退顶层目录
        dirs = [i["path"] for i in items
                if i.get("type") == "tree" and i["path"].count("/") == 1 and i["path"].startswith("src/")]
        if not dirs:
            dirs = [i["path"] for i in items
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
            desc = _readme_summary(text) or d.split("/")[-1]
            # 命中上下文：README 命中取命中行，仅目录名命中取功能描述行，帮 AI 判断语义是否真相关
            ctx = _match_context_line(text, tokens) or desc
            probe = _probe_version(repo, subdir=d)
            plugins.append({
                "name": d.split("/")[-1],  # src/ 布局下去掉 src/ 前缀，仅显示插件名
                "description": desc[:120],
                "match_context": ctx[:80],
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


def _match_context_line(text: str, tokens: list) -> str:
    """返回 README 中首个命中关键词的行（截断 80 字符）；无命中返回空串。"""
    for line in text.splitlines():
        low = line.lower()
        if any(t in low for t in tokens):
            return line.strip()[:80]
    return ""


if __name__ == "__main__":
    # 调试：python github_access.py search <关键词> [TShock版本] [Terraria版本]
    mode = sys.argv[1] if len(sys.argv) > 1 else "search"
    q = sys.argv[2] if len(sys.argv) > 2 else ""
    if mode == "search":
        t2 = sys.argv[3] if len(sys.argv) > 3 else ""
        t3 = sys.argv[4] if len(sys.argv) > 4 else ""
        print(json.dumps(search_repos(q, t2, t3), ensure_ascii=False, indent=2))
    elif mode == "read":
        r = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(read_remote_file(q, r), ensure_ascii=False, indent=2))
    elif mode == "code":
        print(json.dumps(search_code(q), ensure_ascii=False, indent=2))
    elif mode == "library":
        r = sys.argv[3] if len(sys.argv) > 3 else "UnrealMultiple/TShockPlugin"
        t2 = sys.argv[4] if len(sys.argv) > 4 else ""
        t3 = sys.argv[5] if len(sys.argv) > 5 else ""
        print(json.dumps(search_plugin_library(q, r, t2, t3), ensure_ascii=False, indent=2))
