"""计算输入面板（M5）：逐月输入表 + 社保联动参数 + 年终奖 + 专项附加申报管理。

- 全部金额输入走 QLineEdit + Decimal 解析（不用浮点控件，Decimal 全链路口径）；
- 空单元格按 0 处理（与 CLI 输入 schema 语义一致）；
- 社保参数任一填写则四项必填（基数/上下限/费率），费率行为"险种=费率"逗号分隔；
- 专项附加申报：列表管理（添加/编辑/删除），编辑对话框按项目给出对应字段，
  校验交给引擎（违规整单拒绝）——本面板只做收集，不做政策数值判断。
"""

from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from incometax.engine.deductions import Claim, ITEM_LABELS, KNOWN_ITEMS
from incometax.engine.monthly import MONTHS_PER_YEAR, MonthInput
from incometax.engine.pipeline import CalcRequest
from incometax.engine.report import money

MONTH_COLUMNS = ("工资薪金收入", "免税收入", "专项扣除", "专项附加扣除", "其他扣除")


class GuiInputError(Exception):
    """输入面板收集失败（呈现为错误对话框，不进入引擎）。"""


def parse_decimal_text(text: str, where: str) -> Optional[Decimal]:
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise GuiInputError(f"{where}：不是合法金额 {text!r}")


def _money_text(value: Decimal) -> str:
    return f"{money(value):.2f}"


def claim_summary(claim: Claim) -> str:
    """申报条目 → 列表展示摘要（仅用户输入侧字段，金额计算交给引擎）。"""
    label = ITEM_LABELS.get(claim.item, claim.item)
    if claim.item in ("child_education", "infant_care"):
        ratio = f"{claim.share_ratio * 100:.0f}%"
        return f"{label}：{claim.children.to_integral_value()} 孩 × 分摊 {ratio} × {claim.months} 个月"
    if claim.item == "continue_education":
        if claim.kind == "academic":
            return f"{label}：学历（学位）{claim.months} 个月"
        return f"{label}：职业资格（证书当年年度定额）"
    if claim.item == "serious_illness":
        return f"{label}：医保目录内自付累计 {_money_text(claim.self_paid_total)}（仅汇算扣除）"
    if claim.item == "housing_loan":
        return f"{label}：{claim.months} 个月（首套住房贷款）"
    if claim.item == "housing_rent":
        return f"{label}：城市档 {claim.tier} × {claim.months} 个月"
    if claim.item == "support_elderly":
        if claim.only_child:
            return f"{label}：独生子女定额 × {claim.months} 个月"
        others = "、".join(f"{money(a):.2f}" for a in claim.other_shared_amounts)
        return (
            f"{label}：非独生分摊 本人 {_money_text(claim.monthly_amount)}/月"
            + (f"，其他共赡养人 {others}" if others else "")
            + f" × {claim.months} 个月"
        )
    return label


class InputPanel(QWidget):
    """计算输入区（build_request 产出 CalcRequest，交 pipeline 编排）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._claims: List[Claim] = []
        self._rent_tiers: Tuple[str, ...] = ()  # (tier desc, ...) 由 set_ruleset 注入
        self._available_items: Tuple[str, ...] = KNOWN_ITEMS
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.ruleset_label = QLabel("规则包：未加载")
        self.ruleset_label.setWordWrap(True)
        root.addWidget(self.ruleset_label)

        # ---- 逐月表 ----
        months_box = QGroupBox("逐月输入（空 = 0；社保联动产出会计入每月专项扣除）")
        mv = QVBoxLayout(months_box)
        self.months_table = QTableWidget(MONTHS_PER_YEAR, len(MONTH_COLUMNS) + 1)
        self.months_table.setHorizontalHeaderLabels(("月份",) + MONTH_COLUMNS)
        self.months_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.months_table.verticalHeader().setVisible(False)
        for row in range(MONTHS_PER_YEAR):
            item = QTableWidgetItem(f"{row + 1} 月")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.months_table.setItem(row, 0, item)
            for col in range(1, len(MONTH_COLUMNS) + 1):
                self.months_table.setItem(row, col, QTableWidgetItem(""))
        self.months_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        mv.addWidget(self.months_table)
        root.addWidget(months_box, 3)

        # ---- 社保联动 ----
        social_box = QGroupBox("社保公积金联动（可选；基数上下限与费率均为用户输入）")
        sv = QVBoxLayout(social_box)
        form_rows = (
            ("缴费基数（月）", "social_base"),
            ("基数下限", "social_lower"),
            ("基数上限", "social_upper"),
        )
        social_form = QHBoxLayout()
        self.social_edits = {}
        for label_text, key in form_rows:
            social_form.addWidget(QLabel(label_text))
            edit = QLineEdit()
            edit.setPlaceholderText("留空 = 不参与社保联动")
            self.social_edits[key] = edit
            social_form.addWidget(edit)
        root_social = social_form
        sv.addLayout(root_social)
        rates_row = QHBoxLayout()
        rates_row.addWidget(QLabel("个人费率（险种=费率，逗号分隔）"))
        self.social_rates_edit = QLineEdit()
        self.social_rates_edit.setPlaceholderText("养老=0.08, 医疗=0.02, 失业=0.005, 公积金=0.12")
        rates_row.addWidget(self.social_rates_edit, 1)
        sv.addLayout(rates_row)
        root.addWidget(social_box, 0)

        # ---- 年终奖 ----
        bonus_box = QGroupBox("全年一次性奖金（可选；留空 = 不计算年终奖）")
        bv = QHBoxLayout(bonus_box)
        bv.addWidget(QLabel("奖金金额"))
        self.bonus_edit = QLineEdit()
        self.bonus_edit.setPlaceholderText("留空 = 无年终奖")
        bv.addWidget(self.bonus_edit, 1)
        root.addWidget(bonus_box, 0)

        # ---- 专项附加申报管理 ----
        claims_box = QGroupBox("专项附加扣除申报（七项；互斥/分摊/上限校验由引擎执行，违规整单拒绝）")
        cv = QVBoxLayout(claims_box)
        self.claims_list = QListWidget()
        cv.addWidget(self.claims_list, 1)
        buttons = QHBoxLayout()
        add_btn = QPushButton("添加申报")
        add_btn.clicked.connect(self._on_add_claim)
        edit_btn = QPushButton("编辑所选")
        edit_btn.clicked.connect(self._on_edit_claim)
        del_btn = QPushButton("删除所选")
        del_btn.clicked.connect(self._on_delete_claim)
        buttons.addWidget(add_btn)
        buttons.addWidget(edit_btn)
        buttons.addWidget(del_btn)
        buttons.addStretch(1)
        cv.addLayout(buttons)
        root.addWidget(claims_box, 2)

    # ------------------------------------------------------------------
    # 规则包注入
    # ------------------------------------------------------------------

    def set_ruleset(self, ruleset) -> None:
        """年度切换后注入规则包：租金城市档描述与可申报项目按年度规则包刷新。"""
        notes = str(ruleset.data.get("notes", "") or "")
        self.ruleset_label.setText(f"规则包：{ruleset.year} 年度已加载" + (f"（{notes}）" if notes else ""))
        rent = ruleset.data.get("special_deductions", {}).get("housing_rent", {})
        tiers = rent.get("tiers", [])
        self._rent_tiers = tuple(str(t.get("tier", {}).get("desc", f"档 {i}")) for i, t in enumerate(tiers))
        items = ruleset.data.get("special_deductions", {})
        self._available_items = tuple(item for item in KNOWN_ITEMS if item in items)
        self._refresh_claims()

    # ------------------------------------------------------------------
    # 申报管理
    # ------------------------------------------------------------------

    def _refresh_claims(self) -> None:
        self.claims_list.clear()
        for claim in self._claims:
            self.claims_list.addItem(QListWidgetItem(claim_summary(claim)))

    def _on_add_claim(self) -> None:
        from incometax.gui.claim_dialog import ClaimDialog  # 局部导入避免启动加载全部对话框

        dialog = ClaimDialog(self, tiers=self._rent_tiers, available_items=self._available_items)
        if dialog.exec():
            self._claims.append(dialog.build_claim())
            self._refresh_claims()

    def _on_edit_claim(self) -> None:
        row = self.claims_list.currentRow()
        if row < 0 or row >= len(self._claims):
            return
        from incometax.gui.claim_dialog import ClaimDialog

        dialog = ClaimDialog(
            self,
            tiers=self._rent_tiers,
            available_items=self._available_items,
            claim=self._claims[row],
        )
        if dialog.exec():
            self._claims[row] = dialog.build_claim()
            self._refresh_claims()

    def _on_delete_claim(self) -> None:
        row = self.claims_list.currentRow()
        if row < 0 or row >= len(self._claims):
            return
        del self._claims[row]
        self._refresh_claims()

    def add_claim_direct(self, claim: Claim) -> None:
        """测试/脚本入口：不经对话框直接加入一条申报。"""
        self._claims.append(claim)
        self._refresh_claims()

    # ------------------------------------------------------------------
    # 收集 → CalcRequest
    # ------------------------------------------------------------------

    def _parse_social_rates(self, text: str) -> "dict":
        rates = {}
        for part in text.replace("，", ",").replace("；", ";").replace(";", ",").split(","):
            chunk = part.strip()
            if not chunk:
                continue
            for sep in ("=", "：", ":"):
                if sep in chunk:
                    label, _, value = chunk.partition(sep)
                    break
            else:
                raise GuiInputError(f"社保费率项 {chunk!r} 缺少 =（格式：险种=费率）")
            label = label.strip()
            value = value.strip()
            if not label:
                raise GuiInputError(f"社保费率项 {chunk!r} 缺少险种名")
            rate = parse_decimal_text(value, f"社保费率 {label}")
            if rate is None:
                raise GuiInputError(f"社保费率 {label}：费率为空")
            rates[label] = rate
        if not rates:
            raise GuiInputError("社保费率：至少填写一项（如 养老=0.08）")
        return rates

    def build_request(self) -> CalcRequest:
        months: List[MonthInput] = []
        for row in range(self.months_table.rowCount()):
            values = []
            for col in range(1, len(MONTH_COLUMNS) + 1):
                item = self.months_table.item(row, col)
                text = item.text() if item is not None else ""
                value = parse_decimal_text(text, f"第 {row + 1} 月「{MONTH_COLUMNS[col - 1]}」")
                values.append(Decimal(0) if value is None else value)
            months.append(
                MonthInput(
                    gross=values[0],
                    tax_free=values[1],
                    special_deduction=values[2],
                    special_additional_deduction=values[3],
                    other_deduction=values[4],
                )
            )

        social_params = None
        base = parse_decimal_text(self.social_edits["social_base"].text(), "缴费基数")
        lower = parse_decimal_text(self.social_edits["social_lower"].text(), "基数下限")
        upper = parse_decimal_text(self.social_edits["social_upper"].text(), "基数上限")
        rates_text = self.social_rates_edit.text().strip()
        filled = [v is not None for v in (base, lower, upper)] + [bool(rates_text)]
        if any(filled):
            if not all(filled):
                raise GuiInputError("社保联动：基数、下限、上限、费率需填写完整（或全部留空不参与）")
            social_params = (base, self._parse_social_rates(rates_text), lower, upper)

        bonus_income = parse_decimal_text(self.bonus_edit.text(), "年终奖金额")
        return CalcRequest(
            months=tuple(months),
            social_params=social_params,
            claims=tuple(self._claims),
            bonus_income=bonus_income,
        )
