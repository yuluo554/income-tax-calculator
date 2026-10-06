"""FR-4 社保公积金联动引擎。

设计定稿：plan/04 §3.4。要点：
- 缴费基数自动夹取到 [下限, 上限]（基数上下限与费率全部用户输入，规则包不存全国值）；
- 个人部分合计（Decimal）直接作为 monthly 引擎的专项扣除输入，回链"来自社保联动"标注。
M2 实装。
"""


def compute_social_insurance(base_input, rates, base_lower, base_upper) -> object:
    """计算社保公积金个人部分。骨架阶段未实现。"""
    raise NotImplementedError(
        "社保公积金联动引擎在 M2 实装（设计见 plan/04 §3.4）"
    )
