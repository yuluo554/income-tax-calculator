"""FR-2 年终奖引擎测试（M2 单独计税原语 + M3 择优/临界区间）。

口径（data/truth/cases.json notes / plan/04 §3.2）：商数 = 奖金 ÷ 月份数
ROUND_HALF_UP 两位仅定档，税基用奖金全额；按月换算表级距上界闭（"不超过 3000 元"
含 3000）。择优比全年总税负（差 ≤ 申报精度并列）；临界区间端点全部由规则表推导，
首区间锚点由穷举交叉验证（M3 DoD）。
"""

from decimal import Decimal, ROUND_HALF_UP

import pytest

from incometax.engine.bonus import (
    SCHEME_COMBINED,
    SCHEME_SEPARATE,
    compare_bonus_schemes,
    compute_bonus_separate_tax,
    derive_bonus_trap_intervals,
    find_trap_interval,
)
from incometax.engine.report import MONEY_QUANT, money
from incometax.engine.settlement import SettlementInput, compute_annual_settlement
from incometax.rules.loader import effective_ruleset, load_ruleset


def bonus_2024(amount) -> object:
    return compute_bonus_separate_tax(effective_ruleset(load_ruleset(2024)), amount)


def salary_settlement_2024(annual_gross: str):
    return compute_annual_settlement(
        effective_ruleset(load_ruleset(2024)),
        SettlementInput(annual_gross=Decimal(annual_gross)),
    )


def test_truth_case_bonus_36000_first_bracket():
    r = bonus_2024("36000.00")
    assert r.quotient == Decimal("3000.00")
    assert r.bracket_index == 0 and r.rate == Decimal("0.03") and r.quick_deduction == Decimal(0)
    assert r.tax == Decimal("1080.00")
    assert r.after_tax == Decimal("34920.00")
    assert r.policy_valid and "2027" in r.policy_note


def test_truth_case_bonus_36001_trap_jump():
    r = bonus_2024("36001.00")
    assert r.quotient == Decimal("3000.08")
    assert r.bracket_index == 1 and r.rate == Decimal("0.10") and r.quick_deduction == Decimal(210)
    assert r.tax == Decimal("3390.10")
    assert r.after_tax == Decimal("32610.90")
    # 临界陷阱锚点：多发 1 元多缴 2310.10
    assert r.tax - bonus_2024("36000.00").tax == Decimal("2310.10")


def test_quotient_rounding_half_up_two_digits():
    """36000.004÷12=3000.00033→3000.00 仍第一级；商数两位定档不改税基。"""
    r = bonus_2024("36000.004")
    assert r.quotient == Decimal("3000.00")
    assert r.tax == (r.bonus_amount * Decimal("0.03")).quantize(Decimal("0.01"))


def test_policy_expiry_flag(tmp_path):
    """合成年度 2099 > valid_until 2027 → policy_valid=False（提示不拦算）。"""
    from test_rules_loader import write_ruleset

    raw = load_ruleset(2024).data
    data_dir = write_ruleset(tmp_path, raw, 2099)
    r = compute_bonus_separate_tax(effective_ruleset(load_ruleset(2099, data_dir=data_dir)), "36000.00")
    assert not r.policy_valid
    assert "到期" in r.policy_note


def test_nonpositive_bonus_rejected():
    with pytest.raises(ValueError):
        bonus_2024("0.00")
    with pytest.raises(ValueError):
        bonus_2024("-1.00")


# ---------------------------------------------------------------------------
# M3：双方案择优（plan/04 §3.2：比全年总税负，差 ≤ 0.01 并列）
# ---------------------------------------------------------------------------

RECOMMEND_SEPARATE = SCHEME_SEPARATE
RECOMMEND_COMBINED = SCHEME_COMBINED


def test_compare_separate_recommended_when_bracket_jump():
    """工资应纳税所得额恰在级距边界：并入把奖金推入 10% 档 → 单独计税更省。"""
    rs = effective_ruleset(load_ruleset(2024))
    salary = salary_settlement_2024("96000.00")  # 应纳税所得额 36000 → 税 1080
    cmp = compare_bonus_schemes(rs, "36000.00", salary)
    assert cmp.scheme_separate.annual_total_tax == Decimal("2160.00")  # 1080 + 1080
    assert cmp.scheme_combined.annual_total_tax == Decimal("4680.00")  # 72000×10%−2520
    assert cmp.scheme_combined.taxable_income == Decimal("72000.00")
    assert cmp.tax_difference == Decimal("-2520.00")  # A − B：负 = A 更省
    assert not cmp.tie
    assert cmp.recommended == RECOMMEND_SEPARATE
    assert cmp.scheme_separate.available


def test_compare_combined_recommended_when_salary_below_deduction():
    """工资低于减除费用：并入可被免税额度吸收 → 并入综合更省。"""
    rs = effective_ruleset(load_ruleset(2024))
    salary = salary_settlement_2024("30000.00")  # 应纳税所得额 −30000 → 税 0
    cmp = compare_bonus_schemes(rs, "36000.00", salary)
    assert cmp.scheme_separate.annual_total_tax == Decimal("1080.00")
    assert cmp.scheme_combined.annual_total_tax == Decimal("180.00")  # 6000×3%
    assert cmp.scheme_combined.taxable_income == Decimal("6000.00")
    assert cmp.tax_difference == Decimal("900.00")
    assert cmp.recommended == RECOMMEND_COMBINED


def test_compare_tie_within_penny():
    """两方案全年总税负相等 → 并列（两案等同）。"""
    rs = effective_ruleset(load_ruleset(2024))
    salary = salary_settlement_2024("60000.00")  # 应纳税所得额 0
    cmp = compare_bonus_schemes(rs, "36000.00", salary)
    assert cmp.scheme_separate.annual_total_tax == Decimal("1080.00")
    assert cmp.scheme_combined.annual_total_tax == Decimal("1080.00")
    assert cmp.tax_difference == Decimal("0.00")
    assert cmp.tie
    assert cmp.recommended == "tie"


def test_compare_policy_expired_forces_combined(tmp_path):
    """政策到期年份：方案 A 数值上更省也标不可用，强制推荐方案 B。"""
    from test_rules_loader import write_ruleset

    data_dir = write_ruleset(tmp_path, load_ruleset(2024).data, 2099)
    rs = effective_ruleset(load_ruleset(2099, data_dir=data_dir))
    salary = salary_settlement_2024("96000.00")  # A 数值上省 2520
    cmp = compare_bonus_schemes(rs, "36000.00", salary)
    assert not cmp.scheme_separate.available
    assert "到期" in cmp.scheme_separate.note
    assert cmp.recommended == RECOMMEND_COMBINED


def test_compare_nonpositive_bonus_rejected():
    rs = effective_ruleset(load_ruleset(2024))
    with pytest.raises(ValueError):
        compare_bonus_schemes(rs, "0.00", salary_settlement_2024("60000.00"))


def test_compare_and_trap_derive_gate_pending_ruleset(tmp_path):
    """M3 引擎入口红线：择优与临界区间推导同样被门控拦截。"""
    from incometax.rules.loader import RulesetNotEffective

    from test_rules_loader import flip_one_node_pending, write_ruleset

    raw = flip_one_node_pending(load_ruleset(2024).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rs = load_ruleset(2099, data_dir=data_dir)
    salary = salary_settlement_2024("60000.00")
    with pytest.raises(RulesetNotEffective):
        compare_bonus_schemes(rs, "36000.00", salary)
    with pytest.raises(RulesetNotEffective):
        derive_bonus_trap_intervals(rs)


# ---------------------------------------------------------------------------
# M3：临界区间机制性推导（端点全由规则表推导；首区间锚点与穷举一致）
# ---------------------------------------------------------------------------


def test_trap_intervals_all_boundaries_2024():
    """按月换算表逐边界推导：6 个级距边界全部产出陷阱区间（速算扣除数未随年口径
    缩放，边界处税额跳增），端点公式 B* 全部由规则表推导复现经典锚点值。"""
    intervals = derive_bonus_trap_intervals(effective_ruleset(load_ruleset(2024)))
    assert len(intervals) == 6
    boundaries = [iv.lower for iv in intervals]
    assert boundaries == [
        Decimal("36000"),
        Decimal("144000"),
        Decimal("300000"),
        Decimal("420000"),
        Decimal("660000"),
        Decimal("960000"),
    ]
    endpoints = [money(iv.upper) for iv in intervals]
    assert endpoints == [
        Decimal("38566.67"),
        Decimal("160500.00"),
        Decimal("318333.33"),
        Decimal("447500.00"),
        Decimal("706538.46"),
        Decimal("1120000.00"),
    ]
    first = intervals[0]
    assert first.left_bracket_index == 0 and first.right_bracket_index == 1
    assert first.left_rate == Decimal("0.03") and first.right_rate == Decimal("0.10")
    assert first.upper > first.lower


def test_trap_intervals_identical_across_all_years():
    """税率表全期间未变 → 临界区间推导结果逐年一致。"""
    base = derive_bonus_trap_intervals(effective_ruleset(load_ruleset(2019)))
    for year in range(2020, 2027):
        assert derive_bonus_trap_intervals(effective_ruleset(load_ruleset(year))) == base


def test_find_trap_interval_open_interval_semantics():
    intervals = derive_bonus_trap_intervals(effective_ruleset(load_ruleset(2024)))
    assert find_trap_interval(intervals, "36001.00") is intervals[0]
    assert find_trap_interval(intervals, "36000.00") is None  # 左端点不在开区间内
    assert find_trap_interval(intervals, intervals[0].upper) is None  # 右端点税后已追平
    assert find_trap_interval(intervals, "50000.00") is None


def test_trap_interval_brute_force_recovery_point():
    """M3 DoD：首区间端点与穷举一致——区间内税后恒低于左端锚点，右端为恢复点。

    商数两位定档使实际跳档点晚于级距边界数分（查表死区），穷举从实际跳档的
    两位小数金额起扫描；恢复点（税后追平锚点）必须等于推导右端点的申报精度值。
    """
    rs = effective_ruleset(load_ruleset(2024))
    iv = derive_bonus_trap_intervals(rs)[0]
    step = Decimal("0.01")
    anchor = compute_bonus_separate_tax(rs, iv.lower).after_tax

    b = iv.lower + step
    while compute_bonus_separate_tax(rs, b).bracket_index != iv.right_bracket_index:
        b += step  # 跳档点（死区末尾）
    switch = b

    recovery = None
    b = switch
    while recovery is None:
        if compute_bonus_separate_tax(rs, b).after_tax >= anchor:
            recovery = b
        b += step

    assert recovery == money(iv.upper)
    b = switch
    while b < recovery:
        assert compute_bonus_separate_tax(rs, b).after_tax < anchor, b
        b += step
    # 死区（边界与实际跳档点之间）商数仍落左级：税后不低于锚点、且逐额递增
    b = iv.lower + step
    while b < switch:
        assert compute_bonus_separate_tax(rs, b).after_tax >= anchor, b
        b += step
