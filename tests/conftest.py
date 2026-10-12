"""pytest 全局配置（M5 起：GUI offscreen 常驻）。

QT_QPA_PLATFORM=offscreen 必须在**首次导入 PySide6 之前**设置——pytest 先于全部
测试模块导入 conftest，故在本文件顶部设置即为常驻（任何测试模块 import PySide6
时已处于 offscreen 平台，无显示服务器也能跑 GUI 测试）。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
