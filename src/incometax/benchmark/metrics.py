"""基准指标数据类（runner 与各 runner 模块共用的公共定义，避免循环导入）。"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class BenchmarkMetric:
    """单类基准结果：计数 + 人读阈值/摘要 + 失败明细 + 结构化计数。"""

    key: str
    title: str
    total: int
    passed: int
    threshold: str
    summary: str
    stats: Dict[str, int] = field(default_factory=dict)
    failures: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class BenchmarkReport:
    """全量基准结果：四类指标聚合（CLI 渲染指标表，GUI 复用同一对象）。"""

    focus_year: int
    years: Tuple[int, ...]
    metrics: Tuple[BenchmarkMetric, ...]

    @property
    def all_ok(self) -> bool:
        return all(m.ok for m in self.metrics)

    @property
    def total_checks(self) -> int:
        return sum(m.total for m in self.metrics)

    @property
    def total_failures(self) -> int:
        return sum(len(m.failures) for m in self.metrics)
