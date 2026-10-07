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


def test_calc_blocked_by_gate_is_runtime_failure(tmp_path, capsys):
    """合成待核对规则包 → 门控拦截 → 退出码 1 并列出待核对清单。"""
    from test_rules_loader import flip_one_node_pending, load_ruleset, write_ruleset

    raw = flip_one_node_pending(load_ruleset(2026).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rc = main(["--data-dir", data_dir, "calc", "--year", "2099"])
    assert rc == 1
    assert "待核对" in capsys.readouterr().err


def test_calc_without_input_is_usage_error(capsys):
    """M2 calc 已实装：缺 --input → 用法错误 2（门控在前：未过门控仍为 1，见上）。"""
    assert main(["calc", "--year", "2026"]) == 2
    assert "--input" in capsys.readouterr().err


def _write_input(tmp_path, payload) -> str:
    import json

    path = tmp_path / "calc_input.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_calc_truth_withholding_case_success(tmp_path, capsys):
    """真值 withholding-3months-2019 CLI 通路：退出码 0，逐月 90.00 + 汇算 + 依据。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "10000.00", "special_deduction": "2000.00"},
            "month_count": 3,
        },
    )
    assert main(["calc", "--year", "2019", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "累计预扣" in out
    assert "90.00" in out and "270.00" in out
    assert "年度汇算" in out
    assert "S61" in out  # 减除费用与预扣率表依据
    assert "免责声明" in out


def test_calc_with_social_and_bonus(tmp_path, capsys):
    """社保联动并入专项扣除 + 年终奖单独计税块，退出码 0。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "10000.00"},
            "month_count": 12,
            "social": {
                "base_input": "10000.00",
                "base_lower": "4000.00",
                "base_upper": "25000.00",
                "rates": {"养老": "0.08", "医疗": "0.02", "公积金": "0.12"},
            },
            "bonus_income": "36000.00",
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "社保公积金个人部分" in out
    assert "2200.00" in out  # (800+200+1200)/月 计入专项扣除
    assert "1080.00" in out  # 年终奖 36000×3%
    assert "34920.00" in out  # 税后
    assert "单独计税" in out


def test_calc_settlement_explicit_override(tmp_path, capsys):
    """settlement 覆盖字段：显式全年口径覆盖月度聚合（真值 settlement-2024）。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "0.00"},
            "month_count": 1,
            "settlement": {
                "annual_gross": "200000.00",
                "annual_special_deduction": "40000.00",
                "annual_special_additional_deduction": "60000.00",
                "withheld_total": "0.00",
            },
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "40000.00" in out  # 应纳税所得额
    assert "1480.00" in out  # 年应纳税额
    assert "应补税额" in out  # 0 − 1480 = 应补 1480


def test_calc_malformed_json_is_usage_error(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["calc", "--year", "2026", "--input", str(path)]) == 2
    assert "JSON" in capsys.readouterr().err


def test_calc_unknown_field_is_usage_error(tmp_path, capsys):
    path = _write_input(tmp_path, {"months": [{"gros": "10000.00"}]})
    assert main(["calc", "--year", "2026", "--input", path]) == 2
    assert "不认识的字段" in capsys.readouterr().err


def test_calc_missing_input_file_is_usage_error(tmp_path, capsys):
    assert main(["calc", "--year", "2026", "--input", str(tmp_path / "nope.json")]) == 2
    assert "不存在" in capsys.readouterr().err


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
