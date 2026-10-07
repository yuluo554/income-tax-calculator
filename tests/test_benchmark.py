"""M4 基准测试：四类 runner 全量跑 + CLI benchmark 子命令退出码语义。

口径（HANDOFF-M4 DoD）：阈值全达标——算例 100%、税率临界自洽 100%、
陷阱穷举一致 100%、互斥误放行 0 且误拒 0；基准纳入每里程碑收尾必跑项。
run_all() 为 CLI 与 GUI（M5）共用的同一 API，此处全量执行防回退。
"""

import shutil
from pathlib import Path

import pytest

from incometax.benchmark.metrics import BenchmarkMetric, BenchmarkReport
from incometax.benchmark.runner import run_all
from incometax.cli import main
from incometax.rules.loader import load_ruleset

REPO_ROOT = Path(__file__).resolve().parent.parent


def _metric(report, key):
    return next(m for m in report.metrics if m.key == key)


def test_run_all_all_thresholds_met():
    """全量基准一条命令跑全：四类指标全部达标（零 API、纯规则通路）。"""
    report = run_all()
    assert report.all_ok, (
        f"基准未达标：{[(m.key, m.failures) for m in report.metrics if m.failures]}"
    )
    cases = _metric(report, "cases")
    assert cases.total >= 4 and cases.passed == cases.total
    rates = _metric(report, "rates")
    assert rates.total >= 96 and rates.passed == rates.total  # 8 年度 × 2 表 × 6 边界
    assert rates.stats["边界数"] == 96
    traps = _metric(report, "traps")
    assert traps.stats["区间数"] == 6
    assert traps.stats["穷举一致"] == traps.stats["区间数"]
    mutex = _metric(report, "mutex")
    assert mutex.stats["误放行"] == 0 and mutex.stats["误拒"] == 0
    assert mutex.stats["违规组合"] > 0 and mutex.stats["有效组合"] > 0
    assert report.total_checks == sum(m.total for m in report.metrics)


def test_run_all_focus_year_override_and_validation():
    """代表年度可指定为任一可用年度；未知年度拒绝（用法错误语义由 CLI 落 2）。"""
    report = run_all(focus_year=2019)
    assert report.focus_year == 2019 and 2019 in report.years
    assert report.all_ok
    with pytest.raises(ValueError):
        run_all(focus_year=1999)


def test_cli_benchmark_success_renders_metric_table(capsys):
    assert main(["benchmark"]) == 0
    out = capsys.readouterr().out
    for title in ("算例回归", "税率级次临界", "陷阱区间", "扣除互斥组合"):
        assert title in out
    assert "全部达标" in out
    assert "[!!]" not in out
    assert "免责声明" in out


def test_cli_benchmark_unknown_year_is_usage_error(capsys):
    assert main(["benchmark", "--year", "1999"]) == 2
    assert "没有规则包" in capsys.readouterr().err


def test_cli_benchmark_threshold_breach_is_runtime_failure(monkeypatch, capsys):
    """阈值未达标 → 退出码 1（复用运行期失败语义，不得静默通过）。"""
    failing = BenchmarkMetric(
        key="cases", title="算例回归", total=4, passed=3,
        threshold="通过率 100%", summary="3/4", failures=("示例失败",),
    )
    report = BenchmarkReport(focus_year=2024, years=(2024,), metrics=(failing,))
    monkeypatch.setattr("incometax.cli.run_all", lambda data_dir=None, focus_year=None: report)
    assert main(["benchmark"]) == 1
    assert "存在未达标项" in capsys.readouterr().out


def test_cli_benchmark_gate_blocked_is_runtime_failure(tmp_path, capsys):
    """合成待核对规则包目录：门控拦截 → 退出码 1（未核对规则不得进基准计算）。"""
    from test_rules_loader import flip_one_node_pending, load_ruleset, write_ruleset

    raw = flip_one_node_pending(load_ruleset(2026).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    # 基准还需真值库文件：复制后各算例年度在本目录无规则包 → 记条目失败而非崩溃
    truth_dir = tmp_path / "truth"
    truth_dir.mkdir()
    shutil.copy(REPO_ROOT / "data" / "truth" / "cases.json", truth_dir / "cases.json")
    rc = main(["--data-dir", data_dir, "benchmark", "--year", "2099"])
    assert rc == 1
    assert "待核对" in capsys.readouterr().err


def test_cli_benchmark_missing_truth_is_usage_error(tmp_path, capsys):
    """数据目录缺真值库 → 算例回归无法执行 → 用法错误 2。"""
    from test_rules_loader import write_ruleset

    data_dir = write_ruleset(tmp_path, load_ruleset(2026).data, 2099)
    assert main(["--data-dir", data_dir, "benchmark", "--year", "2099"]) == 2
    assert "cases.json" in capsys.readouterr().err
