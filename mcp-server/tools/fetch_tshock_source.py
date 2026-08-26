# TShock 源码获取工具（对应 skill Phase 2 L4）
# 作用：下载指定版本 TShock 源码（codeload zip），解压到本地缓存目录；可选 grep 定位 API 符号。
# 注意：属于「联网下载」操作，调用前必须先征得用户同意（skill 硬性规则 2）。
import json
import os
import re
import sys
import zipfile

import requests

# 缓存根目录（Windows 用 %LOCALAPPDATA%，其他平台用 ~/.cache）
CACHE_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.cache")),
    "tshock-dev-cache",
)

TIMEOUT = 60


def _err(message: str, hint: str = "", fallback: str = "") -> dict:
    """统一错误格式：error 表示出错，hint 为排查建议，fallback 为降级路径。"""
    return {"error": message, "hint": hint, "fallback": fallback}


def _codeload_url(version: str) -> str:
    """TShock 源码 zip 的 codeload 地址（tag 形如 6.1.0）。"""
    return f"https://codeload.github.com/Pryaxis/TShock/zip/refs/tags/{version}"


def fetch(version: str = "", api_symbol: str = "") -> dict:
    """下载 TShock 源码并（可选）定位 API 符号。

    参数：
        version: TShock 版本（如 6.1.0）；留空则提示需要版本号
        api_symbol: 要 grep 的符号名（如 PacketTypes、NetMessage）；留空只下载不解压检索

    返回：
        JSON 字符串，含 version/source_dir/downloaded/matched_symbols/error。
    """
    if not version:
        return _err("缺少参数 version", "先用 resolve_version 工具解析出目标 TShock 版本", "")

    dest_dir = os.path.join(CACHE_ROOT, f"tshock-{version}")
    zip_path = os.path.join(CACHE_ROOT, f"tshock-{version}.zip")

    # 已存在则跳过下载
    if os.path.isdir(dest_dir):
        source_dir = dest_dir
        downloaded = False
    else:
        try:
            os.makedirs(CACHE_ROOT, exist_ok=True)
            resp = requests.get(_codeload_url(version), timeout=TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 解压（zip 内含一层 tshock-<version>/ 目录）
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(CACHE_ROOT)
            os.remove(zip_path)
            downloaded = True

            # 定位真正的源码根目录
            inner = [d for d in os.listdir(CACHE_ROOT) if d.startswith(f"tshock-{version}") and os.path.isdir(os.path.join(CACHE_ROOT, d))]
            source_dir = os.path.join(CACHE_ROOT, inner[0]) if inner else dest_dir
        except requests.RequestException as e:
            return _err(f"下载失败：{e}", "检查网络后重试", "按 references/03-参考源码获取.md 手动下载")
        except zipfile.BadZipFile:
            return _err(f"下载文件损坏（{zip_path}）", "删除缓存目录后重新下载", "")

    # 可选：grep API 符号定义
    matched = []
    if api_symbol and os.path.isdir(source_dir):
        for root, _, files in os.walk(source_dir):
            # 只看 .cs 源码
            cs_files = [f for f in files if f.endswith(".cs")]
            for fn in cs_files:
                fp = os.path.join(root, fn)
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        for ln_no, line in enumerate(f, 1):
                            # 匹配符号定义（类/枚举/方法声明），排除注释行
                            if re.search(rf"\b{re.escape(api_symbol)}\b", line) and not line.strip().startswith(("//", "*", "/*")):
                                matched.append({
                                    "file": os.path.relpath(fp, source_dir),
                                    "line": ln_no,
                                    "snippet": line.strip()[:200],
                                })
                                break  # 每文件只取首个命中
                except OSError:
                    continue
            if len(matched) >= 20:  # 限制结果量
                break

    return {
        "version": version,
        "source_dir": source_dir,
        "downloaded": downloaded,
        "matched_symbols": matched[:20] if matched else [],
        "hint": "matched_symbols 为空时，符号可能在 TerrariaServerAPI 子模块（.gitmodules 中查找），需另行下载。",
    }


if __name__ == "__main__":
    # 命令行调试：python fetch_tshock_source.py [版本] [符号]
    v = sys.argv[1] if len(sys.argv) > 1 else ""
    s = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(fetch(v, s), ensure_ascii=False, indent=2))
