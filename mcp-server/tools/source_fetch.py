# TShock 生态资源获取工具（对应 skill Phase 2 L4）
# 作用：
#   fetch_terrariaapi   —— 下载 TerrariaServerAPI 子模块源码（CS0117 报错的根源通常在这里）
#   fetch_release_asset —— 下载 TShock 发布包 zip（自动准备测试服务器）
#   list_submodules     —— 解析 TShock 源码 .gitmodules，列出子模块仓库
# 注意：属于「联网下载」操作，调用前必须先征得用户同意（skill 硬性规则 2）。
import json
import os
import re
import sys
import time
import zipfile

import requests

# 与 fetch_tshock_source.py 共用缓存目录
CACHE_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.cache")),
    "tshock-dev-cache",
)
TIMEOUT = 60
API = "https://api.github.com"


def _err(message: str, hint: str = "", fallback: str = "") -> dict:
    """统一错误格式：error 表示出错，hint 为排查建议，fallback 为降级路径。"""
    return {"error": message, "hint": hint, "fallback": fallback}


def _get_json(url: str, retries: int = 2) -> dict:
    """GET 并返回 JSON；瞬时失败自动重试 retries 次，仍失败抛异常。"""
    last = None
    for i in range(retries + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last = e
            if i == retries:
                raise
            time.sleep(1)
    raise last  # 理论上不可达，仅为类型提示


def _extract_zip(zip_path: str, dest_dir: str) -> str:
    """解压 zip 到目标目录，返回真实源码根目录。"""
    os.makedirs(CACHE_ROOT, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(CACHE_ROOT)
    inner = [d for d in os.listdir(CACHE_ROOT)
             if d.startswith(os.path.basename(dest_dir)) and os.path.isdir(os.path.join(CACHE_ROOT, d))]
    return os.path.join(CACHE_ROOT, inner[0]) if inner else dest_dir


def fetch_terrariaapi(version: str = "") -> dict:
    """下载 TerrariaServerAPI 子模块源码。

    参数：
        version: 目标 TShock 版本（可选，用于下载对应 tag；留空取默认分支）

    返回 JSON：source_dir/downloaded/hint。
    """
    # TShock 的 .gitmodules 指向的 TerrariaServerAPI 已更名/重定向为 Pryaxis/TSAPI（默认分支 general-devel）
    repo = "Pryaxis/TSAPI"
    if version:
        url = f"https://codeload.github.com/{repo}/zip/refs/tags/{version}"
    else:
        url = f"https://codeload.github.com/{repo}/zip/refs/heads/general-devel"
    dest_dir = os.path.join(CACHE_ROOT, f"terrariaapi-{version or 'general-devel'}")
    if os.path.isdir(dest_dir):
        return {"version": version or "general-devel", "source_dir": dest_dir, "downloaded": False}

    zip_path = os.path.join(CACHE_ROOT, f"terrariaapi-{version or 'general-devel'}.zip")
    try:
        resp = requests.get(url, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        source_dir = _extract_zip(zip_path, dest_dir)
        os.remove(zip_path)
        return {"version": version or "general-devel", "source_dir": source_dir, "downloaded": True,
                "hint": "该仓库定义 TerrariaApi.Server 类型（如 PacketTypes），可在此 grep 签名。"}
    except requests.RequestException as e:
        return {"error": f"下载失败：{e}。若 tag 不存在，可留空 version 用默认分支。"}


def fetch_release_asset(version: str = "", platform: str = "win-x64") -> dict:
    """下载 TShock 官方发布包 zip（测试服务器用）。

    参数：
        version: TShock 版本（如 6.1.0）；留空取最新稳定版
        platform: 平台（win-x64 / linux-x64 / osx-x64），默认 win-x64

    返回 JSON：version/asset_name/save_path/size_mb。
    """
    try:
        if version:
            data = requests.get(f"{API}/repos/Pryaxis/TShock/releases/tags/{version}",
                                timeout=TIMEOUT).json()
        else:
            data = requests.get(f"{API}/repos/Pryaxis/TShock/releases/latest", timeout=TIMEOUT).json()
        if "assets" not in data:
            return {"error": f"找不到版本 {version or 'latest'} 的发布信息：{data.get('message', '未知错误')}"}

        asset = next((a for a in data["assets"] if platform in (a.get("name") or "")), None)
        if asset is None:
            names = [a.get("name") for a in data["assets"]]
            return {"error": f"未找到 {platform} 资产。可用资产：{names}"}

        save_path = os.path.join(CACHE_ROOT, asset["name"])
        if not os.path.exists(save_path):
            os.makedirs(CACHE_ROOT, exist_ok=True)
            resp = requests.get(asset["browser_download_url"], timeout=TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

        return {
            "version": data.get("tag_name", version),
            "asset_name": asset["name"],
            "save_path": save_path,
            "size_mb": round(asset.get("size", 0) / 1024 / 1024, 1),
            "hint": "用 save_path 解压到测试服务器目录即可（需先征得用户同意）。",
        }
    except requests.RequestException as e:
        return {"error": f"下载失败：{e}"}


def list_submodules(source_dir: str = "") -> dict:
    """解析 TShock 源码根目录的 .gitmodules，列出子模块仓库。

    参数：
        source_dir: TShock 源码目录（来自 fetch_source 的 source_dir）

    返回 JSON：submodules[{path/url/description}]。
    """
    if not source_dir:
        return _err("缺少参数 source_dir", "用法：list_submodules(source_dir)，目录来自 fetch_source 结果", "")
    gitmodules = os.path.join(source_dir, ".gitmodules")
    if not os.path.isfile(gitmodules):
        return _err(f"{gitmodules} 不存在", "codeload zip 通常不含子模块，需按 .gitmodules 里的 URL 单独下载", "")
    try:
        with open(gitmodules, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return _err(f"读取失败：{e}", "确认文件存在且可读", "")

    subs = []
    for m in re.finditer(r"\[submodule \"([^\"]+)\"\]", text):
        path = m.group(1)
        url_m = re.search(rf"\[submodule \"{re.escape(path)}\"\][^[]*?url\s*=\s*([^\s]+)", text, re.S)
        subs.append({"path": path, "url": url_m.group(1) if url_m else ""})
    return {"submodules": subs, "hint": "下载时把 url 的 .git 去掉，用 codeload zip 即可。"}


if __name__ == "__main__":
    # 调试：python source_fetch.py submodules <源码目录>
    mode = sys.argv[1] if len(sys.argv) > 1 else "submodules"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    if mode == "terrariaapi":
        print(json.dumps(fetch_terrariaapi(arg), ensure_ascii=False, indent=2))
    elif mode == "release":
        print(json.dumps(fetch_release_asset(arg), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(list_submodules(arg), ensure_ascii=False, indent=2))
