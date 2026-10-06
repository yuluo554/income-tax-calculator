"""FR-5 年度汇算引擎。

设计定稿：plan/04 §3.5。要点：
- 应纳税所得额 = 收入额合计 − 减除费用 − 专项扣除 − 专项附加扣除 − 其他扣除；
- 应纳税额查综合所得税率表；应退/应补 = 已预缴 − 应纳税额（正=应退）；
- 大病医疗等 settlement_only 扣除在本环节纳入。
M2 实装。
"""

from incometax.rules.loader import Ruleset


def compute_annual_settlement(ruleset: Ruleset, inputs) -> object:
    """年度汇算计算。骨架阶段未实现。"""
    raise NotImplementedError(
        "年度汇算引擎在 M2 实装（设计见 plan/04 §3.5）"
    )
