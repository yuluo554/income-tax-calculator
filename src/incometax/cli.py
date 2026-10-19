"""CLI 通路（M2：calc 已实装，消费引擎 Report 渲染）。

退出码语义（定稿，锁进 tests/test_cli.py，不得漂移）：
  0 = 成功
  1 = 运行期失败（status 门控拦截 / 计算期失败）
  2 = 用法与输入错误（参数缺失、输入 JSON 非法、年度无规则包、schema 非法、数据目录缺失）

控制台兼容：main() 入口在现编码无法承载中文时把 stdio 切到 UTF-8（见 `_ensure_utf8_stdio`），
故中文标题/依据在 cp936 控制台与 cp1252 管道下均不抛 UnicodeEncodeError；状态标记用 ASCII。
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from incometax import __version__
from incometax.benchmark.runner import run_all
from incometax.engine import bonus as bonus_engine
from incometax.engine import deductions as deductions_engine
from incometax.engine import monthly as monthly_engine
from incometax.engine import pipeline as pipeline_engine
from incometax.engine import settlement as settlement_engine
from incometax.engine import social as social_engine
from incometax.engine.monthly import MONTHS_PER_YEAR, MonthInput
from incometax.engine.report import money, render_ref, short_ref
from incometax.rules import loader
from incometax.rules.schema import RulesetSchemaError, to_decimal

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2


class CliUsageError(Exception):
    """输入/用法错误 → 退出码 2。"""


class RuntimeFailure(Exception):
    """运行期失败 → 退出码 1。"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="incometax",
        description="个人所得税联动计算器（全本地计算，结果仅供参考，以税务机关核定为准）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data-dir",
        help="规则包数据目录（含 rules/ 子目录）；默认按自动定位顺序查找",
    )
    sub = parser.add_subparsers(dest="command", metavar="命令")
    sub.required = True

    p_rules = sub.add_parser("rules", help="查看年度规则包与核对状态（不参与计算）")
    p_rules.add_argument("--year", type=int, required=True, help="规则包年度（需已有对应规则包文件）")
    p_rules.set_defaults(func=cmd_rules)

    p_calc = sub.add_parser(
        "calc",
        help="计算：累计预扣逐月表 + 社保联动 + 专项附加扣除 + 年度汇算 + 年终奖择优与临界区间",
    )
    p_calc.add_argument("--year", type=int, required=True, help="适用纳税年度（需已有对应规则包文件）")
    p_calc.add_argument(
        "--input",
        help="计算输入 JSON 文件路径（格式见 README「calc 输入格式」）",
    )
    p_calc.set_defaults(func=cmd_calc)

    p_bench = sub.add_parser(
        "benchmark",
        help="内置评测基准一条命令跑全：算例回归 + 税率级次临界 + 陷阱区间 + 扣除互斥组合",
    )
    p_bench.add_argument(
        "--year",
        type=int,
        default=None,
        help="陷阱区间穷举深扫的代表年度（缺省 = 最新可用年度）",
    )
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def _load_or_usage_error(year: int, data_dir):
    try:
        return loader.load_ruleset(year, data_dir=data_dir)
    except loader.RulesetNotFoundError as exc:
        raise CliUsageError(str(exc))
    except loader.DataDirNotFoundError as exc:
        raise CliUsageError(str(exc))
    except RulesetSchemaError as exc:
        raise CliUsageError(f"规则包 schema 非法（年度 {year}）：{exc}")

def cmd_rules(args) -> int:
    ruleset = _load_or_usage_error(args.year, args.data_dir)
    report = loader.status_report(ruleset)
    print(f"年度规则包 {ruleset.year}（schema v1）")
    print(f"文件：{ruleset.path}")
    review = ruleset.data.get("review", {})
    if review:
        print(
            f"核对日期:{review.get('reviewed_at', '')}；"
            f"下次复核:{review.get('next_review', '')}"
        )
        print(f"依据年度:{review.get('basis_year', '')}；口径：{review.get('scope_note', '')}")
    for src in ruleset.data["sources"]:
        note = f"（{src['note']}）" if src.get("note") else ""
        print(f"  来源 {src['id']}：{src['doc']} [状态:{src['status']}]{note}")
    print(f"数值条目：已核对 {report.verified} 条 / 待核对 {report.pending} 条")
    if report.pending_paths:
        print("待核对条目（逐条挂原文核对后才可生效）：")
        for path in report.pending_paths[:10]:
            print(f"  - {path}")
        if len(report.pending_paths) > 10:
            print(f"  ...共 {len(report.pending_paths)} 条")
        print("[!!] 门控状态：存在待核对条目，计算引擎拒绝生效")
    else:
        print("[OK] 门控状态：全部已核对，可生效")
    print("免责声明：计算结果供参考，以税务机关核定为准；政策以发文机关正式文本为准。")
    return EXIT_OK


# ---------------------------------------------------------------------------
# calc 输入解析（JSON → 引擎输入；全部非法输入 → CliUsageError → 退出码 2）
# ---------------------------------------------------------------------------

MONTH_FIELDS = (
    "gross",
    "tax_free",
    "special_deduction",
    "special_additional_deduction",
    "other_deduction",
)
SETTLEMENT_FIELDS = (
    "annual_gross",
    "annual_special_deduction",
    "annual_special_additional_deduction",
    "annual_other_deduction",
    "withheld_total",
)


@dataclass
class CalcInput:
    months: List[MonthInput] = field(default_factory=list)
    social_params: Optional[Tuple[Any, Any, Any, Any]] = None  # (base_input, rates, lower, upper)
    bonus_income: Optional[Decimal] = None
    settlement_overrides: Dict[str, Decimal] = field(default_factory=dict)
    claims: List[deductions_engine.Claim] = field(default_factory=list)  # 七项专项附加申报


def _user_decimal(node: Dict[str, Any], key: str, where: str) -> Decimal:
    try:
        return to_decimal(node[key], f"{where}.{key}")
    except KeyError:
        raise CliUsageError(f"{where}: 缺少必填字段 {key}")
    except Exception as exc:  # to_decimal 抛 RulesetSchemaError → 用法错误
        raise CliUsageError(f"{where}.{key}: {exc}")


def _optional_decimal(node: Dict[str, Any], key: str, where: str) -> Optional[Decimal]:
    if key not in node:
        return None
    try:
        return to_decimal(node[key], f"{where}.{key}")
    except Exception as exc:
        raise CliUsageError(f"{where}.{key}: {exc}")


def _check_unknown_keys(node: Dict[str, Any], allowed, where: str) -> None:
    unknown = sorted(set(node) - set(allowed))
    if unknown:
        raise CliUsageError(f"{where}: 不认识的字段 {unknown}（允许：{sorted(allowed)}）")


def _parse_month_object(node: Any, where: str) -> MonthInput:
    if not isinstance(node, dict):
        raise CliUsageError(f"{where}: 月度输入必须是对象")
    _check_unknown_keys(node, MONTH_FIELDS, where)
    kwargs = {}
    for key in MONTH_FIELDS:
        value = _optional_decimal(node, key, where)
        kwargs[key] = value if value is not None else Decimal(0)
    return MonthInput(**kwargs)


def _parse_calc_months(raw: Dict[str, Any]) -> List[MonthInput]:
    """月度输入：months 显式列表 或 uniform_month+month_count；缺月按 0 补足 12 个月。"""
    has_months = "months" in raw
    has_uniform = "uniform_month" in raw or "month_count" in raw
    if has_months and has_uniform:
        raise CliUsageError("calc 输入：months 与 uniform_month/month_count 只能二选一")

    months: List[MonthInput] = []
    if has_months:
        nodes = raw["months"]
        if not isinstance(nodes, list) or not nodes:
            raise CliUsageError("calc 输入：months 必须为非空数组")
        if len(nodes) > MONTHS_PER_YEAR:
            raise CliUsageError(f"calc 输入：months 最多 {MONTHS_PER_YEAR} 个月，收到 {len(nodes)} 个")
        months = [_parse_month_object(node, f"months[{i}]") for i, node in enumerate(nodes)]
    elif has_uniform:
        uniform = _parse_month_object(raw.get("uniform_month", {}), "uniform_month")
        count = raw.get("month_count")
        if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= MONTHS_PER_YEAR):
            raise CliUsageError(f"calc 输入：month_count 必须为 1-{MONTHS_PER_YEAR} 的整数")
        months = [uniform] * count
    else:
        raise CliUsageError("calc 输入：缺少月度输入（months 列表，或 uniform_month+month_count）")

    for i in range(len(months), MONTHS_PER_YEAR):
        months.append(MonthInput(note="未提供，按 0 处理"))
    return months


def _parse_calc_social(raw: Dict[str, Any]) -> Optional[Tuple[Any, Any, Any, Any]]:
    if "social" not in raw or raw["social"] is None:
        return None
    node = raw["social"]
    where = "social"
    if not isinstance(node, dict):
        raise CliUsageError(f"{where}: 必须为对象")
    _check_unknown_keys(node, ("base_input", "base_lower", "base_upper", "rates"), where)
    base_input = _user_decimal(node, "base_input", where)
    base_lower = _optional_decimal(node, "base_lower", where)
    base_upper = _optional_decimal(node, "base_upper", where)
    if (base_lower is None) != (base_upper is None):
        raise CliUsageError(f"{where}: base_lower 与 base_upper 必须成对提供（夹取区间）")
    if base_lower is None:
        raise CliUsageError(f"{where}: 缺少 base_lower/base_upper（缴费基数上下限，用户输入）")
    rates = node.get("rates")
    if not isinstance(rates, dict) or not rates:
        raise CliUsageError(f"{where}.rates: 必须为非空对象（{{险种名: 个人费率}}）")
    parsed_rates = {}
    for label, value in rates.items():
        try:
            parsed_rates[str(label)] = to_decimal(value, f"{where}.rates.{label}")
        except Exception as exc:
            raise CliUsageError(f"{where}.rates.{label}: {exc}")
    return (base_input, parsed_rates, base_lower, base_upper)


def _parse_calc_settlement(raw: Dict[str, Any]) -> Dict[str, Decimal]:
    if "settlement" not in raw or raw["settlement"] is None:
        return {}
    node = raw["settlement"]
    if not isinstance(node, dict):
        raise CliUsageError("settlement: 必须为对象")
    _check_unknown_keys(node, SETTLEMENT_FIELDS, "settlement")
    overrides = {}
    for key in SETTLEMENT_FIELDS:
        value = _optional_decimal(node, key, "settlement")
        if value is not None:
            overrides[key] = value
    return overrides


CLAIM_FIELDS = (
    "item",
    "children",
    "share_ratio",
    "kind",
    "months",
    "tier",
    "only_child",
    "monthly_amount",
    "other_shared_amounts",
    "self_paid_total",
    "note",
)
CLAIM_DECIMAL_FIELDS = ("children", "share_ratio", "monthly_amount", "self_paid_total")


def _parse_calc_claims(raw: Dict[str, Any]) -> List[deductions_engine.Claim]:
    """专项附加扣除申报清单（七项；字段按项目取用，非法组合由引擎校验拒绝）。"""
    if raw.get("special_additional_claims") is None:
        return []
    nodes = raw["special_additional_claims"]
    if not isinstance(nodes, list):
        raise CliUsageError("special_additional_claims: 必须为数组")
    claims: List[deductions_engine.Claim] = []
    for i, node in enumerate(nodes):
        where = f"special_additional_claims[{i}]"
        if not isinstance(node, dict):
            raise CliUsageError(f"{where}: 必须为对象")
        _check_unknown_keys(node, CLAIM_FIELDS, where)
        item = node.get("item")
        if not isinstance(item, str) or not item:
            raise CliUsageError(f"{where}: 缺少 item（扣除项目键，如 child_education）")
        kwargs: Dict[str, Any] = {"item": item}
        for key in CLAIM_DECIMAL_FIELDS:
            value = _optional_decimal(node, key, where)
            if value is not None:
                kwargs[key] = value
        kind = node.get("kind")
        if kind is not None:
            if not isinstance(kind, str):
                raise CliUsageError(f"{where}.kind: 必须为字符串（academic/vocational）")
            kwargs["kind"] = kind
        months = node.get("months")
        if months is not None:
            if not isinstance(months, int) or isinstance(months, bool) or not (
                1 <= months <= MONTHS_PER_YEAR
            ):
                raise CliUsageError(f"{where}.months: 必须为 1-{MONTHS_PER_YEAR} 的整数")
            kwargs["months"] = months
        tier = node.get("tier")
        if tier is not None:
            if not isinstance(tier, int) or isinstance(tier, bool) or tier < 0:
                raise CliUsageError(f"{where}.tier: 必须为非负整数（住房租金城市档下标）")
            kwargs["tier"] = tier
        only_child = node.get("only_child")
        if only_child is not None:
            if not isinstance(only_child, bool):
                raise CliUsageError(f"{where}.only_child: 必须为布尔值")
            kwargs["only_child"] = only_child
        others = node.get("other_shared_amounts")
        if others is not None:
            if not isinstance(others, list):
                raise CliUsageError(f"{where}.other_shared_amounts: 必须为数组")
            parsed_others = []
            for j, value in enumerate(others):
                try:
                    parsed_others.append(to_decimal(value, f"{where}.other_shared_amounts[{j}]"))
                except Exception as exc:
                    raise CliUsageError(f"{where}.other_shared_amounts[{j}]: {exc}")
            kwargs["other_shared_amounts"] = tuple(parsed_others)
        note = node.get("note")
        if note is not None:
            if not isinstance(note, str):
                raise CliUsageError(f"{where}.note: 必须为字符串")
            kwargs["note"] = note
        claims.append(deductions_engine.Claim(**kwargs))
    return claims


def _read_calc_input(path_str: str) -> Dict[str, Any]:
    path = Path(path_str)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f, parse_float=Decimal)
    except FileNotFoundError:
        raise CliUsageError(f"输入文件不存在：{path}")
    except OSError as exc:
        raise CliUsageError(f"输入文件无法读取：{path}（{exc}）")
    except json.JSONDecodeError as exc:
        raise CliUsageError(f"输入文件不是合法 JSON：{path}（{exc}）")
    if not isinstance(raw, dict):
        raise CliUsageError("calc 输入文件顶层必须是 JSON 对象")
    _check_unknown_keys(
        raw,
        ("months", "uniform_month", "month_count", "social", "bonus_income", "settlement", "special_additional_claims"),
        "calc 输入",
    )
    return raw


def _parse_calc_input(raw: Dict[str, Any]) -> CalcInput:
    months = _parse_calc_months(raw)
    social_params = _parse_calc_social(raw)
    bonus_income = None
    if raw.get("bonus_income") is not None:
        try:
            bonus_income = to_decimal(raw["bonus_income"], "bonus_income")
        except Exception as exc:
            raise CliUsageError(f"bonus_income: {exc}")
    settlement_overrides = _parse_calc_settlement(raw)
    claims = _parse_calc_claims(raw)
    return CalcInput(
        months=months,
        social_params=social_params,
        bonus_income=bonus_income,
        settlement_overrides=settlement_overrides,
        claims=claims,
    )


# ---------------------------------------------------------------------------
# calc 编排与渲染
# ---------------------------------------------------------------------------

def _fmt(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _pct(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _print_legend(ruleset) -> None:
    print("依据来源（行内引用 = 来源ID·条款）：")
    for src in ruleset.data["sources"]:
        url = f"（{src['url']}）" if src.get("url") else ""
        reviewed_at = src.get("reviewed_at")
        date_note = f"（核对日期:{reviewed_at}）" if reviewed_at else ""
        print(f"  {src['id']}：{src['doc']}{url}{date_note}")


def _render_social(report: social_engine.SocialReport) -> None:
    print("== 社保公积金个人部分（基数/费率均为用户输入，规则包不存全国值） ==")
    print(
        f"  缴费基数：{_fmt(report.clamped_base)}"
        f"（输入 {_fmt(report.base_input)}；用户输入区间 "
        f"[{_fmt(report.base_lower)}, {_fmt(report.base_upper)}]）"
    )
    if report.clamp_note:
        print(f"  [注] {report.clamp_note}")
    for item in report.items:
        print(f"  {item.label}：{_fmt(item.base)} × {_pct(item.rate)} = {_fmt(item.personal_amount)}")
    print(f"  个人部分合计（计入每月专项扣除）：{_fmt(report.total)}")


def _render_monthly(ruleset, report: monthly_engine.MonthlyReport) -> None:
    print("== 累计预扣（61号公告第六条累计预扣法；预扣率表一=综合所得税率表级距） ==")
    header = (
        f"{'月':>2} {'收入':>10} {'免税':>9} {'专项扣除':>10} {'专项附加':>10} {'其他':>9} "
        f"{'累计应纳税所得额':>14} {'预扣率':>7} {'速算扣除':>9} {'累计应预扣':>10} {'本期应预扣':>10}  依据"
    )
    print(header)
    for m in report.months:
        bracket_ref = ""
        if m.bracket_index is not None:
            row = ruleset.data["rate_tables"][report.table_field][m.bracket_index]
            bracket_ref = short_ref(row["ref"])
            if row.get("ref_qd"):
                bracket_ref += f"；{short_ref(row['ref_qd'])}"
        print(
            f"{m.month_no:>2} {_fmt(m.inp.gross):>10} {_fmt(m.inp.tax_free):>9} "
            f"{_fmt(m.inp.special_deduction):>10} {_fmt(m.inp.special_additional_deduction):>10} "
            f"{_fmt(m.inp.other_deduction):>9} {_fmt(m.cumulative_taxable):>14} "
            f"{_pct(m.rate):>7} {_fmt(m.quick_deduction):>9} {_fmt(m.cumulative_tax):>10} "
            f"{_fmt(m.withholding):>10}  [{report.standard_deduction_ref_note}"
            + (f"；{bracket_ref}" if bracket_ref else "")
            + "]"
        )
        if m.note:
            print(f"    [注] 第{m.month_no}月：{m.note}")
    print(f"  已预扣预缴合计：{_fmt(report.withheld_total)}")
    print(f"  减除费用依据：{render_ref(report.standard_deduction_ref, ruleset.data['sources'])}")


def _render_settlement(ruleset, report: settlement_engine.SettlementReport) -> None:
    print("== 年度汇算（综合所得年度口径，M2 简化：工资薪金） ==")
    print(f"  减除费用（全年）：{_fmt(report.annual_standard_deduction)}")
    print(
        f"  应纳税所得额：{_fmt(report.cumulative_taxable_income)}"
        + (
            f" → 综合所得税率表第 {report.bracket_index + 1} 级 {_pct(report.rate)}"
            f"（速算扣除数 {_fmt(report.quick_deduction)}）"
            if report.bracket_index is not None
            else " → 无需缴税"
        )
    )
    row_idx = report.bracket_index
    if row_idx is not None:
        row = ruleset.data["rate_tables"]["comprehensive_annual"][row_idx]
        print(f"    税率依据：{short_ref(row['ref'])}；速算扣除数依据：{short_ref(row['ref_qd'])}")
    print(f"  年应纳税额：{_fmt(report.annual_tax)}")
    print(f"  已预扣预缴合计：{_fmt(report.withheld_total)}")
    sign = "应退税额" if report.refund_or_owe >= 0 else "应补税额"
    print(f"  {sign}（已预缴 − 应纳税额）：{_fmt(abs(report.refund_or_owe))}")
    if report.note:
        print(f"  [注] {report.note}")
    print(f"  减除费用依据：{render_ref(report.standard_deduction_ref, ruleset.data['sources'])}")


CLAIM_LABELS = deductions_engine.ITEM_LABELS  # 展示名单一来源在引擎层（GUI 共用）


def _render_deductions(ruleset, report: deductions_engine.DeductionsReport) -> None:
    print("== 专项附加扣除申报清单（41号办法/增设与提标通知，逐项挂依据） ==")
    for cr in report.claims:
        label = CLAIM_LABELS.get(cr.item, cr.item)
        print(f"  {label}：{cr.detail}")
        if cr.stage == deductions_engine.STAGE_SETTLEMENT_ONLY:
            print(f"    年额 {_fmt(cr.annual_amount)}（仅年度汇算扣除，预扣链不计）[{short_ref(cr.standard_ref)}]")
        else:
            print(
                f"    月额 {_fmt(cr.monthly_amount)} × {cr.months_claimed} 月 = 年额 {_fmt(cr.annual_amount)}"
                f"（预扣+汇算）[{short_ref(cr.standard_ref)}]"
            )
        if cr.note:
            print(f"    [注] {cr.note}")
    print(f"  预扣链月合计（已逐月计入下方累计预扣表）：{_fmt(report.monthly_total)}")
    print(f"  汇算链年合计（含仅汇算项 {_fmt(report.settlement_only_annual_total)}）：{_fmt(report.annual_total)}")


def _render_bonus(
    ruleset,
    report: bonus_engine.BonusSeparateTaxResult,
    comparison: Optional[bonus_engine.BonusComparisonReport],
    trap_intervals: Optional[List[bonus_engine.BonusTrapInterval]],
    active_trap: Optional[bonus_engine.BonusTrapInterval],
) -> None:
    print("== 全年一次性奖金（单独计税，164号第一条（一）） ==")
    print(f"  奖金：{_fmt(report.bonus_amount)} ÷ {report.divisor:f} = {_fmt(report.quotient)}（商数定档，税基用全额）")
    if report.bracket_index is not None:
        row = ruleset.data["rate_tables"][report.table_field][report.bracket_index]
        print(
            f"  按月换算税率表第 {report.bracket_index + 1} 级 {_pct(report.rate)}"
            f"（速算扣除数 {_fmt(report.quick_deduction)}）"
        )
        print(f"    税率依据：{short_ref(row['ref'])}")
    print(f"  应纳税额：{_fmt(report.bonus_amount)} × {_pct(report.rate)} − {_fmt(report.quick_deduction)} = {_fmt(report.tax)}")
    print(f"  税后奖金：{_fmt(report.after_tax)}")
    print(f"  政策：{report.policy_note}")
    if trap_intervals:
        text = "；".join(f"({_fmt(iv.lower)}, {_fmt(iv.upper)})" for iv in trap_intervals)
        print(f"  临界区间（由按月换算表逐边界推导，共 {len(trap_intervals)} 个）：{text}")
    if active_trap is not None:
        lo, hi = _fmt(active_trap.lower), _fmt(active_trap.upper)
        print(
            f"  [!!] 奖金落入\"多发一元、到手变少\"临界区间（{lo}, {hi}）：区间内税后奖金"
            f"低于 {lo} 处对应的税后金额（税率表级距机制客观呈现，非避税建议）"
        )
    if comparison is not None:
        print("== 年终奖择优对比（全年总税负口径） ==")
        a, b = comparison.scheme_separate, comparison.scheme_combined
        salary_tax = a.annual_total_tax - report.tax
        print(
            f"  {a.label}：工资汇算 {_fmt(salary_tax)} + 奖金单独计税 {_fmt(report.tax)}"
            f" = 全年总税负 {_fmt(a.annual_total_tax)}"
        )
        b_line = f"  {b.label}：并入后应纳税所得额 {_fmt(b.taxable_income)}"
        if b.bracket_index is not None:
            row = ruleset.data["rate_tables"]["comprehensive_annual"][b.bracket_index]
            b_line += f" → 第 {b.bracket_index + 1} 级 {_pct(b.rate)}（速算扣除数 {_fmt(b.quick_deduction)}）"
        b_line += f" → 全年应纳税额 {_fmt(b.annual_total_tax)}"
        print(b_line)
        diff = comparison.tax_difference
        if comparison.tie:
            print(f"  差额（A−B）：{_fmt(diff)} → 两案等同（差不超过申报精度 0.01 元），可任选")
        elif comparison.recommended == bonus_engine.SCHEME_SEPARATE:
            print(f"  差额（A−B）：{_fmt(diff)} → 推荐方案A：单独计税全年少缴 {_fmt(-diff)}")
        else:
            print(f"  差额（A−B）：{_fmt(diff)} → 推荐方案B：并入综合全年少缴 {_fmt(diff)}")
        if not a.available:
            print(f"  [!!] {a.note}")


def cmd_calc(args) -> int:
    ruleset = _load_or_usage_error(args.year, args.data_dir)
    try:
        effective = loader.effective_ruleset(ruleset)
    except loader.RulesetNotEffective as exc:
        raise RuntimeFailure(str(exc))

    if not args.input:
        raise CliUsageError("calc 需要 --input <计算输入JSON文件路径>（格式见 README「calc 输入格式」）")
    calc_input = _parse_calc_input(_read_calc_input(args.input))
    request = pipeline_engine.CalcRequest(
        months=tuple(calc_input.months),
        social_params=calc_input.social_params,
        claims=tuple(calc_input.claims),
        bonus_income=calc_input.bonus_income,
        settlement_overrides=calc_input.settlement_overrides,
    )

    try:
        result = pipeline_engine.compute_full_calc(effective, request)
    except deductions_engine.DeductionViolationError as exc:
        raise CliUsageError(f"专项附加扣除申报校验未通过：{exc}")
    except ValueError as exc:
        raise RuntimeFailure(f"计算失败：{exc}")

    print(f"个人所得税联动计算 —— {ruleset.year} 纳税年度")
    if result.social_report is not None:
        _render_social(result.social_report)
    if result.deductions_report is not None:
        _render_deductions(ruleset, result.deductions_report)
    _render_monthly(ruleset, result.monthly_report)
    _render_settlement(ruleset, result.settlement_report)
    if result.bonus_report is not None:
        _render_bonus(
            ruleset,
            result.bonus_report,
            result.bonus_comparison,
            list(result.trap_intervals) if result.trap_intervals else None,
            result.active_trap,
        )
    _print_legend(ruleset)
    print("免责声明：计算结果供参考，以税务机关核定为准；政策以发文机关正式文本为准。")
    return EXIT_OK


def cmd_benchmark(args) -> int:
    """内置评测基准一条命令跑全（M4）：达标 0 / 未达标或门控拦截 1 / 用法错误 2。"""
    try:
        report = run_all(data_dir=args.data_dir, focus_year=args.year)
    except (
        loader.RulesetNotFoundError,
        loader.DataDirNotFoundError,
        RulesetSchemaError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        raise CliUsageError(str(exc))
    except loader.RulesetNotEffective as exc:
        raise RuntimeFailure(str(exc))

    print(
        f"== 内置评测基准（纯规则通路、零 API；覆盖年度 "
        f"{report.years[0]}-{report.years[-1]}，穷举深扫代表年度 {report.focus_year}） =="
    )
    for metric in report.metrics:
        mark = "[OK]" if metric.ok else "[!!]"
        print(f"  {metric.title}：{metric.summary}（阈值：{metric.threshold}）{mark}")
        for line in metric.failures[:10]:
            print(f"    - {line}")
        if len(metric.failures) > 10:
            print(f"    ...共 {len(metric.failures)} 条失败明细")
    overall = "[OK]" if report.all_ok else "[!!]"
    verdict = "全部达标" if report.all_ok else "存在未达标项"
    print(f"  基准结论：{report.total_checks} 项检查，{verdict} {overall}")
    print("免责声明：基准仅验证引擎与规则包的自洽性，计算结果以税务机关核定为准。")
    return EXIT_OK if report.all_ok else EXIT_RUNTIME


def _ensure_utf8_stdio() -> None:
    """保证标准输出/错误能承载中文：现编码不行时切到 UTF-8。

    输出含中文（标题、依据）。CI/重定向场景 stdout 可能是 cp1252 等不含中文字形的
    编码，print 会抛 UnicodeEncodeError（实测 win CI 首跑即因此失败）。策略：先用
    现编码试编一个中文探针——能过则**保持不动**（中文 Windows cp936 控制台照常正确
    显示），不能过才 reconfigure 到 UTF-8。被测试捕获（capsys）替换过的对象无
    reconfigure，静默跳过。
    """
    probe = "个人所得税"
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        encoding = getattr(stream, "encoding", None)
        if encoding:
            try:
                probe.encode(encoding)
                continue
            except (UnicodeEncodeError, LookupError):
                pass
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main(argv=None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliUsageError as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return EXIT_USAGE
    except RuntimeFailure as exc:
        print(f"运行期失败：{exc}", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
