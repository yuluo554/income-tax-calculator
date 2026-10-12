"""GUI 应用入口：QApplication 装配与命令行参数。

命令行（打包后 GUI exe 同样接受这些参数）：
  --data-dir <路径>                 显式数据目录（覆盖自动定位）
  --selftest <输入JSON> <输出文本>  冻结态自检（打包验收用，不打开窗口）

应用显示名（plan/06 待定决策 #2 定稿）：「个人所得税联动计算器」——
GUI 窗口标题与打包 exe 名共用该常量。
"""

import sys
from typing import Optional

from incometax.gui.main_window import APP_TITLE, MainWindow

__all__ = ["APP_TITLE", "main"]


def _parse_args(argv):
    """返回 (data_dir: Optional[str], selftest: Optional[(输入, 输出)])。

    极简解析：只认 --data-dir <路径> 与 --selftest <输入> <输出>
    （打包后的 GUI exe 通常无参数启动）。
    """
    data_dir = None
    selftest = None
    i = 0
    while i < len(argv):
        if argv[i] == "--data-dir" and i + 1 < len(argv):
            data_dir = argv[i + 1]
            i += 2
        elif argv[i] == "--selftest" and i + 2 < len(argv):
            selftest = (argv[i + 1], argv[i + 2])
            i += 3
        else:
            i += 1
    return data_dir, selftest


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir, selftest = _parse_args(argv)
    if selftest is not None:
        from incometax.gui.selftest import run_selftest

        return run_selftest(selftest[0], selftest[1], data_dir=data_dir)

    from PySide6.QtWidgets import QApplication

    app = QApplication(argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow(data_dir=data_dir)
    window.show()
    return app.exec()
