"""FR-3 七项专项附加扣除管理引擎。

设计定稿：plan/04 §3.3。要点：
- 分档标准计算（子女教育/婴幼儿按孩数、租金按城市档）；
- 房贷利息与住房租金互斥校验（规则包 housing_loan_vs_rent 门控）；
- 赡养老人独生定额 vs 非独生分摊上限校验；
- 大病医疗 stage=settlement_only：预扣链剔除、汇算链纳入。
M3 实装。
"""


def evaluate_claims(ruleset, claims) -> object:
    """校验并计算扣除项申报清单。骨架阶段未实现。"""
    raise NotImplementedError(
        "专项附加扣除引擎在 M3 实装（设计见 plan/04 §3.3）"
    )
