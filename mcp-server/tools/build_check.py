# 编译检查工具（对应 skill Phase 6）
# 作用：执行 dotnet build / test，解析输出中的错误码，并对照内置速查表给出修复建议。
# 错误码速查表与 references/10-排错手册.md 保持一致。
import json
import re
import subprocess
import sys

# 编译错误码速查表（与 10-排错手册.md 编译类错误一致）
ERROR_TIPS = {
    "CS0117": "类型不包含定义：成员可能定义在未下载的子模块源码里，或 API 已改名/移除。读 .gitmodules 下载对应源码后 grep 确认签名。",
    "CS1061": "类型不包含成员：同上，多半是 API 在新版本改名。对照 L1/L3 参考源核实签名。",
    "CS0246": "找不到类型/命名空间：NuGet 包版本与代码不匹配，或 csproj 缺引用。核对 PackageReference TShock 版本 = 目标 TShock 版本。",
    "CS0234": "命名空间不存在：用了目标版本不存在的 API/命名空间。对照参考源换公开 API。",
    "CS0012": "类型定义在不同程序集：bin/obj 残留旧版本 OTAPI/TShockAPI 引用，或同时引用多个版本。dotnet clean 后重新还原。",
    "CS0103": "名称不存在：Hook 点 API 已变更。查询对应版本的正确 API 名（见 06-TShockAPI速查）。",
    "NU1101": "找不到 NuGet 包：包源配置错误或包不存在。dotnet nuget list source 确认 nuget.org 可用，或切换镜像源。",
    "NU1701": "包兼容性警告：TShock 包 TFM 与项目 TFM 不一致。把项目 TFM 改为包 lib/ 目录一致的 TFM。",
    "NU1603": "包版本降级警告：引用版本与依赖链要求不一致。固定 PackageReference 版本。",
}


def _parse_build_output(text: str) -> dict:
    """从 build 输出中提取错误码与建议。"""
    errors, warnings = [], []
    for code in ERROR_TIPS:
        matches = re.findall(rf"error\s+({code})\s*:", text, re.IGNORECASE)
        for _ in matches:
            errors.append({"code": code, "suggestion": ERROR_TIPS[code]})
        for _ in re.findall(rf"warning\s+({code})\s*:", text, re.IGNORECASE):
            warnings.append({"code": code, "suggestion": ERROR_TIPS[code]})

    # 去重（同一错误码可能多次出现）
    def dedup(items):
        seen, out = set(), []
        for item in items:
            key = item["code"]
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    return {"errors": dedup(errors), "warnings": dedup(warnings)}


def check(csproj_path: str, run_tests: bool = False) -> dict:
    """编译并解析结果。

    参数：
        csproj_path: 插件工程 csproj 的绝对路径
        run_tests: 是否同时运行 dotnet test

    返回：
        JSON 字符串，含 success/exit_code/errors/warnings/output_tail。
    """
    if not csproj_path:
        return {"error": "缺少参数 csproj_path"}

    # 1. 编译
    build = subprocess.run(
        ["dotnet", "build", "-c", "Release", csproj_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    output = build.stdout + build.stderr
    parsed = _parse_build_output(output)

    # 2. 可选跑测试
    test_result = None
    if run_tests:
        test = subprocess.run(
            ["dotnet", "test", csproj_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        test_result = {
            "exit_code": test.returncode,
            "passed": "Passed!" in test.stdout,
            "summary": [ln for ln in test.stdout.splitlines() if "Passed" in ln or "Failed" in ln][:5],
        }

    success = build.returncode == 0 and not parsed["errors"] and (test_result is None or test_result["passed"])

    # 3. 输出尾部（最多 20 行，帮助人工判断）
    tail = [ln.strip() for ln in output.splitlines() if ln.strip()][-20:]

    return {
        "success": success,
        "exit_code": build.returncode,
        "errors": parsed["errors"],
        "warnings": parsed["warnings"],
        "test": test_result,
        "output_tail": tail,
        "hint": "0 错误 0 警告为通过标准；有错误请按 suggestion 修复后重跑。",
    }


if __name__ == "__main__":
    # 命令行调试：python build_check.py <csproj路径> [--test]
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    do_test = "--test" in sys.argv
    print(json.dumps(check(path, do_test), ensure_ascii=False, indent=2))
