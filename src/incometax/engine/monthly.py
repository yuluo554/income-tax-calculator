"""FR-1 累计预扣法逐月引擎（M2 实装）。

设计定稿：plan/04 §3.1——61 号公告第六条公式逐字实现 + 逐月状态机，Decimal 全链路：

    累计预扣预缴应纳税所得额 = 累计收入 − 累计免税收入 − 累计减除费用(月度减除×m，查规则包)
                               − 累计专项扣除 − 累计专项附加扣除 − 累计依法确定的其他扣除
    累计应预扣预缴税额       = 累计应纳税所得额 × 预扣率 − 速算扣除数
    本期应预扣预缴税额       = 累计应预扣预缴税额 − 累计已预扣预缴税额

边界行为（plan/04 §3.1 定稿）：累计应纳税所得额 ≤ 0 → 当期税额 0；本期应预扣为负 →
按 0 处理（暂不退税，负数不滚入下月抵扣，公告口径），余额留给年度汇算（settlement.py）。

适用税率 = 预扣率表一（居民个人工资、薪金所得预扣预缴适用）：与规则包
rate_tables.comprehensive_annual 同一级距/税率/速算扣除数（出处 ref_qd=61号公告附件），
故复用 Ruleset.comprehensive_brackets，代码零政策数值字面量。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence, Tuple

from incometax.engine.report import money
from incometax.rules.loader import Ruleset

ZERO = Decimal(0)

# 日历常数（一年 12 个月），非政策数值；政策数值全部来自规则包。
MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class MonthInput:
    """单月输入（金额一律 Decimal；缺失按 0，社保联动产出由调用方并入 special_deduction）。"""

    gross: Decimal = ZERO  # 当月工资薪金收入
    tax_free: Decimal = ZERO  # 当月免税收入
    special_deduction: Decimal = ZERO  # 当月专项扣除（三险一金个人部分，可来自社保联动）
    special_additional_deduction: Decimal = ZERO  # 当月专项附加扣除（不含 settlement_only 项目）
    other_deduction: Decimal = ZERO  # 当月依法确定的其他扣除
    note: str = ""  # 输入侧标注（如"来自社保联动"/"未提供按 0 处理"）


@dataclass(frozen=True)
class MonthResult:
    """单月结果：公式逐项中间量 + 适用级次 + 本期应预扣（每项可挂依据）。"""

    month_no: int
    inp: MonthInput
    cumulative_income: Decimal
    cumulative_tax_free: Decimal
    cumulative_standard_deduction: Decimal
    cumulative_special_deduction: Decimal
    cumulative_special_additional_deduction: Decimal
    cumulative_other_deduction: Decimal
    cumulative_taxable: Decimal
    bracket_index: Optional[int]  # 累计应纳税所得额 ≤ 0 时为 None（不进表）
    rate: Optional[Decimal]
    quick_deduction: Optional[Decimal]
    cumulative_tax: Decimal
    withheld_before: Decimal
    withholding: Decimal  # 本期应预扣（≥0，负值按 0 并记 note）
    note: str = ""


@dataclass(frozen=True)
class MonthlyReport:
    """逐月预扣报告：withheld_total 供年度汇算"已预缴"衔接。"""

    months: Tuple[MonthResult, ...]
    withheld_total: Decimal
    standard_deduction_ref: Dict[str, Any]  # 减除费用依据（规则包原始 ref 节点）
    table_field: str = "comprehensive_annual"  # 预扣率表一 = 该表级距（见模块 docstring）

    @property
    def standard_deduction_ref_note(self) -> str:
        ref = self.standard_deduction_ref
        if not ref:
            return ""
        return f"{ref.get('source', '')}·{ref.get('clause', '')}"


def find_bracket(brackets, taxable: Decimal):
    """返回 (级次下标, Bracket)。

    官方税率表级距口径为上界闭区间（"不超过 X 元" / "超过 X 元至 Y 元"）：
    首级 0 ≤ taxable ≤ upper₀；后续级 lower < taxable ≤ upper；末级上不封顶。
    级距相接（schema 校验保证 lower=上一级 upper），故顺序查到第一个
    taxable ≤ upper 的级次即为命中（taxable=上一级上界时已在上一级命中）。
    """
    if taxable <= ZERO:
        raise ValueError(f"查表要求应纳税所得额为正数，得到 {taxable}")
    for i, bracket in enumerate(brackets):
        if bracket.upper is None or taxable <= bracket.upper:
            return i, bracket
    raise ValueError(f"累计应纳税所得额 {taxable} 不在任何税率级次内（规则包税率表非法）")


def compute_monthly_withholding(ruleset: Ruleset, monthly_inputs: Sequence[MonthInput]) -> MonthlyReport:
    """逐月累计预扣计算（引擎入口只接受 effective_ruleset() 放行的规则包）。"""
    from incometax.rules.loader import effective_ruleset

    ruleset = effective_ruleset(ruleset)
    if not monthly_inputs:
        raise ValueError("至少需要一个月度输入")
    if len(monthly_inputs) > MONTHS_PER_YEAR:
        raise ValueError(f"月度输入最多 {MONTHS_PER_YEAR} 个月，收到 {len(monthly_inputs)} 个")

    standard_deduction_ref = ruleset.data["withholding"]["monthly_standard_deduction"].get("ref", {})
    monthly_standard = ruleset.monthly_standard_deduction
    brackets = ruleset.comprehensive_brackets

    results = []
    cumulative_income = cumulative_tax_free = ZERO
    cumulative_special = cumulative_additional = cumulative_other = ZERO
    withheld_before = ZERO  # 累计已预扣（实际入库部分，负值余额不入账）

    for month_no, month_input in enumerate(monthly_inputs, start=1):
        cumulative_income += month_input.gross
        cumulative_tax_free += month_input.tax_free
        cumulative_special += month_input.special_deduction
        cumulative_additional += month_input.special_additional_deduction
        cumulative_other += month_input.other_deduction
        cumulative_standard = monthly_standard * month_no

        cumulative_taxable = (
            cumulative_income
            - cumulative_tax_free
            - cumulative_standard
            - cumulative_special
            - cumulative_additional
            - cumulative_other
        )

        bracket_index = None
        rate = quick = None
        cumulative_tax = ZERO
        if cumulative_taxable > ZERO:
            bracket_index, bracket = find_bracket(brackets, cumulative_taxable)
            rate = bracket.rate
            quick = bracket.quick_deduction
            cumulative_tax = money(cumulative_taxable * bracket.rate - bracket.quick_deduction)

        withheld_before_this_month = withheld_before
        withholding = cumulative_tax - withheld_before
        note = month_input.note
        if withholding < ZERO:
            note = "；".join(filter(None, [note, "本期应预扣为负，按 0 处理（暂不退税，余额留年度汇算）"]))
            withholding = ZERO
        withheld_before += withholding

        results.append(
            MonthResult(
                month_no=month_no,
                inp=month_input,
                cumulative_income=cumulative_income,
                cumulative_tax_free=cumulative_tax_free,
                cumulative_standard_deduction=cumulative_standard,
                cumulative_special_deduction=cumulative_special,
                cumulative_special_additional_deduction=cumulative_additional,
                cumulative_other_deduction=cumulative_other,
                cumulative_taxable=cumulative_taxable,
                bracket_index=bracket_index,
                rate=rate,
                quick_deduction=quick,
                cumulative_tax=cumulative_tax,
                withheld_before=withheld_before_this_month,
                withholding=withholding,
                note=note,
            )
        )

    return MonthlyReport(
        months=tuple(results),
        withheld_total=withheld_before,
        standard_deduction_ref=standard_deduction_ref,
    )
