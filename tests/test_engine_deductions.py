"""FR-3 七项专项附加扣除引擎测试（M3）。

口径（plan/04 §3.3）：标准值全部查规则包（年度切换即标准切换）；房贷利息与住房
租金互斥（规则包显式标记）、赡养老人分摊上限、分摊比例枚举——违规**整单拒绝**
（DeductionViolationError 携带全部违规，不产出部分结果，误放行 0）；大病医疗
settlement_only：预扣链月额恒 0，汇算链按起付线/限额计算。
"""

from decimal import Decimal

import pytest

from incometax.engine.deductions import (
    STAGE_BOTH,
    STAGE_SETTLEMENT_ONLY,
    Claim,
    DeductionViolationError,
    evaluate_claims,
)
from incometax.rules.loader import effective_ruleset, load_ruleset


def evaluate(year, *claims):
    return evaluate_claims(effective_ruleset(load_ruleset(year)), list(claims))


def violation_reason(year, *claims) -> str:
    with pytest.raises(DeductionViolationError) as excinfo:
        evaluate(year, *claims)
    return str(excinfo.value)


# ---------------------------------------------------------------------------
# 标准计算：按孩数 / 分摊比例 / 城市档 / 申报月数（标准值随年度规则包切换）
# ---------------------------------------------------------------------------


def test_child_education_standard_2024():
    report = evaluate(2024, Claim(item="child_education"))
    claim = report.claims[0]
    assert claim.monthly_amount == Decimal("2000.00")  # 国发〔2023〕13号提标后标准
    assert claim.annual_amount == Decimal("24000.00")
    assert claim.stage == STAGE_BOTH and claim.months_claimed == 12


def test_child_education_half_share_two_children():
    report = evaluate(2024, Claim(item="child_education", children=2, share_ratio=Decimal("0.5")))
    assert report.claims[0].monthly_amount == Decimal("2000.00")  # 2000×2×50%
    assert report.annual_total == Decimal("24000.00")


def test_child_education_2019_uses_old_standard():
    report = evaluate(2019, Claim(item="child_education"))
    assert report.claims[0].monthly_amount == Decimal("1000.00")
    assert report.annual_total == Decimal("12000.00")


def test_child_education_invalid_share_ratio_rejected():
    reason = violation_reason(2024, Claim(item="child_education", share_ratio=Decimal("0.3")))
    assert "分摊比例" in reason and "第六条" in reason


def test_child_education_fractional_children_rejected():
    reason = violation_reason(2024, Claim(item="child_education", children=Decimal("1.5")))
    assert "孩数" in reason


def test_infant_care_standards_by_year():
    assert evaluate(2022, Claim(item="infant_care")).claims[0].monthly_amount == Decimal("1000.00")
    assert evaluate(2024, Claim(item="infant_care")).claims[0].monthly_amount == Decimal("2000.00")


def test_infant_care_not_available_before_introduction_year():
    reason = violation_reason(2019, Claim(item="infant_care"))
    assert "无此扣除项" in reason


def test_continue_education_academic_monthly():
    report = evaluate(2024, Claim(item="continue_education", kind="academic", months=12))
    assert report.claims[0].monthly_amount == Decimal("400.00")
    assert report.claims[0].annual_amount == Decimal("4800.00")


def test_continue_education_months_within_single_year():
    reason = violation_reason(2024, Claim(item="continue_education", kind="academic", months=13))
    assert "申报月数" in reason


def test_continue_education_academic_max_months_cap(tmp_path):
    """同一学历扣除期限上限由规则包 academic_max_months 驱动（单年度申报 ≤ 12 个月，
    跨年上限用合成规则包缩限验证机制）。"""
    from test_rules_loader import write_ruleset

    raw = load_ruleset(2024).data
    raw["special_deductions"]["continue_education"]["academic_max_months"]["value"] = 6
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rs = effective_ruleset(load_ruleset(2099, data_dir=data_dir))
    with pytest.raises(DeductionViolationError) as excinfo:
        evaluate_claims(rs, [Claim(item="continue_education", kind="academic", months=12)])
    assert "扣除期限" in str(excinfo.value) and "6" in str(excinfo.value)


def test_continue_education_vocational_annual_lump():
    report = evaluate(2024, Claim(item="continue_education", kind="vocational"))
    claim = report.claims[0]
    assert claim.monthly_amount == Decimal("0.00")
    assert claim.annual_amount == Decimal("3600.00")
    assert claim.stage == STAGE_SETTLEMENT_ONLY


def test_continue_education_kind_required():
    reason = violation_reason(2024, Claim(item="continue_education"))
    assert "academic" in reason and "vocational" in reason


# ---------------------------------------------------------------------------
# 大病医疗：settlement_only 链路分离 + 起付线/限额
# ---------------------------------------------------------------------------


def test_serious_illness_threshold_cap_and_stage():
    report = evaluate(2024, Claim(item="serious_illness", self_paid_total=Decimal("30000.00")))
    claim = report.claims[0]
    assert claim.stage == STAGE_SETTLEMENT_ONLY
    assert claim.monthly_amount == Decimal("0.00")  # 预扣链恒 0
    assert claim.annual_amount == Decimal("15000.00")  # 30000 − 15000 起付
    assert report.settlement_only_annual_total == Decimal("15000.00")
    assert report.monthly_total == Decimal("0.00")


def test_serious_illness_annual_cap():
    report = evaluate(2024, Claim(item="serious_illness", self_paid_total=Decimal("95000.00")))
    assert report.claims[0].annual_amount == Decimal("80000.00")  # 限额封顶


def test_serious_illness_below_threshold_zero():
    report = evaluate(2024, Claim(item="serious_illness", self_paid_total=Decimal("10000.00")))
    claim = report.claims[0]
    assert claim.annual_amount == Decimal("0.00")
    assert "未超起付线" in claim.note


def test_serious_illness_negative_self_paid_rejected():
    reason = violation_reason(2024, Claim(item="serious_illness", self_paid_total=Decimal("-1.00")))
    assert "不能为负" in reason


# ---------------------------------------------------------------------------
# 住房：贷款利息定额 / 租金城市档分档 / 互斥
# ---------------------------------------------------------------------------


def test_housing_loan_standard():
    report = evaluate(2024, Claim(item="housing_loan", months=12))
    assert report.claims[0].monthly_amount == Decimal("1000.00")
    assert report.claims[0].annual_amount == Decimal("12000.00")


def test_housing_rent_tier_standards():
    for tier, expected in ((0, "1500.00"), (1, "1100.00"), (2, "800.00")):
        report = evaluate(2024, Claim(item="housing_rent", tier=tier))
        assert report.claims[0].monthly_amount == Decimal(expected), tier
        assert "城市" in report.claims[0].detail


def test_housing_rent_invalid_tier_rejected():
    reason = violation_reason(2024, Claim(item="housing_rent", tier=3))
    assert "城市档" in reason
    reason = violation_reason(2024, Claim(item="housing_rent", tier=-1))
    assert "城市档" in reason


def test_housing_loan_and_rent_mutually_exclusive():
    """互斥整单拒绝（误放行 0）：不产出部分结果，违规挂条款依据。"""
    reason = violation_reason(
        2024, Claim(item="housing_loan"), Claim(item="housing_rent", tier=0)
    )
    assert "不得同时申报" in reason and "第二十条" in reason


# ---------------------------------------------------------------------------
# 赡养老人：独生定额 vs 非独生分摊上限（每人 + 合计）
# ---------------------------------------------------------------------------


def test_support_elderly_only_child_standard_by_year():
    assert evaluate(2024, Claim(item="support_elderly", only_child=True)).claims[
        0
    ].monthly_amount == Decimal("3000.00")
    assert evaluate(2019, Claim(item="support_elderly", only_child=True)).claims[
        0
    ].monthly_amount == Decimal("2000.00")


def test_support_elderly_shared_within_per_child_cap():
    report = evaluate(
        2024, Claim(item="support_elderly", only_child=False, monthly_amount=Decimal("1500.00"))
    )
    assert report.claims[0].monthly_amount == Decimal("1500.00")
    assert report.claims[0].annual_amount == Decimal("18000.00")


def test_support_elderly_shared_exceeds_per_child_cap():
    reason = violation_reason(
        2024, Claim(item="support_elderly", only_child=False, monthly_amount=Decimal("1500.01"))
    )
    assert "每人上限" in reason


def test_support_elderly_shared_total_cap_across_siblings():
    reason = violation_reason(
        2024,
        Claim(
            item="support_elderly",
            only_child=False,
            monthly_amount=Decimal("1500.00"),
            other_shared_amounts=(Decimal("1500.00"), Decimal("500.00")),
        ),
    )
    assert "合计" in reason and "额度" in reason


def test_support_elderly_only_child_flag_required():
    reason = violation_reason(2024, Claim(item="support_elderly"))
    assert "独生子女" in reason


def test_support_elderly_only_child_rejects_sibling_amounts():
    reason = violation_reason(
        2024,
        Claim(
            item="support_elderly",
            only_child=True,
            other_shared_amounts=(Decimal("1000.00"),),
        ),
    )
    assert "共赡养人" in reason


# ---------------------------------------------------------------------------
# 整单拒绝语义与聚合
# ---------------------------------------------------------------------------


def test_duplicate_claim_rejected():
    reason = violation_reason(
        2024, Claim(item="child_education"), Claim(item="child_education")
    )
    assert "重复申报" in reason


def test_same_continue_education_kind_twice_rejected_but_two_kinds_ok():
    reason = violation_reason(
        2024,
        Claim(item="continue_education", kind="academic"),
        Claim(item="continue_education", kind="academic"),
    )
    assert "重复申报" in reason
    report = evaluate(
        2024,
        Claim(item="continue_education", kind="academic"),
        Claim(item="continue_education", kind="vocational"),
    )
    assert len(report.claims) == 2  # 学历与职业资格可同年度并存（41号第八条口径）


def test_unknown_item_rejected():
    reason = violation_reason(2024, Claim(item="pet_care"))
    assert "未知扣除项目" in reason


def test_report_aggregates_split_chains():
    """多申报聚合：预扣链月合计 / 仅汇算项年额 / 汇算链年合计分列。"""
    report = evaluate(
        2024,
        Claim(item="child_education"),
        Claim(item="support_elderly", only_child=True),
        Claim(item="serious_illness", self_paid_total=Decimal("30000.00")),
    )
    assert report.monthly_total == Decimal("5000.00")  # 2000 + 3000
    assert report.settlement_only_annual_total == Decimal("15000.00")
    assert report.annual_total == Decimal("75000.00")  # 24000 + 36000 + 15000
    assert len(report.claims) == 3


def test_claims_gate_pending_ruleset(tmp_path):
    """引擎入口红线：扣除引擎同样只接受门控放行的规则包。"""
    from incometax.rules.loader import RulesetNotEffective

    from test_rules_loader import flip_one_node_pending, write_ruleset

    raw = flip_one_node_pending(load_ruleset(2024).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rs = load_ruleset(2099, data_dir=data_dir)
    with pytest.raises(RulesetNotEffective):
        evaluate_claims(rs, [Claim(item="child_education")])
