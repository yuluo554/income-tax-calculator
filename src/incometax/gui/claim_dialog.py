"""专项附加扣除申报编辑对话框（M5）：按扣除项目切换对应字段页。

- 字段只做收集与基本解析（金额 Decimal）；互斥/分摊/上限等政策校验交给引擎
  （违规整单拒绝），本对话框不判断政策合法性；
- 城市档下拉项 = 规则包租金分档描述（set_ruleset 时注入，无政策字面量）；
- 确定按钮先 build_claim() 成功才 accept（解析失败在框内提示，不关闭）。
"""

from decimal import Decimal, InvalidOperation
from typing import Optional, Sequence, Tuple

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from incometax.engine.deductions import Claim, ITEM_LABELS, KNOWN_ITEMS
from incometax.engine.monthly import MONTHS_PER_YEAR
from incometax.engine.report import money

HALF = Decimal("0.5")  # 分摊比例取值（引擎校验口径 100%/50%），非政策数值

# 项目 → 字段页下标
_PAGE_CHILDREN = 0  # child_education / infant_care
_PAGE_EDUCATION = 1
_PAGE_ILLNESS = 2
_PAGE_LOAN = 3
_PAGE_RENT = 4
_PAGE_ELDERLY = 5

_ITEM_PAGE = {
    "child_education": _PAGE_CHILDREN,
    "infant_care": _PAGE_CHILDREN,
    "continue_education": _PAGE_EDUCATION,
    "serious_illness": _PAGE_ILLNESS,
    "housing_loan": _PAGE_LOAN,
    "housing_rent": _PAGE_RENT,
    "support_elderly": _PAGE_ELDERLY,
}


class ClaimDialog(QDialog):
    """添加/编辑一条专项附加扣除申报。"""

    def __init__(
        self,
        parent=None,
        tiers: Tuple[str, ...] = (),
        available_items: Sequence[str] = KNOWN_ITEMS,
        claim: Optional[Claim] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("专项附加扣除申报")
        self.setMinimumWidth(420)
        self._tiers = tuple(tiers)
        self._build_ui(available_items)
        if claim is not None:
            self._load_claim(claim)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self, available_items: Sequence[str]) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel("扣除项目："))
        self.item_combo = QComboBox()
        for item in KNOWN_ITEMS:
            if item in available_items:
                self.item_combo.addItem(ITEM_LABELS.get(item, item), item)
        self.item_combo.currentIndexChanged.connect(self._on_item_changed)
        root.addWidget(self.item_combo)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_children())
        self.stack.addWidget(self._page_education())
        self.stack.addWidget(self._page_illness())
        self.stack.addWidget(self._page_loan())
        self.stack.addWidget(self._page_rent())
        self.stack.addWidget(self._page_elderly())
        root.addWidget(self.stack, 1)

        note_form = QFormLayout()
        self.note_edit = QLineEdit()
        note_form.addRow("备注（可选）", self.note_edit)
        root.addLayout(note_form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("确定")
        ok.setDefault(True)
        ok.clicked.connect(self._on_ok)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

    @staticmethod
    def _months_spin(default: int = MONTHS_PER_YEAR) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, MONTHS_PER_YEAR)
        spin.setValue(default)
        spin.setSuffix(" 个月")
        return spin

    def _page_children(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.children_spin = QSpinBox()
        self.children_spin.setRange(1, 99)
        self.children_spin.setValue(1)
        self.children_spin.setSuffix(" 个子女")
        form.addRow("子女数", self.children_spin)
        self.share_combo = QComboBox()
        self.share_combo.addItem("100%（一方全额扣除）", Decimal(1))
        self.share_combo.addItem("50%（双方各半分摊）", HALF)
        form.addRow("分摊比例", self.share_combo)
        self.children_months_spin = self._months_spin()
        form.addRow("申报月数", self.children_months_spin)
        return page

    def _page_education(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("学历（学位）继续教育", "academic")
        self.kind_combo.addItem("职业资格继续教育（证书当年定额）", "vocational")
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("类型", self.kind_combo)
        self.edu_months_spin = self._months_spin()
        form.addRow("申报月数（学历）", self.edu_months_spin)
        return page

    def _page_illness(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.self_paid_edit = QLineEdit()
        self.self_paid_edit.setPlaceholderText("医保目录范围内自付累计（仅年度汇算扣除）")
        form.addRow("自付累计", self.self_paid_edit)
        return page

    def _page_loan(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.loan_months_spin = self._months_spin()
        form.addRow("申报月数", self.loan_months_spin)
        return page

    def _page_rent(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.tier_combo = QComboBox()
        for desc in self._tiers:
            self.tier_combo.addItem(desc)
        if not self._tiers:
            self.tier_combo.addItem("（规则包未提供城市档）")
        form.addRow("主要工作城市档", self.tier_combo)
        self.rent_months_spin = self._months_spin()
        form.addRow("申报月数", self.rent_months_spin)
        return page

    def _page_elderly(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.only_child_check = QCheckBox("独生子女（定额扣除）")
        self.only_child_check.toggled.connect(self._on_only_child)
        form.addRow("身份", self.only_child_check)
        self.self_share_edit = QLineEdit()
        self.self_share_edit.setPlaceholderText("非独生：本人月分摊额")
        form.addRow("本人月分摊额", self.self_share_edit)
        self.other_share_edit = QLineEdit()
        self.other_share_edit.setPlaceholderText("非独生：其他共赡养人月分摊额，逗号分隔（可空）")
        form.addRow("其他共赡养人分摊", self.other_share_edit)
        self.elderly_months_spin = self._months_spin()
        form.addRow("申报月数", self.elderly_months_spin)
        return page

    # ------------------------------------------------------------------
    # 联动
    # ------------------------------------------------------------------

    def _on_item_changed(self, index: int) -> None:
        item = self.item_combo.itemData(index)
        self.stack.setCurrentIndex(_ITEM_PAGE.get(item, _PAGE_CHILDREN))

    def _on_kind_changed(self, index: int) -> None:
        academic = self.kind_combo.itemData(index) == "academic"
        self.edu_months_spin.setEnabled(academic)

    def _on_only_child(self, checked: bool) -> None:
        self.self_share_edit.setEnabled(not checked)
        self.other_share_edit.setEnabled(not checked)

    # ------------------------------------------------------------------
    # 取值 / 回填
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_amount(text: str, where: str) -> Optional[Decimal]:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            raise ValueError(f"{where}：不是合法金额 {text!r}")

    def build_claim(self) -> Claim:
        """收集当前表单 → Claim（解析失败抛 ValueError，政策校验在引擎）。"""
        item = self.item_combo.currentData()
        note = self.note_edit.text().strip()
        kwargs = {"item": item, "note": note}

        if item in ("child_education", "infant_care"):
            kwargs.update(
                children=Decimal(self.children_spin.value()),
                share_ratio=self.share_combo.currentData(),
                months=self.children_months_spin.value(),
            )
        elif item == "continue_education":
            kind = self.kind_combo.currentData()
            kwargs.update(kind=kind)
            if kind == "academic":
                kwargs.update(months=self.edu_months_spin.value())
        elif item == "serious_illness":
            amount = self._parse_amount(self.self_paid_edit.text(), "自付累计")
            kwargs.update(self_paid_total=amount if amount is not None else Decimal(0))
        elif item == "housing_loan":
            kwargs.update(months=self.loan_months_spin.value())
        elif item == "housing_rent":
            kwargs.update(tier=self.tier_combo.currentIndex(), months=self.rent_months_spin.value())
        elif item == "support_elderly":
            kwargs.update(only_child=self.only_child_check.isChecked())
            if not self.only_child_check.isChecked():
                amount = self._parse_amount(self.self_share_edit.text(), "本人月分摊额")
                kwargs.update(monthly_amount=amount if amount is not None else Decimal(0))
                others_text = self.other_share_edit.text().replace("，", ",")
                others = []
                for i, part in enumerate(others_text.split(",")):
                    value = self._parse_amount(part, f"其他共赡养人分摊[{i + 1}]")
                    if value is not None:
                        others.append(value)
                kwargs.update(other_shared_amounts=tuple(others))
            kwargs.update(months=self.elderly_months_spin.value())
        return Claim(**kwargs)

    def _load_claim(self, claim: Claim) -> None:
        index = self.item_combo.findData(claim.item)
        if index >= 0:
            self.item_combo.setCurrentIndex(index)
        if claim.item in ("child_education", "infant_care"):
            self.children_spin.setValue(int(claim.children.to_integral_value()))
            ratio_index = self.share_combo.findData(claim.share_ratio)
            if ratio_index >= 0:
                self.share_combo.setCurrentIndex(ratio_index)
            self.children_months_spin.setValue(claim.months)
        elif claim.item == "continue_education":
            kind_index = self.kind_combo.findData(claim.kind)
            if kind_index >= 0:
                self.kind_combo.setCurrentIndex(kind_index)
            if claim.kind == "academic":
                self.edu_months_spin.setValue(claim.months)
        elif claim.item == "serious_illness":
            if claim.self_paid_total:
                self.self_paid_edit.setText(f"{claim.self_paid_total:f}")
        elif claim.item == "housing_loan":
            self.loan_months_spin.setValue(claim.months)
        elif claim.item == "housing_rent":
            if 0 <= claim.tier < self.tier_combo.count():
                self.tier_combo.setCurrentIndex(claim.tier)
            self.rent_months_spin.setValue(claim.months)
        elif claim.item == "support_elderly":
            self.only_child_check.setChecked(bool(claim.only_child))
            if claim.only_child is False:
                if claim.monthly_amount:
                    self.self_share_edit.setText(f"{claim.monthly_amount:f}")
                parts = ",".join(f"{money(a):.2f}" for a in claim.other_shared_amounts)
                self.other_share_edit.setText(parts)
            self.elderly_months_spin.setValue(claim.months)
        if claim.note:
            self.note_edit.setText(claim.note)

    def _on_ok(self) -> None:
        try:
            self.build_claim()
        except ValueError as exc:
            QMessageBox.warning(self, "输入有误", str(exc))
            return
        self.accept()
