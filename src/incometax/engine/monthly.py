"""FR-1 累计预扣法逐月引擎。

设计定稿：plan/04 §3.1（61 号公告第六条公式逐字实现 + 逐月状态机）。
M2 实装；届时官方算例真值（data/truth/）回归通过率 100% 为验收线。
"""

from incometax.rules.loader import Ruleset


def compute_monthly_withholding(ruleset: Ruleset, monthly_inputs) -> object:
    """逐月累计预扣计算。

    monthly_inputs: 12 个月的序列（每月工资、当月专项扣除、当月专项附加扣除、
    当月其他扣除；社保联动模块产出自动填充专项扣除字段）。
    返回 Report：逐月应预扣税额、累计应纳税所得额、适用预扣率级次，每项挂依据。

    骨架阶段未实现。
    """
    raise NotImplementedError(
        "累计预扣引擎在 M2 实装（设计见 plan/04 §3.1）；"
        "当前为骨架阶段，规则包可用 incometax rules 命令预览"
    )
