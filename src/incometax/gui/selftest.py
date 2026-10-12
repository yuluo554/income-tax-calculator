"""冻结态自检通道（M5 打包验收用，不参与正常 GUI 交互）。

用途：`exe --selftest <输入JSON> <输出文本>` —— 在**中立工作目录**下验证打包产物：
1. 数据目录定位命中内嵌 sys._MEIPASS/data（loader.find_data_dir 第三优先级）；
2. calc 全链路编排（engine.pipeline.compute_full_calc）可跑通；
3. 内置基准 run_all() 全部达标；
结果写入输出文本文件（GUI exe 为窗口程序，无控制台，故用文件回传），
并按结论设置退出码（0 = 自检通过）。

本模块只做「读输入 → 调引擎/基准 → 写结论」，零政策数值字面量（输入值全部
来自外部 JSON，规则数值全部来自内嵌规则包）。
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import List

from incometax import __version__
from incometax.benchmark.runner import run_all
from incometax.engine import deductions as deductions_engine
from incometax.engine import pipeline as pipeline_engine
from incometax.engine.monthly import MonthInput
from incometax.rules import loader


def _month_from_node(node: dict) -> MonthInput:
    return MonthInput(
        gross=Decimal(str(node.get("gross", 0))),
        tax_free=Decimal(str(node.get("tax_free", 0))),
        special_deduction=Decimal(str(node.get("special_deduction", 0))),
        special_additional_deduction=Decimal(str(node.get("special_additional_deduction", 0))),
        other_deduction=Decimal(str(node.get("other_deduction", 0))),
    )


def _claims_from_nodes(nodes) -> List[deductions_engine.Claim]:
    claims = []
    for node in nodes or []:
        kwargs = {"item": node["item"]}
        for key in ("children", "share_ratio", "monthly_amount", "self_paid_total"):
            if key in node:
                kwargs[key] = Decimal(str(node[key]))
        for key in ("kind", "months", "tier", "only_child"):
            if key in node:
                kwargs[key] = node[key]
        if "other_shared_amounts" in node:
            kwargs["other_shared_amounts"] = tuple(
                Decimal(str(v)) for v in node["other_shared_amounts"]
            )
        claims.append(deductions_engine.Claim(**kwargs))
    return claims


def _gui_smoke(lines) -> bool:
    """offscreen 构建主窗口（证明打包产物 Qt 运行期与 GUI 装配可用）。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        from incometax.gui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window._enter_main()  # 免责首屏 → 主界面 + 加载年度规则包
        years = window.year_combo.count()
        loaded = window.ruleset.year if window.ruleset is not None else None
        window.close()
        if loaded is None:
            lines.append("[FAIL] GUI 冒烟：主界面未加载任何年度规则包")
            return False
        lines.append(f"[OK] GUI 冒烟（offscreen）：主界面可用，年度下拉 {years} 项，当前 {loaded}")
        return True
    except Exception as exc:
        lines.append(f"[FAIL] GUI 冒烟：{type(exc).__name__}: {exc}")
        return False


def run_selftest(input_path: str, output_path: str, data_dir: str = None) -> int:
    """执行自检并写结论文件；返回退出码（0 = 通过）。"""
    lines = [f"个人所得税联动计算器 冻结态自检（v{__version__}）"]
    ok = True
    try:
        resolved = loader.find_data_dir(data_dir)
        lines.append(f"[OK] 数据目录定位：{resolved}")
        years = loader.available_years(resolved)
        lines.append(f"[OK] 可用年度规则包：{years}")

        raw = json.loads(Path(input_path).read_text(encoding="utf-8"), parse_float=Decimal)
        year = int(raw["year"])
        ruleset = loader.effective_ruleset(loader.load_ruleset(year, data_dir=str(resolved)))

        social = raw.get("social")
        social_params = None
        if social:
            social_params = (
                Decimal(str(social["base_input"])),
                {k: Decimal(str(v)) for k, v in social["rates"].items()},
                Decimal(str(social["base_lower"])),
                Decimal(str(social["base_upper"])),
            )
        request = pipeline_engine.CalcRequest(
            months=tuple(_month_from_node(m) for m in raw["months"]),
            social_params=social_params,
            claims=tuple(_claims_from_nodes(raw.get("special_additional_claims"))),
            bonus_income=(
                Decimal(str(raw["bonus_income"])) if raw.get("bonus_income") is not None else None
            ),
        )
        result = pipeline_engine.compute_full_calc(ruleset, request)
        mr = result.monthly_report
        sr = result.settlement_report
        lines.append(f"[OK] calc 全链路：{year} 年度，逐月表 {len(mr.months)} 行")
        lines.append(f"     已预扣预缴合计 {mr.withheld_total}；年应纳税额 {sr.annual_tax}")
        if result.bonus_report is not None:
            trap = "落入临界区间" if result.active_trap is not None else "未落入临界区间"
            lines.append(f"     年终奖税后 {result.bonus_report.after_tax}（{trap}）")

        report = run_all(data_dir=str(resolved))
        lines.append(
            f"[{'OK' if report.all_ok else '!!'}] 内置基准：{report.total_checks} 项检查，"
            f"{'全部达标' if report.all_ok else '存在未达标项'}"
        )
        ok = ok and report.all_ok
        ok = _gui_smoke(lines) and ok
    except Exception as exc:  # 自检任何异常都如实回传，避免静默通过
        ok = False
        lines.append(f"[FAIL] {type(exc).__name__}: {exc}")

    lines.append("自检结论：" + ("通过" if ok else "未通过"))
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
