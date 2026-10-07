"""包级冒烟测试。"""

import re
from pathlib import Path


def test_version_matches_pyproject():
    import incometax

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
    assert match, "pyproject.toml 缺少 version 字段"
    assert incometax.__version__ == match.group(1)


def test_cli_main_importable():
    from incometax.cli import main

    assert callable(main)


def test_rules_loader_importable():
    from incometax.rules import load_ruleset, status_report  # noqa: F401
