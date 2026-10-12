"""脱敏审计守门测试（M6 发布门常驻闸门）。

把发布门审计固化进全量测试：任何提交若把邮箱/密钥/个人路径/个人标记带进
跟踪树、历史或提交信息，本测试当场拦下。审计器见 tools/desensitize_audit.py。

CI 注意：历史扫描依赖完整 git 历史，`actions/checkout` 必须 `fetch-depth: 0`
（下方 test_ci_checkout_fetches_full_history 断言这一点，防"CI 里历史扫描静默空跑"）。
"""

import importlib.util
import io
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_audit():
    spec = importlib.util.spec_from_file_location(
        "desensitize_audit", REPO_ROOT / "tools" / "desensitize_audit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return load_audit()


def test_selftest_positive_and_negative_control(audit):
    """扫描器自身有效：阳性夹具全命中，GitHub noreply 不被误判。"""
    stream = io.StringIO()
    assert audit.selftest(stream) == 0
    assert "selftest][OK]" in stream.getvalue()


def test_tracked_tree_has_no_hard_hits(audit):
    """跟踪树：邮箱/个人路径/个人标记/手机号/身份证/密钥/敏感文件名 零命中。"""
    fatal = audit.hard_hits([("tracked", hit) for hit in audit.run_tracked()])
    assert not fatal, "跟踪树存在硬门命中：%s" % [str(h) for _, h in fatal]


def test_history_has_no_hard_hits(audit):
    """全历史 blob：零硬门命中（需完整历史，见 CI fetch-depth 断言）。"""
    fatal = audit.hard_hits([("history", hit) for hit in audit.run_history()])
    assert not fatal, "git 历史存在硬门命中：%s" % [str(h) for _, h in fatal]


def test_commit_metadata_has_no_personal_email(audit):
    """提交元数据盲区：作者/提交者邮箱不得含个人邮箱（内容级扫描覆盖不到）。"""
    out = subprocess.run(
        ["git", "log", "--all", "--format=%ae|%ce"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    emails = {line for line in out.splitlines() if line.strip()}
    assert emails, "git log 未返回任何提交（浅克隆？）"
    allowed_domain = "users" + chr(46) + "noreply" + chr(46) + "github" + chr(46) + "com"
    offenders = [e for e in emails if allowed_domain not in e]
    assert not offenders, "提交元数据含非 GitHub noreply 邮箱：%s" % offenders


def test_ci_checkout_fetches_full_history():
    """CI 必须取全量历史——否则脱敏历史扫描在 CI 里退化为空跑（假绿）。"""
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    checkout_blocks = re.findall(r"uses:\s*actions/checkout@[^\n]*\n(?:\s+with:\n(?:\s+[^\n]*\n)*)?", workflow)
    assert checkout_blocks, "CI 未见 actions/checkout 步骤"
    for block in checkout_blocks:
        assert re.search(r"fetch-depth:\s*0\b", block), (
            "actions/checkout 未配 fetch-depth: 0（历史脱敏扫描会静默空跑）"
        )


def test_ci_workflow_is_valid_yaml():
    """CI workflow 必须可解析且每个 job 有 runs-on/steps。

    非法 YAML 不会报错，而是 GitHub 端**不建任何 job**（run 0 秒失败、jobs=0、
    workflow 状态却仍显示 active）——只有真解析/真跑才暴露，故在测试期先拦。

    pyyaml 已声明在 dev extra（CI 装 `.[dev,gui]`）；此处**直接导入不用
    importorskip**——缺依赖必须硬失败，否则会静默跳过、退化成"绿但少跑"。
    """
    import yaml

    workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "workflow 顶层不是映射"
    jobs = data.get("jobs")
    assert jobs, "workflow 未定义任何 job"
    for name, job in jobs.items():
        assert job.get("runs-on"), "job %s 缺 runs-on" % name
        assert job.get("steps"), "job %s 缺 steps" % name


def test_history_scan_channel_is_alive(audit):
    """机制探活（防静默空扫=假绿）：历史扫描通道必须真能检索到已知串。"""
    revs = subprocess.run(
        ["git", "rev-list", "--all"], cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout.split()
    assert revs, "git rev-list --all 为空"
    probe = subprocess.run(
        ["git", "grep", "-I", "-l", "-E", "-e", "incometax", revs[0]],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    assert probe.strip(), "历史检索通道失效（git grep 未命中已知串）"
