"""FR-4 社保公积金联动引擎（M2 实装）。

设计定稿：plan/04 §3.4 + plan/06 D-4：缴费基数上下限与费率**全部用户输入**
（各城市差异大，规则包不存全国值）——本引擎因此不接收 Ruleset、不含任何政策数值。
计算结果（个人部分合计）由调用方填入 monthly 引擎每月的专项扣除
（专项扣除官方口径含基本养老/医疗/失业保险费与住房公积金，个税法第六条），
并回链"来自社保联动"标注。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Tuple

from incometax.engine.report import money


@dataclass(frozen=True)
class SocialItem:
    """单一险种个人部分：费率与基数均为用户输入。"""

    label: str
    rate: Decimal
    base: Decimal
    personal_amount: Decimal


@dataclass(frozen=True)
class SocialReport:
    """社保公积金联动结果：total 直接作为 monthly 引擎的每月专项扣除增量。"""

    base_input: Decimal
    base_lower: Decimal
    base_upper: Decimal
    clamped_base: Decimal
    clamp_note: str  # 基数被夹取时的说明；区间内为空串
    items: Tuple[SocialItem, ...]
    total: Decimal

    @property
    def source_note(self) -> str:
        """回链标注：填入 monthly 专项扣除时附带，呈现"来自社保联动"。"""
        return f"含社保公积金个人部分 {self.total:.2f} 元/月（社保联动计算）"


def compute_social_insurance(base_input, rates, base_lower, base_upper) -> SocialReport:
    """计算社保公积金个人部分（参数全部用户输入，Decimal 全链路）。

    - base_input 自动夹取到 [base_lower, base_upper]；
    - rates：{险种名: 个人费率}，险种名仅作呈现标签（如 养老/医疗/失业/公积金）；
    - 单项个人部分 = 缴费基数 × 费率（两位小数），合计为 monthly 专项扣除输入。
    """
    base_input = Decimal(base_input)
    base_lower = Decimal(base_lower)
    base_upper = Decimal(base_upper)
    if base_lower > base_upper:
        raise ValueError(f"缴费基数下限 {base_lower} 不能高于上限 {base_upper}")
    if base_input < 0:
        raise ValueError(f"缴费基数不能为负：{base_input}")
    if not rates:
        raise ValueError("社保公积金费率不能为空（至少一项，如 养老/医疗/失业/公积金）")

    clamped_base = min(max(base_input, base_lower), base_upper)
    clamp_note = ""
    if clamped_base != base_input:
        clamp_note = (
            f"缴费基数 {base_input:.2f} 超出用户输入区间 "
            f"[{base_lower:.2f}, {base_upper:.2f}]，已夹取为 {clamped_base:.2f}"
        )

    items = []
    for label, rate_value in rates.items():
        rate = Decimal(rate_value)
        if rate < 0:
            raise ValueError(f"费率不能为负：{label}={rate}")
        items.append(
            SocialItem(
                label=str(label),
                rate=rate,
                base=clamped_base,
                personal_amount=money(clamped_base * rate),
            )
        )
    total = money(sum((item.personal_amount for item in items), Decimal(0)))
    return SocialReport(
        base_input=base_input,
        base_lower=base_lower,
        base_upper=base_upper,
        clamped_base=clamped_base,
        clamp_note=clamp_note,
        items=tuple(items),
        total=total,
    )
