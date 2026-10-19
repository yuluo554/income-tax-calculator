"""GUI offscreen 测试（M5）。

纪律（HANDOFF-M5）：
- QT_QPA_PLATFORM=offscreen 由 tests/conftest.py 在任何 PySide6 导入之前设置；
- 模态对话框全部经由 MainWindow._show_error/_show_info 出口（测试 monkeypatch
  屏蔽）与 ClaimDialog 的"确定时构建成功才 accept"（测试直接调用 build_claim，
  不 exec），全程无阻塞；
- 顶层窗口未 show 时 isVisible() 恒为 False，"已显示"断言一律用 isHidden()/文本。
"""

from decimal import Decimal

import json

import pytest
from PySide6.QtWidgets import QApplication

from incometax.gui.app import _parse_args
from incometax.gui.benchmark_panel import BenchmarkPanel
from incometax.gui.claim_dialog import ClaimDialog
from incometax.gui.main_window import APP_TITLE, MainWindow
from incometax.gui.input_panel import GuiInputError, claim_summary
from incometax.engine.deductions import Claim


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def window(qapp, monkeypatch):
    """确认免责首屏后的主窗口；_show_error/_show_info 记录到 errors 列表不弹窗。"""
    w = MainWindow()
    w.show()
    w.errors = []
    monkeypatch.setattr(w, "_show_error", lambda title, detail: w.errors.append((title, detail)))
    monkeypatch.setattr(w, "_show_info", lambda title, detail: w.errors.append((title, detail)))
    w._enter_main()
    yield w
    w.close()


def _fill_uniform_months(w, gross, special_deduction):
    for row in range(w.input_panel.months_table.rowCount()):
        w.input_panel.months_table.item(row, 1).setText(gross)
        w.input_panel.months_table.item(row, 3).setText(special_deduction)


# ---------------------------------------------------------------------------
# 首屏 / 年度切换
# ---------------------------------------------------------------------------


def test_disclaimer_is_first_screen(qapp):
    w = MainWindow()
    w.show()
    assert w._stack.currentIndex() == 0
    assert "免责声明" in w.disclaimer_browser.toPlainText()
    w._enter_main()
    assert w._stack.currentIndex() == 1
    w.close()


def test_year_combo_defaults_to_latest_and_ruleset_loaded(window):
    assert window.year_combo.count() >= 2
    latest = window.year_combo.currentData()
    assert latest is not None
    assert window.ruleset is not None
    assert window.ruleset.year == latest
    assert "已加载" in window.input_panel.ruleset_label.text()


def test_switch_year_clears_results(window):
    _fill_uniform_months(window, "8000", "1000")
    window._on_compute()
    assert window.results_panel.monthly_table.rowCount() == 12
    window.year_combo.setCurrentIndex(0)  # 切到最早年度 → 旧结果清空、输入保留
    assert window.ruleset.year == window.year_combo.itemData(0)
    assert window.results_panel.monthly_table.rowCount() == 0
    assert "已加载" in window.input_panel.ruleset_label.text()


def test_compute_with_bad_input_shows_error_dialog(window):
    window.input_panel.months_table.item(0, 1).setText("abc")
    window._on_compute()
    assert window.errors and "输入有误" in window.errors[0][0]


# ---------------------------------------------------------------------------
# 计算：逐月表 + 汇算 + 年终奖择优与临界标红
# ---------------------------------------------------------------------------


def test_compute_monthly_and_settlement(window):
    _fill_uniform_months(window, "8000", "1000")
    window._on_compute()
    assert window.tabs.currentWidget() is window.results_panel
    assert window.results_panel.monthly_table.rowCount() == 12
    # 汇总链路：月度聚合 → 汇算（无 bonus 时无择优面板）
    assert "应退税额 0.00" in window.results_panel.settlement_labels["refund"].text()
    assert window.results_panel.bonus_group.isHidden()


def test_bonus_trap_highlighted_and_recommendation_rendered(window):
    _fill_uniform_months(window, "8000", "1000")
    window.input_panel.bonus_edit.setText("36001")
    window._on_compute()
    assert not window.results_panel.trap_banner.isHidden()
    assert "临界区间" in window.results_panel.trap_banner.text()
    bonus_text = window.results_panel.bonus_browser.toPlainText()
    assert "单独计税" in bonus_text and "推荐方案" in bonus_text


def test_bonus_outside_trap_no_banner(window):
    _fill_uniform_months(window, "8000", "1000")
    window.input_panel.bonus_edit.setText("20000")
    window._on_compute()
    assert window.results_panel.trap_banner.isHidden()
    assert window.results_panel.bonus_group.isVisibleTo(window.results_panel)


def test_social_linkage_feeds_monthly(window):
    window.input_panel.social_edits["social_base"].setText("8000")
    window.input_panel.social_edits["social_lower"].setText("4000")
    window.input_panel.social_edits["social_upper"].setText("30000")
    window.input_panel.social_rates_edit.setText("养老=0.08, 公积金=0.12")
    window.input_panel.months_table.item(0, 1).setText("8000")
    window._on_compute()
    assert not window.results_panel.social_group.isHidden()
    social_text = window.results_panel.social_browser.toPlainText()
    assert "个人部分合计" in social_text
    # 第 1 月专项扣除 = 用户输入 0 + 社保联动合计（1600 = 8000×(0.08+0.12)）
    row0 = [window.results_panel.monthly_table.item(0, c).text() for c in range(11)]
    assert row0[3] == "1600.00"


# ---------------------------------------------------------------------------
# 专项附加申报：违规整单拒绝 + 合法链路
# ---------------------------------------------------------------------------


def test_claim_violation_whole_rejected(window):
    window.input_panel.add_claim_direct(Claim(item="housing_loan"))
    window.input_panel.add_claim_direct(Claim(item="housing_rent", tier=0))
    _fill_uniform_months(window, "8000", "1000")
    window._on_compute()
    assert window.errors, "违规必须以对话框呈现"
    title, detail = window.errors[0]
    assert "申报校验未通过" in title
    assert "住房" in detail
    assert window.results_panel.monthly_table.rowCount() == 0, "整单拒绝不产出部分结果"


def test_claim_valid_child_education_flows_into_settlement(window):
    window.input_panel.add_claim_direct(
        Claim(item="child_education", children=Decimal(1), share_ratio=Decimal(1), months=12)
    )
    _fill_uniform_months(window, "8000", "1000")
    window._on_compute()
    assert not window.results_panel.deductions_group.isHidden()
    text = window.results_panel.deductions_browser.toPlainText()
    assert "子女教育" in text
    # 申报月额逐月计入预扣链 → 全年应纳税所得额归零 → 年应纳税额 0.00、汇算应退
    assert "0.00" in window.results_panel.settlement_labels["annual_tax"].text()
    assert "应退税额" in window.results_panel.settlement_labels["refund"].text()


def test_claim_serious_illness_settlement_only_not_in_withholding(window):
    window.input_panel.add_claim_direct(Claim(item="serious_illness", self_paid_total=Decimal("20000")))
    _fill_uniform_months(window, "8000", "1000")
    window._on_compute()
    text = window.results_panel.deductions_browser.toPlainText()
    assert "仅年度汇算扣除" in text
    # 预扣链不受 settlement_only 影响（月度专项附加保持 0），汇算链单独纳入
    row0 = [window.results_panel.monthly_table.item(0, c).text() for c in range(11)]
    assert row0[4] == "0.00"


# ---------------------------------------------------------------------------
# 申报对话框（直接 build_claim，不 exec —— 无模态阻塞）
# ---------------------------------------------------------------------------


def test_claim_dialog_builds_children_claim(qapp, monkeypatch):
    dialog = ClaimDialog(tiers=("直辖市/省会", "其他城市"), available_items=("child_education",))
    dialog.item_combo.setCurrentIndex(0)
    dialog.children_spin.setValue(2)
    dialog.share_combo.setCurrentIndex(1)
    dialog.children_months_spin.setValue(10)
    claim = dialog.build_claim()
    assert claim.item == "child_education"
    assert claim.children == Decimal(2)
    assert claim.share_ratio == Decimal("0.5")
    assert claim.months == 10


def test_claim_dialog_invalid_amount_stays_open(qapp, monkeypatch):
    dialog = ClaimDialog(available_items=("serious_illness",))
    dialog.item_combo.setCurrentIndex(0)
    dialog.self_paid_edit.setText("not-a-number")
    warnings = []
    monkeypatch.setattr(
        "incometax.gui.claim_dialog.QMessageBox.warning",
        lambda *a, **k: warnings.append(a),
    )
    dialog._on_ok()
    assert warnings, "解析失败必须在框内提示"
    assert dialog.result() != ClaimDialog.Accepted


def test_claim_dialog_rent_tier_from_ruleset(qapp):
    dialog = ClaimDialog(tiers=("直辖市/省会", "市辖区户籍人口", "市辖区户籍人口以下"), available_items=("housing_rent",))
    dialog.item_combo.setCurrentIndex(0)
    dialog.tier_combo.setCurrentIndex(2)
    dialog.rent_months_spin.setValue(6)
    claim = dialog.build_claim()
    assert claim.item == "housing_rent"
    assert claim.tier == 2
    assert claim.months == 6


def test_claim_summary_text(qapp):
    text = claim_summary(Claim(item="support_elderly", only_child=False, monthly_amount=Decimal("1000")))
    assert "赡养老人" in text and "1000.00" in text
    assert "子女教育" in claim_summary(Claim(item="child_education", children=Decimal(1)))


def test_input_panel_social_partial_fill_rejected(window):
    window.input_panel.social_edits["social_base"].setText("8000")
    with pytest.raises(GuiInputError):
        window.input_panel.build_request()


# ---------------------------------------------------------------------------
# 内置基准面板（GUI 与 CLI 共用 run_all 同一 API）
# ---------------------------------------------------------------------------


def test_benchmark_panel_runs_all_metrics(qapp):
    panel = BenchmarkPanel()
    panel.run_benchmark()
    assert panel.table.rowCount() == 4
    assert "全部达标" in panel.summary_label.text()
    for row in range(panel.table.rowCount()):
        assert "[OK] 达标" in panel.table.item(row, 4).text()
    assert "无失败明细" in panel.failures.toPlainText()


# ---------------------------------------------------------------------------
# 入口杂项
# ---------------------------------------------------------------------------


def test_parse_args_helper():
    assert _parse_args([]) == (None, None)
    assert _parse_args(["--data-dir", "X", "--other"]) == ("X", None)
    assert _parse_args(["--data-dir"]) == (None, None)
    data_dir, selftest = _parse_args(["--data-dir", "X", "--selftest", "in.json", "out.txt"])
    assert data_dir == "X"
    assert selftest == ("in.json", "out.txt")


def test_selftest_runs_end_to_end(tmp_path, qapp):
    """冻结态自检通道（打包验收用）：中性 CWD 下走通引擎与基准，写结论文件。"""
    from incometax.gui.selftest import run_selftest

    input_path = tmp_path / "selftest-in.json"
    input_path.write_text(
        json.dumps(
            {
                "year": 2024,
                "months": [{"gross": "8000", "special_deduction": "1000"}] * 12,
                "bonus_income": "36001",
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "selftest-out.txt"
    rc = run_selftest(str(input_path), str(output_path))
    assert rc == 0
    text = output_path.read_text(encoding="utf-8")
    assert "数据目录定位" in text
    assert "calc 全链路" in text
    assert "内置基准" in text
    assert "自检结论：通过" in text


def test_app_display_name_finalized():
    # plan/06 决策 #2 定稿：应用显示名（GUI 标题/exe 名共用）
    assert APP_TITLE == "个人所得税联动计算器"


def test_gui_ref_panel_shows_reviewed_at(qapp):
    """依据面板来源图例显示核对日期（值来自 sources[]，不硬编码）。"""
    from types import SimpleNamespace

    from incometax.gui.ref_panel import RefPanel
    from incometax.rules import load_ruleset

    ruleset = load_ruleset(2026)
    expected = ruleset.data["sources"][0]["reviewed_at"]
    panel = RefPanel()
    panel.show_result(
        ruleset,
        SimpleNamespace(
            monthly_report=None,
            settlement_report=None,
            deductions_report=None,
            bonus_report=None,
            bonus_comparison=None,
            trap_intervals=(),
        ),
    )
    text = panel.browser.toPlainText()
    assert "核对日期：" in text
    assert expected in text
