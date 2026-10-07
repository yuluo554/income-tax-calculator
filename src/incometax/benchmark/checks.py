"""基准检查公共工具：断言收集（失败逐条记入清单，不中断基准）。

纪律：本包与引擎同受零政策数值字面量门禁扫描（宁严勿松）——所有标准值、
边界、年度均取自规则包对象，本文件与后续 runner 不得出现任何政策数值字面量
（含文档字符串与注释）。
"""

from typing import List


def expect(failures: List[str], ok: bool, where: str, detail: str = "") -> bool:
    """单点断言：通过返回 True；失败把位置与原因记入 failures 并返回 False。"""
    if not ok:
        failures.append(f"{where}: {detail}" if detail else where)
    return ok
