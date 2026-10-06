"""FR-2 年终奖计税方式择优引擎 + 临界区间机制推导。

设计定稿：plan/04 §3.2。要点：
- 双方案（单独计税 vs 并入综合）对比自动推荐；
- 临界区间由按月换算税率表机制性推导（公式见 plan/04 §3.2），代码零字面量；
- 政策有效期校验（30 号公告至 2027-12-31）。
M3 实装。
"""

from incometax.rules.loader import Ruleset


def compare_bonus_schemes(ruleset: Ruleset, bonus_amount, salary_annual_result) -> object:
    """双方案对比并推荐。骨架阶段未实现。"""
    raise NotImplementedError(
        "年终奖择优引擎在 M3 实装（设计见 plan/04 §3.2）"
    )


def derive_bonus_trap_intervals(ruleset: Ruleset) -> list:
    """由按月换算税率表推导"多发一元、到手变少"临界区间（区间端点公式见 plan/04 §3.2）。

    返回 [(区间左端, 区间右端, 依据级次), ...]。骨架阶段未实现。
    """
    raise NotImplementedError(
        "临界区间推导在 M3 实装（区间端点由规则表推导生成，不硬编码）"
    )
