#!/usr/bin/env python3
"""校验 SKILL.md 中反引号引用的文件是否全部存在（CI 文档结构门禁）。

SKILL.md 新增/改名引用文件后，若漏建文件，CI 会在此标红。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"

# 匹配 SKILL.md 反引号中的相对路径引用（支持中文文件名）
PATH_RE = re.compile(r"`([A-Za-z0-9_\-\u4e00-\u9fa5./]+\.(?:md|tpl|cs|py|txt|json))`")


def resolve(ref: str) -> pathlib.Path | None:
    """解析引用路径：带目录前缀按原路径，裸文件名按扩展名在已知目录中查找。"""
    candidates = [ROOT / ref]
    if "/" not in ref:
        # SKILL.md 里引用 references/ 与 templates/ 下的文件时经常省略前缀
        candidates.append(ROOT / "references" / ref)
        candidates.append(ROOT / "templates" / ref)
    for p in candidates:
        if p.exists():
            return p
    return None


def main() -> int:
    text = SKILL.read_text(encoding="utf-8")
    refs, seen = [], set()
    for m in PATH_RE.finditer(text):
        ref = m.group(1)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    missing = [r for r in refs if resolve(r) is None]
    if missing:
        print("缺失引用文件：")
        for r in missing:
            print(" -", r)
        return 1
    print(f"校验通过：SKILL.md 共引用 {len(refs)} 个文件，全部存在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
