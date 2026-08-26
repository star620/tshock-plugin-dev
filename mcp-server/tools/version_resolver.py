# 版本解析工具（对应 skill Phase 1）
# 作用：动态解析「Terraria ↔ TShock ↔ .NET TFM ↔ NuGet 包版本」四元组，并做门禁判断。
# 数据来源：NuGet 官方 API + GitHub Releases API（与 references/02-版本解析与兼容性.md 一致）。
import json
import re
from datetime import datetime

import requests

# NuGet 上 TShock 包的版本列表
NUGET_INDEX_URL = "https://api.nuget.org/v3-flatcontainer/tshock/index.json"
# GitHub 上 TShock 的发布列表（每页 10 条足够覆盖最新几个版本）
GITHUB_RELEASES_URL = "https://api.github.com/repos/Pryaxis/TShock/releases?per_page=10"

# 内置 TFM 映射（6 系列 = net9.0；最终以还原包后 lib/ 目录名为准）
TFM_BY_MAJOR = {6: "net9.0"}

# 网络请求超时（秒）
TIMEOUT = 15


def _get_json(url: str) -> dict:
    """GET 请求并返回 JSON；失败抛异常，由上层转成错误信息。"""
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _stable_versions(all_versions: list) -> list:
    """过滤掉预发布版本（NuGet 预发布版本号含 '-'）。"""
    return [v for v in all_versions if "-" not in v]


def _parse_terraria_from_release(name: str) -> str:
    """从发布名提取 Terraria 版本，如 'TShock 6.1 for Terraria 1.4.5.6' → '1.4.5.6'。"""
    m = re.search(r"Terraria\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", name or "")
    return m.group(1) if m else ""


def resolve(terraria_version: str = "") -> dict:
    """解析版本四元组。

    参数：
        terraria_version: 用户目标的 Terraria 版本；留空表示取最新稳定版。

    返回：
        JSON 字符串，含 terraria/tshock/tfm/nuget_version/gate_status/experimental_notes/sources。
    """
    try:
        # 1. 取 NuGet 稳定版本列表
        nuget_versions = _stable_versions(_get_json(NUGET_INDEX_URL).get("versions", []))
        if not nuget_versions:
            return {"error": "NuGet 返回空版本列表"}

        # 2. 取 GitHub 发布列表，建立「Terraria 版本 ↔ TShock 版本」映射
        releases = _get_json(GITHUB_RELEASES_URL)
        mapping = []  # 每项 {terraria, tshock}
        for rel in releases:
            tshock = (rel.get("tag_name") or "").lstrip("v")
            terraria = _parse_terraria_from_release(rel.get("name"))
            if tshock and terraria:
                mapping.append({"terraria": terraria, "tshock": tshock})

        # 3. 匹配目标版本
        target = None
        if terraria_version:
            target = next((m for m in mapping if m["terraria"] == terraria_version), None)
            if target is None:
                # 门禁：该 Terraria 版本没有对应的已发布 TShock
                return {
                    "terraria": terraria_version,
                    "tshock": None,
                    "tfm": None,
                    "nuget_version": None,
                    "gate_status": "blocked",
                    "experimental_notes": (
                        "TShock 尚未发布支持该 Terraria 版本。无法编写插件（无编译引用/无官方服务器），"
                        "除非用户提供已跟进该版本的本地 TShock 源码。"
                        f"当前已发布映射：{mapping}"
                    ),
                    "sources": {"nuget": NUGET_INDEX_URL, "github": GITHUB_RELEASES_URL},
                }
        else:
            # 取最新：GitHub 映射最新者优先，否则 NuGet 最高版本
            if mapping:
                target = mapping[0]
            else:
                target = {"terraria": "", "tshock": nuget_versions[-1]}

        tshock = target["tshock"]
        # TShock 版本号可能形如 6.1.0（tag），也可能是 6.1；统一补足三位
        tshock_parts = tshock.split(".")
        while len(tshock_parts) < 3:
            tshock_parts.append("0")
        tshock_full = ".".join(tshock_parts)

        # 4. 确定 TFM 与 NuGet 包版本
        major = int(tshock_parts[0])
        tfm = TFM_BY_MAJOR.get(major)
        if tfm is None:
            tfm = "未知（请以还原包后 lib/ 目录名为准）"
        nuget_version = tshock_full if tshock_full in nuget_versions else nuget_versions[-1]

        # 实验性提示：1.4.5.7 / 1.4.5.8 等新版本
        experimental = ""
        if target["terraria"] in ("1.4.5.7", "1.4.5.8"):
            experimental = "目标版本处于实验性阶段（OTAPI/TShock 可能未完整适配），不建议生产使用。"

        return {
            "terraria": target["terraria"],
            "tshock": tshock_full,
            "tfm": tfm,
            "nuget_version": nuget_version,
            "gate_status": "ok",
            "experimental_notes": experimental,
            "resolved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sources": {"nuget": NUGET_INDEX_URL, "github": GITHUB_RELEASES_URL},
        }
    except requests.RequestException as e:
        return {"error": f"网络请求失败：{e}。请检查网络后重试，或降级为手动流程（references/02）。"}
    except Exception as e:  # noqa: BLE001 —— 工具层兜底，避免崩溃
        return {"error": f"解析失败：{e}"}


if __name__ == "__main__":
    # 命令行直接调试：python version_resolver.py [terraria_version]
    import sys

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(resolve(arg), ensure_ascii=False, indent=2))
