"""内置基准面板（M5）：GUI 复用 benchmark.runner.run_all() 同一 API。

- 指标表渲染与 CLI cmd_benchmark 同一数据对象（BenchmarkReport）；
- 门控拦截/数据目录缺失等异常以对话框呈现，不弹栈；
- 全量基准不足 1 秒，直接在主线程执行（无需后台线程）。
"""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from incometax.benchmark.runner import run_all
from incometax.rules.loader import (
    DataDirNotFoundError,
    RulesetNotEffective,
    RulesetNotFoundError,
)
from incometax.rules.schema import RulesetSchemaError


class BenchmarkPanel(QWidget):
    """内置基准页：一条命令跑全（算例回归 + 税率临界 + 陷阱区间 + 互斥组合）。"""

    def __init__(self, data_dir=None, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self._build_ui()
        self._reset()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        intro = QLabel(
            "内置评测基准：算例回归（真值库全字段对账）+ 税率级次临界（±0.01 邻域自洽）"
            "+ 陷阱区间（推导 × 穷举双向对账）+ 扣除互斥组合（组合矩阵）。"
            "纯规则通路、零 API、无随机数，可重复。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        bar = QHBoxLayout()
        self.run_button = QPushButton("跑全量基准")
        self.run_button.clicked.connect(self.run_benchmark)
        bar.addWidget(self.run_button)
        bar.addStretch(1)
        self.summary_label = QLabel()
        bar.addWidget(self.summary_label)
        root.addLayout(bar)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(("指标", "检查数", "通过", "阈值", "结论"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.table, 2)

        self.failures = QTextBrowser()
        root.addWidget(self.failures, 1)

    def _reset(self) -> None:
        self.table.setRowCount(0)
        self.summary_label.setText("")
        self.failures.setPlainText("尚未运行。")

    # ------------------------------------------------------------------
    # 运行
    # ------------------------------------------------------------------

    def _show_error(self, title: str, detail: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self, title, detail)

    def run_benchmark(self) -> None:
        """执行 run_all 并渲染指标表（异常 → 对话框；offscreen 测试 monkeypatch _show_error）。"""
        self.run_button.setEnabled(False)
        try:
            report = run_all(data_dir=self.data_dir)
        except (
            DataDirNotFoundError,
            RulesetNotFoundError,
            RulesetSchemaError,
            FileNotFoundError,
            ValueError,
        ) as exc:
            self._show_error("基准无法运行（输入/数据问题）", str(exc))
            return
        except RulesetNotEffective as exc:
            self._show_error("规则包门控拦截", str(exc))
            return
        finally:
            self.run_button.setEnabled(True)

        self.table.setRowCount(len(report.metrics))
        for row, metric in enumerate(report.metrics):
            values = (
                metric.title,
                str(metric.total),
                f"{metric.passed} / {metric.total}",
                metric.threshold,
                "[OK] 达标" if metric.ok else "[!!] 未达标",
            )
            for col, text in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(text))
        verdict = "全部达标" if report.all_ok else "存在未达标项"
        self.summary_label.setText(
            f"基准结论：{report.total_checks} 项检查，{verdict}"
            f"（覆盖年度 {report.years[0]}-{report.years[-1]}，深扫代表年度 {report.focus_year}）"
        )
        lines = []
        for metric in report.metrics:
            for line in metric.failures:
                lines.append(f"[{metric.title}] {line}")
        if lines:
            shown = lines[:200]
            if len(lines) > len(shown):
                shown.append(f"...共 {len(lines)} 条失败明细")
            self.failures.setPlainText("\n".join(shown))
        else:
            self.failures.setPlainText("无失败明细。")
