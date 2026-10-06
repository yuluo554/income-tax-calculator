"""CLI 通路（骨架阶段）。

退出码语义（定稿，锁进 tests/test_cli.py，不得漂移）：
  0 = 成功
  1 = 运行期失败（功能未实现 / 计算失败 / status 门控拦截）
  2 = 用法与输入错误（参数缺失、年度无规则包、schema 非法、数据目录缺失）

控制台兼容：输出只用 GBK 可编码字符（Windows cp936 控制台），状态标记用 ASCII。
"""

import argparse
import sys

from incometax import __version__
from incometax.rules import loader

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2


class CliUsageError(Exception):
    """输入/用法错误 → 退出码 2。"""


class RuntimeFailure(Exception):
    """运行期失败 → 退出码 1。"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="incometax",
        description="个人所得税联动计算器（全本地计算，结果仅供参考，以税务机关核定为准）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data-dir",
        help="规则包数据目录（含 rules/ 子目录）；默认按自动定位顺序查找",
    )
    sub = parser.add_subparsers(dest="command", metavar="命令")
    sub.required = True

    p_rules = sub.add_parser("rules", help="查看年度规则包与核对状态（不参与计算）")
    p_rules.add_argument("--year", type=int, required=True, help="规则包年度，如 2026")
    p_rules.set_defaults(func=cmd_rules)

    p_calc = sub.add_parser("calc", help="计算（累计预扣/择优/汇算，随里程碑逐步实装）")
    p_calc.add_argument("--year", type=int, required=True, help="适用年度")
    p_calc.set_defaults(func=cmd_calc)

    return parser


def _load_or_usage_error(year: int, data_dir):
    try:
        return loader.load_ruleset(year, data_dir=data_dir)
    except loader.RulesetNotFoundError as exc:
        raise CliUsageError(str(exc))
    except loader.DataDirNotFoundError as exc:
        raise CliUsageError(str(exc))
    except loader.RulesetSchemaError as exc:
        raise CliUsageError(f"规则包 schema 非法（年度 {year}）：{exc}")


def cmd_rules(args) -> int:
    ruleset = _load_or_usage_error(args.year, args.data_dir)
    report = loader.status_report(ruleset)
    print(f"年度规则包 {ruleset.year}（schema v1）")
    print(f"文件：{ruleset.path}")
    for src in ruleset.data["sources"]:
        note = f"（{src['note']}）" if src.get("note") else ""
        print(f"  来源 {src['id']}：{src['doc']} [状态:{src['status']}]{note}")
    print(f"数值条目：已核对 {report.verified} 条 / 待核对 {report.pending} 条")
    if report.pending_paths:
        print("待核对条目（逐条挂原文核对后才可生效）：")
        for path in report.pending_paths[:10]:
            print(f"  - {path}")
        if len(report.pending_paths) > 10:
            print(f"  ...共 {len(report.pending_paths)} 条")
        print("[!!] 门控状态：存在待核对条目，计算引擎拒绝生效")
    else:
        print("[OK] 门控状态：全部已核对，可生效")
    print("免责声明：计算结果供参考，以税务机关核定为准；政策以发文机关正式文本为准。")
    return EXIT_OK


def cmd_calc(args) -> int:
    # 骨架阶段仅校验输入可达性；引擎实装后此处按 plan/04 编排各引擎
    ruleset = _load_or_usage_error(args.year, args.data_dir)
    try:
        loader.effective_ruleset(ruleset)
    except loader.RulesetNotEffective as exc:
        raise RuntimeFailure(str(exc))
    raise RuntimeFailure("计算引擎尚未实装（骨架阶段，计划见 plan/04 与 plan/05 里程碑 M2-M3）")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliUsageError as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return EXIT_USAGE
    except RuntimeFailure as exc:
        print(f"运行期失败：{exc}", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
