"""计算结果面板（M5）：社保/扣除清单/逐月预扣表/年度汇算/年终奖择优与临界标红。

- 只渲染 engine.pipeline.CalcResult，不做任何数值计算（Decimal → 两位小数呈现）；
- 年终奖落入临界区间时红色标注（税率表机制客观呈现，非避税建议）；
- 依据引用显示为 "来源ID·条款" 短引用（完整文号在依据面板渲染）。
"""

from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from incometax.engine import pipeline as pipeline_engine
from incometax.engine.deductions import ITEM_LABELS, STAGE_SETTLEMENT_ONLY
from incometax.engine.report import money, short_ref

TRAP_HIGHLIGHT_STYLE = "color:#c00000; font-weight:bold;"

_MONTH_HEADERS = (
    "月份",
    "收入",
    "免税收入",
    "专项扣除",
    "专项附加扣除",
    "其他扣除",
    "累计应纳税所得额",
    "预扣率",
    "速算扣除",
    "累计应预扣",
    "本期应预扣",
)


def _fmt(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    return f"{money(value):.2f}"


def _pct(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _row(item_text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(item_text)
    return item


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.trap_banner = QLabel()
        self.trap_banner.setStyleSheet(TRAP_HIGHLIGHT_STYLE)
        self.trap_banner.setWordWrap(True)
        self.trap_banner.hide()
        root.addWidget(self.trap_banner)

        self.social_browser = QTextBrowser()
        self.social_group = QGroupBox("社保公积金个人部分（联动结果，已计入每月专项扣除）")
        social_layout = QVBoxLayout(self.social_group)
        social_layout.addWidget(self.social_browser)
        root.addWidget(self.social_group)

        self.deductions_browser = QTextBrowser()
        self.deductions_group = QGroupBox("专项附加扣除申报清单")
        deductions_layout = QVBoxLayout(self.deductions_group)
        deductions_layout.addWidget(self.deductions_browser)
        root.addWidget(self.deductions_group)

        self.monthly_table = QTableWidget()
        self.monthly_table.setColumnCount(len(_MONTH_HEADERS))
        self.monthly_table.setHorizontalHeaderLabels(_MONTH_HEADERS)
        self.monthly_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.monthly_table.verticalHeader().setVisible(False)
        self.monthly_group = QGroupBox("累计预扣法逐月表（61号公告第六条口径，预扣率表一级距）")
        monthly_layout = QVBoxLayout(self.monthly_group)
        monthly_layout.addWidget(self.monthly_table)
        root.addWidget(self.monthly_group, 2)

        settlement_box = QGroupBox("年度汇算（简化口径：工资薪金）")
        self.settlement_form = QFormLayout(settlement_box)
        self.settlement_labels = {}
        for key, label in (
            ("taxable", "应纳税所得额"),
            ("annual_tax", "年应纳税额"),
            ("withheld", "已预扣预缴合计"),
            ("refund", "汇算结论"),
        ):
            value_label = QLabel()
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.settlement_labels[key] = value_label
            self.settlement_form.addRow(label, value_label)
        root.addWidget(settlement_box)

        self.bonus_browser = QTextBrowser()
        self.bonus_group = QGroupBox("全年一次性奖金：单独计税 + 双方案择优 + 临界区间")
        bonus_layout = QVBoxLayout(self.bonus_group)
        bonus_layout.addWidget(self.bonus_browser)
        root.addWidget(self.bonus_group, 1)

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self.trap_banner.hide()
        self.social_group.hide()
        self.deductions_group.hide()
        self.bonus_group.hide()
        self.monthly_table.setRowCount(0)
        for key in self.settlement_labels:
            self.settlement_labels[key].setText("-")

    def show_result(self, ruleset, result: pipeline_engine.CalcResult) -> None:
        self.clear()
        if result.social_report is not None:
            self._show_social(result)
        if result.deductions_report is not None:
            self._show_deductions(result)
        self._show_monthly(result)
        self._show_settlement(result)
        if result.bonus_report is not None:
            self._show_bonus(ruleset, result)
        self.bonus_group.setVisible(result.bonus_report is not None)

    def _show_social(self, result) -> None:
        report = result.social_report
        lines = [
            f"缴费基数：{_fmt(report.clamped_base)}"
            f"（输入 {_fmt(report.base_input)}，区间 [{_fmt(report.base_lower)}, {_fmt(report.base_upper)}]）"
        ]
        if report.clamp_note:
            lines.append(f"[注] {report.clamp_note}")
        for item in report.items:
            lines.append(f"{item.label}：{_fmt(item.base)} × {_pct(item.rate)} = {_fmt(item.personal_amount)}")
        lines.append(f"个人部分合计（计入每月专项扣除）：{_fmt(report.total)}")
        self.social_browser.setPlainText("\n".join(lines))
        self.social_group.show()

    def _show_deductions(self, result) -> None:
        report = result.deductions_report
        lines = []
        for cr in report.claims:
            label = ITEM_LABELS.get(cr.item, cr.item)
            lines.append(f"◆ {label}：{cr.detail}")
            if cr.stage == STAGE_SETTLEMENT_ONLY:
                lines.append(f"    年额 {_fmt(cr.annual_amount)}（仅年度汇算扣除，预扣链不计）[{short_ref(cr.standard_ref)}]")
            else:
                lines.append(
                    f"    月额 {_fmt(cr.monthly_amount)} × {cr.months_claimed} 月 = 年额 {_fmt(cr.annual_amount)}"
                    f"（预扣+汇算）[{short_ref(cr.standard_ref)}]"
                )
            if cr.note:
                lines.append(f"    [注] {cr.note}")
        lines.append(f"预扣链月合计（已逐月计入逐月表）：{_fmt(report.monthly_total)}")
        lines.append(f"汇算链年合计（含仅汇算项 {_fmt(report.settlement_only_annual_total)}）：{_fmt(report.annual_total)}")
        self.deductions_browser.setPlainText("\n".join(lines))
        self.deductions_group.show()

    def _show_monthly(self, result) -> None:
        report = result.monthly_report
        self.monthly_table.setRowCount(len(report.months))
        for row, m in enumerate(report.months):
            values = (
                f"{m.month_no} 月",
                _fmt(m.inp.gross),
                _fmt(m.inp.tax_free),
                _fmt(m.inp.special_deduction),
                _fmt(m.inp.special_additional_deduction),
                _fmt(m.inp.other_deduction),
                _fmt(m.cumulative_taxable),
                _pct(m.rate),
                _fmt(m.quick_deduction),
                _fmt(m.cumulative_tax),
                _fmt(m.withholding),
            )
            for col, text in enumerate(values):
                item = _row(text)
                if m.note:
                    item.setToolTip(m.note)
                self.monthly_table.setItem(row, col, item)

    def _show_settlement(self, result) -> None:
        report = result.settlement_report
        taxable = f"{_fmt(report.cumulative_taxable_income)}"
        if report.bracket_index is not None:
            taxable += f" → 第 {report.bracket_index + 1} 级 {_pct(report.rate)}（速算扣除 {_fmt(report.quick_deduction)}）"
        else:
            taxable += " → 无需缴税"
        sign = "应退税额" if report.refund_or_owe >= 0 else "应补税额"
        self.settlement_labels["taxable"].setText(taxable)
        self.settlement_labels["annual_tax"].setText(_fmt(report.annual_tax))
        self.settlement_labels["withheld"].setText(_fmt(report.withheld_total))
        self.settlement_labels["refund"].setText(f"{sign} {_fmt(abs(report.refund_or_owe))}")
        if report.note:
            self.settlement_labels["refund"].setToolTip(report.note)

    def _show_bonus(self, ruleset, result) -> None:
        report = result.bonus_report
        rows = result.trap_intervals or ()
        lines = [
            f"奖金 {_fmt(report.bonus_amount)} ÷ {report.divisor:f} = {_fmt(report.quotient)}"
            "（商数定档，税基用全额）"
        ]
        if report.bracket_index is not None:
            lines.append(
                f"按月换算税率表第 {report.bracket_index + 1} 级 {_pct(report.rate)}"
                f"（速算扣除 {_fmt(report.quick_deduction)}）"
            )
        lines.append(
            f"应纳税额 = {_fmt(report.bonus_amount)} × {_pct(report.rate)} − {_fmt(report.quick_deduction)}"
            f" = {_fmt(report.tax)}；税后奖金 {_fmt(report.after_tax)}"
        )
        lines.append(f"政策：{report.policy_note}")
        if rows:
            lines.append(f"临界区间（由按月换算表逐边界推导，共 {len(rows)} 个，区间为开区间）：")
            for iv in rows:
                mark = ""
                if result.active_trap is not None and iv == result.active_trap:
                    mark = " ← 当前奖金落入"
                lines.append(f"    ({_fmt(iv.lower)}, {_fmt(iv.upper)}){mark}")
        html = "<pre>" + "\n".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"

        comparison = result.bonus_comparison
        if comparison is not None:
            a, b = comparison.scheme_separate, comparison.scheme_combined
            salary_tax = a.annual_total_tax - report.tax
            diff = comparison.tax_difference
            html += "<hr><pre>"
            html += f"{a.label}：工资汇算 {_fmt(salary_tax)} + 奖金单独计税 {_fmt(report.tax)} = 全年总税负 {_fmt(a.annual_total_tax)}\n"
            b_line = f"{b.label}：并入后应纳税所得额 {_fmt(b.taxable_income)}"
            if b.bracket_index is not None:
                b_line += f" → 第 {b.bracket_index + 1} 级 {_pct(b.rate)}（速算扣除 {_fmt(b.quick_deduction)}）"
            b_line += f" → 全年应纳税额 {_fmt(b.annual_total_tax)}"
            html += b_line + "\n"
            if comparison.tie:
                recommend = f"差额（A−B）：{_fmt(diff)} → 两案等同（差不超过申报精度），可任选"
            elif comparison.recommended == "separate":
                recommend = f"差额（A−B）：{_fmt(diff)} → 推荐方案A：单独计税全年少缴 {_fmt(-diff)}"
            else:
                recommend = f"差额（A−B）：{_fmt(diff)} → 推荐方案B：并入综合全年少缴 {_fmt(diff)}"
            html += f"<b>{recommend}</b>\n"
            if not a.available:
                html += f"[!!] {a.note}\n"
            html += "</pre>"

        self.bonus_browser.setHtml(html)
        self.bonus_group.show()

        if result.active_trap is not None:
            lo, hi = _fmt(result.active_trap.lower), _fmt(result.active_trap.upper)
            self.trap_banner.setText(
                f"[!!] 当前奖金落入\"多发反而少得\"临界区间（{lo}, {hi}）：区间内税后奖金低于区间左端点处的税后金额"
                "（税率表级距机制客观呈现，非避税建议；可将奖金申报至区间左端点比较税后所得）"
            )
            self.trap_banner.show()
        else:
            self.trap_banner.hide()
