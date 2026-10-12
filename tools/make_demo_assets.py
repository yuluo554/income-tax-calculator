"""M5 演示素材生成（截图 PNG + 演示 GIF）。

在 offscreen 平台渲染 GUI 各功能页为 PNG，并用 Pillow（**可选开发工具，非项目依赖**）
把若干帧合成为演示 GIF。产物落 docs/demo/。

用法：
    PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen py -X utf8 tools/make_demo_assets.py

纪律：本脚本仅驱动 GUI（填输入 → 点计算 → 抓图），不实现任何计算；
所有数值来自用户输入与规则包，源码零政策数值字面量。
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "demo"

# 演示用输入（业务示例数据，非政策数值）
DEMO_YEAR = 2024
DEMO_GROSS = "20000"
DEMO_SPECIAL = "3000"
DEMO_BONUS = "36001"  # 落在"多发一元、到手变少"临界区间，用于展示标红警示


def _grab(widget, path: Path) -> None:
    widget.grab().save(str(path))
    print("已保存", path.relative_to(REPO_ROOT))


def _install_cjk_font(app) -> None:
    """offscreen 平台不带字体，需显式注册系统中文字体（否则渲染为方框）。

    仅影响演示素材生成；缺失时静默跳过（正常桌面启动用系统字体）。
    """
    from PySide6.QtGui import QFont, QFontDatabase

    candidates = (
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "simhei.ttf",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "Deng.ttf",
    )
    for font_path in candidates:
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    app.setFont(QFont(families[0], 10))
                    print("已注册演示字体：", families[0])
                    return
    print("[提示] 未找到系统中文字体，截图文字可能为方框")


def _fill_months(w, gross, special):
    for row in range(w.input_panel.months_table.rowCount()):
        w.input_panel.months_table.item(row, 1).setText(gross)
        w.input_panel.months_table.item(row, 3).setText(special)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from incometax.gui.main_window import MainWindow

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    _install_cjk_font(app)

    frames = []
    w = MainWindow()
    w.resize(1180, 780)
    w.show()

    # 帧 1：免责声明首屏（DoD：免责声明首屏）
    app.processEvents()
    _grab(w, OUT_DIR / "01-免责声明首屏.png")
    frames.append(OUT_DIR / "01-免责声明首屏.png")

    # 进入主界面
    w._enter_main()
    idx = w.year_combo.findData(DEMO_YEAR)
    if idx >= 0:
        w.year_combo.setCurrentIndex(idx)
    app.processEvents()

    # 帧 2：计算输入（逐月表 + 年终奖）
    _fill_months(w, DEMO_GROSS, DEMO_SPECIAL)
    w.input_panel.bonus_edit.setText(DEMO_BONUS)
    from incometax.engine.deductions import Claim

    w.input_panel.add_claim_direct(
        Claim(item="child_education", children=Decimal(1), share_ratio=Decimal(1), months=12)
    )
    w.tabs.setCurrentWidget(w.input_panel)
    app.processEvents()
    _grab(w, OUT_DIR / "02-计算输入.png")
    frames.append(OUT_DIR / "02-计算输入.png")

    # 帧 3：计算结果（逐月表 + 择优 + 临界标红）
    w._on_compute()
    app.processEvents()
    _grab(w, OUT_DIR / "03-计算结果与临界标红.png")
    frames.append(OUT_DIR / "03-计算结果与临界标红.png")

    # 帧 4：依据面板（ref → 文号+条款）
    w.tabs.setCurrentWidget(w.ref_panel)
    app.processEvents()
    _grab(w, OUT_DIR / "04-依据面板.png")
    frames.append(OUT_DIR / "04-依据面板.png")

    # 帧 5：内置基准（GUI 复用 run_all 同一 API）
    w.tabs.setCurrentWidget(w.benchmark_panel)
    app.processEvents()
    w.benchmark_panel.run_benchmark()
    app.processEvents()
    _grab(w, OUT_DIR / "05-内置基准.png")
    frames.append(OUT_DIR / "05-内置基准.png")

    w.close()

    # 合成演示 GIF（可选依赖 Pillow；缺失时仅保留 PNG 截图）
    try:
        from PIL import Image

        images = [Image.open(p).convert("RGB") for p in frames]
        target_w = 1180
        scaled = []
        for im in images:
            ratio = target_w / im.width
            scaled.append(im.resize((target_w, int(im.height * ratio)), Image.LANCZOS))
        gif_path = OUT_DIR / "演示.gif"
        # 各帧时长（毫秒）：首屏与基准页停留久一些
        durations = [2600, 2200, 3400, 3000, 3000]
        scaled[0].save(
            str(gif_path),
            save_all=True,
            append_images=scaled[1:],
            duration=durations[: len(scaled)],
            loop=0,
        )
        print("已保存", gif_path.relative_to(REPO_ROOT))
    except ImportError:
        print("[提示] 未安装 Pillow，仅保留 PNG 截图（GIF 合成跳过）")

    print("演示素材目录：", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
