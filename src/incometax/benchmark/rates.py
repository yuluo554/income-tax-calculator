"""基准二：税率级次临界扫描（两张税率表逐有限上界边界的精确邻域）。

口径（plan/04 §四 / plan/06 M2 级距语义）：
- 级距为上界闭区间（"不超过X元"）：边界处命中本级、边界加一分命中次级、
  边界减一分仍在本级（邻域宽度 = 申报精度 0.01 元，非政策数值）；
- 税额行为分表断言：综合所得年度表在边界处税额连续（速算扣除数吸收，逐分
  精确相等）；年终奖按月换算表以奖金全额为税基、速算扣除数不随年口径缩放
  → 边界处税额向上跳变（即陷阱区间机制，与基准三衔接）；
- 引擎通路抽查：年度汇算与年终奖单独计税在边界/边界邻域的级次与税额逐一对账，
  含商数定档死区（跳档点 = 月上界 × 月份数 + 商数半分 × 月份数）。

全部期望值由税率表行数据（lower/upper/rate/quick_deduction）独立公式计算，
与引擎双向对账；覆盖全部可用年度规则包。
"""

from decimal import Decimal
from typing import Dict, List

from incometax.benchmark.checks import expect
from incometax.benchmark.metrics import BenchmarkMetric
from incometax.engine.bonus import compute_bonus_separate_tax
from incometax.engine.monthly import MONTHS_PER_YEAR, find_bracket
from incometax.engine.report import MONEY_QUANT, money
from incometax.engine.settlement import SettlementInput, compute_annual_settlement
from incometax.rules.loader import Ruleset

TABLE_ANNUAL = "comprehensive_annual"
TABLE_MONTHLY = "monthly_converted"
EPS = MONEY_QUANT  # 邻域宽度 = 申报精度（0.01 元，申报口径约定，非政策数值）


def _zero_negative_probes(failures: List[str], ruleset: Ruleset, field: str, brackets) -> int:
    """查表前置：应纳税所得额为零与负数必须拒绝（ValueError）。"""
    checks = 0
    for probe in (Decimal(0), -EPS):
        checks += 1
        rejected = False
        try:
            find_bracket(brackets, probe)
        except ValueError:
            rejected = True
        except Exception:  # 非预期异常类型同样视为失败
            rejected = False
        expect(failures, rejected, f"{ruleset.year} {field}", f"查表入参 {probe} 应被拒绝")
    return checks


def _check_annual_boundary(failures: List[str], ruleset: Ruleset, i: int, br, nxt) -> int:
    """综合所得年度表边界：级次切换 + 税额连续 + 年度汇算引擎通路。"""
    checks = 0
    where = f"{ruleset.year} {TABLE_ANNUAL} 边界[{i}]"
    b = br.upper
    checks += 1
    expect(failures, find_bracket(ruleset.comprehensive_brackets, b)[0] == i, where,
           "上界闭：边界处应命中本级")
    checks += 1
    expect(failures, find_bracket(ruleset.comprehensive_brackets, b + EPS)[0] == i + 1, where,
           "边界加一分应命中次级")
    checks += 1
    expect(failures, find_bracket(ruleset.comprehensive_brackets, b - EPS)[0] == i, where,
           "边界减一分应仍在本级")

    left_tax = b * br.rate - br.quick_deduction
    right_tax = b * nxt.rate - nxt.quick_deduction
    checks += 1
    expect(failures, left_tax == right_tax, where,
           f"速算扣除数应吸收级差：左公式 {left_tax} != 右公式 {right_tax}")

    # 引擎通路：年度汇算在边界/邻域的级次与税额
    annual_standard = money(ruleset.monthly_standard_deduction * MONTHS_PER_YEAR)
    report = compute_annual_settlement(
        ruleset, SettlementInput(annual_gross=b + annual_standard)
    )
    checks += 2
    expect(failures, report.bracket_index == i, where, "年度汇算边界处级次不一致")
    expect(failures, report.annual_tax == money(left_tax), where,
           f"年度汇算边界税额 {report.annual_tax} != 公式 {money(left_tax)}")
    report_next = compute_annual_settlement(
        ruleset, SettlementInput(annual_gross=b + EPS + annual_standard)
    )
    checks += 1
    expect(failures, report_next.bracket_index == i + 1, where, "年度汇算边界加一分级次不一致")
    return checks


def _check_monthly_boundary(failures: List[str], ruleset: Ruleset, i: int, br, nxt, divisor: Decimal) -> int:
    """按月换算表边界：查表级次切换 + 年口径税基跳变 + 单独计税引擎通路（含死区）。"""
    checks = 0
    where = f"{ruleset.year} {TABLE_MONTHLY} 边界[{i}]"
    b = br.upper
    checks += 1
    expect(failures, find_bracket(ruleset.monthly_brackets, b)[0] == i, where,
           "上界闭：商数等于月上界时应命中本级")
    checks += 1
    expect(failures, find_bracket(ruleset.monthly_brackets, b + EPS)[0] == i + 1, where,
           "商数加一分应命中次级")
    checks += 1
    expect(failures, find_bracket(ruleset.monthly_brackets, b - EPS)[0] == i, where,
           "商数减一分应仍在本级")

    # 年口径（税基=奖金全额）：速算扣除数不随年缩放 → 边界处右级税额更高（跳变）
    base = b * divisor
    left_tax = base * br.rate - br.quick_deduction
    right_tax = base * nxt.rate - nxt.quick_deduction
    checks += 1
    expect(failures, right_tax > left_tax, where,
           f"年口径边界应跳变：右公式 {right_tax} 未高于左公式 {left_tax}")

    # 引擎通路：边界处命中本级且税额与公式一致；死区末尾跳档、死区内一分仍本级
    report = compute_bonus_separate_tax(ruleset, base)
    checks += 2
    expect(failures, report.bracket_index == i, where, "奖金=年口径边界时应命中本级")
    expect(failures, report.tax == money(base * br.rate - br.quick_deduction), where,
           "奖金边界税额与税率表公式不一致")
    dead_width = divisor * MONEY_QUANT / 2  # 商数定档半分 × 月份数
    report_dead_end = compute_bonus_separate_tax(ruleset, base + dead_width)
    checks += 1
    expect(failures, report_dead_end.bracket_index == i + 1, where,
           f"死区末尾（边界+{dead_width}）应跳档至次级")
    report_in_dead = compute_bonus_separate_tax(ruleset, base + EPS)
    checks += 1
    expect(failures, report_in_dead.bracket_index == i, where, "死区内一分应仍命中本级")
    return checks


def run_rate_boundaries(rulesets: Dict[int, Ruleset]) -> BenchmarkMetric:
    """每项检查失败记一条 failure，最终 通过数 = 总数 − 失败数。"""
    failures: List[str] = []
    total = 0
    boundary_total = 0

    for year in sorted(rulesets):
        ruleset = rulesets[year]
        divisor = Decimal(ruleset.data["bonus"]["monthly_divisor"]["value"])
        for field, brackets in (
            (TABLE_ANNUAL, ruleset.comprehensive_brackets),
            (TABLE_MONTHLY, ruleset.monthly_brackets),
        ):
            total += _zero_negative_probes(failures, ruleset, field, brackets)
            for i, br in enumerate(brackets):
                if br.upper is None:
                    continue
                boundary_total += 1
                nxt = brackets[i + 1]
                if field == TABLE_ANNUAL:
                    total += _check_annual_boundary(failures, ruleset, i, br, nxt)
                else:
                    total += _check_monthly_boundary(failures, ruleset, i, br, nxt, divisor)
    passed = total - len(failures)
    return BenchmarkMetric(
        key="rates",
        title="税率级次临界",
        total=total,
        passed=passed,
        threshold="与规则表自洽 100%",
        summary=f"{len(rulesets)} 个年度 × 两张税率表 {boundary_total} 个有限边界，"
                f"级次切换/税额连续与跳变/引擎通路 {passed}/{total} 自洽",
        stats={"边界数": boundary_total, "覆盖年度": len(rulesets)},
        failures=tuple(failures),
    )
