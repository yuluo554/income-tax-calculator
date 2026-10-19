"""依据面板（M5）：来源图例 + 结果数值条目的依据清单。

- 复用 engine.report.render_ref（ref 节点 → "文号 条款"，与 CLI 同一渲染语义）；
- 依据收集自最近一次计算结果：减除费用、逐月命中级次、扣除标准、年终奖级次与
  政策、汇算级次、临界区间两侧级次——全部去重后按出现顺序列出；
- 本面板不做计算，只读规则包 sources[] 与 Report 中的 ref 节点。
"""

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from incometax.engine import pipeline as pipeline_engine
from incometax.engine.report import render_ref, short_ref


class RefPanel(QWidget):
    """依据面板：来源图例（文号+URL）+ 本次数值条目的依据清单。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.browser)
        self.clear()

    def clear(self) -> None:
        self.browser.setHtml("<p>尚无计算结果：完成一次计算后，此处列出本次结果引用的全部依据。</p>")

    # ------------------------------------------------------------------
    # 依据收集
    # ------------------------------------------------------------------

    @staticmethod
    def _ref_key(ref: Any) -> Optional[Tuple[str, str]]:
        if not isinstance(ref, dict):
            return None
        return (str(ref.get("source", "")), str(ref.get("clause", "")))

    def _collect_refs(self, ruleset, result) -> List[Dict[str, Any]]:
        refs: List[Tuple[Tuple[str, str], Dict[str, Any]]] = []
        seen = set()

        def add(ref: Any) -> None:
            key = self._ref_key(ref)
            if key is None or key == ("", "") or key in seen:
                return
            seen.add(key)
            refs.append((key, ref))

        tables = ruleset.data["rate_tables"]

        def add_table_row(table_field: str, index: Optional[int]) -> None:
            if index is None:
                return
            row = tables[table_field][index]
            add(row.get("ref"))
            add(row.get("ref_qd"))

        mr = result.monthly_report
        if mr is not None:
            add(mr.standard_deduction_ref)
            for m in mr.months:
                add_table_row(mr.table_field, m.bracket_index)

        sr = result.settlement_report
        if sr is not None:
            add(sr.standard_deduction_ref)
            add_table_row("comprehensive_annual", sr.bracket_index)

        dr = result.deductions_report
        if dr is not None:
            for cr in dr.claims:
                add(cr.standard_ref)

        br = result.bonus_report
        if br is not None:
            add_table_row(br.table_field, br.bracket_index)
            policy = ruleset.data.get("bonus", {}).get("separate_tax_policy", {})
            add(policy.get("ref"))

        comp = result.bonus_comparison
        if comp is not None:
            add_table_row("comprehensive_annual", comp.scheme_combined.bracket_index)

        for iv in result.trap_intervals or ():
            add_table_row("monthly_converted", iv.left_bracket_index)
            add_table_row("monthly_converted", iv.right_bracket_index)

        return [ref for _, ref in refs]

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def show_result(self, ruleset, result: pipeline_engine.CalcResult) -> None:
        sources = ruleset.data.get("sources", [])
        legend = ["<h3>来源图例</h3>"]
        for src in sources:
            doc = str(src.get("doc", ""))
            url = str(src.get("url", "") or "")
            status = str(src.get("status", ""))
            reviewed_at = str(src.get("reviewed_at", "") or "")
            note = str(src.get("note", "") or "")
            tags = []
            if status:
                tags.append(f"核对状态：{status}")
            if reviewed_at:
                tags.append(f"核对日期：{reviewed_at}")
            line = f"<p><b>{src.get('id', '')}</b>：{doc}"
            if url:
                line += f"<br/>&nbsp;&nbsp;&nbsp;&nbsp;{url}"
            if tags:
                line += f"（{'；'.join(tags)}）"
            if note:
                line += f"<br/>&nbsp;&nbsp;&nbsp;&nbsp;{note}"
            legend.append(line + "</p>")

        refs = self._collect_refs(ruleset, result)
        listing = ["<h3>本次结果依据清单</h3>"]
        if refs:
            rows = []
            for i, ref in enumerate(refs, start=1):
                short = short_ref(ref)
                full = render_ref(ref, sources)
                rows.append(f"<p>{i}. <b>{short}</b> —— {full}</p>")
            listing.append("".join(rows))
        else:
            listing.append("<p>本次计算未引用税率表级次（如全部收入免税）。</p>")
        self.browser.setHtml("".join(legend) + "<hr>" + "".join(listing))
