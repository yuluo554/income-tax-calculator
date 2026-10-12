"""零政策数值字面量门禁（HANDOFF-M2 既定口径 4，M4/M5 扩围）。

引擎、CLI、GUI 与基准代码中不得出现任何规则包政策数值（税率级距/速算扣除数/
扣除标准/临界端点）——全部数值必须查规则包。本测试把 2019-2026 全部规则包的
数值条目与两张税率表数值收编为禁用 token（>=100 的整数、对应小数与原样税率串），
对 src/incometax 的引擎、CLI、benchmark/ 与 gui/ 源码做词边界扫描。

豁免口径：
- < 100 的小数值不收编（如月份数 12 是日历常数、两位小数精度 0.01 是申报口径约定）；
- data/ 与 tools/ 不在扫描范围（生成器/数据本身当然含政策数值）。
"""

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "incometax"
SCAN_FILES = (
    sorted((SRC_ROOT / "engine").glob("*.py"))
    + sorted((SRC_ROOT / "benchmark").glob("*.py"))
    + sorted((SRC_ROOT / "gui").glob("*.py"))
    + [SRC_ROOT / "cli.py"]
)


def _numeric_tokens(node):
    if isinstance(node, bool):
        return
    if isinstance(node, dict):
        for value in node.values():
            yield from _numeric_tokens(value)
    elif isinstance(node, list):
        for value in node:
            yield from _numeric_tokens(value)
    elif isinstance(node, (int, float, str, Decimal)):
        text = str(node)
        try:
            value = Decimal(text)
        except InvalidOperation:
            return
        if value == value.to_integral_value():
            if abs(value) >= 100:
                yield str(int(value))
        elif abs(value) >= 1:
            yield format(value.normalize(), "f")
        if isinstance(node, str) and abs(value) < 1:
            yield text.strip()  # 原样税率串，如 "0.10"


def collect_forbidden_tokens():
    tokens = set()
    rules_dir = REPO_ROOT / "data" / "rules"
    for path in sorted(rules_dir.glob("ruleset-*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        tokens.update(_numeric_tokens(raw))
    return tokens


def _match_pattern(token: str):
    return re.compile(r"(?<![0-9.])" + re.escape(token) + r"(?![0-9])")


def test_scan_files_exist():
    assert len(SCAN_FILES) >= 22  # engine 8 模块 + benchmark 8 模块 + gui 9 模块 + cli.py
    assert (SRC_ROOT / "cli.py").exists()
    assert (SRC_ROOT / "benchmark" / "runner.py").exists()
    assert (SRC_ROOT / "gui" / "main_window.py").exists()
    assert (SRC_ROOT / "engine" / "pipeline.py").exists()


def test_engine_cli_gui_free_of_policy_literals():
    tokens = collect_forbidden_tokens()
    # 禁用集必须覆盖已知代表性政策数值（守门自检：收编逻辑本身有效）
    for must in ("5000", "36000", "2520", "15160", "15000", "80000"):
        assert must in tokens
    offenders = []
    for path in SCAN_FILES:
        source = path.read_text(encoding="utf-8")
        for token in tokens:
            if _match_pattern(token).search(source):
                offenders.append(f"{path.name}: {token}")
    assert not offenders, f"引擎/CLI/GUI 代码出现政策数值字面量：{offenders}"
