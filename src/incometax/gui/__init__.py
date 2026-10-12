"""GUI 前端（M5）：PySide6 桌面界面。

分层纪律（plan/03）：GUI 是引擎之上的薄壳——只消费引擎 API 与 benchmark.run_all()，
不实现任何政策计算逻辑；政策数值全部来自规则包（本包源码零政策数值字面量，
由 tests/test_zero_policy_literals.py 收编扫描）。
"""
