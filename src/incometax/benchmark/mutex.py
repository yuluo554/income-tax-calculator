"""基准四：扣除互斥与校验组合枚举（全年度规则包 × 组合矩阵）。

口径（plan/04 §3.3 / HANDOFF-M4）：违规组合必须整单拒绝（拒绝率 100%、误放行 0），
有效组合必须放行（误拒 0——防止校验越收越紧误伤正常申报）。组合矩阵：
- 互斥：住房贷款利息 × 住房租金全档位；
- 上限边界：赡养老人每人上限/合计总额的边界值与边界值加一分、负数分摊、
  独生附加共赡养人、未指明独生与否、分摊合计为零；
- 重复申报：同项目重复（继续教育按类型细分，学历与职业资格可并存）；
- 非法字段：未知项目、分摊比例、孩数、申报月数、城市档越界、未指明类型；
- 年度适用：规则包无该扣除项目的年度申报（如早期年度的婴幼儿照护）；
- 有效对照：各项目正常申报（含边界值恰达上限、大病超/未超起付线等）。

全部标准值取自当年规则包（零政策字面量），期望放行与否由规则包结构推导
（如项目键是否存在、申报月数是否超过包内期限）。
"""

from decimal import Decimal
from typing import Dict, List, Sequence, Tuple

from incometax.benchmark.checks import expect
from incometax.benchmark.metrics import BenchmarkMetric
from incometax.engine.deductions import HALF, ONE, Claim, DeductionViolationError, evaluate_claims
from incometax.engine.monthly import MONTHS_PER_YEAR, ZERO
from incometax.rules.loader import Ruleset

CATEGORY_MUTEX = "互斥"
CATEGORY_CAP = "上限边界"
CATEGORY_DUP = "重复申报"
CATEGORY_FIELD = "非法字段"
CATEGORY_YEAR = "年度适用"
CATEGORY_CONTROL = "有效对照"

Combo = Tuple[str, str, Tuple[Claim, ...], bool]


def _build_combos(ruleset: Ruleset) -> List[Combo]:
    """单年度组合矩阵：期望放行与否全部由规则包结构推导。"""
    sd = ruleset.data["special_deductions"]
    cent = Decimal("0.01")
    months_full = MONTHS_PER_YEAR
    has_infant = "infant_care" in sd
    rent_tier_count = len(sd["housing_rent"]["tiers"])
    per_child_cap = Decimal(sd["support_elderly"]["shared_per_child_cap"]["value"])
    total_cap = Decimal(sd["support_elderly"]["shared_total_cap"]["value"])
    threshold = Decimal(sd["serious_illness"]["deductible_threshold"]["value"])
    loan_max_months = int(Decimal(sd["housing_loan"]["max_months"]["value"]))
    academic_max_months = int(Decimal(sd["continue_education"]["academic_max_months"]["value"]))

    combos: List[Combo] = []

    def add(category: str, desc: str, claims: Sequence[Claim], expect_accept: bool) -> None:
        combos.append((category, desc, tuple(claims), expect_accept))

    # —— 有效对照（应放行；误拒即基准失败）——
    add(CATEGORY_CONTROL, "子女教育一方全额",
        [Claim(item="child_education", children=ONE, share_ratio=ONE)], True)
    add(CATEGORY_CONTROL, "子女教育双方各半两名",
        [Claim(item="child_education", children=Decimal(2), share_ratio=HALF)], True)
    add(CATEGORY_CONTROL, "婴幼儿照护",
        [Claim(item="infant_care", children=ONE, share_ratio=HALF)], has_infant)
    add(CATEGORY_CONTROL, "学历继续教育整段申报",
        [Claim(item="continue_education", kind="academic", months=months_full)],
        months_full <= academic_max_months)
    add(CATEGORY_CONTROL, "职业资格继续教育",
        [Claim(item="continue_education", kind="vocational")], True)
    add(CATEGORY_CONTROL, "学历与职业资格同年并存",
        [Claim(item="continue_education", kind="academic", months=months_full),
         Claim(item="continue_education", kind="vocational")], True)
    add(CATEGORY_CONTROL, "大病自付恰超起付线一分",
        [Claim(item="serious_illness", self_paid_total=threshold + cent)], True)
    add(CATEGORY_CONTROL, "大病自付未达起付线",
        [Claim(item="serious_illness", self_paid_total=threshold - cent)], True)
    add(CATEGORY_CONTROL, "住房贷款利息正常申报",
        [Claim(item="housing_loan", months=months_full)], months_full <= loan_max_months)
    for tier in range(rent_tier_count):
        add(CATEGORY_CONTROL, f"住房租金城市档{tier}",
            [Claim(item="housing_rent", tier=tier, months=months_full)], True)
    add(CATEGORY_CONTROL, "赡养老人独生定额",
        [Claim(item="support_elderly", only_child=True)], True)
    add(CATEGORY_CONTROL, "非独生本人分摊恰达每人上限",
        [Claim(item="support_elderly", only_child=False, monthly_amount=per_child_cap)], True)
    add(CATEGORY_CONTROL, "非独生全体分摊恰达总额度",
        [Claim(item="support_elderly", only_child=False, monthly_amount=per_child_cap,
               other_shared_amounts=(total_cap - per_child_cap,))], True)

    # —— 互斥：房贷利息 × 住房租金全档位 ——
    for tier in range(rent_tier_count):
        add(CATEGORY_MUTEX, f"房贷利息与租金档{tier}同报",
            [Claim(item="housing_loan", months=months_full),
             Claim(item="housing_rent", tier=tier, months=months_full)], False)

    # —— 上限边界 ——
    add(CATEGORY_CAP, "本人分摊超每人上限一分",
        [Claim(item="support_elderly", only_child=False, monthly_amount=per_child_cap + cent)], False)
    add(CATEGORY_CAP, "全体分摊超总额度一分",
        [Claim(item="support_elderly", only_child=False, monthly_amount=per_child_cap,
               other_shared_amounts=(total_cap - per_child_cap + cent,))], False)
    add(CATEGORY_CAP, "共赡养人分摊为负",
        [Claim(item="support_elderly", only_child=False, monthly_amount=per_child_cap,
               other_shared_amounts=(-cent,))], False)
    add(CATEGORY_CAP, "独生子女不应提供共赡养人分摊",
        [Claim(item="support_elderly", only_child=True, other_shared_amounts=(per_child_cap,))], False)
    add(CATEGORY_CAP, "未指明是否独生子女",
        [Claim(item="support_elderly")], False)
    add(CATEGORY_CAP, "分摊合计为零",
        [Claim(item="support_elderly", only_child=False, monthly_amount=ZERO)], False)
    add(CATEGORY_CAP, "大病自付为负",
        [Claim(item="serious_illness", self_paid_total=-cent)], False)

    # —— 重复申报 ——
    add(CATEGORY_DUP, "子女教育重复申报",
        [Claim(item="child_education", children=ONE, share_ratio=ONE),
         Claim(item="child_education", children=Decimal(2), share_ratio=HALF)], False)
    add(CATEGORY_DUP, "学历继续教育重复申报",
        [Claim(item="continue_education", kind="academic", months=months_full),
         Claim(item="continue_education", kind="academic", months=months_full)], False)
    add(CATEGORY_DUP, "职业资格重复申报",
        [Claim(item="continue_education", kind="vocational"),
         Claim(item="continue_education", kind="vocational")], False)

    # —— 非法字段 ——
    add(CATEGORY_FIELD, "未知扣除项目", [Claim(item="unknown_item")], False)
    add(CATEGORY_FIELD, "分摊比例不在允许枚举",
        [Claim(item="child_education", share_ratio=HALF / 2)], False)
    add(CATEGORY_FIELD, "孩数为零", [Claim(item="child_education", children=ZERO)], False)
    add(CATEGORY_FIELD, "孩数为负", [Claim(item="child_education", children=-ONE)], False)
    add(CATEGORY_FIELD, "孩数为小数", [Claim(item="child_education", children=ONE + HALF)], False)
    add(CATEGORY_FIELD, "申报月数为零", [Claim(item="housing_loan", months=0)], False)
    add(CATEGORY_FIELD, "申报月数超日历月数",
        [Claim(item="housing_loan", months=MONTHS_PER_YEAR + 1)], False)
    add(CATEGORY_FIELD, "租金城市档越界",
        [Claim(item="housing_rent", tier=rent_tier_count)], False)
    add(CATEGORY_FIELD, "租金城市档为负", [Claim(item="housing_rent", tier=-1)], False)
    add(CATEGORY_FIELD, "继续教育未指明类型",
        [Claim(item="continue_education", kind="")], False)

    # —— 年度适用：规则包无此扣除项目的年度申报 ——
    add(CATEGORY_YEAR, "婴幼儿照护（按年度适用性推导）",
        [Claim(item="infant_care", children=ONE, share_ratio=HALF)], has_infant)

    return combos


def run_mutex_combinations(rulesets: Dict[int, Ruleset]) -> BenchmarkMetric:
    """逐组合执行：违规整单拒绝语义下，断言拒绝/放行与期望一致。"""
    failures: List[str] = []
    total = passed = invalid_total = valid_total = misallowed = misrejected = 0
    for year in sorted(rulesets):
        ruleset = rulesets[year]
        for category, desc, claims, expect_accept in _build_combos(ruleset):
            total += 1
            if expect_accept:
                valid_total += 1
            else:
                invalid_total += 1
            accepted = True
            try:
                evaluate_claims(ruleset, claims)
            except DeductionViolationError:
                accepted = False
            where = f"{year} [{category}] {desc}"
            if expect(failures, accepted == expect_accept, where,
                      f"期望{'放行' if expect_accept else '拒绝'}，实际{'放行' if accepted else '拒绝'}"):
                passed += 1
            elif expect_accept:
                misrejected += 1
            else:
                misallowed += 1
    return BenchmarkMetric(
        key="mutex",
        title="扣除互斥组合",
        total=total,
        passed=passed,
        threshold="误放行 0 且误拒 0",
        summary=f"违规组合 {invalid_total - misallowed}/{invalid_total} 拒绝（误放行 {misallowed}），"
                f"有效组合 {valid_total - misrejected}/{valid_total} 放行（误拒 {misrejected}）",
        stats={
            "违规组合": invalid_total,
            "误放行": misallowed,
            "有效组合": valid_total,
            "误拒": misrejected,
        },
        failures=tuple(failures),
    )
