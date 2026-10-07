"""算例真值库 schema 测试（FR-7，M1 建库；M2 引擎回归以本库为真值）。

纪律（plan/05 §1.2）：无来源 URL 的条目不得入库；金额/税率一律 Decimal 字符串；
expected 为主期望，同一输入隐含的中间量记 also_expect。
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TRUTH_FILE = REPO_ROOT / "data" / "truth" / "cases.json"

VALID_CATEGORIES = {"bonus_separate", "withholding_cumulative", "annual_settlement"}


@pytest.fixture(scope="module")
def truth():
    raw = TRUTH_FILE.read_bytes()
    assert b"\r\n" not in raw, "真值库冻结产物必须 LF"
    return json.loads(raw.decode("utf-8"))


def test_truth_file_exists_and_schema_version():
    assert TRUTH_FILE.exists()
    raw = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1


def test_at_least_three_cases_with_unique_ids(truth):
    cases = truth["cases"]
    assert len(cases) >= 3
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for case_id in ids:
        assert case_id == case_id.strip() and case_id


def test_each_case_structure(truth):
    for case in truth["cases"]:
        assert case["category"] in VALID_CATEGORIES, case["id"]
        assert 2019 <= case["year"] <= 2026, case["id"]
        assert isinstance(case["title"], str) and case["title"]
        assert isinstance(case["input"], dict) and case["input"], case["id"]
        assert isinstance(case["expected"], dict) and case["expected"], case["id"]
        source = case["source"]
        assert source["refs"], case["id"]
        assert source["urls"], case["id"]
        for url in source["urls"]:
            assert url.startswith("https://") or url.startswith("http://"), case["id"]
        assert isinstance(source["note"], str) and source["note"], case["id"]


def test_amounts_are_decimal_strings(truth):
    """expected/also_expect 的所有标量必须是字符串（Decimal 语义）；input 里
    金额字段同样为字符串，计数（如 months）允许整数。"""

    def walk_expect(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                walk_expect(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk_expect(v, f"{where}[{i}]")
        else:
            assert isinstance(node, str), f"{where}: 期望值必须为 Decimal 字符串，得到 {node!r}"
            Decimal_check(node, where)

    def Decimal_check(text, where):
        try:
            Decimal(text)
        except InvalidOperation:
            pytest.fail(f"{where}: 非法 Decimal 字面值 {text!r}")

    for case in truth["cases"]:
        walk_expect(case["expected"], f"{case['id']}.expected")
        walk_expect(case.get("also_expect", {}), f"{case['id']}.also_expect")


def test_bonus_boundary_trap_pair(truth):
    """36000/36001 临界对：多发 1 元税额跳增必须为正（陷阱锚点，M4 基准用）。"""
    cases = {c["id"]: c for c in truth["cases"]}
    assert "bonus-36000-2024" in cases and "bonus-36001-2024" in cases
    t0 = Decimal(cases["bonus-36000-2024"]["expected"]["tax"])
    t1 = Decimal(cases["bonus-36001-2024"]["expected"]["tax"])
    assert t1 > t0
    extra = Decimal(cases["bonus-36001-2024"]["also_expect"]["extra_tax_vs_bonus_36000"])
    assert extra == t1 - t0
