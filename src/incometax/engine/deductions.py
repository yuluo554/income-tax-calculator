"""FR-3 七项专项附加扣除管理引擎（M3 实装）。

设计定稿：plan/04 §3.3。要点：
- 分档标准计算：子女教育/婴幼儿照护按孩数×分摊比例，住房租金按城市档，
  继续教育分学历（按月）与职业资格（年度定额），全部标准值查规则包；
- 房贷利息与住房租金互斥校验（规则包 housing_loan_vs_rent 显式门控 +
  housing_rent.mutually_exclusive_with 条款 ref），违规整单拒绝、误放行 0；
- 赡养老人独生定额 vs 非独生分摊上限校验（每人上限 + 合计上限）；
- 大病医疗 stage=settlement_only（规则包 claimable_stage.stage 标记）：
  预扣链月额恒为 0、汇算链按起付线/限额计算纳入；
- 输出逐项 ClaimResult（月额/年额 + 依据 ref），供 monthly / settlement 链汇总。

校验失败语义：所有违规（互斥/分摊/分档/上限/未知项目/重复申报）收集后一次性
抛 DeductionViolationError（继承 ValueError）——不产出部分结果的 Report，
杜绝违规组合被部分放行。引擎入口只接受 effective_ruleset() 放行的规则包。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from incometax.engine.monthly import MONTHS_PER_YEAR, ZERO
from incometax.engine.report import money, short_ref
from incometax.rules.loader import Ruleset

ONE = Decimal(1)
HALF = Decimal("0.5")

STAGE_BOTH = "withholding_and_settlement"  # 预扣链与汇算链均可扣
STAGE_SETTLEMENT_ONLY = "settlement_only"  # 仅年度汇算扣除（预扣链剔除）

# 七项扣除的规则包键（婴幼儿照护自设立纳税年度起适用，早期年度规则包无此键）
KNOWN_ITEMS = (
    "child_education",
    "infant_care",
    "continue_education",
    "serious_illness",
    "housing_loan",
    "housing_rent",
    "support_elderly",
)

EDUCATION_KINDS = ("academic", "vocational")


@dataclass(frozen=True)
class Claim:
    """单项扣除申报（金额一律 Decimal；字段按 item 取用，非法组合被校验拒绝）。"""

    item: str
    children: Decimal = ONE  # child_education / infant_care：孩数（整数 ≥ 1）
    share_ratio: Decimal = ONE  # child_education / infant_care：本方分摊比例（100% 或 50%）
    kind: str = ""  # continue_education：academic（学历）/ vocational（职业资格）
    months: int = MONTHS_PER_YEAR  # 按月类扣除的申报月数（1-12）
    tier: int = -1  # housing_rent：城市档下标（0 基，对应规则包 tiers[]）
    only_child: Optional[bool] = None  # support_elderly：是否独生子女（必填）
    monthly_amount: Decimal = ZERO  # support_elderly 非独生：本人月分摊额
    other_shared_amounts: Tuple[Decimal, ...] = ()  # support_elderly 非独生：其他共赡养人月分摊额
    self_paid_total: Decimal = ZERO  # serious_illness：医保目录范围内自付累计
    note: str = ""


@dataclass(frozen=True)
class Violation:
    """单条校验违规：项目 + 原因 + 依据（规则包原始 ref 节点，可为 None）。"""

    item: str
    reason: str
    ref: Optional[Dict[str, Any]] = None


class DeductionViolationError(ValueError):
    """扣除申报校验未通过（收集全部违规后整单拒绝）。"""

    def __init__(self, violations: Sequence[Violation]):
        self.violations = tuple(violations)
        lines = []
        for v in self.violations:
            basis = f"（依据：{short_ref(v.ref)}）" if v.ref else ""
            lines.append(f"  - [{v.item}] {v.reason}{basis}")
        super().__init__("共 {} 项违规：\n{}".format(len(self.violations), "\n".join(lines)))


@dataclass(frozen=True)
class ClaimResult:
    """单项扣除计算结果（供 monthly / settlement 链与清单渲染消费）。"""

    item: str
    kind: str  # continue_education 细分；其余空串
    stage: str  # STAGE_BOTH / STAGE_SETTLEMENT_ONLY
    monthly_amount: Decimal  # 计入预扣链的月额（settlement_only 恒为 0）
    months_claimed: int
    annual_amount: Decimal  # 计入汇算链的年额（月额×月数 或 定额/限额结果）
    detail: str  # 计算式描述（用户输入侧，供清单渲染）
    standard_ref: Dict[str, Any]  # 金额标准依据（规则包原始 ref 节点）
    note: str = ""


@dataclass(frozen=True)
class DeductionsReport:
    """扣除申报整体结果：预扣链月合计 / 汇算链年合计分列（stage 分离）。"""

    claims: Tuple[ClaimResult, ...]
    monthly_total: Decimal  # 预扣链月合计（逐月填入 MonthInput.special_additional_deduction）
    annual_total: Decimal  # 汇算链年合计（= 预扣链项目年额 + 仅汇算项目年额）
    settlement_only_annual_total: Decimal  # 仅汇算链项目的年额合计（汇算聚合时单独加回）


def _add(violations: List[Violation], item: str, reason: str, ref=None) -> None:
    violations.append(Violation(item=item, reason=reason, ref=ref))


def _check_months(violations: List[Violation], claim: Claim) -> bool:
    if not isinstance(claim.months, int) or isinstance(claim.months, bool):
        _add(violations, claim.item, f"申报月数必须为整数，收到 {claim.months!r}")
        return False
    if not 1 <= claim.months <= MONTHS_PER_YEAR:
        _add(
            violations,
            claim.item,
            f"申报月数必须在 1-{MONTHS_PER_YEAR} 内，收到 {claim.months}",
        )
        return False
    return True


def _compute_children_based(
    node: Dict[str, Any], violations: List[Violation], claim: Claim
) -> Optional[Tuple[Decimal, Dict[str, Any], str]]:
    """子女教育 / 婴幼儿照护共用：标准 × 孩数 × 分摊比例。"""
    split_ref = node.get("split_mode", {}).get("ref")
    if claim.children != claim.children.to_integral_value() or claim.children < ONE:
        _add(violations, claim.item, f"孩数必须为不小于 1 的整数，收到 {claim.children}")
        return None
    if claim.share_ratio not in (ONE, HALF):
        _add(
            violations,
            claim.item,
            f"分摊比例只能为 100%（一方全额）或 50%（双方各半），收到 {claim.share_ratio}",
            split_ref,
        )
        return None
    per_child = Decimal(node["monthly_per_child"]["value"])
    monthly = money(per_child * claim.children * claim.share_ratio)
    detail = (
        f"{per_child:.2f} 元/孩/月 × {claim.children.to_integral_value()} 孩 × "
        f"分摊 {claim.share_ratio * 100:.0f}%"
    )
    return monthly, node["monthly_per_child"]["ref"], detail


def _claim_duplicate_keys(claims: Sequence[Claim]) -> List[Tuple[str, str]]:
    """重复申报键：同项目（继续教育按 kind 细分）只能申报一次。"""
    seen = []
    dup = []
    for claim in claims:
        key = (claim.item, claim.kind)
        if key in seen and key not in dup:
            dup.append(key)
        seen.append(key)
    return dup


def _compute_claim(
    ruleset: Ruleset, claim: Claim, violations: List[Violation]
) -> Optional[ClaimResult]:
    """单项计算；违规写入 violations 并返回 None（不产出部分结果）。"""
    sd = ruleset.data["special_deductions"]
    if claim.item == "child_education":
        return _item_children_based(sd, claim, violations, "child_education")
    if claim.item == "infant_care":
        return _item_children_based(sd, claim, violations, "infant_care")
    if claim.item == "continue_education":
        return _item_continue_education(sd, claim, violations)
    if claim.item == "serious_illness":
        return _item_serious_illness(sd, claim, violations)
    if claim.item == "housing_loan":
        return _item_housing_loan(sd, claim, violations)
    if claim.item == "housing_rent":
        return _item_housing_rent(sd, claim, violations)
    if claim.item == "support_elderly":
        return _item_support_elderly(sd, claim, violations)
    _add(violations, claim.item, f"未知扣除项目（允许：{', '.join(KNOWN_ITEMS)}）")
    return None


def _item_children_based(
    sd: Dict[str, Any], claim: Claim, violations: List[Violation], key: str
) -> Optional[ClaimResult]:
    if key not in sd:
        _add(
            violations,
            claim.item,
            f"该纳税年度规则包无此扣除项（{key}），不能申报",
        )
        return None
    computed = _compute_children_based(sd[key], violations, claim)
    if computed is None or not _check_months(violations, claim):
        return None
    monthly, standard_ref, detail = computed
    annual = money(monthly * claim.months)
    return ClaimResult(
        item=claim.item,
        kind="",
        stage=STAGE_BOTH,
        monthly_amount=monthly,
        months_claimed=claim.months,
        annual_amount=annual,
        detail=detail,
        standard_ref=standard_ref,
        note=claim.note,
    )


def _item_continue_education(
    sd: Dict[str, Any], claim: Claim, violations: List[Violation]
) -> Optional[ClaimResult]:
    node = sd["continue_education"]
    if claim.kind not in EDUCATION_KINDS:
        _add(
            violations,
            claim.item,
            f"继续教育必须指明类型 academic（学历）或 vocational（职业资格），收到 {claim.kind!r}",
            node["academic_monthly"]["ref"],
        )
        return None
    if claim.kind == "academic":
        if not _check_months(violations, claim):
            return None
        max_months = int(Decimal(node["academic_max_months"]["value"]))
        if claim.months > max_months:
            _add(
                violations,
                claim.item,
                f"学历继续教育同一学位扣除期限不能超过 {max_months} 个月，收到 {claim.months} 个月",
                node["academic_max_months"]["ref"],
            )
            return None
        monthly = money(Decimal(node["academic_monthly"]["value"]))
        return ClaimResult(
            item=claim.item,
            kind=claim.kind,
            stage=STAGE_BOTH,
            monthly_amount=monthly,
            months_claimed=claim.months,
            annual_amount=money(monthly * claim.months),
            detail=f"学历（学位）继续教育 {monthly:.2f} 元/月 × {claim.months} 个月",
            standard_ref=node["academic_monthly"]["ref"],
            note=claim.note,
        )
    # 职业资格：取得证书当年定额，一次性扣除 → 本工具计入汇算链（月额 0）
    annual = money(Decimal(node["vocational_annual"]["value"]))
    return ClaimResult(
        item=claim.item,
        kind=claim.kind,
        stage=STAGE_SETTLEMENT_ONLY,
        monthly_amount=ZERO,
        months_claimed=0,
        annual_amount=annual,
        detail=f"职业资格继续教育取得证书当年定额 {annual:.2f} 元（计入年度汇算链）",
        standard_ref=node["vocational_annual"]["ref"],
        note="；".join(filter(None, [claim.note, "年度定额一次性扣除，汇算链计入"])),
    )


def _item_serious_illness(
    sd: Dict[str, Any], claim: Claim, violations: List[Violation]
) -> Optional[ClaimResult]:
    node = sd["serious_illness"]
    stage_node = node.get("claimable_stage", {})
    stage = stage_node.get("stage", STAGE_SETTLEMENT_ONLY)
    if stage != STAGE_SETTLEMENT_ONLY:
        # 规则包阶段标记异常属于规则包合法性问题（非用户输入错误）→ 计算失败
        raise ValueError(
            f"serious_illness.claimable_stage.stage 非法：{stage!r}（应为 {STAGE_SETTLEMENT_ONLY}）"
        )
    if claim.self_paid_total < ZERO:
        _add(
            violations,
            claim.item,
            f"医保目录范围内自付累计不能为负：{claim.self_paid_total}",
            stage_node.get("ref"),
        )
        return None
    threshold = Decimal(node["deductible_threshold"]["value"])
    cap = Decimal(node["annual_cap"]["value"])
    deductible = min(max(claim.self_paid_total - threshold, ZERO), cap)
    annual = money(deductible)
    note = "仅年度汇算清缴时扣除，预扣环节不可扣（预扣链月额 0）"
    if claim.self_paid_total <= threshold:
        note += "；自付累计未超起付线，可扣除额为 0"
    return ClaimResult(
        item=claim.item,
        kind="",
        stage=STAGE_SETTLEMENT_ONLY,
        monthly_amount=ZERO,
        months_claimed=0,
        annual_amount=annual,
        detail=(
            f"（自付累计 {claim.self_paid_total:.2f} − 起付线 {threshold:.2f}）"
            f"取正值后与限额 {cap:.2f} 取低 → {annual:.2f}"
        ),
        standard_ref=node["deductible_threshold"]["ref"],
        note="；".join(filter(None, [claim.note, note])),
    )


def _item_housing_loan(
    sd: Dict[str, Any], claim: Claim, violations: List[Violation]
) -> Optional[ClaimResult]:
    node = sd["housing_loan"]
    if not _check_months(violations, claim):
        return None
    max_months = int(Decimal(node["max_months"]["value"]))
    if claim.months > max_months:
        _add(
            violations,
            claim.item,
            f"住房贷款利息扣除期限最长不超过 {max_months} 个月，收到 {claim.months} 个月",
            node["max_months"]["ref"],
        )
        return None
    monthly = money(Decimal(node["monthly"]["value"]))
    return ClaimResult(
        item=claim.item,
        kind="",
        stage=STAGE_BOTH,
        monthly_amount=monthly,
        months_claimed=claim.months,
        annual_amount=money(monthly * claim.months),
        detail=f"首套住房贷款利息定额 {monthly:.2f} 元/月 × {claim.months} 个月（夫妻约定由一方全额扣除）",
        standard_ref=node["monthly"]["ref"],
        note=claim.note,
    )


def _item_housing_rent(
    sd: Dict[str, Any], claim: Claim, violations: List[Violation]
) -> Optional[ClaimResult]:
    node = sd["housing_rent"]
    tiers = node["tiers"]
    if not isinstance(claim.tier, int) or isinstance(claim.tier, bool):
        _add(violations, claim.item, f"城市档必须为整数下标，收到 {claim.tier!r}")
        return None
    if not 0 <= claim.tier < len(tiers):
        _add(
            violations,
            claim.item,
            f"城市档下标必须在 0-{len(tiers) - 1} 内（对应规则包租金分档），收到 {claim.tier}",
            tiers[0]["tier"]["ref"] if tiers else None,
        )
        return None
    if not _check_months(violations, claim):
        return None
    tier_node = tiers[claim.tier]
    monthly = money(Decimal(tier_node["monthly"]["value"]))
    tier_desc = str(tier_node["tier"].get("desc", ""))
    return ClaimResult(
        item=claim.item,
        kind="",
        stage=STAGE_BOTH,
        monthly_amount=monthly,
        months_claimed=claim.months,
        annual_amount=money(monthly * claim.months),
        detail=f"主要工作城市租金分档（{tier_desc}）{monthly:.2f} 元/月 × {claim.months} 个月",
        standard_ref=tier_node["monthly"]["ref"],
        note="；".join(filter(None, [claim.note, f"城市档：{tier_desc}"])),
    )


def _item_support_elderly(
    sd: Dict[str, Any], claim: Claim, violations: List[Violation]
) -> Optional[ClaimResult]:
    node = sd["support_elderly"]
    mode_ref = node["shared_mode"]["ref"]
    if claim.only_child is None:
        _add(violations, claim.item, "必须指明是否独生子女（only_child）", mode_ref)
        return None
    if not _check_months(violations, claim):
        return None
    if claim.only_child:
        if claim.other_shared_amounts:
            _add(
                violations,
                claim.item,
                "独生子女定额扣除不存在共赡养人分摊，不应提供 other_shared_amounts",
                mode_ref,
            )
            return None
        monthly = money(Decimal(node["only_child_monthly"]["value"]))
        return ClaimResult(
            item=claim.item,
            kind="",
            stage=STAGE_BOTH,
            monthly_amount=monthly,
            months_claimed=claim.months,
            annual_amount=money(monthly * claim.months),
            detail=f"独生子女定额 {monthly:.2f} 元/月 × {claim.months} 个月",
            standard_ref=node["only_child_monthly"]["ref"],
            note=claim.note,
        )

    per_child_cap = Decimal(node["shared_per_child_cap"]["value"])
    total_cap = Decimal(node["shared_total_cap"]["value"])
    if claim.monthly_amount < ZERO:
        _add(violations, claim.item, f"本人月分摊额不能为负：{claim.monthly_amount}", mode_ref)
        return None
    if claim.monthly_amount > per_child_cap:
        _add(
            violations,
            claim.item,
            f"非独生子女本人月分摊额 {claim.monthly_amount} 超过每人上限 {per_child_cap}",
            node["shared_per_child_cap"]["ref"],
        )
        return None
    others = list(claim.other_shared_amounts)
    if any(amount < ZERO for amount in others):
        _add(violations, claim.item, "其他共赡养人分摊额不能为负", mode_ref)
        return None
    shared_total = claim.monthly_amount + sum(others, ZERO)
    if shared_total > total_cap:
        _add(
            violations,
            claim.item,
            f"全体赡养人月分摊合计 {shared_total} 超过扣除总额度 {total_cap}",
            node["shared_total_cap"]["ref"],
        )
        return None
    if shared_total <= ZERO:
        _add(
            violations,
            claim.item,
            f"全体赡养人月分摊合计必须为正数，收到 {shared_total}",
            mode_ref,
        )
        return None
    monthly = money(claim.monthly_amount)
    others_text = "+ 其他共赡养人 " + " + ".join(f"{a:.2f}" for a in others) if others else ""
    return ClaimResult(
        item=claim.item,
        kind="",
        stage=STAGE_BOTH,
        monthly_amount=monthly,
        months_claimed=claim.months,
        annual_amount=money(monthly * claim.months),
        detail=(
            f"非独生子女分摊：本人 {monthly:.2f} 元/月{others_text}"
            f"（合计上限 {total_cap:.2f}、每人上限 {per_child_cap:.2f}）× {claim.months} 个月"
        ),
        standard_ref=node["shared_per_child_cap"]["ref"],
        note=claim.note,
    )


def _normalize_claim(claim: Claim) -> Claim:
    """数值字段统一 Decimal 化（调用方可能传 int/str；引擎内部只处理 Decimal）。"""
    kwargs: Dict[str, Any] = {
        "item": claim.item,
        "kind": claim.kind,
        "months": claim.months,
        "tier": claim.tier,
        "only_child": claim.only_child,
        "note": claim.note,
    }
    for key in ("children", "share_ratio", "monthly_amount", "self_paid_total"):
        kwargs[key] = Decimal(getattr(claim, key))
    kwargs["other_shared_amounts"] = tuple(Decimal(a) for a in claim.other_shared_amounts)
    return Claim(**kwargs)


def evaluate_claims(ruleset: Ruleset, claims: Sequence[Claim]) -> DeductionsReport:
    """校验并计算扣除申报清单（引擎入口只接受 effective_ruleset() 放行的规则包）。

    互斥/分摊/分档/上限校验全部通过才产出 DeductionsReport；任一违规 →
    DeductionViolationError（携带全部违规清单），不产出部分结果（误放行 0）。
    """
    from incometax.rules.loader import effective_ruleset

    ruleset = effective_ruleset(ruleset)
    claim_list = [_normalize_claim(c) for c in claims]
    violations: List[Violation] = []

    for claim in claim_list:
        if claim.item not in KNOWN_ITEMS:
            _add(violations, claim.item, f"未知扣除项目（允许：{', '.join(KNOWN_ITEMS)}）")
    for item, kind in _claim_duplicate_keys(claim_list):
        label = f"{item}/{kind}" if kind else item
        _add(violations, item, f"同一扣除项目重复申报：{label}")

    # 房贷利息与住房租金互斥（规则包显式互斥标记 + 条款依据）
    items = {claim.item for claim in claim_list}
    mutex_pair = {"housing_loan", "housing_rent"}
    if mutex_pair <= items:
        rent_node = ruleset.data["special_deductions"]["housing_rent"]
        mutex_flag = ruleset.data["special_deductions"].get("housing_loan_vs_rent")
        if mutex_flag != "mutually_exclusive":
            raise ValueError(
                f"special_deductions.housing_loan_vs_rent 非法：{mutex_flag!r}"
                "（应为 mutually_exclusive）"
            )
        _add(
            violations,
            "housing_loan+housing_rent",
            "住房贷款利息与住房租金不得同时申报（一个纳税年度内不能同时分别享受）",
            rent_node["mutually_exclusive_with"]["ref"],
        )

    results = []
    if not violations:
        for claim in claim_list:
            result = _compute_claim(ruleset, claim, violations)
            if result is not None:
                results.append(result)

    if violations:
        raise DeductionViolationError(violations)

    monthly_total = money(sum((r.monthly_amount for r in results), ZERO))
    settlement_only_annual = sum(
        (r.annual_amount for r in results if r.stage == STAGE_SETTLEMENT_ONLY), ZERO
    )
    annual_total = money(
        sum(
            (
                r.annual_amount for r in results if r.stage == STAGE_BOTH
            ),
            ZERO,
        )
        + settlement_only_annual
    )
    return DeductionsReport(
        claims=tuple(results),
        monthly_total=monthly_total,
        annual_total=annual_total,
        settlement_only_annual_total=money(settlement_only_annual),
    )
