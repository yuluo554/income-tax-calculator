"""FR-2 年终奖单独计税原语测试（M2；M3 择优/临界区间在真值对账基础上扩展）。

口径（data/truth/cases.json notes）：商数 = 奖金 ÷ 月份数 ROUND_HALF_UP 两位仅定档，
税基用奖金全额；按月换算表级距上界闭（"不超过 3000 元"含 3000）。
"""

from decimal import Decimal

import pytest

from incometax.engine.bonus import compute_bonus_separate_tax
from incometax.rules.loader import effective_ruleset, load_ruleset


def bonus_2024(amount) -> object:
    return compute_bonus_separate_tax(effective_ruleset(load_ruleset(2024)), amount)


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
