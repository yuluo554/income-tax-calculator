"""CLI 测试：退出码语义定稿（0=成功 / 1=运行期失败 / 2=用法输入错误），不得漂移。"""

import pytest

from incometax import __version__
from incometax.cli import main


def test_rules_reports_status(capsys):
    assert main(["rules", "--year", "2026"]) == 0
    out = capsys.readouterr().out
    assert "2026" in out
    assert "已核对" in out and "待核对" in out
    assert "免责声明" in out


def test_rules_unknown_year_is_usage_error(capsys):
    assert main(["rules", "--year", "1999"]) == 2
    assert "没有规则包" in capsys.readouterr().err


def test_calc_blocked_by_gate_is_runtime_failure(capsys):
    """2026 规则包含待核对条目 → 门控拦截 → 退出码 1 并列出待核对清单。"""
    assert main(["calc", "--year", "2026"]) == 1
    assert "待核对" in capsys.readouterr().err


def test_calc_stub_after_gate_passes(tmp_path, capsys):
    """全核对规则包过门控后命中未实装桩 → 同为运行期失败 1。"""
    from test_rules_loader import all_verified, load_ruleset, write_ruleset

    raw = all_verified(load_ruleset(2026).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rc = main(["--data-dir", data_dir, "calc", "--year", "2099"])
    assert rc == 1
    assert "尚未实装" in capsys.readouterr().err


def test_bad_data_dir_is_usage_error(tmp_path, capsys):
    rc = main(["--data-dir", str(tmp_path / "nope"), "rules", "--year", "2026"])
    assert rc == 2


def test_no_command_exits_2():
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2


def test_missing_year_arg_exits_2():
    with pytest.raises(SystemExit) as excinfo:
        main(["rules"])
    assert excinfo.value.code == 2


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out
