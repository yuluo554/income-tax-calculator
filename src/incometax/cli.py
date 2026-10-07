"""CLI 通路（M2：calc 已实装，消费引擎 Report 渲染）。

退出码语义（定稿，锁进 tests/test_cli.py，不得漂移）：
  0 = 成功
  1 = 运行期失败（status 门控拦截 / 计算期失败）
  2 = 用法与输入错误（参数缺失、输入 JSON 非法、年度无规则包、schema 非法、数据目录缺失）

控制台兼容：输出只用 GBK 可编码字符（Windows cp936 控制台），状态标记用 ASCII。
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from incometax import __version__
from incometax.engine import bonus as bonus_engine
from incometax.engine import monthly as monthly_engine
from incometax.engine import settlement as settlement_engine
from incometax.engine import social as social_engine
from incometax.engine.monthly import MONTHS_PER_YEAR, MonthInput
from incometax.engine.report import money, render_ref, short_ref
from incometax.rules import loader
from incometax.rules.schema import to_decimal

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

    p_calc = sub.add_parser("calc", help="计算：累计预扣逐月表 + 社保联动 + 年度汇算 + 年终奖单独计税")
    p_calc.add_argument("--year", type=int, required=True, help="适用纳税年度（需已有对应规则包文件）")
    p_calc.add_argument(
        "--input",
        help="计算输入 JSON 文件路径（格式见 README「calc 输入格式」）",
    )
    p_calc.set_defaults(func=cmd_calc)

    return parser


def _load_or_usage_error(year: int, data_dir):
    try:
        return loader.load_ruleset(year, data_dir=data_dir)
    except loader.RulesetNotFoundError as exc:
        raise CliUsageError(str(exc))
    except loader.DataDirNotFoundError as exc:
        raise CliUsageError(str(exc))
    except loader.RulesetSchemaError as exc:
        raise CliUsageError(f"规则包 schema 非法（年度 {year}）：{exc}")


def cmd_rules(args) -> int:
    ruleset = _load_or_usage_error(args.year, args.data_dir)
    report = loader.status_report(ruleset)
    print(f"年度规则包 {ruleset.year}（schema v1）")
    print(f"文件：{ruleset.path}")
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
    _check_unknown_keys(raw, ("months", "uniform_month", "month_count", "social", "bonus_income", "settlement"), "calc 输入")
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
    return CalcInput(
        months=months,
        social_params=social_params,
        bonus_income=bonus_income,
        settlement_overrides=settlement_overrides,
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
        print(f"  {src['id']}：{src['doc']}{url}")


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


def _render_bonus(ruleset, report: bonus_engine.BonusSeparateTaxResult) -> None:
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
    print("  [注] 择优对比（并入综合所得）与临界区间提示在 M3 实装")


def cmd_calc(args) -> int:
    ruleset = _load_or_usage_error(args.year, args.data_dir)
    try:
        effective = loader.effective_ruleset(ruleset)
    except loader.RulesetNotEffective as exc:
        raise RuntimeFailure(str(exc))

    if not args.input:
        raise CliUsageError("calc 需要 --input <计算输入JSON文件路径>（格式见 README「calc 输入格式」）")
    calc_input = _parse_calc_input(_read_calc_input(args.input))

    try:
        social_report = None
        months = list(calc_input.months)
        if calc_input.social_params is not None:
            base_input, rates, base_lower, base_upper = calc_input.social_params
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

        monthly_report = monthly_engine.compute_monthly_withholding(effective, months)

        aggregates = {
            "annual_gross": sum((mi.gross for mi in months), Decimal(0)),
            "annual_special_deduction": sum((mi.special_deduction for mi in months), Decimal(0)),
            "annual_special_additional_deduction": sum(
                (mi.special_additional_deduction for mi in months), Decimal(0)
            ),
            "annual_other_deduction": sum((mi.other_deduction for mi in months), Decimal(0)),
            "withheld_total": monthly_report.withheld_total,
        }
        aggregates.update(calc_input.settlement_overrides)
        settlement_report = settlement_engine.compute_annual_settlement(
            effective, settlement_engine.SettlementInput(**aggregates)
        )

        bonus_report = None
        if calc_input.bonus_income is not None:
            bonus_report = bonus_engine.compute_bonus_separate_tax(effective, calc_input.bonus_income)
    except ValueError as exc:
        raise RuntimeFailure(f"计算失败：{exc}")

    print(f"个人所得税联动计算 —— {ruleset.year} 纳税年度")
    if social_report is not None:
        _render_social(social_report)
    _render_monthly(ruleset, monthly_report)
    _render_settlement(ruleset, settlement_report)
    if bonus_report is not None:
        _render_bonus(ruleset, bonus_report)
    _print_legend(ruleset)
    print("免责声明：计算结果供参考，以税务机关核定为准；政策以发文机关正式文本为准。")
    return EXIT_OK


def main(argv=None) -> int:
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
