"""M4 基准编排：一条命令跑全四类基准（CLI `benchmark` 子命令与 GUI 共用）。

流程（plan/04 §四 / HANDOFF-M4）：
1. 定位数据目录并加载全部可用年度规则包（schema 校验；门控在引擎入口逐次生效，
   存在待核对条目 → RulesetNotEffective 原样上抛，由调用方按运行期失败处理）；
2. 四类 runner 顺序执行：算例回归（真值库全字段对账）、税率级次临界（两表逐
   边界邻域自洽）、陷阱区间（推导 × 穷举双向对账）、扣除互斥组合（组合矩阵）；
3. 聚合 BenchmarkReport：指标表渲染交给呈现层（CLI/GUI），本模块不打印。

纯规则通路：输入只有数据目录；零 API、零网络、无随机数，固定输入可复现。
"""

from typing import Dict, Optional

from incometax.benchmark import cases, mutex, rates, traps
from incometax.benchmark.metrics import BenchmarkMetric, BenchmarkReport
from incometax.rules.loader import Ruleset, available_years, find_data_dir, load_ruleset

__all__ = ["BenchmarkMetric", "BenchmarkReport", "run_all"]


def run_all(data_dir=None, focus_year: Optional[int] = None) -> BenchmarkReport:
    """跑全四类基准。focus_year 为陷阱区间穷举深扫的代表年度，缺省取最新可用年度。"""
    resolved = find_data_dir(data_dir)
    years = tuple(available_years(resolved))
    if not years:
        raise ValueError(f"数据目录没有任何规则包：{resolved}")
    if focus_year is None:
        focus_year = years[-1]
    if focus_year not in years:
        raise ValueError(f"年度 {focus_year} 没有规则包（可用年度：{list(years)}）")

    rulesets: Dict[int, Ruleset] = {}
    for year in years:
        rulesets[year] = load_ruleset(year, data_dir=str(resolved))

    metrics = (
        cases.run_cases(rulesets, resolved),
        rates.run_rate_boundaries(rulesets),
        traps.run_trap_intervals(rulesets, focus_year),
        mutex.run_mutex_combinations(rulesets),
    )
    return BenchmarkReport(focus_year=focus_year, years=years, metrics=metrics)
