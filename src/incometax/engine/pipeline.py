"""calc 全链路编排（M5 自 cli.cmd_calc 上收：CLI 与 GUI 两个前端共用同一编排）。

分层职责（plan/03：CLI 与 GUI 是两个薄壳，不另起第二套计算行为）：
- 前端层职责 = 输入解析、呈现、错误映射（CLI → 退出码，GUI → 对话框）；
- 本模块职责 = 把社保联动、七项专项附加、累计预扣、年度汇算、年终奖择优与
  临界区间按既定口径串成一次完整计算：

  1. 社保联动（可选）：个人部分合计逐月并入专项扣除，回链标注；
  2. 专项附加申报（可选）：先经引擎校验——违规整单拒绝，DeductionViolationError
     原样上抛（前端映射为用法错误/违规提示，不产出部分结果）；月额逐月并入
     预扣链（settlement_only 项目不进预扣链），明细标注挂到受影响月份；
  3. 累计预扣逐月表（必算）；
  4. 年度汇算：聚合 = 月度输入加总 + 预扣结果；settlement_only 年额并入汇算链
     专项附加；显式 settlement 覆盖字段优先级最高；
  5. 年终奖（可选）：单独计税 + 双方案择优 + 临界区间全表（含当前奖金落点）。

门控语义：各引擎入口内部仍会执行 effective_ruleset()；前端可在调用前先行
门控以获得统一的拦截呈现。本模块不做输入合法性兜底（非法输入由前端解析层
拒绝或引擎 ValueError 上抛）。
"""

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from incometax.engine import bonus as bonus_engine
from incometax.engine import deductions as deductions_engine
from incometax.engine import monthly as monthly_engine
from incometax.engine import settlement as settlement_engine
from incometax.engine import social as social_engine
from incometax.engine.monthly import MonthInput
from incometax.engine.settlement import SettlementReport
from incometax.rules.loader import Ruleset

ZERO = Decimal(0)

# 社保联动参数元组口径（与 social_engine.compute_social_insurance 入参一致）：
# (base_input, rates{险种: 费率}, base_lower, base_upper)
SocialParams = Tuple[Any, Any, Any, Any]


@dataclass(frozen=True)
class CalcRequest:
    """一次完整计算的用户输入（金额一律 Decimal；缺省部分按无处理）。"""

    months: Tuple[MonthInput, ...] = ()
    social_params: Optional[SocialParams] = None
    claims: Tuple[deductions_engine.Claim, ...] = ()
    bonus_income: Optional[Decimal] = None
    settlement_overrides: Dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class CalcResult:
    """完整计算结果：逐 Report 聚合（None = 该部分无输入未参与计算）。"""

    year: int
    social_report: Optional[social_engine.SocialReport] = None
    deductions_report: Optional[deductions_engine.DeductionsReport] = None
    monthly_report: Optional[monthly_engine.MonthlyReport] = None
    settlement_report: Optional[SettlementReport] = None
    bonus_report: Optional[bonus_engine.BonusSeparateTaxResult] = None
    bonus_comparison: Optional[bonus_engine.BonusComparisonReport] = None
    trap_intervals: Optional[Tuple[bonus_engine.BonusTrapInterval, ...]] = None
    active_trap: Optional[bonus_engine.BonusTrapInterval] = None


def compute_full_calc(ruleset: Ruleset, request: CalcRequest) -> CalcResult:
    """按既定口径跑完 calc 全链路（引擎入口只接受已门控规则包，各入口内部再校验）。"""
    if not request.months:
        raise ValueError("至少需要一个月度输入")

    social_report = None
    months = list(request.months)
    if request.social_params is not None:
        base_input, rates, base_lower, base_upper = request.social_params
        social_report = social_engine.compute_social_insurance(
            base_input, rates, base_lower, base_upper
        )
        months = [
            replace(
                mi,
                special_deduction=mi.special_deduction + social_report.total,
                note="；".join(filter(None, [mi.note, social_report.source_note])),
            )
            for mi in months
        ]

    # 七项专项附加申报：先校验（违规整单拒绝），再按 stage 分链并入预扣输入
    deductions_report = None
    if request.claims:
        deductions_report = deductions_engine.evaluate_claims(ruleset, request.claims)
        affected_months = set()
        for cr in deductions_report.claims:
            if cr.monthly_amount <= 0:
                continue  # settlement_only / 年度定额项不进预扣链
            for m in range(min(cr.months_claimed, len(months))):
                mi = months[m]
                months[m] = replace(
                    mi,
                    special_additional_deduction=mi.special_additional_deduction
                    + cr.monthly_amount,
                )
                affected_months.add(m)
        for m in affected_months:
            mi = months[m]
            months[m] = replace(
                mi,
                note="；".join(
                    filter(None, [mi.note, "含专项附加扣除申报计入（明细见申报清单）"])
                ),
            )

    monthly_report = monthly_engine.compute_monthly_withholding(ruleset, months)

    aggregates = {
        "annual_gross": sum((mi.gross for mi in months), ZERO),
        "annual_special_deduction": sum((mi.special_deduction for mi in months), ZERO),
        "annual_special_additional_deduction": sum(
            (mi.special_additional_deduction for mi in months), ZERO
        ),
        "annual_other_deduction": sum((mi.other_deduction for mi in months), ZERO),
        "withheld_total": monthly_report.withheld_total,
    }
    if deductions_report is not None:
        # settlement_only 项（大病医疗等）不在预扣链月度输入里，汇算链单独纳入
        aggregates["annual_special_additional_deduction"] += (
            deductions_report.settlement_only_annual_total
        )
    aggregates.update(request.settlement_overrides)
    settlement_report = settlement_engine.compute_annual_settlement(
        ruleset, settlement_engine.SettlementInput(**aggregates)
    )

    bonus_report = bonus_comparison = None
    trap_intervals: Optional[Tuple[bonus_engine.BonusTrapInterval, ...]] = None
    active_trap = None
    if request.bonus_income is not None:
        bonus_report = bonus_engine.compute_bonus_separate_tax(ruleset, request.bonus_income)
        bonus_comparison = bonus_engine.compare_bonus_schemes(
            ruleset, request.bonus_income, settlement_report
        )
        trap_intervals = tuple(bonus_engine.derive_bonus_trap_intervals(ruleset))
        active_trap = bonus_engine.find_trap_interval(trap_intervals, request.bonus_income)

    return CalcResult(
        year=ruleset.year,
        social_report=social_report,
        deductions_report=deductions_report,
        monthly_report=monthly_report,
        settlement_report=settlement_report,
        bonus_report=bonus_report,
        bonus_comparison=bonus_comparison,
        trap_intervals=trap_intervals,
        active_trap=active_trap,
    )
