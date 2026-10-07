"""FR-4 社保公积金联动引擎测试（M2）。

口径（plan/06 D-4）：基数上下限与费率全部用户输入，引擎不接收 Ruleset、零政策数值；
个人部分合计供 monthly 引擎并入专项扣除。
"""

from decimal import Decimal

import pytest

from incometax.engine.social import compute_social_insurance


def test_within_range_base_sum_of_items():
    report = compute_social_insurance(
        Decimal("10000.00"),
        {"养老": Decimal("0.08"), "医疗": Decimal("0.02"), "失业": Decimal("0.005"), "公积金": Decimal("0.12")},
        Decimal("4000.00"),
        Decimal("25000.00"),
    )
    assert report.clamped_base == Decimal("10000.00")
    assert report.clamp_note == ""
    assert [i.personal_amount for i in report.items] == [
        Decimal("800.00"),
        Decimal("200.00"),
        Decimal("50.00"),
        Decimal("1200.00"),
    ]
    assert report.total == Decimal("2250.00")
    assert "社保联动" in report.source_note


def test_base_clamped_to_lower_and_upper():
    rates = {"养老": Decimal("0.08")}
    low = compute_social_insurance(Decimal("3000.00"), rates, Decimal("4000.00"), Decimal("25000.00"))
    assert low.clamped_base == Decimal("4000.00")
    assert low.total == Decimal("320.00")
    assert "夹取" in low.clamp_note

    high = compute_social_insurance(Decimal("30000.00"), rates, Decimal("4000.00"), Decimal("25000.00"))
    assert high.clamped_base == Decimal("25000.00")
    assert high.total == Decimal("2000.00")
    assert "夹取" in high.clamp_note


def test_empty_and_negative_inputs_rejected():
    with pytest.raises(ValueError):
        compute_social_insurance(Decimal("10000"), {}, Decimal("4000"), Decimal("25000"))
    with pytest.raises(ValueError):
        compute_social_insurance(Decimal("10000"), {"养老": Decimal("-0.08")}, Decimal("4000"), Decimal("25000"))
    with pytest.raises(ValueError):
        compute_social_insurance(Decimal("-1"), {"养老": Decimal("0.08")}, Decimal("4000"), Decimal("25000"))


def test_lower_above_upper_rejected():
    with pytest.raises(ValueError):
        compute_social_insurance(
            Decimal("10000"), {"养老": Decimal("0.08")}, Decimal("25000"), Decimal("4000")
        )
