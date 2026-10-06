"""年度规则包 schema v1 校验与解析。

设计定稿见 plan/04 §一。要点：
- 所有数值条目（含 "value" 键的节点）必带 ref（文号+条款），status 缺失按"待核对"处理（宁缺勿错）；
- 税率表固定 7 级、区间相接、末级上界开放（null）；
- 金额/税率统一转 Decimal（JSON 以 parse_float=Decimal 加载，rate 字段为字符串）。
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

STATUS_VERIFIED = "已核对"
STATUS_PENDING = "待核对"
VALID_STATUSES = (STATUS_VERIFIED, STATUS_PENDING)

REQUIRED_TOP_KEYS = (
    "schema_version",
    "year",
    "notes",
    "sources",
    "withholding",
    "rate_tables",
    "bonus",
    "special_deductions",
)

RATE_TABLE_FIELDS = ("comprehensive_annual", "monthly_converted")


class RulesetSchemaError(Exception):
    """规则包结构/取值不符合 schema v1。"""


@dataclass(frozen=True)
class Bracket:
    """税率表级次：[lower, upper)（元），末级 upper=None 表示上不封顶。"""

    lower: Decimal
    upper: Optional[Decimal]
    rate: Decimal
    quick_deduction: Decimal


def to_decimal(value: Any, where: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise RulesetSchemaError(f"{where}: 布尔值不能作为金额/税率")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise RulesetSchemaError(f"{where}: 非法数值 {value!r}")
    raise RulesetSchemaError(f"{where}: 非法数值类型 {type(value).__name__}")


def iter_value_nodes(obj: Any, path: str = ""):
    """深度优先遍历，产出 (路径, 节点)。数值条目=含 "value" 键的 dict，视为叶子。"""
    if isinstance(obj, dict):
        if "value" in obj:
            yield path, obj
            return
        for key, child in obj.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_value_nodes(child, child_path)
    elif isinstance(obj, list):
        for index, child in enumerate(obj):
            yield from iter_value_nodes(child, f"{path}[{index}]")


def normalize_status(node: Dict[str, Any]) -> str:
    status = node.get("status", STATUS_PENDING)
    if status not in VALID_STATUSES:
        raise RulesetSchemaError(f"非法 status {status!r}（允许：{VALID_STATUSES}）")
    return status


def _validate_value_nodes(raw: Dict[str, Any], problems: List[str]) -> None:
    for path, node in iter_value_nodes(raw):
        if not isinstance(node.get("value"), (int, float, str, Decimal)) or isinstance(
            node["value"], bool
        ):
            problems.append(f"{path}: value 缺失或类型非法")
            continue
        if "ref" not in node or not isinstance(node["ref"], dict):
            problems.append(f"{path}: 数值条目必须挂 ref（文号+条款）")
        try:
            normalize_status(node)
        except RulesetSchemaError as exc:
            problems.append(f"{path}: {exc}")


def _parse_rate_table(rows: Any, field: str) -> Tuple[Bracket, ...]:
    if not isinstance(rows, list) or len(rows) != 7:
        raise RulesetSchemaError(f"rate_tables.{field}: 必须为 7 级")
    brackets: List[Bracket] = []
    prev_upper = Decimal(0)
    for i, row in enumerate(rows):
        where = f"rate_tables.{field}[{i}]"
        if not isinstance(row, dict):
            raise RulesetSchemaError(f"{where}: 必须为对象")
        for key in ("lower", "upper", "rate", "quick_deduction", "ref"):
            if key not in row:
                raise RulesetSchemaError(f"{where}: 缺少 {key}")
        lower = to_decimal(row["lower"], f"{where}.lower")
        upper = None if row["upper"] is None else to_decimal(row["upper"], f"{where}.upper")
        rate = to_decimal(row["rate"], f"{where}.rate")
        quick = to_decimal(row["quick_deduction"], f"{where}.quick_deduction")
        if lower != prev_upper:
            raise RulesetSchemaError(f"{where}: lower {lower} 与上一级 upper {prev_upper} 不相接")
        if upper is not None and upper <= lower:
            raise RulesetSchemaError(f"{where}: upper {upper} 必须大于 lower {lower}")
        if not Decimal(0) < rate < Decimal(1):
            raise RulesetSchemaError(f"{where}: 税率 {rate} 必须在 (0,1) 区间")
        if quick < 0:
            raise RulesetSchemaError(f"{where}: 速算扣除数不能为负")
        brackets.append(Bracket(lower, upper, rate, quick))
        prev_upper = upper
        if upper is None and i != len(rows) - 1:
            raise RulesetSchemaError(f"{where}: 上不封顶级次只能是最后一级")
    if brackets[-1].upper is not None:
        raise RulesetSchemaError(f"rate_tables.{field}: 末级必须上不封顶（upper=null）")
    return tuple(brackets)


def validate_ruleset(raw: Dict[str, Any], expected_year: Optional[int] = None) -> None:
    if not isinstance(raw, dict):
        raise RulesetSchemaError("规则包顶层必须是 JSON 对象")
    for key in REQUIRED_TOP_KEYS:
        if key not in raw:
            raise RulesetSchemaError(f"缺少顶层字段 {key}")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise RulesetSchemaError(f"schema_version 必须为 {SCHEMA_VERSION}")
    if not isinstance(raw["year"], int):
        raise RulesetSchemaError("year 必须为整数")
    if expected_year is not None and raw["year"] != expected_year:
        raise RulesetSchemaError(f"文件内 year={raw['year']} 与请求年度 {expected_year} 不一致")
    if not isinstance(raw["sources"], list) or not raw["sources"]:
        raise RulesetSchemaError("sources 必须为非空数组")
    for i, src in enumerate(raw["sources"]):
        if not isinstance(src, dict) or "id" not in src or "doc" not in src:
            raise RulesetSchemaError(f"sources[{i}]: 必须含 id 与 doc")
        if src.get("status") not in VALID_STATUSES:
            raise RulesetSchemaError(f"sources[{i}]: status 非法")
    rate_tables = raw["rate_tables"]
    if not isinstance(rate_tables, dict):
        raise RulesetSchemaError("rate_tables 必须为对象")
    for field in RATE_TABLE_FIELDS:
        if field not in rate_tables:
            raise RulesetSchemaError(f"rate_tables 缺少 {field}")
    withholding = raw["withholding"]
    if not isinstance(withholding, dict) or "monthly_standard_deduction" not in withholding:
        raise RulesetSchemaError("withholding 缺少 monthly_standard_deduction")
    if not isinstance(raw["special_deductions"], dict):
        raise RulesetSchemaError("special_deductions 必须为对象")
    if raw["special_deductions"].get("housing_loan_vs_rent") != "mutually_exclusive":
        raise RulesetSchemaError(
            "special_deductions.housing_loan_vs_rent 必须显式为 mutually_exclusive"
            "（房贷利息与住房租金互斥，规则不许省略）"
        )

    problems: List[str] = []
    _validate_value_nodes(raw, problems)
    if problems:
        raise RulesetSchemaError("数值条目校验失败：\n" + "\n".join(problems))
