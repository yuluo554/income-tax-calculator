"""FR-1 累计预扣逐月引擎测试（M2）。

口径（plan/04 §3.1 定稿）：61号第六条公式逐字实现；累计应纳税所得额 ≤ 0 → 当期 0；
本期应预扣为负 → 按 0 处理（暂不退税，负数不滚入下月抵扣）。
税率级距 = 上界闭区间（"不超过 X 元"），边界点税额连续（速算扣除数吸收）。
"""

from decimal import Decimal

import pytest

from incometax.engine.monthly import MonthInput, compute_monthly_withholding, find_bracket
from incometax.rules.loader import effective_ruleset, load_ruleset


def run_2019(months):
    return compute_monthly_withholding(effective_ruleset(load_ruleset(2019)), months)


def test_truth_case_three_months_uniform():
    """真值 withholding-3months-2019：每月 10000、三险一金 2000 → 逐月 90。"""
    report = run_2019([MonthInput(gross=Decimal("10000.00"), special_deduction=Decimal("2000.00"))] * 3)
    assert [m.cumulative_taxable for m in report.months] == [Decimal(3000), Decimal(6000), Decimal(9000)]
    assert [m.cumulative_standard_deduction for m in report.months] == [
        Decimal(5000),
        Decimal(10000),
        Decimal(15000),
    ]
    assert [m.cumulative_tax for m in report.months] == [Decimal("90.00"), Decimal("180.00"), Decimal("270.00")]
    assert [m.withholding for m in report.months] == [Decimal("90.00")] * 3
    assert report.withheld_total == Decimal("270.00")
    assert all(m.bracket_index == 0 for m in report.months)


def test_bracket_jump_mid_year_progressive():
    """年内跳档：23000×m 累计，第 2 月进入第二级（10%），当月税额跳增。"""
    report = run_2019([MonthInput(gross=Decimal("30000.00"), special_deduction=Decimal("2000.00"))] * 3)
    m1, m2, m3 = report.months
    assert m1.cumulative_taxable == Decimal(23000)
    assert m1.bracket_index == 0 and m1.withholding == Decimal("690.00")
    assert m2.cumulative_taxable == Decimal(46000)
    assert m2.bracket_index == 1
    assert m2.cumulative_tax == Decimal("2080.00")  # 46000×10%−2520
    assert m2.withholding == Decimal("1390.00")  # 2080−690
    m3 = report.months[2]
    assert m3.cumulative_taxable == Decimal(69000)
    assert m3.cumulative_tax == Decimal("4380.00")  # 69000×10%−2520
    assert m3.withholding == Decimal("2300.00")  # 4380−2080


def test_nonpositive_cumulative_taxable_is_zero_tax():
    """累计应纳税所得额 ≤ 0 → 税额 0；级次为 None。"""
    report = run_2019([MonthInput(gross=Decimal("0.00"))] * 3)
    for m in report.months:
        assert m.cumulative_taxable < 0
        assert m.bracket_index is None
        assert m.cumulative_tax == Decimal("0.00")
        assert m.withholding == Decimal("0.00")


def test_negative_withholding_clamped_no_refund():
    """首月高税额、次月起收入归零：本期应预扣为负 → 0（暂不退税），已预扣不回吐。"""
    months = [MonthInput(gross=Decimal("100000.00"))] + [MonthInput(gross=Decimal("0.00"))] * 11
    report = run_2019(months)
    m1 = report.months[0]
    # 95000 → 第二级（10%，2520）→ 6980
    assert m1.bracket_index == 1
    assert m1.withholding == Decimal("6980.00")
    for later in report.months[1:]:
        assert later.withholding == Decimal("0.00")
        assert "暂不退税" in later.note
    # 期末累计应纳税所得额 95000−55000=40000 → 累计应预扣 1480 < 已预扣 6980，差额留汇算
    assert report.months[-1].cumulative_tax == Decimal("1480.00")
    assert report.withheld_total == Decimal("6980.00")


def test_recovery_after_zero_months_pays_full_cumulative():
    """前期无收入、后期有收入：累计口径自动补收（前期 0 不损失）。"""
    report = run_2019([MonthInput(gross=Decimal("0.00")), MonthInput(gross=Decimal("20000.00"))])
    assert report.months[0].withholding == Decimal("0.00")
    m2 = report.months[1]
    # 累计应纳税所得额 = 20000−10000 = 10000 → 3% → 300
    assert m2.cumulative_taxable == Decimal(10000)
    assert m2.withholding == Decimal("300.00")


def test_social_linkage_note_propagates():
    """社保联动产出并入专项扣除时，回链标注随输入带出。"""
    report = run_2019([MonthInput(gross=Decimal("10000"), special_deduction=Decimal("2250.00"), note="含社保公积金个人部分 2250.00 元/月（社保联动计算）")])
    assert "社保联动" in report.months[0].note


def test_month_count_bounds():
    with pytest.raises(ValueError):
        compute_monthly_withholding(effective_ruleset(load_ruleset(2026)), [])
    with pytest.raises(ValueError):
        compute_monthly_withholding(
            effective_ruleset(load_ruleset(2026)), [MonthInput()] * 13
        )


def test_find_bracket_inclusive_upper_official_semantics():
    """官方级距"不超过 X 元"= 上界闭：边界点命中前一级（税额连续，速算扣除数吸收）。"""
    brackets = effective_ruleset(load_ruleset(2026)).comprehensive_brackets
    assert find_bracket(brackets, Decimal(36000))[0] == 0
    assert find_bracket(brackets, Decimal("36000.01"))[0] == 1
    assert find_bracket(brackets, Decimal(144000))[0] == 1
    assert find_bracket(brackets, Decimal("0.01"))[0] == 0
    with pytest.raises(ValueError):
        find_bracket(brackets, Decimal(0))
