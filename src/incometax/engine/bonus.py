"""FR-2 年终奖计税引擎。

M2 落地：单独计税原语 compute_bonus_separate_tax（164号第一条（一）公式）——
真值库 bonus 算例对账与 CLI calc 奖金块的基础件，M3 的双方案择优/临界区间推导
在其上构建。商数查表口径：奖金 ÷ 月份数 ROUND_HALF_UP 保留两位仅用于定档，
税基仍用奖金全额（见 data/truth/cases.json notes）。

M3 实装（设计定稿：plan/04 §3.2）：
- compare_bonus_schemes：双方案（单独计税 vs 并入综合）对比自动推荐；
- derive_bonus_trap_intervals：临界区间由按月换算税率表机制性推导，代码零字面量。
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from incometax.engine.report import MONEY_QUANT, money
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


def compare_bonus_schemes(ruleset: Ruleset, bonus_amount, salary_annual_result) -> object:
    """双方案对比并推荐。M3 实装。"""
    raise NotImplementedError(
        "年终奖择优引擎在 M3 实装（设计见 plan/04 §3.2；单独计税原语已就绪）"
    )


def derive_bonus_trap_intervals(ruleset: Ruleset) -> list:
    """由按月换算税率表推导"多发一元、到手变少"临界区间（区间端点公式见 plan/04 §3.2）。

    返回 [(区间左端, 区间右端, 依据级次), ...]。M3 实装。
    """
    raise NotImplementedError(
        "临界区间推导在 M3 实装（区间端点由规则表推导生成，不硬编码）"
    )
