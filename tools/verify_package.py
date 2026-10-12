"""M5 打包产物冻结态验收（中立目录实测，DoD 项）。

在**临时中立目录**（非仓库、非 dist）下调用打包后的 exe：
    exe --selftest <输入JSON> <输出文本>
验证三件事（exe 为窗口程序无控制台，结论经文本文件回传）：
1. 冻结态数据目录定位命中内嵌 sys._MEIPASS/data（而非仓库 data/）；
2. calc 全链路编排在冻结态可跑通；
3. 内置基准 run_all() 全部达标。

用法：
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/verify_package.py [--input <json>]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_NAME = "个人所得税联动计算器"
EXE_PATH = REPO_ROOT / "dist" / DIST_NAME / f"{DIST_NAME}.exe"

# 中立目录自检输入（值全部落在这里，exe 侧零政策字面量）
DEFAULT_SELFTEST_INPUT = {
    "year": 2024,
    "months": [{"gross": "12000.00", "special_deduction": "2000.00"}] * 12,
    "bonus_income": "36001.00",
}


class VerifyError(Exception):
    pass


def verify(input_path=None) -> None:
    if not EXE_PATH.is_file():
        raise VerifyError(f"未找到打包产物：{EXE_PATH}（先运行 tools/build_package.py）")

    with tempfile.TemporaryDirectory(prefix="incometax-neutral-") as neutral:
        neutral_dir = Path(neutral)
        # 中立工作目录专用（exe 的 CWD = 此目录，上溯找不到仓库 data/）
        in_json = Path(input_path) if input_path else neutral_dir / "selftest-in.json"
        if input_path is None:
            in_json.write_text(json.dumps(DEFAULT_SELFTEST_INPUT), encoding="utf-8")
        out_txt = neutral_dir / "selftest-out.txt"

        cmd = [str(EXE_PATH), "--selftest", str(in_json), str(out_txt)]
        print("中立目录：", neutral_dir)
        print("运行：", " ".join(f'"{c}"' if " " in c else c for c in cmd))
        result = subprocess.run(cmd, cwd=str(neutral_dir))
        if not out_txt.is_file():
            raise VerifyError(f"exe 未产出结论文件（退出码 {result.returncode}）")
        text = out_txt.read_text(encoding="utf-8")
        print("---- exe 自检结论 ----")
        print(text.rstrip())
        print("----------------------")

        if result.returncode != 0:
            raise VerifyError(f"exe 自检退出码 {result.returncode}（见上方结论）")
        if "自检结论：通过" not in text:
            raise VerifyError("结论文件未标记通过")
        # 冻结态定位必须命中内嵌目录（dist 内），不得回落到仓库 data/
        located = None
        for line in text.splitlines():
            if line.startswith("[OK] 数据目录定位："):
                located = Path(line.split("：", 1)[1].strip())
                break
        if located is None:
            raise VerifyError("结论文件缺少数据目录定位行")
        dist_resolved = (REPO_ROOT / "dist").resolve()
        try:
            located.resolve().relative_to(dist_resolved)
        except ValueError:
            raise VerifyError(
                f"数据目录未命中冻结态内嵌路径：{located}（应位于 {dist_resolved} 之下；"
                "若为仓库 data/ 则说明回落到了仓库而非内嵌数据）"
            )
    print("[OK] 打包产物在中立目录可用：冻结态数据定位（dist 内嵌）+ calc 全链路 + 内置基准全达标")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M5 打包产物冻结态验收（中立目录实测）")
    parser.add_argument("--input", help="自检输入 JSON（缺省用内置样例）")
    args = parser.parse_args(argv)
    try:
        verify(input_path=args.input)
    except VerifyError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
