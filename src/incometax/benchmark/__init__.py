"""M4 内置评测基准（FR-7）：算例回归 + 税率级次临界 + 陷阱区间 + 扣除互斥组合。

设计定稿：plan/04 §四。纯规则通路——数据只来自 data/rules 规则包与 data/truth
真值库，零 API、零网络、固定输入可复现；期望值由独立实现路径（推导公式）与
引擎双向对账。CLI `benchmark` 子命令与 GUI（M5）共用 run_all() 同一 API。
"""

from incometax.benchmark.runner import BenchmarkMetric, BenchmarkReport, run_all

__all__ = ["BenchmarkMetric", "BenchmarkReport", "run_all"]
