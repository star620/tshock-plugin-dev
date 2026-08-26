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
