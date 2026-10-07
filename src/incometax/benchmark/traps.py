"""基准三：年终奖陷阱区间扫描（推导区间 × 端点内外邻域 × 穷举恢复点一致）。

口径（plan/06 M3 定稿 / HANDOFF-M4 既定口径）：
- 区间为开区间：端点不属陷阱；区间内税后到手低于左端锚点，区间外恢复；
- 商数两位定档产生查表死区：实际跳档点晚于级距边界，断言一律从实际跳档点起，
  恢复点 = 推导右端点的申报精度值 money(B*)；
- 穷举用独立实现路径（右级次净额公式 N(B) = B − money(B·r₂ − q₂)）：
  净额逐分非降由量化算术保证（money 对 B 单调、每分原始增量小于半分），
  故"粗扫全区间（1 元步长）+ 恢复窗口逐分细扫"等价于全逐分穷举，
  穷举到的首个恢复分点必须等于推导右端点的申报精度值；
- 引擎与公式双向对账：锚点/跳档点/恢复点邻域的税后净额逐一相等。

覆盖全部推导区间（代表年度深扫 + 全年度推导一致性比对）。
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from incometax.benchmark.checks import expect
from incometax.benchmark.metrics import BenchmarkMetric
from incometax.engine.bonus import (
    BonusTrapInterval,
    compute_bonus_separate_tax,
    derive_bonus_trap_intervals,
    find_trap_interval,
)
from incometax.engine.report import MONEY_QUANT, money
from incometax.rules.loader import Ruleset

CENT = MONEY_QUANT
COARSE_STRIDE = Decimal(1)  # 粗扫步长（元）：计数常数，非政策数值


def _local_net(amount: Decimal, interval: BonusTrapInterval) -> Decimal:
    """独立实现路径：右级次税后净额 N(B) = B − money(B·r₂ − q₂)。"""
    tax = (amount * interval.right_rate - interval.right_quick_deduction).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    return amount - tax


def _dead_zone_switch(failures: List[str], ruleset: Ruleset, interval: BonusTrapInterval,
                      anchor: Decimal, dead_width: Decimal, index: int) -> Tuple[int, Decimal]:
    """从边界 + 一分起逐分扫到实际跳档点；死区内（仍落左级）税后不得低于锚点。

    计数口径：死区整体 1 项。
    """
    where = f"区间[{index}] 死区"
    max_steps = int(dead_width / CENT) + 2
    amount = interval.lower + CENT
    steps = 0
    while True:
        report = compute_bonus_separate_tax(ruleset, amount)
        if report.bracket_index != interval.left_bracket_index:
            break
        expect(failures, report.after_tax >= anchor, where, f"{amount} 仍落左级但税后低于锚点")
        amount += CENT
        steps += 1
        if steps > max_steps:
            expect(failures, False, where,
                   f"逐分扫描超过商数定档死区宽 {dead_width} 仍未跳档")
            break
    return 1, amount


def _brute_force_recovery(failures: List[str], interval: BonusTrapInterval, anchor: Decimal,
                          declared: Decimal, switch: Decimal, index: int) -> Tuple[int, Decimal]:
    """两段穷举：粗扫全区间（1 元步长，采样断言净额非降）→ 恢复窗口逐分细扫。

    净额逐分非降由量化算术保证（模块 docstring），故粗扫不漏窗口；
    恢复窗口（最后低于锚点与首个不低于锚点的粗扫点之间）逐分细扫取首个恢复分点。
    计数口径：粗扫整体 1 项 + 恢复点一致 1 项。
    """
    where = f"区间[{index}] 穷举"
    point = switch
    window_lo: Optional[Decimal] = None
    prev_net: Optional[Decimal] = None
    coarse_hit: Optional[Decimal] = None
    while point <= declared + COARSE_STRIDE:
        net = _local_net(point, interval)
        if prev_net is not None and net < prev_net:
            failures.append(f"{where}: 粗扫 {point} 净额非降被破坏（{prev_net} → {net}）")
            break
        if net >= anchor:
            coarse_hit = point
            break
        window_lo = point
        prev_net = net
        point += COARSE_STRIDE
    checks = 1
    if coarse_hit is None:
        failures.append(f"{where}: 粗扫至推导右端点邻域（上限 {declared + COARSE_STRIDE}）未见恢复点")
        return checks, Decimal(-1)

    recovery = None
    fine = (window_lo if window_lo is not None else coarse_hit - COARSE_STRIDE) + CENT
    while fine <= coarse_hit:
        if _local_net(fine, interval) >= anchor:
            recovery = fine
            break
        fine += CENT
    checks += 1
    expect(failures, recovery == declared, where,
           f"穷举恢复点 {recovery} != 推导右端点申报精度值 {declared}")
    return checks, recovery if recovery is not None else Decimal(-1)


def run_trap_intervals(rulesets: Dict[int, Ruleset], focus_year: int) -> BenchmarkMetric:
    """代表年度深扫全部推导区间 + 全年度推导一致性比对（每项失败记一条）。"""
    failures: List[str] = []
    total = 0
    ruleset = rulesets[focus_year]
    intervals = derive_bonus_trap_intervals(ruleset)

    # 全年度推导一致性：税率表全期间一致 → 推导区间逐年一致
    for year in sorted(rulesets):
        if year == focus_year:
            continue
        total += 1
        expect(failures, derive_bonus_trap_intervals(rulesets[year]) == intervals,
               f"年度 {year}", "推导区间与代表年度不一致")

    # 机制结构：区间下端集合 == 年口径跳变边界集合（右级税额 > 左级税额）
    divisor = Decimal(ruleset.data["bonus"]["monthly_divisor"]["value"])
    brackets = ruleset.monthly_brackets
    jump_boundaries = []
    for i in range(len(brackets) - 1):
        boundary = brackets[i].upper * divisor
        left_tax = boundary * brackets[i].rate - brackets[i].quick_deduction
        right_tax = boundary * brackets[i + 1].rate - brackets[i + 1].quick_deduction
        if right_tax > left_tax:
            jump_boundaries.append(boundary)
    total += 1
    expect(failures, [iv.lower for iv in intervals] == jump_boundaries, "机制结构",
           "推导区间下端与跳变边界集合不一致")

    dead_width = divisor * CENT / 2
    recovered_count = 0
    for index, interval in enumerate(intervals, start=1):
        where = f"区间[{index}] ({money(interval.lower)}, {money(interval.upper)})"
        anchor_report = compute_bonus_separate_tax(ruleset, interval.lower)
        anchor = anchor_report.after_tax
        total += 1
        if not expect(failures, anchor_report.bracket_index == interval.left_bracket_index, where,
                      "左端点应命中左级次"):
            continue

        checks, switch = _dead_zone_switch(failures, ruleset, interval, anchor, dead_width, index)
        total += checks
        total += 1
        if not expect(failures, switch - interval.lower == dead_width, where,
                      f"实际跳档点 {switch} 偏移 {switch - interval.lower} != 商数定档死区宽 {dead_width}"):
            continue  # 死区口径被破坏，本区间后续断言失去前提
        switch_report = compute_bonus_separate_tax(ruleset, switch)
        total += 3
        expect(failures, switch_report.bracket_index == interval.right_bracket_index, where,
               "实际跳档点应命中右级次")
        expect(failures, switch_report.after_tax == _local_net(switch, interval), where,
               f"引擎税后 {switch_report.after_tax} != 独立公式净额 {_local_net(switch, interval)}")
        expect(failures, switch_report.after_tax < anchor, where, "跳档即应落入陷阱（税后低于锚点）")

        declared = money(interval.upper)
        checks, recovery = _brute_force_recovery(failures, interval, anchor, declared, switch, index)
        total += checks
        if recovery == declared:
            recovered_count += 1

        # 端点内外邻域（申报精度逐分）：恢复点恢复、前一分仍在区间内、区间外保持恢复
        declared_report = compute_bonus_separate_tax(ruleset, declared)
        total += 4
        expect(failures, declared_report.bracket_index == interval.right_bracket_index, where,
               "恢复点应命中右级次")
        expect(failures, declared_report.after_tax >= anchor, where, "恢复点税后应追平锚点")
        expect(failures, compute_bonus_separate_tax(ruleset, declared - CENT).after_tax < anchor,
               where, "恢复点前一分仍应在区间内（税后低于锚点）")
        expect(failures, compute_bonus_separate_tax(ruleset, declared + CENT).after_tax >= anchor,
               where, "区间外一分应保持恢复")

        midpoint = money(interval.lower + (interval.upper - interval.lower) / 2)
        total += 1
        expect(failures, compute_bonus_separate_tax(ruleset, midpoint).after_tax < anchor, where,
               f"区间中点 {midpoint} 税后应低于锚点")

        # 开区间语义：精确端点不命中（M3 语义）；申报精度右端点的区间归属由其
        # 与精确上端的相对位置推导——money(B*) 向下取整时仍严格小于精确上端，
        # 属区间内（该点税后已在申报精度追平锚点，见恢复点断言），两者不矛盾。
        declared_inside = interval.lower < declared < interval.upper
        total += 5
        expect(failures, find_trap_interval(intervals, interval.lower) is None, where,
               "左端点不应命中（开区间）")
        expect(failures, find_trap_interval(intervals, interval.upper) is None, where,
               "精确右端点不应命中（开区间）")
        expect(failures, (find_trap_interval(intervals, declared) is interval) == declared_inside,
               where, "申报精度右端点的区间归属与推导不一致")
        expect(failures, find_trap_interval(intervals, interval.lower + CENT) is interval, where,
               "左端点加一分应命中本区间")
        expect(failures, find_trap_interval(intervals, declared - CENT) is interval, where,
               "恢复点前一分应命中本区间")

    return BenchmarkMetric(
        key="traps",
        title="陷阱区间",
        total=total,
        passed=total - len(failures),
        threshold="穷举恢复点与推导端点一致 100%",
        summary=f"{len(intervals)} 个推导区间：死区 + 端点内外邻域 + 粗细两段穷举，"
                f"恢复点与推导右端点申报精度值一致 {recovered_count}/{len(intervals)}",
        stats={"区间数": len(intervals), "穷举一致": recovered_count},
        failures=tuple(failures),
    )
