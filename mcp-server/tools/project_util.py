# 项目辅助工具（对应 skill Phase 3/1）
# 作用：
#   check_csproj     —— 检查插件工程 csproj 的 TFM 与 TShock 包版本是否正确
#   find_test_server —— 探测本地测试服务器目录
import json
import os
import re
import sys


def check_csproj(csproj_path: str) -> dict:
    """检查 csproj 的 TargetFramework 与 TShock 包版本（Phase 3）。

    参数：
        csproj_path: 插件工程 csproj 绝对路径

    返回 JSON：target_framework/tshock_package/tfm_major_warning/issues。
    """
    if not csproj_path:
        return {"error": "缺少参数 csproj_path"}
    if not os.path.isfile(csproj_path):
        return {"error": f"文件不存在：{csproj_path}"}

    try:
        with open(csproj_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return {"error": f"读取失败：{e}"}

    tfm = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", text)
    pkg = re.search(r"PackageReference\s+Include=\"TShock\"\s+Version=\"([^\"]+)\"", text)

    issues = []
    if not tfm:
        issues.append("缺少 <TargetFramework>")
    if not pkg:
        issues.append("缺少 PackageReference TShock（必须引用官方 TShock 包）")
    else:
        # 6.x 系列应为 net9.0；非 net9.0 提示（与 references/02 一致）
        if tfm and "net9.0" not in tfm.group(1):
            issues.append(f"TFM {tfm.group(1)} 与 TShock 6.x 的 net9.0 不一致，可能编译失败")

    return {
        "target_framework": tfm.group(1) if tfm else "",
        "tshock_package": pkg.group(1) if pkg else "",
        "issues": issues,
        "hint": "issue 为空即为合规配置。",
    }


def find_test_server(search_root: str = "") -> dict:
    """探测本地测试服务器目录（Phase 1）。

    参数：
        search_root: 搜索根目录；留空则探测常见位置（桌面/插件开发目录）

    返回 JSON：found（true/false）/server_dir/server_exe。
    """
    candidates = []
    if search_root:
        candidates.append(search_root)
    else:
        # 常见位置（Windows）
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        candidates += [
            os.path.join(desktop, "插件开发"),
            desktop,
            os.path.join(os.path.expanduser("~"), "TShock"),
            r"D:\TShock", r"C:\TShock",
        ]

    for root in candidates:
        if not os.path.isdir(root):
            continue
        # 深度限制为 3 层，避免全局搜索过慢
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth > 3:
                dirnames.clear()
                continue
            if "TShock.Server.exe" in filenames:
                return {
                    "found": True,
                    "server_dir": dirpath,
                    "server_exe": os.path.join(dirpath, "TShock.Server.exe"),
                    "plugins_dir": os.path.join(dirpath, "ServerPlugins"),
                    "hint": "Phase 7 部署时把 DLL 复制到 ServerPlugins/ 并重启。",
                }
    return {"found": False, "hint": "未找到测试服务器。可用 fetch_release_asset 下载官方发布包作测试服务器。"}


if __name__ == "__main__":
    # 调试：python project_util.py csproj <路径> | server [根目录]
    mode = sys.argv[1] if len(sys.argv) > 1 else "server"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    if mode == "csproj":
        print(json.dumps(check_csproj(arg), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(find_test_server(arg), ensure_ascii=False, indent=2))
