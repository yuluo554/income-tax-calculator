# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 打包配置（M5）。

产物：dist/个人所得税联动计算器/（onedir，含 exe + _internal/）
- 数据内嵌：data/rules 与 data/truth 打到 sys._MEIPASS/data（loader.find_data_dir
  的第三级定位优先级，见 plan/06 口径 12）；打包后规则包只读内嵌，不再动。
- 打包白名单：核心层零第三方依赖，额外仅需 PySide6 的 Qt 运行期模块；
  不引入 numpy/pandas 等（仓库无此依赖，PyInstaller 也不会自动带上）。

本 spec 由 tools/build_package.py 以变量注入方式驱动（EXE_NAME/ENTRY/RESOURCES），
也可直接 `pyinstaller tools/incometax.spec` 用其内置默认值执行。
"""

import os

_REPO_ROOT = os.environ.get("INCOMETAX_SPEC_ROOT", os.getcwd())
# 入口一律用绝对路径：spec 内相对路径按 spec 所在目录（tools/）解析
ENTRY = os.environ.get(
    "INCOMETAX_SPEC_ENTRY", os.path.join(_REPO_ROOT, "src", "incometax", "gui", "__main__.py")
)
EXE_NAME = os.environ.get("INCOMETAX_SPEC_NAME", "个人所得税联动计算器")

# 内嵌资源：(源目录, 打包后相对 data/ 的路径)
_RULE_SRC = os.path.join(_REPO_ROOT, "data", "rules")
_TRUTH_SRC = os.path.join(_REPO_ROOT, "data", "truth")
_DATA_README = os.path.join(_REPO_ROOT, "data", "README.md")

datas = [
    (_RULE_SRC, "data/rules"),
    (_TRUTH_SRC, "data/truth"),
]
if os.path.isfile(_DATA_README):
    datas.append((_DATA_README, "data"))

hiddenimports = [
    "incometax.gui",
    "incometax.gui.app",
    "incometax.gui.main_window",
    "incometax.gui.input_panel",
    "incometax.gui.results_panel",
    "incometax.gui.ref_panel",
    "incometax.gui.benchmark_panel",
    "incometax.gui.claim_dialog",
    "incometax.gui.selftest",
]

a = Analysis(
    [ENTRY],
    pathex=[os.path.join(_REPO_ROOT, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 打包白名单最小化：排除科学计算/绘图等无关重依赖（本仓库不依赖，防意外带入）
    excludes=["numpy", "pandas", "matplotlib", "scipy", "PIL", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=EXE_NAME,
)
