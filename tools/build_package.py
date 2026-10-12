"""M5 打包驱动与构建后断言（PyInstaller onedir）。

用法：
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/build_package.py [--clean-build]

流程：
1. 用 tools/incometax.spec 打包 dist/个人所得税联动计算器/（onedir）；
2. **构建后断言**（任一不过 → 非零退出，构建视为失败）：
   a. dist 目录无禁区成分（__pycache__/*.py 源文件/测试目录/plan 文档/仓库私密文件）；
   b. 内嵌 data/rules 与 data/truth 与仓库当前内容逐文件 sha256 对账（打包冻结口径）；
   c. exe 存在，且 _internal/ 内含 PySide6 运行期模块；
   d. 冻结态数据目录定位可解析（在中立 CWD 调用 exe 的 --help 等价物：直接运行
      benchmark 子命令由 tools/verify_package.py 负责，此处只校验结构）。
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_NAME = "个人所得税联动计算器"
DIST_DIR = REPO_ROOT / "dist" / DIST_NAME
SPEC_PATH = REPO_ROOT / "tools" / "incometax.spec"


def _content_root() -> Path:
    """运行期文件所在目录。

    PyInstaller 5.x onedir = dist/<name>/ 平铺；6.x onedir = dist/<name>/_internal/。
    内嵌 data/ 与 PySide6 都随运行期文件同层，故按存在性自动选择。
    """
    internal = DIST_DIR / "_internal"
    return internal if internal.is_dir() else DIST_DIR


# dist 禁区：源码/缓存/测试/计划文档等不得进入发布产物
FORBIDDEN_DIR_NAMES = {"__pycache__", "tests", "plan", ".git", ".pytest_cache"}
FORBIDDEN_SUFFIXES = (".py", ".pyc", ".pyo", ".spec")


class BuildError(Exception):
    """构建后断言未通过（构建视为失败）。"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_pyinstaller() -> None:
    env = dict(os.environ)
    env["INCOMETAX_SPEC_ROOT"] = str(REPO_ROOT)
    env["INCOMETAX_SPEC_NAME"] = DIST_NAME
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(REPO_ROOT / "dist"),
           "--workpath", str(REPO_ROOT / "build"), str(SPEC_PATH)]
    print("运行：", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        raise BuildError(f"PyInstaller 退出码 {result.returncode}")


def assert_no_forbidden_files() -> None:
    offenders = []
    for path in DIST_DIR.rglob("*"):
        if path.is_dir():
            if path.name in FORBIDDEN_DIR_NAMES:
                offenders.append(f"目录 {path.relative_to(DIST_DIR)}")
            continue
        if path.name in FORBIDDEN_DIR_NAMES:
            offenders.append(str(path.relative_to(DIST_DIR)))
        elif path.suffix in FORBIDDEN_SUFFIXES:
            offenders.append(str(path.relative_to(DIST_DIR)))
    if offenders:
        raise BuildError("dist 含禁区成分：\n  - " + "\n  - ".join(sorted(offenders)[:20]))
    print("[OK] dist 无禁区成分（无源码/缓存/测试/计划文档）")


def assert_embedded_data_matches_repo() -> None:
    embedded_data = _content_root() / "data"
    for sub in ("rules", "truth"):
        src_dir = REPO_ROOT / "data" / sub
        dst_dir = embedded_data / sub
        if not dst_dir.is_dir():
            raise BuildError(f"dist 未内嵌 data/{sub}")
        src_files = {p.name: p for p in src_dir.iterdir() if p.is_file()}
        dst_files = {p.name: p for p in dst_dir.iterdir() if p.is_file()}
        if set(src_files) != set(dst_files):
            raise BuildError(
                f"data/{sub} 文件集不一致：仓库 {sorted(src_files)} vs 内嵌 {sorted(dst_files)}"
            )
        for name, src in src_files.items():
            if _sha256(src) != _sha256(dst_files[name]):
                raise BuildError(f"data/{sub}/{name} 与仓库内容不一致（sha256 不同）")
    print("[OK] 内嵌 data/rules 与 data/truth 和仓库逐文件 sha256 对账一致")


def assert_exe_and_runtime_present() -> None:
    exe_path = DIST_DIR / f"{DIST_NAME}.exe"
    if not exe_path.is_file():
        raise BuildError(f"未找到可执行文件：{exe_path}")
    content_root = _content_root()
    if not (content_root / "PySide6").is_dir():
        raise BuildError(f"运行期文件层内缺少 PySide6 模块（{content_root}）")
    # 核心层零第三方依赖：不应出现被 excludes 排除的重依赖
    for banned in ("numpy", "pandas", "matplotlib", "scipy"):
        if (content_root / banned).exists():
            raise BuildError(f"dist 意外带入被排除的重依赖：{banned}")
    print(f"[OK] exe 与 PySide6 运行期模块就位（{exe_path.name}，布局 = {content_root.name}）")


def build(clean: bool = False) -> None:
    if clean and (REPO_ROOT / "build").exists():
        shutil.rmtree(REPO_ROOT / "build")
    if clean and DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    run_pyinstaller()
    if not DIST_DIR.is_dir():
        raise BuildError(f"PyInstaller 未产出 dist 目录：{DIST_DIR}")
    assert_exe_and_runtime_present()
    assert_no_forbidden_files()
    assert_embedded_data_matches_repo()
    print("\n构建完成，全部断言通过：", DIST_DIR)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M5 PyInstaller 打包与构建后断言")
    parser.add_argument("--clean-build", action="store_true", help="打包前清理 build/ 与旧 dist")
    args = parser.parse_args(argv)
    try:
        build(clean=args.clean_build)
    except BuildError as exc:
        print(f"[FAIL] 构建断言未通过：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
