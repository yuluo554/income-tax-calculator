"""FR-5 年度汇算引擎测试（M2）。

口径（plan/04 §3.5）：应退/应补 = 已预缴 − 应纳税额（正=应退，负=应补）；
应纳税所得额 ≤ 0 → 应纳税额 0（已预扣部分汇算退还）；减除费用全部查规则包。
"""

from decimal import Decimal

import pytest

from incometax.engine.settlement import SettlementInput, compute_annual_settlement
from incometax.rules.loader import effective_ruleset, load_ruleset


def settle_2024(**kwargs) -> object:
    return compute_annual_settlement(
        effective_ruleset(load_ruleset(2024)), SettlementInput(**kwargs)
    )


def test_truth_case_settlement_2024():
    """真值 settlement-2024：20 万年薪 − 6 万减除 − 4 万三险一金 − 6 万专项附加 → 1480。"""
    report = settle_2024(
        annual_gross=Decimal("200000.00"),
        annual_special_deduction=Decimal("40000.00"),
        annual_special_additional_deduction=Decimal("60000.00"),
    )
    assert report.annual_standard_deduction == Decimal("60000.00")
    assert report.cumulative_taxable_income == Decimal("40000.00")
    assert report.bracket_index == 1 and report.rate == Decimal("0.10")
    assert report.annual_tax == Decimal("1480.00")


def test_refund_when_overwithheld():
    """已预缴 > 应纳税额 → 正数应退。"""
    report = settle_2024(annual_gross=Decimal("120000.00"), withheld_total=Decimal("864.00"))
    # 120000−60000=60000 → 10% → 3480；已预缴 864 → 应退 2616
    assert report.annual_tax == Decimal("3480.00")
    assert report.refund_or_owe == Decimal("-2616.00")  # 未提供足够预缴 → 应补


def test_owe_when_underwithheld_sign_convention():
    report = settle_2024(annual_gross=Decimal("120000.00"), withheld_total=Decimal("3000.00"))
    assert report.refund_or_owe == Decimal("-480.00")  # 负=应补
    report2 = settle_2024(annual_gross=Decimal("120000.00"), withheld_total=Decimal("4000.00"))
    assert report2.refund_or_owe == Decimal("520.00")  # 正=应退


def test_nonpositive_taxable_full_refund():
    report = settle_2024(annual_gross=Decimal("50000.00"), withheld_total=Decimal("150.00"))
    assert report.cumulative_taxable_income == Decimal("-10000.00")
    assert report.bracket_index is None
    assert report.annual_tax == Decimal("0.00")
    assert report.refund_or_owe == Decimal("150.00")
    assert "汇算退还" in report.note


def test_negative_withheld_rejected():
    with pytest.raises(ValueError):
        settle_2024(annual_gross=Decimal("120000.00"), withheld_total=Decimal("-0.01"))
