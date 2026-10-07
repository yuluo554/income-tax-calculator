"""基准一：算例回归（data/truth 真值库 × 引擎全字段对账）。

对账语义（plan/05 §1.2）自 tests/test_truth_reconciliation 上收至此，测试与基准
共用同一实现：expected 为主期望、also_expect 为隐含中间量，按"全部非 pass 字段
集"对账——引擎输出必须覆盖且逐一等于真值字段（键集相等 + 数值相等）。

类别执行器按 category 分派（bonus_separate / withholding_cumulative /
annual_settlement）；跨算例字段 extra_tax_vs_bonus_<基数金额> 由字段名内嵌的
基数动态计算（真值键驱动，代码零字面量）。**不许改真值凑引擎答案。**
"""

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from incometax.benchmark.checks import expect
from incometax.benchmark.metrics import BenchmarkMetric
from incometax.engine.bonus import compute_bonus_separate_tax
from incometax.engine.monthly import MonthInput, compute_monthly_withholding
from incometax.engine.settlement import SettlementInput, compute_annual_settlement
from incometax.rules.loader import Ruleset, effective_ruleset

TRUTH_RELATIVE_PATH = ("truth", "cases.json")

EXTRA_TAX_KEY_PREFIX = "extra_tax_vs_bonus_"

CATEGORY_BONUS = "bonus_separate"
CATEGORY_WITHHOLDING = "withholding_cumulative"
CATEGORY_SETTLEMENT = "annual_settlement"


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


def _execute_bonus(case: Dict[str, Any], ruleset: Ruleset, wanted: Dict[str, Decimal]) -> dict:
    result = compute_bonus_separate_tax(ruleset, case["input"]["bonus_income"])
    actual: Dict[str, Any] = {
        "divisor_quotient": result.quotient,
        "rate": result.rate,
        "quick_deduction": result.quick_deduction,
        "tax": result.tax,
        "after_tax": result.after_tax,
    }
    for key in wanted:
        if not key.startswith(EXTRA_TAX_KEY_PREFIX):
            continue
        # 跨算例字段：与字段名内嵌基数金额的单独计税税额之差（临界陷阱锚点）
        base_amount = Decimal(key[len(EXTRA_TAX_KEY_PREFIX):])
        base_tax = compute_bonus_separate_tax(ruleset, base_amount).tax
        actual[key] = result.tax - base_tax
    return actual


def _execute_withholding(case: Dict[str, Any], ruleset: Ruleset, wanted) -> dict:
    inp = case["input"]
    months = [
        MonthInput(
            gross=Decimal(inp["monthly_gross"]),
            special_deduction=Decimal(inp["monthly_social_insurance"]),
            special_additional_deduction=Decimal(inp["monthly_special_additional"]),
            other_deduction=Decimal(inp["monthly_other_deductions"]),
        )
    ] * int(inp["months"])
    report = compute_monthly_withholding(ruleset, months)
    return {
        "cumulative_taxable": [m.cumulative_taxable for m in report.months],
        "cumulative_tax": [m.cumulative_tax for m in report.months],
        "monthly_tax": [m.withholding for m in report.months],
        "cumulative_standard_deduction": [m.cumulative_standard_deduction for m in report.months],
    }


def _execute_settlement(case: Dict[str, Any], ruleset: Ruleset, wanted) -> dict:
    inp = case["input"]
    special_additional_total = sum(
        (Decimal(v) for v in inp["special_additional_detail"].values()), Decimal(0)
    )
    report = compute_annual_settlement(
        ruleset,
        SettlementInput(
            annual_gross=Decimal(inp["annual_gross"]),
            annual_special_deduction=Decimal(inp["annual_social_insurance"]),
            annual_special_additional_deduction=special_additional_total,
            annual_other_deduction=Decimal(inp["annual_other_deductions"]),
        ),
    )
    return {
        "comprehensive_taxable_income": report.cumulative_taxable_income,
        "annual_tax": report.annual_tax,
        "standard_deduction_total": report.annual_standard_deduction,
        "special_additional_total": special_additional_total,
    }


EXECUTORS = {
    CATEGORY_BONUS: _execute_bonus,
    CATEGORY_WITHHOLDING: _execute_withholding,
    CATEGORY_SETTLEMENT: _execute_settlement,
}


def load_truth(data_dir) -> dict:
    path = data_dir.joinpath(*TRUTH_RELATIVE_PATH)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f, parse_float=Decimal)


def run_cases(rulesets: Dict[int, Ruleset], data_dir) -> BenchmarkMetric:
    """逐条真值对账：键集相等 + 数值逐一相等；单条失败不中断基准。"""
    failures: List[str] = []
    total = passed = 0
    for index, case in enumerate(load_truth(data_dir).get("cases", [])):
        total += 1
        case_id = str(case.get("id", f"cases[{index}]"))
        try:
            executor = EXECUTORS.get(str(case.get("category")))
            if executor is None:
                raise ValueError(f"未知算例类别 {case.get('category')!r}")
            year = int(case["year"])
            ruleset = rulesets.get(year)
            if ruleset is None:
                raise ValueError("该年度没有已加载规则包")
            wanted = flatten(case["expected"])
            wanted.update(flatten(case.get("also_expect", {})))
            actual = flatten(executor(case, effective_ruleset(ruleset), wanted))
            missing = sorted(set(wanted) - set(actual))
            extra = sorted(set(actual) - set(wanted))
            if not expect(
                failures,
                not missing and not extra,
                case_id,
                f"字段覆盖差异 缺失={missing} 多余={extra}",
            ):
                continue
            case_failed = False
            for key in sorted(wanted):
                if not expect(failures, actual[key] == wanted[key], f"{case_id}.{key}",
                              f"引擎={actual[key]} 真值={wanted[key]}"):
                    case_failed = True
            if not case_failed:
                passed += 1
        except (KeyError, ValueError, ArithmeticError, InvalidOperation, TypeError) as exc:
            failures.append(f"{case_id}: 执行失败 {type(exc).__name__}: {exc}")
    return BenchmarkMetric(
        key="cases",
        title="算例回归",
        total=total,
        passed=passed,
        threshold="通过率 100%",
        summary=f"真值算例 {passed}/{total} 全字段对账通过",
        stats={"算例数": total},
        failures=tuple(failures),
    )
