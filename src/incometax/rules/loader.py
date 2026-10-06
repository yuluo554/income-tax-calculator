"""规则包加载与 status 门控（设计定稿见 plan/04 §二）。

数据目录定位（M5 打包后冻结优先级，改动需同步分支测试）：
显式 --data-dir > 环境变量 INCOMETAX_DATA_DIR > PyInstaller 内嵌 sys._MEIPASS/data
> 从当前目录逐级上溯查找 data/rules。
"""

import json
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from incometax.rules.schema import (
    STATUS_VERIFIED,
    Bracket,
    _parse_rate_table,
    iter_value_nodes,
    normalize_status,
    validate_ruleset,
)

ENV_DATA_DIR = "INCOMETAX_DATA_DIR"


class DataDirNotFoundError(Exception):
    """找不到数据目录（data/rules）。"""


class RulesetNotFoundError(Exception):
    """请求年度没有对应规则包文件。"""

    def __init__(self, year: int, available: List[int]):
        self.year = year
        self.available = available
        super().__init__(
            f"年度 {year} 没有规则包（可用年度：{available or '无'}）。"
            "规则包覆盖范围见 data/rules/README.md。"
        )


@dataclass(frozen=True)
class Ruleset:
    """年度规则包：schema 校验后的不可变视图。

    data 为原始 dict（含 ref/status）；引擎入口只接受 effective_ruleset() 的产物。
    """

    year: int
    data: Dict[str, Any]
    path: Path
    comprehensive_brackets: Tuple[Bracket, ...] = field(default_factory=tuple)
    monthly_brackets: Tuple[Bracket, ...] = field(default_factory=tuple)

    @property
    def monthly_standard_deduction(self) -> Decimal:
        node = self.data["withholding"]["monthly_standard_deduction"]
        return Decimal(str(node["value"]))


@dataclass(frozen=True)
class StatusReport:
    verified: int
    pending: int
    pending_paths: Tuple[str, ...]

    @property
    def all_effective(self) -> bool:
        return self.pending == 0


def find_data_dir(explicit: Optional[str] = None) -> Path:
    if explicit is not None:
        data_dir = Path(explicit)
        if not (data_dir / "rules").is_dir():
            raise DataDirNotFoundError(f"指定数据目录下没有 rules/ 子目录：{data_dir}")
        return data_dir

    env_value = os.environ.get(ENV_DATA_DIR)
    if env_value:
        data_dir = Path(env_value)
        if not (data_dir / "rules").is_dir():
            raise DataDirNotFoundError(f"{ENV_DATA_DIR} 指向的目录没有 rules/ 子目录：{data_dir}")
        return data_dir

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        data_dir = Path(meipass) / "data"
        if (data_dir / "rules").is_dir():
            return data_dir

    cwd = Path.cwd()
    for base in (cwd, *cwd.parents):
        data_dir = base / "data"
        if (data_dir / "rules").is_dir():
            return data_dir
    raise DataDirNotFoundError(
        "未找到数据目录（data/rules）：请在仓库根目录运行，"
        f"或用 --data-dir / {ENV_DATA_DIR} 显式指定"
    )


def available_years(data_dir: Optional[Path] = None) -> List[int]:
    data_dir = data_dir if data_dir is not None else find_data_dir()
    years = []
    prefix = "ruleset-"
    for path in (data_dir / "rules").glob("ruleset-*.json"):
        stem = path.stem[len(prefix):] if path.stem.startswith(prefix) else path.stem
        if stem.isdigit():
            years.append(int(stem))
    return sorted(years)


def load_ruleset(year: int, data_dir: Optional[str] = None) -> Ruleset:
    """加载并校验年度规则包（结构加载，不等于可生效——生效见 effective_ruleset）。"""
    resolved = find_data_dir(data_dir)
    path = resolved / "rules" / f"ruleset-{year}.json"
    if not path.exists():
        raise RulesetNotFoundError(year, available_years(resolved))
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f, parse_float=Decimal)
    validate_ruleset(raw, expected_year=year)
    return Ruleset(
        year=year,
        data=raw,
        path=path,
        comprehensive_brackets=_parse_rate_table(raw["rate_tables"]["comprehensive_annual"], "comprehensive_annual"),
        monthly_brackets=_parse_rate_table(raw["rate_tables"]["monthly_converted"], "monthly_converted"),
    )


@dataclass(frozen=True)
class RulesetNotEffective(Exception):
    """存在待核对条目——按免责红线拒绝进计算引擎。"""

    pending_paths: Tuple[str, ...]

    def __str__(self) -> str:
        shown = "\n".join(f"  - {p}" for p in self.pending_paths[:10])
        more = "" if len(self.pending_paths) <= 10 else f"\n  ...共 {len(self.pending_paths)} 条"
        return (
            f"规则包存在 {len(self.pending_paths)} 条待核对条目，"
            f"未挂原文核对不得生效：\n{shown}{more}"
        )


def status_report(ruleset: Ruleset) -> StatusReport:
    """门控覆盖面 = 数值条目（含 value 键的节点）+ 两张税率表逐行。

    sources[] 与 desc 说明节点的 status 仅作信息展示，不参与门控
    （门控拦的是会进入计算结论的数值规则）。
    """
    verified = 0
    pending: List[str] = []

    def _count(path: str, node: Dict[str, Any]) -> None:
        nonlocal verified
        if normalize_status(node) == STATUS_VERIFIED:
            verified += 1
        else:
            pending.append(path)

    for path, node in iter_value_nodes(ruleset.data):
        _count(path, node)
    for table_field in ("comprehensive_annual", "monthly_converted"):
        rows = ruleset.data["rate_tables"][table_field]
        for i, row in enumerate(rows):
            _count(f"rate_tables.{table_field}[{i}]", row)
    return StatusReport(verified=verified, pending=len(pending), pending_paths=tuple(sorted(pending)))


def effective_ruleset(ruleset: Ruleset) -> Ruleset:
    """门控单点：全部数值条目已核对才放行；否则抛 RulesetNotEffective 并列出清单。"""
    report = status_report(ruleset)
    if not report.all_effective:
        raise RulesetNotEffective(report.pending_paths)
    return ruleset
