"""FR-2 年终奖计税引擎（M3 实装：双方案择优 + 临界区间机制性推导）。

单独计税原语 compute_bonus_separate_tax（164号第一条（一）公式，M2 落地）——
商数查表口径：奖金 ÷ 月份数 ROUND_HALF_UP 保留两位仅用于定档，税基仍用奖金全额
（见 data/truth/cases.json notes）。

M3 新增（设计定稿：plan/04 §3.2）：
- compare_bonus_schemes：方案 A（单独计税）vs 方案 B（并入综合所得重跑汇算），
  比"全年总税负"，差 ≤ 申报精度（两位小数单位）并列；政策到期年份方案 A 标不可用；
- derive_bonus_trap_intervals：对按月换算表逐级距边界推导"多发一元、到手变少"
  临界区间，端点全部由规则表推导，代码零政策数值字面量。
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from incometax.engine.report import MONEY_QUANT, money
from incometax.engine.settlement import SettlementReport
from incometax.rules.loader import Ruleset

from incometax.engine.monthly import find_bracket


@dataclass(frozen=True)
class BonusSeparateTaxResult:
    """单独计税结果（税基=奖金全额；商数仅定档）。"""

    bonus_amount: Decimal
    divisor: Decimal  # 月份数（规则包 bonus.monthly_divisor，如 12）
    quotient: Decimal  # 商数（两位小数，仅定档用）
    bracket_index: Optional[int]
    rate: Optional[Decimal]
    quick_deduction: Optional[Decimal]
    tax: Decimal
    after_tax: Decimal
    policy_valid: bool
    policy_note: str
    table_field: str = "monthly_converted"  # 按月换算后的综合所得税率表（164号附件1）


def compute_bonus_separate_tax(ruleset: Ruleset, bonus_amount) -> BonusSeparateTaxResult:
    """全年一次性奖金单独计税（引擎入口只接受 effective_ruleset() 放行的规则包）。

    应纳税额 = 奖金全额 × 税率(商数查按月换算表) − 速算扣除数；
    政策有效期按规则包 bonus.separate_tax_policy 的 valid_until 校验（仅提示，不拦计算）。
    """
    from incometax.rules.loader import effective_ruleset

    ruleset = effective_ruleset(ruleset)
    bonus_amount = Decimal(bonus_amount)
    if bonus_amount <= 0:
        raise ValueError(f"年终奖金额应为正数：{bonus_amount}")

    divisor_node = ruleset.data["bonus"]["monthly_divisor"]
    divisor = Decimal(divisor_node["value"])
    quotient = (bonus_amount / divisor).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    bracket_index, bracket = find_bracket(ruleset.monthly_brackets, quotient)
    tax = money(bonus_amount * bracket.rate - bracket.quick_deduction)

    policy = ruleset.data["bonus"]["separate_tax_policy"]
    valid_until = str(policy.get("valid_until", ""))
    policy_valid, policy_note = True, ""
    if valid_until:
        try:
            until_year = int(valid_until.split("-")[0])
        except (ValueError, TypeError):
            until_year = None
        if until_year is not None and ruleset.year > until_year:
            policy_valid = False
            policy_note = f"单独计税政策已到期（{policy.get('ref', {}).get('source', '')}，至 {valid_until}）"
        else:
            policy_note = f"单独计税政策有效期内（至 {valid_until}）"

    return BonusSeparateTaxResult(
        bonus_amount=bonus_amount,
        divisor=divisor,
        quotient=quotient,
        bracket_index=bracket_index,
        rate=bracket.rate,
        quick_deduction=bracket.quick_deduction,
        tax=tax,
        after_tax=bonus_amount - tax,
        policy_valid=policy_valid,
        policy_note=policy_note,
    )


# ---------------------------------------------------------------------------
# M3：双方案择优（plan/04 §3.2）
# ---------------------------------------------------------------------------

SCHEME_SEPARATE = "separate"  # 方案 A：单独计税
SCHEME_COMBINED = "combined"  # 方案 B：并入综合所得


@dataclass(frozen=True)
class BonusSchemeResult:
    """单方案视角：全年总税负 + 可用性（供对比与渲染）。"""

    scheme_id: str  # SCHEME_SEPARATE / SCHEME_COMBINED
    label: str
    available: bool
    annual_total_tax: Decimal  # 全年总税负（该方案口径）
    taxable_income: Optional[Decimal]  # 方案 B：并入后应纳税所得额；方案 A：None
    bracket_index: Optional[int]
    rate: Optional[Decimal]
    quick_deduction: Optional[Decimal]
    note: str


@dataclass(frozen=True)
class BonusComparisonReport:
    """择优结论：tax_difference = A − B（负 = 方案 A 全年更省）；|差| ≤ 申报精度并列。"""

    bonus_amount: Decimal
    scheme_separate: BonusSchemeResult
    scheme_combined: BonusSchemeResult
    recommended: str  # SCHEME_SEPARATE / SCHEME_COMBINED / "tie"
    tax_difference: Decimal
    tie: bool
    note: str = ""


def compare_bonus_schemes(
    ruleset: Ruleset, bonus_amount, salary_settlement: SettlementReport
) -> BonusComparisonReport:
    """双方案对比并推荐（引擎入口只接受 effective_ruleset() 放行的规则包）。

    口径（plan/04 §3.2 定稿）：
    - salary_settlement = **不含奖金**的工资薪金年度汇算结果（方案 B 在其应纳税
      所得额基础上并入奖金重算）；
    - 方案 A 全年总税负 = 工资汇算应纳税额 + 奖金单独计税税额；
      方案 B 全年总税负 = 并入后重跑汇算的全年应纳税额
      （已预缴为现金流，不进入总税负比较）；
    - 政策到期年份方案 A 标不可用，强制推荐方案 B（提示政策到期）。
    """
    from incometax.rules.loader import effective_ruleset

    ruleset = effective_ruleset(ruleset)
    bonus_amount = Decimal(bonus_amount)
    if bonus_amount <= 0:
        raise ValueError(f"年终奖金额应为正数：{bonus_amount}")

    # 方案 A：单独计税（原语已含政策有效期标注）
    separate = compute_bonus_separate_tax(ruleset, bonus_amount)
    separate_total = money(salary_settlement.annual_tax + separate.tax)
    separate_note = separate.policy_note
    if not separate.policy_valid:
        separate_note += "；方案 A 在该纳税年度不可选，推荐并入综合所得"

    # 方案 B：奖金并入工资汇算应纳税所得额，重跑综合所得税率表
    combined_taxable = salary_settlement.cumulative_taxable_income + bonus_amount
    combined_bracket_index: Optional[int] = None
    combined_rate: Optional[Decimal] = None
    combined_quick: Optional[Decimal] = None
    if combined_taxable > 0:
        combined_bracket_index, combined_bracket = find_bracket(
            ruleset.comprehensive_brackets, combined_taxable
        )
        combined_rate = combined_bracket.rate
        combined_quick = combined_bracket.quick_deduction
        combined_total = money(combined_taxable * combined_bracket.rate - combined_bracket.quick_deduction)
    else:
        combined_total = money(Decimal(0))

    tax_difference = money(separate_total - combined_total)
    tie = abs(tax_difference) <= MONEY_QUANT

    if not separate.policy_valid:
        recommended = SCHEME_COMBINED
    elif tie:
        recommended = "tie"
    elif tax_difference < 0:
        recommended = SCHEME_SEPARATE
    else:
        recommended = SCHEME_COMBINED

    scheme_separate = BonusSchemeResult(
        scheme_id=SCHEME_SEPARATE,
        label="方案A 单独计税",
        available=separate.policy_valid,
        annual_total_tax=separate_total,
        taxable_income=None,
        bracket_index=separate.bracket_index,
        rate=separate.rate,
        quick_deduction=separate.quick_deduction,
        note=separate_note,
    )
    scheme_combined = BonusSchemeResult(
        scheme_id=SCHEME_COMBINED,
        label="方案B 并入综合所得",
        available=True,
        annual_total_tax=combined_total,
        taxable_income=combined_taxable,
        bracket_index=combined_bracket_index,
        rate=combined_rate,
        quick_deduction=combined_quick,
        note="奖金并入全年应纳税所得额重跑综合所得税率表（30号公告：可择优）",
    )
    return BonusComparisonReport(
        bonus_amount=bonus_amount,
        scheme_separate=scheme_separate,
        scheme_combined=scheme_combined,
        recommended=recommended,
        tax_difference=tax_difference,
        tie=tie,
        note="全年总税负口径（已预缴为现金流不参与比较）；salary_settlement 须为不含奖金的汇算结果",
    )


# ---------------------------------------------------------------------------
# M3：临界区间机制性推导（plan/04 §3.2；代码零政策数值字面量）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BonusTrapInterval:
    """单一临界区间（开区间）：奖金落在 (lower, upper) 内 → 税后低于 lower 处。

    lower = 级距边界年口径（月口径上界 × 月份数）；upper = B*，由端点公式
    B* = ( b·(1−r₁) + q₁ − q₂ ) / (1 − r₂) 推导（b=边界，r/q 取左/右级次）。
    B* ≤ b 时该边界无陷阱（级距边界税额连续或右净额已更高），不产出区间。
    """

    lower: Decimal
    upper: Decimal
    left_bracket_index: int
    right_bracket_index: int
    left_rate: Decimal
    right_rate: Decimal
    left_quick_deduction: Decimal
    right_quick_deduction: Decimal
    note: str = "区间内多发奖金 → 税后到手反而少于区间左端点处（税率表机制客观呈现，非避税建议）"


def derive_bonus_trap_intervals(ruleset: Ruleset) -> List[BonusTrapInterval]:
    """由按月换算税率表逐边界推导临界区间（引擎入口只接受已门控规则包）。

    推导（plan/04 §3.2）：级距左/右级次 (r₁,q₁)/(r₂,q₂)，奖金税后净额
    N(B) = B − (B·r − q)；右侧净额追平左侧边界净额 N(b) = b·(1−r₁) + q₁ 的
    奖金值 B* = ( b·(1−r₁) + q₁ − q₂ ) / (1 − r₂)。区间 (b, B*) 内净额更低。
    端点全部来自规则包税率表与月份数，规则表变更自动跟随。
    """
    from incometax.rules.loader import effective_ruleset

    ruleset = effective_ruleset(ruleset)
    brackets = ruleset.monthly_brackets
    divisor = Decimal(ruleset.data["bonus"]["monthly_divisor"]["value"])

    intervals: List[BonusTrapInterval] = []
    for i in range(len(brackets) - 1):
        left, right = brackets[i], brackets[i + 1]
        # 边界年口径 b = 月口径上界 × 月份数（月份数来自规则包，非日历字面量）
        boundary = left.upper * divisor
        one_minus_left = Decimal(1) - left.rate
        one_minus_right = Decimal(1) - right.rate
        b_star = (
            boundary * one_minus_left + left.quick_deduction - right.quick_deduction
        ) / one_minus_right
        if b_star <= boundary:
            continue  # 边界处税额连续（速算扣除数吸收），无"多发反而少得"陷阱
        intervals.append(
            BonusTrapInterval(
                lower=boundary,
                upper=b_star,
                left_bracket_index=i,
                right_bracket_index=i + 1,
                left_rate=left.rate,
                right_rate=right.rate,
                left_quick_deduction=left.quick_deduction,
                right_quick_deduction=right.quick_deduction,
            )
        )
    return intervals


def find_trap_interval(
    intervals: List[BonusTrapInterval], bonus_amount
) -> Optional[BonusTrapInterval]:
    """奖金落入的临界区间（开区间匹配）；未落入返回 None。"""
    amount = Decimal(bonus_amount)
    for interval in intervals:
        if interval.lower < amount < interval.upper:
            return interval
    return None
