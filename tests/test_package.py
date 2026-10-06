"""包级冒烟测试。"""


def test_version():
    import incometax

    assert incometax.__version__ == "0.1.0"


def test_cli_main_importable():
    from incometax.cli import main

    assert callable(main)


def test_rules_loader_importable():
    from incometax.rules import load_ruleset, status_report  # noqa: F401
