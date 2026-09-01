"""Find facts written in more than one place.

Five bugs in this project have had one shape: a value or a rule stated twice, the two copies
drifting, and the failure appearing far from either. The version pin lived in three files;
the torch pin in two; "what counts as a delta" in analysis and database; the ASR
short-text rule briefly in the segment gate and the chapter gate; and publish_with_review
named a branch instead of reading the verdict that branch had already set.

None of those were visible by reading one file. This reads all of them and reports:

- **literals**: the same non-trivial number or string assigned to differently named
  module-level constants, which is how a pin drifts;
- **thresholds**: comparisons against the same bare number in several modules, which is a
  policy nobody named;
- **codes**: string literals that look like warning or failure codes and appear in more
  files than the module that defines them.

It is an advisor, not a gate. Plenty of duplication is fine - two modules may legitimately
both cap something at 1.0. It exists so a human looks, which is exactly what nobody did the
five previous times.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

# Numbers too common to mean anything: bounds, identities, unit conversions, small counts.
UNREMARKABLE = {0, 1, 2, 3, 4, 8, 10, 16, 24, 32, 60, 64, 100, 128, 256, 1000, 1024}
UNREMARKABLE_FLOATS = {0.0, 0.5, 1.0, 2.0, 100.0}
CODE_MIN_LENGTH = 8


def _module_constants(tree: ast.AST) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                found[target.id] = node.value
    return found


def _literal(node: ast.expr) -> object | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        if isinstance(node.value, bool):
            return None
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return -node.operand.value
    return None


def _interesting(value: object) -> bool:
    if isinstance(value, str):
        return len(value) >= CODE_MIN_LENGTH
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value not in UNREMARKABLE and abs(value) > 4
    if isinstance(value, float):
        return value not in UNREMARKABLE_FLOATS
    return False


def audit(root: Path) -> int:
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    by_value: dict[object, set[tuple[str, str]]] = defaultdict(set)
    comparisons: dict[object, set[str]] = defaultdict(set)
    codes: dict[str, set[str]] = defaultdict(set)

    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        name = path.name
        for constant, node in _module_constants(tree).items():
            value = _literal(node)
            if value is not None and _interesting(value):
                by_value[value].add((name, constant))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for operand in node.comparators:
                    value = _literal(operand)
                    if isinstance(value, (int, float)) and _interesting(value):
                        comparisons[value].add(name)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if (
                    len(text) >= CODE_MIN_LENGTH
                    and text.replace("_", "").isalnum()
                    and text.isupper()
                ):
                    codes[text].add(name)

    findings = 0
    print("== Cùng một giá trị, hai tên hằng số khác nhau ==")
    for value, places in sorted(by_value.items(), key=lambda kv: str(kv[0])):
        names = {constant for _file, constant in places}
        if len(names) > 1:
            findings += 1
            where = ", ".join(f"{file}:{constant}" for file, constant in sorted(places))
            print(f"  {value!r:28} {where}")

    print("\n== Cùng một ngưỡng so sánh, nhiều module ==")
    for value, where in sorted(comparisons.items(), key=lambda kv: str(kv[0])):
        if len(where) > 2:
            findings += 1
            print(f"  {value!r:28} {', '.join(sorted(where))}")

    print("\n== Mã cảnh báo xuất hiện ở nhiều file ==")
    for code, where in sorted(codes.items()):
        if len(where) > 2:
            findings += 1
            print(f"  {code:36} {', '.join(sorted(where))}")

    print(f"\n{findings} chỗ đáng nhìn. Không phải lỗi - là chỗ cần một người quyết định.")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("ebook_reader"))
    return audit(parser.parse_args().root)


if __name__ == "__main__":
    raise SystemExit(main())
