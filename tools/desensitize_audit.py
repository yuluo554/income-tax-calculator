"""脱敏审计（M6 发布门；四步 + 构建产物本体扫描，入仓可复跑）。

四步内容级审计（对应发布纪律）：
  1. 敏感文件名：跟踪文件里不得出现 .env/.key/secret/token 类产物；
  2. 内容级扫描：全部跟踪文本文件中的邮箱/手机号/身份证/密钥/个人目录路径/个人标记；
  3. 二进制/构建产物单独扫：dist 树按字节读法跑强标记（个人标记 + 用户目录路径）；
  4. 提交元数据盲区：作者/提交者邮箱单独扫（内容级扫描不覆盖 git 元数据）。

设计纪律（防扫描器自命中，模式一律片段拼接构造，源码中不出现完整敏感字面值）：
  - 输出一律「文件:行号 [类别] x次数」，**不回显敏感串原文** → 报告可随仓留档；
  - selftest 用程序化合成夹具做阳性对照（无字面假密钥/假手机号入库）；
  - 扫描器源码自身也在 tracked 扫描范围内（自己过自己的扫描）。

用法：
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py                 # tracked（缺省）
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --mode history
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --mode messages
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --mode dist
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --mode all
    PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --selftest

退出码：0 = 无硬门命中（打印 DESSENSITIZE_AUDIT_OK）；1 = 硬门命中或审计失败。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- 模式构造
# 片段拼接：源码里不出现完整敏感字面值，扫描器自身可过 tracked 扫描。
_AT = chr(64)          # @
_DOT = chr(46)         # .
_BS = chr(92)          # 反斜杠
_BRE = chr(92)         # 正则转义符（与 _BS 同值，语义分开命名）

# 邮箱：通用形态；GitHub noreply 属发布固有公开元数据，豁免。
EMAIL_RE = re.compile(
    "[A-Za-z0-9._%+-]+" + _AT + "[A-Za-z0-9.-]+" + _BRE + _DOT + "[A-Za-z]{2,}"
)
NOREPLY_SUFFIX = _AT + "users" + _DOT + "noreply" + _DOT + "github" + _DOT + "com"

# 个人目录路径：Windows 盘符用户目录 / 类 Unix 用户目录
USER_DIR_RE = re.compile(
    "[A-Za-z]:" + _BRE + _BRE + "Users" + _BRE + _BRE + "[^" + _BRE + "s\"']+"
    + "|/" + "Users" + "/[^/\\s\"']+"
)

# 个人标记 = **组合路径签名**（片段拼接防自命中）。裸用户名短标记会误报
# （实测：Qt 二进制含厂商串 "AS"+"USTek COMPUTER INC"，裸词面命中），
# 真实泄露形式是组合路径段，故按组合形式匹配。
_SLASH = chr(47)
_MARKER_SEG = "AS" + "US"
_WORKROOT_SEG = "zcode"
PERSONAL_MARKERS = (
    "Users" + _BS + _MARKER_SEG,
    _SLASH + "Users" + _SLASH + _MARKER_SEG,
    "Program" + "Data" + _BS + _WORKROOT_SEG,
)

# 手机号 / 身份证：加数字边界，避开长数字串（追踪 ID、图片名、字体 Panose）误报
PHONE_RE = re.compile("(?<![0-9])1[3-9]" + _BRE + "d{9}(?![0-9])")
ID_CARD_RE = re.compile("(?<![0-9])" + _BRE + "d{17}[0-9Xx](?![0-9])")

# 密钥/令牌形态
SECRET_RES = (
    re.compile("sk-[A-Za-z0-9]{16,}"),
    re.compile("gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile("AKIA[0-9A-Z]{16}"),
    re.compile("-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        "(?i)\\b(api[_-]?key|secret[_-]?key|access[_-]?token)\\b"
        "\\s*[:=]\\s*[\"'][A-Za-z0-9/+_-]{16,}[\"']"
    ),
)

# 跟踪文件名禁区（第 1 步）
SENSITIVE_FILENAME_RE = re.compile("(?i)(\\.env$|\\.key$|secret|token)")
# 构建产物树禁区成分（第 3 步）——仅用于 dist 树：源码/缓存/测试/计划文档不得进产物。
# （跟踪树里 plan/ 与 tests/ 系决策 D 有意入仓，不属禁区，故此处只扫 dist。）
FORBIDDEN_COMPONENT_RE = re.compile(
    "(?i)(^|/)(__pycache__|\\.pytest_cache|plan|tests)(/|$)|" + _BRE + "\\.py[co]?$|\\.egg-info(/|$)"
)

# 其他绝对路径（复核项，非硬门）
ABS_PATH_RE = re.compile("(?<![A-Za-z0-9])[A-Za-z]:" + _BRE + _BRE + "[A-Za-z]")

# 系列表述（复核项；前作均已公开时保留，结论记决策记录）
SERIES_RE = re.compile("系列第")

HARD = "hard"
REVIEW = "review"

CATEGORY_LEVEL = {
    "email": HARD,
    "user-dir-path": HARD,
    "personal-marker": HARD,
    "phone": HARD,
    "id-card": HARD,
    "secret-key": HARD,
    "sensitive-filename": HARD,
    "forbidden-component": HARD,
    "abs-path": REVIEW,
    "series-mention": REVIEW,
}


class Hit:
    __slots__ = ("location", "category", "count")

    def __init__(self, location, category, count=1):
        self.location = location
        self.category = category
        self.count = count

    def __str__(self):
        return "%s [%s] x%d" % (self.location, self.category, self.count)


# ---------------------------------------------------------------- 文本扫描
def scan_text(text):
    """返回 (line_no, category) 列表；计数按行内出现次数累计。"""
    findings = []

    def add_line(category, line_no):
        findings.append((line_no, category))

    for idx, line in enumerate(text.splitlines(), start=1):
        for match in EMAIL_RE.finditer(line):
            if not match.group(0).endswith(NOREPLY_SUFFIX):
                add_line("email", idx)
        if USER_DIR_RE.search(line):
            add_line("user-dir-path", idx)
        for marker in PERSONAL_MARKERS:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(marker) + r"(?![A-Za-z0-9_])", line):
                add_line("personal-marker", idx)
        if PHONE_RE.search(line):
            add_line("phone", idx)
        if ID_CARD_RE.search(line):
            add_line("id-card", idx)
        for pattern in SECRET_RES:
            if pattern.search(line):
                add_line("secret-key", idx)
        if ABS_PATH_RE.search(line):
            add_line("abs-path", idx)
        if SERIES_RE.search(line):
            add_line("series-mention", idx)
    return findings


def _collapse(raw_findings, location_prefix=""):
    """按 (location, category) 归并计数；location 为「路径:行号」文本。"""
    bucket = {}
    for location, category in raw_findings:
        key = ("%s%s" % (location_prefix, location), category)
        bucket[key] = bucket.get(key, 0) + 1
    return [Hit(loc, cat, count) for (loc, cat), count in sorted(bucket.items())]


# ---------------------------------------------------------------- git 辅助
def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _tracked_files():
    out = _git("ls-files", "-z").stdout
    return [name for name in out.split("\0") if name]


def _is_binary(path):
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(8192)
    except OSError:
        return False
    return b"\0" in chunk


# ---------------------------------------------------------------- 各模式
def run_tracked():
    hits = []
    files = _tracked_files()
    if not files:
        raise AuditError("git ls-files 为空（应在仓库根运行）")
    for name in files:
        if SENSITIVE_FILENAME_RE.search(name):
            hits.append(Hit(name, "sensitive-filename"))
        path = REPO_ROOT / name
        if not path.is_file() or _is_binary(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits.extend(_collapse(scan_text(text), location_prefix="%s:" % name))
    return hits


def run_history():
    revs = _git("rev-list", "--all").stdout.split()
    if not revs:
        raise AuditError("git rev-list --all 为空（浅克隆？CI 需 fetch-depth:0）")
    # 模式 → 类别；`git grep` 只接受**单个** revision，多开会当作 pathspec 静默失配
    # （实测教训：`git grep pat r1 r2 ...` 返回 0 行，"全历史干净"是假的），故逐提交迭代。
    patterns = [
        ("email", EMAIL_RE.pattern),
        ("user-dir-path", USER_DIR_RE.pattern),
        ("phone", PHONE_RE.pattern),
        ("id-card", ID_CARD_RE.pattern),
    ]
    for idx, pattern in enumerate(SECRET_RES):
        patterns.append(("secret-key", pattern.pattern))
    for marker in PERSONAL_MARKERS:
        patterns.append(("personal-marker", re.escape(marker)))
    locations = {}
    for rev in revs:
        for category, pattern in patterns:
            result = _git("grep", "-I", "-n", "-E", "-e", pattern, rev)
            for line in result.stdout.splitlines():
                if category == "email" and NOREPLY_SUFFIX in line:
                    continue
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                _, path, _ = parts
                locations.setdefault((path, category), set()).add(rev[:7])
    # 机制自检（防"静默空扫=假绿"）：每个提交必有 pyproject.toml 含包名，用它探活；
    # 探不到即说明检索通道失效（如把多个 revision 当 pathspec），显式失败而非报"干净"。
    probe = _git("grep", "-I", "-l", "-E", "-e", "incometax", revs[0])
    if not probe.stdout.strip():
        raise AuditError(
            "历史扫描通道自检失败：无法在历史中检索到已知串（检索机制失效，勿信空结果）"
        )
    return [Hit(path, category, len(revs_)) for (path, category), revs_ in sorted(locations.items())]


def run_messages():
    log = _git("log", "--all", "--format=%H|%an <%ae>|%cn <%ce>|%s%n%b").stdout
    hits = _collapse(scan_text(log), location_prefix="git-log:")
    return hits


def run_dist():
    dist_root = REPO_ROOT / "dist"
    if not dist_root.is_dir():
        return []  # 尚未打包 → 无产物可扫（非失败）
    # 仅跑强标记（个人目录名/本地工作根）；反斜杠后接 "Users" 的裸词面在 Qt 二进制里
    # 系通用串、非本机个人路径，故不入表：真实泄露形式必含下方 markers 段（组合签名）。
    markers = PERSONAL_MARKERS
    hits = []
    for path in sorted(dist_root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if FORBIDDEN_COMPONENT_RE.search(rel):
            hits.append(Hit(rel, "forbidden-component"))
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        text = blob.decode("latin-1")
        counts = {}
        for marker in markers:
            found = text.count(marker)
            if found:
                counts["personal-marker"] = counts.get("personal-marker", 0) + found
        for category, count in counts.items():
            hits.append(Hit(rel, category, count))
    return hits


MODES = {
    "tracked": run_tracked,
    "history": run_history,
    "messages": run_messages,
    "dist": run_dist,
}


class AuditError(Exception):
    pass


def run_modes(mode):
    names = list(MODES) if mode == "all" else [mode]
    all_hits = []
    for name in names:
        for hit in MODES[name]():
            all_hits.append((name, hit))
    return all_hits


def report(hits, stream):
    if not hits:
        return
    for mode, hit in hits:
        stream.write("[%s] %s\n" % (mode, hit))


def hard_hits(hits):
    return [(mode, hit) for mode, hit in hits if CATEGORY_LEVEL.get(hit.category) == HARD]


# ---------------------------------------------------------------- selftest
def _synth_samples():
    """程序化合成阳性夹具（不落任何真实敏感值）。"""
    digits = "1" + "3" + "8" + ("0" * 8)           # 11 位合成号
    ident = ("1" * 6) + "19900101" + "1234"        # 18 位合成身份证（6 位地区码 + 8 位生日 + 4 位）
    return {
        "email": "user" + _AT + "example" + _DOT + "com",
        "user-dir-path": "C:" + _BS + "Users" + _BS + "someone" + _BS + "work",
        "personal-marker": "root C:" + _BS + "Users" + _BS + _MARKER_SEG + _BS + "proj",
        "phone": "tel " + digits,
        "id-card": "id " + ident,
        "secret-key": "key = " + "sk-" + ("A" * 24),
    }


def selftest(stream):
    samples = _synth_samples()
    failures = []
    for expected, sample in samples.items():
        found = [cat for _, cat in scan_text(sample)]
        if expected not in found:
            failures.append("夹具未命中：期望 %s，实际 %s" % (expected, found))
    # 阴性对照：GitHub noreply 不得判命中
    noreply = "282769740+yuluo554" + NOREPLY_SUFFIX
    if any(cat == "email" for _, cat in scan_text(noreply)):
        failures.append("阴性对照失败：GitHub noreply 被误判为敏感邮箱")
    if failures:
        for item in failures:
            stream.write("[selftest][FAIL] %s\n" % item)
        return 1
    stream.write("[selftest][OK] 阳性对照 %d 类全部命中，阴性对照通过\n" % len(samples))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="脱敏审计（M6 发布门，四步 + 产物扫描）")
    parser.add_argument("--mode", choices=["tracked", "history", "messages", "dist", "all"],
                        default="tracked")
    parser.add_argument("--selftest", action="store_true", help="阳性对照自检（不读仓库）")
    parser.add_argument("--report", help="命中明细写入文件（便于随仓留档）")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(sys.stdout)

    if args.mode == "all" and not (REPO_ROOT / ".git").exists():
        print("[FAIL] 不在 git 仓库内，无法执行 history/messages 扫描", file=sys.stderr)
        return 1

    try:
        hits = run_modes(args.mode)
    except AuditError as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        return 1

    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            report(hits, handle)

    report(hits, sys.stdout)
    fatal = hard_hits(hits)
    review = [item for item in hits if item not in fatal]
    print("---- 脱敏审计（mode=%s）----" % args.mode)
    print("硬门命中：%d 项；复核项：%d 项" % (len(fatal), len(review)))
    if fatal:
        print("[FAIL] 存在硬门命中（上方 [hard] 类）", file=sys.stderr)
        return 1
    print("DESSENSITIZE_AUDIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
