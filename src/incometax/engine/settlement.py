"""FR-5 年度汇算引擎（M2 实装）。

设计定稿：plan/04 §3.5 + 个税法年度汇算口径：

    应纳税所得额 = 收入额合计 − 减除费用(月度减除×12，查规则包) − 专项扣除
                   − 专项附加扣除 − 其他扣除（含 settlement_only 项目，如大病医疗）
    应纳税额     = 应纳税所得额 × 税率 − 速算扣除数（查综合所得税率表一）
    应退/应补    = 已预扣预缴合计 − 应纳税额   （正=应退，负=应补）

M2 简化口径（plan/06）：仅工资薪金收入；劳务报酬等留待后续扩展。
代码零政策数值字面量：减除费用 = 规则包 monthly_standard_deduction × 12（日历月数）。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from incometax.engine.monthly import MONTHS_PER_YEAR, ZERO, find_bracket
from incometax.engine.report import money
from incometax.rules.loader import Ruleset


@dataclass(frozen=True)
class SettlementInput:
    """年度汇算输入（全年口径，金额 Decimal；settlement_only 扣除并入专项附加）。"""

    annual_gross: Decimal  # 全年工资薪金收入额
    annual_special_deduction: Decimal = ZERO  # 全年专项扣除（三险一金）
    annual_special_additional_deduction: Decimal = ZERO  # 全年专项附加扣除
    annual_other_deduction: Decimal = ZERO  # 全年其他扣除
    withheld_total: Decimal = ZERO  # 全年已预扣预缴合计（正数）


@dataclass(frozen=True)
class SettlementReport:
    """汇算结果：refund_or_owe 正=应退，负=应补。"""

    annual_standard_deduction: Decimal
    cumulative_taxable_income: Decimal
    bracket_index: Optional[int]  # 应纳税所得额 ≤ 0 时为 None（无需缴税）
    rate: Optional[Decimal]
    quick_deduction: Optional[Decimal]
    annual_tax: Decimal
    withheld_total: Decimal
    refund_or_owe: Decimal
    standard_deduction_ref: Dict[str, Any]  # 减除费用依据（规则包原始 ref 节点）
    note: str = ""


def compute_annual_settlement(ruleset: Ruleset, inputs: SettlementInput) -> SettlementReport:
    """年度汇算计算（引擎入口只接受 effective_ruleset() 放行的规则包）。"""
    from incometax.rules.loader import effective_ruleset

    ruleset = effective_ruleset(ruleset)
    withheld_total = inputs.withheld_total
    if withheld_total < ZERO:
        raise ValueError(f"已预扣预缴合计不能为负：{withheld_total}")

    standard_deduction_ref = ruleset.data["withholding"]["monthly_standard_deduction"].get("ref", {})
    annual_standard = money(ruleset.monthly_standard_deduction * MONTHS_PER_YEAR)

    taxable = (
        inputs.annual_gross
        - annual_standard
        - inputs.annual_special_deduction
        - inputs.annual_special_additional_deduction
        - inputs.annual_other_deduction
    )

    bracket_index = None
    rate = quick = None
    annual_tax = ZERO
    note = ""
    if taxable > ZERO:
        bracket_index, bracket = find_bracket(ruleset.comprehensive_brackets, taxable)
        rate = bracket.rate
        quick = bracket.quick_deduction
        annual_tax = money(taxable * bracket.rate - bracket.quick_deduction)
    else:
        note = "应纳税所得额 ≤ 0，年度应纳税额为 0（已预扣部分汇算退还）"

    refund_or_owe = money(withheld_total - annual_tax)
    return SettlementReport(
        annual_standard_deduction=annual_standard,
        cumulative_taxable_income=taxable,
        bracket_index=bracket_index,
        rate=rate,
        quick_deduction=quick,
        annual_tax=annual_tax,
        withheld_total=withheld_total,
        refund_or_owe=refund_or_owe,
        standard_deduction_ref=standard_deduction_ref,
        note=note,
    )
