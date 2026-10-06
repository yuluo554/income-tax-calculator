"""计算引擎包：纯函数、全 Decimal、无 IO。

统一约定（plan/04 §三）：输入 (Ruleset, 参数)，输出 Report（数值+依据引用）；
引擎入口只接受 effective_ruleset() 放行的规则包。
"""
