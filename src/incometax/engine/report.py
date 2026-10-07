"""引擎 Report 公共约定（plan/04 §三）：金额精度与依据渲染。

- 引擎纯函数、无 IO：Report 树的每个数值叶子 = value(Decimal) + label + ref 节点 + note；
  ref 存规则包原始 ref 节点（{"source": "S61", "clause": "第六条"}），由前端层渲染成
  "文号+条款" 文本（CLI/GUI 共用，不另起第二套依据语义）。
- 金额呈现/申报口径 = 两位小数 ROUND_HALF_UP。这是申报表精度约定，不是政策数值；
  真值库"商数查表保留两位"口径同源（见 data/truth/cases.json notes）。
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List

MONEY_QUANT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """金额按申报口径保留两位小数（ROUND_HALF_UP）。"""
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def source_doc(source_id: str, sources: List[Dict[str, Any]]) -> str:
    """把 ref 节点里的 source id 解析为 sources[] 里的文号全称；找不到则原样返回 id。"""
    for src in sources:
        if src.get("id") == source_id:
            return str(src.get("doc", source_id))
    return source_id


def render_ref(ref_node: Any, sources: List[Dict[str, Any]]) -> str:
    """ref 节点 → "文号 条款"（依据面板/CLI 直接可读）。"""
    if not isinstance(ref_node, dict):
        return str(ref_node)
    doc = source_doc(str(ref_node.get("source", "")), sources)
    clause = str(ref_node.get("clause", ""))
    return f"{doc} {clause}".strip()


def short_ref(ref_node: Any) -> str:
    """ref 节点 → "S61·第六条"（表格行内紧凑引用；完整文号由来源图例给出）。"""
    if not isinstance(ref_node, dict):
        return str(ref_node)
    source_id = str(ref_node.get("source", ""))
    clause = str(ref_node.get("clause", ""))
    return f"{source_id}·{clause}".strip("·")
