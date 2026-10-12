"""主窗口（M5）：免责声明首屏 → 计算主界面（年度切换 + 四个功能区页）。

- 首屏为免责声明（确认后才进入计算，DoD 项）；
- 年度切换 = 重新加载规则包（加载失败/门控拦截以对话框呈现，不静默）；
- 「计算」按钮 = 输入面板收集 → engine.pipeline.compute_full_calc（与 CLI 同一编排）
  → 结果/依据两页刷新；扣除申报违规整单拒绝（对话框列出全部违规，不产出部分结果）；
- 对话框统一走 _show_error/_show_info 两个方法（offscreen 测试 monkeypatch 这两个
  方法即可屏蔽全部模态弹窗）。
"""

from decimal import Decimal
from typing import List, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from incometax import __version__
from incometax.engine import pipeline as pipeline_engine
from incometax.engine.deductions import DeductionViolationError
from incometax.gui.benchmark_panel import BenchmarkPanel
from incometax.gui.input_panel import GuiInputError, InputPanel
from incometax.gui.ref_panel import RefPanel
from incometax.gui.results_panel import ResultsPanel
from incometax.rules import loader
from incometax.rules.loader import Ruleset
from incometax.rules.schema import RulesetSchemaError

# 应用显示名（plan/06 决策 #2 定稿 = 默认值）：窗口标题与打包 exe 名共用
APP_TITLE = "个人所得税联动计算器"

DISCLAIMER_TEXT = """\
<h2>免责声明与使用须知</h2>
<p><b>本工具的计算结果仅供参考，不构成任何税务意见；最终以税务机关核定为准，政策以发文机关正式文本为准。</b></p>
<ul>
<li>适用口径：工资薪金所得的累计预扣预缴、全年一次性奖金单独计税与并入综合所得择优、
七项专项附加扣除、年度汇算清缴的<b>简化口径</b>；劳务报酬等其他所得暂未纳入。</li>
<li>社保公积金缴费基数上下限与个人费率为<b>用户输入</b>（各地差异大，规则包不存全国值），
请按所在地口径自行填写。</li>
<li>全部税率、扣除标准、政策有效期来自内置的年度版本化规则包，每条数值挂官方文号与条款，
可在「依据面板」逐条溯源；规则包覆盖范围内的年度均可切换计算。</li>
<li>引擎未核实的数据不会参与计算（status 门控拦截），并在界面上明示原因。</li>
<li>年终奖临界区间提示是税率表级距机制的客观呈现（区间内多发奖金税后反而变少），
不是避税建议；择优推荐为全年总税负口径的机械比较。</li>
</ul>
<p>确认本页后进入计算界面。</p>
"""


class MainWindow(QMainWindow):
    """免责首屏 + 计算主界面（输入/结果/依据/基准四页共用一次规则包加载）。"""

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__()
        self.data_dir = data_dir
        self.ruleset: Optional[Ruleset] = None
        self.setWindowTitle(f"{APP_TITLE} v{__version__}")
        self.resize(1080, 720)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_disclaimer_page())
        self._stack.addWidget(self._build_main_page())
        self.setCentralWidget(self._stack)

    # ------------------------------------------------------------------
    # 页面构建
    # ------------------------------------------------------------------

    def _build_disclaimer_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        browser = QTextBrowser()
        browser.setHtml(DISCLAIMER_TEXT)
        browser.setOpenExternalLinks(False)
        layout.addWidget(browser, 1)
        self.disclaimer_browser = browser  # 供测试断言首屏内容
        enter = QPushButton("我已阅读并理解，进入计算")
        enter.clicked.connect(self._enter_main)
        layout.addWidget(enter, 0)
        return page

    def _build_main_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("纳税年度："))
        self.year_combo = QComboBox()
        self.year_combo.currentIndexChanged.connect(self._on_year_changed)
        bar.addWidget(self.year_combo)
        bar.addStretch(1)
        self.compute_button = QPushButton("计算")
        self.compute_button.clicked.connect(self._on_compute)
        bar.addWidget(self.compute_button)
        root.addLayout(bar)

        self.input_panel = InputPanel()
        self.results_panel = ResultsPanel()
        self.ref_panel = RefPanel()
        self.benchmark_panel = BenchmarkPanel(self.data_dir)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.input_panel, "计算输入")
        self.tabs.addTab(self.results_panel, "计算结果")
        self.tabs.addTab(self.ref_panel, "依据面板")
        self.tabs.addTab(self.benchmark_panel, "内置基准")
        root.addWidget(self.tabs, 1)
        return page

    # ------------------------------------------------------------------
    # 对话框出口（offscreen 测试 monkeypatch 这两个方法屏蔽模态弹窗）
    # ------------------------------------------------------------------

    def _show_error(self, title: str, detail: str) -> None:
        QMessageBox.critical(self, title, detail)

    def _show_info(self, title: str, detail: str) -> None:
        QMessageBox.information(self, title, detail)

    # ------------------------------------------------------------------
    # 首屏 / 年度切换
    # ------------------------------------------------------------------

    def _enter_main(self) -> None:
        """确认免责声明后进入主界面并加载年度列表（DoD：免责声明首屏）。"""
        years = self._available_years()
        if not years:
            return
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in years:
            self.year_combo.addItem(f"{year} 纳税年度", year)
        self.year_combo.setCurrentIndex(self.year_combo.count() - 1)  # 缺省选中最新可用年度
        self.year_combo.blockSignals(False)
        self._stack.setCurrentIndex(1)
        self._load_year(years[-1])

    def _available_years(self) -> List[int]:
        try:
            years = loader.available_years(
                self.data_dir if self.data_dir is not None else None
            )
        except loader.DataDirNotFoundError as exc:
            self._show_error("数据目录缺失", str(exc))
            return []
        if not years:
            self._show_error("数据目录缺失", "数据目录下没有任何规则包（rules/ruleset-*.json）。")
        return years

    def _load_year(self, year: int) -> None:
        try:
            ruleset = loader.load_ruleset(year, data_dir=self.data_dir)
        except loader.RulesetNotFoundError as exc:
            self._show_error("年度规则包缺失", str(exc))
            return
        except loader.DataDirNotFoundError as exc:
            self._show_error("数据目录缺失", str(exc))
            return
        except RulesetSchemaError as exc:
            self._show_error("规则包 schema 非法", str(exc))
            return
        self.ruleset = ruleset
        # 切换年度后旧结果不再适用：清空结果与依据两页，输入保留供改算
        self.results_panel.clear()
        self.ref_panel.clear()
        self.input_panel.set_ruleset(ruleset)

    def _on_year_changed(self, index: int) -> None:
        year = self.year_combo.itemData(index)
        if year is not None:
            self._load_year(int(year))

    # ------------------------------------------------------------------
    # 计算（与 CLI 共用 engine.pipeline.compute_full_calc 编排）
    # ------------------------------------------------------------------

    def _on_compute(self) -> None:
        if self.ruleset is None:
            self._show_error("尚未加载规则包", "请先选择纳税年度。")
            return
        try:
            effective = loader.effective_ruleset(self.ruleset)
        except loader.RulesetNotEffective as exc:
            self._show_error("规则包存在待核对条目（门控拦截）", str(exc))
            return

        try:
            request = self.input_panel.build_request()
        except GuiInputError as exc:
            self._show_error("输入有误", str(exc))
            return

        try:
            result = pipeline_engine.compute_full_calc(effective, request)
        except DeductionViolationError as exc:
            # 违规整单拒绝：逐条列出全部违规（含条款依据），不产出部分结果
            self._show_error("专项附加扣除申报校验未通过（整单拒绝）", str(exc))
            return
        except ValueError as exc:
            self._show_error("计算失败", str(exc))
            return

        self.results_panel.show_result(effective, result)
        self.ref_panel.show_result(effective, result)
        self.tabs.setCurrentWidget(self.results_panel)

    # 供 offscreen 测试在不点按钮的情况下校验金额解析（Decimal 全链路）
    @staticmethod
    def parse_money_text(text: str) -> Optional[Decimal]:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except Exception:
            raise GuiInputError(f"不是合法金额：{text!r}")
