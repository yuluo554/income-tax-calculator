"""真值库对账测试（M2 DoD 核心）：data/truth/cases.json 4 条 × 引擎 100% 通过。

对账语义（plan/05 §1.2）：expected 为主期望 + also_expect 隐含中间量，
按"全部非 pass 字段集"对账——引擎输出必须覆盖并逐一等于真值字段。
真值由官方文件数值+手工推导构建（推导式见各条 note），引擎是独立实现路径；
**不许改真值凑引擎答案**。
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from incometax.engine.bonus import compute_bonus_separate_tax
from incometax.engine.monthly import MonthInput, compute_monthly_withholding
from incometax.engine.settlement import SettlementInput, compute_annual_settlement
from incometax.rules.loader import effective_ruleset, load_ruleset

REPO_ROOT = Path(__file__).resolve().parent.parent
TRUTH_FILE = REPO_ROOT / "data" / "truth" / "cases.json"

TRUTH = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in TRUTH["cases"]}


def flatten(node, prefix=""):
    """把期望/实际值展平成 {路径: Decimal}（列表带下标路径），两侧同构对账。"""
    out = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.update(flatten(value, f"{prefix}[{i}]"))
    else:
        out[prefix] = Decimal(node)
    return out


def check_case(case_id, actual_nested):
    """实际值与真值（expected+also_expect）键集与数值逐一相等。"""
    case = CASES[case_id]
    wanted = flatten(case["expected"])
    wanted.update(flatten(case.get("also_expect", {})))
    actual = flatten(actual_nested)
    assert set(actual) == set(wanted), (
        f"{case_id}: 字段覆盖差异缺失={sorted(set(wanted) - set(actual))} "
        f"多余={sorted(set(actual) - set(wanted))}"
    )
    for key, want in wanted.items():
        assert actual[key] == want, f"{case_id}.{key}: 引擎={actual[key]} 真值={want}"


def test_case_bonus_36000():
    case = CASES["bonus-36000-2024"]
    result = compute_bonus_separate_tax(
        effective_ruleset(load_ruleset(case["year"])), case["input"]["bonus_income"]
    )
    check_case(
        case["id"],
        {
            "divisor_quotient": result.quotient,
            "rate": result.rate,
            "quick_deduction": result.quick_deduction,
            "tax": result.tax,
            "after_tax": result.after_tax,
        },
    )


def test_case_bonus_36001_with_cross_case_extra_tax():
    """36001 算例含跨算例字段 extra_tax_vs_bonus_36000（临界陷阱锚点）。"""
    case = CASES["bonus-36001-2024"]
    base_tax = compute_bonus_separate_tax(
        effective_ruleset(load_ruleset(case["year"])), "36000.00"
    ).tax
    result = compute_bonus_separate_tax(
        effective_ruleset(load_ruleset(case["year"])), case["input"]["bonus_income"]
    )
    check_case(
        case["id"],
        {
            "divisor_quotient": result.quotient,
            "rate": result.rate,
            "quick_deduction": result.quick_deduction,
            "tax": result.tax,
            "after_tax": result.after_tax,
            "extra_tax_vs_bonus_36000": result.tax - base_tax,
        },
    )


def test_case_withholding_three_months():
    case = CASES["withholding-3months-2019"]
    inp = case["input"]
    months = [
        MonthInput(
            gross=Decimal(inp["monthly_gross"]),
            special_deduction=Decimal(inp["monthly_social_insurance"]),
            special_additional_deduction=Decimal(inp["monthly_special_additional"]),
            other_deduction=Decimal(inp["monthly_other_deductions"]),
        )
    ] * int(inp["months"])
    report = compute_monthly_withholding(effective_ruleset(load_ruleset(case["year"])), months)
    check_case(
        case["id"],
        {
            "cumulative_taxable": [m.cumulative_taxable for m in report.months],
            "cumulative_tax": [m.cumulative_tax for m in report.months],
            "monthly_tax": [m.withholding for m in report.months],
            "cumulative_standard_deduction": [m.cumulative_standard_deduction for m in report.months],
        },
    )


def test_case_settlement_2024():
    case = CASES["settlement-2024"]
    inp = case["input"]
    special_additional_total = sum(
        (Decimal(v) for v in inp["special_additional_detail"].values()), Decimal(0)
    )
    report = compute_annual_settlement(
        effective_ruleset(load_ruleset(case["year"])),
        SettlementInput(
            annual_gross=Decimal(inp["annual_gross"]),
            annual_special_deduction=Decimal(inp["annual_social_insurance"]),
            annual_special_additional_deduction=special_additional_total,
            annual_other_deduction=Decimal(inp["annual_other_deductions"]),
        ),
    )
    check_case(
        case["id"],
        {
            "comprehensive_taxable_income": report.cumulative_taxable_income,
            "annual_tax": report.annual_tax,
            "standard_deduction_total": report.annual_standard_deduction,
            "special_additional_total": special_additional_total,
        },
    )


def test_all_four_cases_covered():
    """守门：真值库当前 4 条必须全部有对账用例（新增真值须同步补对账）。"""
    assert set(CASES) == {
        "bonus-36000-2024",
        "bonus-36001-2024",
        "withholding-3months-2019",
        "settlement-2024",
    }


def test_engines_reject_pending_ruleset(tmp_path):
    """引擎入口红线：未过 effective_ruleset 门控的规则包在引擎内部再次被拦。"""
    from incometax.rules.loader import RulesetNotEffective
    from test_rules_loader import flip_one_node_pending, write_ruleset

    raw = flip_one_node_pending(load_ruleset(2026).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rs = load_ruleset(2099, data_dir=data_dir)
    with pytest.raises(RulesetNotEffective):
        compute_monthly_withholding(rs, [MonthInput(gross=Decimal("1.00"))])
    with pytest.raises(RulesetNotEffective):
        compute_annual_settlement(rs, SettlementInput(annual_gross=Decimal("1.00")))
    with pytest.raises(RulesetNotEffective):
        compute_bonus_separate_tax(rs, "1.00")
