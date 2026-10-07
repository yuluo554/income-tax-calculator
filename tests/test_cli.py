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


# ---------------------------------------------------------------------------
# M3：专项附加申报清单 / 择优对比 / 临界区间提示
# ---------------------------------------------------------------------------


def test_calc_with_claims_renders_checklist_and_chains(tmp_path, capsys):
    """申报清单渲染 + 预扣链逐月计入 + 汇算链聚合（子女教育 + 赡养老人独生）。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "15000.00"},
            "month_count": 12,
            "special_additional_claims": [
                {"item": "child_education", "children": 1, "share_ratio": "1.0"},
                {"item": "support_elderly", "only_child": True},
            ],
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "专项附加扣除申报清单" in out
    assert "子女教育" in out and "赡养老人" in out
    assert "2000.00" in out and "3000.00" in out  # 逐项标准（2023 提标后）
    assert "5000.00" in out  # 预扣链月合计
    assert "3480.00" in out  # 汇算：180000−60000−60000=60000 → 10%−2520
    assert "S2023" in out and "S41" in out  # 逐项依据


def test_calc_claims_serious_illness_stays_out_of_withholding(tmp_path, capsys):
    """大病医疗 settlement_only：预扣链不出现，汇算链计入。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "0.00"},
            "month_count": 1,
            "special_additional_claims": [
                {"item": "serious_illness", "self_paid_total": "30000.00"}
            ],
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "大病医疗" in out
    assert "仅年度汇算扣除" in out
    assert "15000.00" in out  # 30000 − 15000 起付


def test_calc_claims_violation_is_usage_error(tmp_path, capsys):
    """房贷+租金互斥 → 整单拒绝，退出码 2 并列出依据条款。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "10000.00"},
            "month_count": 1,
            "special_additional_claims": [
                {"item": "housing_loan"},
                {"item": "housing_rent", "tier": 0},
            ],
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 2
    err = capsys.readouterr().err
    assert "不得同时申报" in err and "第二十条" in err


def test_calc_claims_unknown_field_is_usage_error(tmp_path, capsys):
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "0.00"},
            "month_count": 1,
            "special_additional_claims": [{"item": "child_education", "chld": 1}],
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 2
    assert "不认识的字段" in capsys.readouterr().err


def test_calc_bonus_comparison_recommends_and_warns_trap(tmp_path, capsys):
    """择优对比输出（两方案税额+差额+推荐）+ 临界区间标红提示。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "8000.00"},
            "month_count": 12,
            "bonus_income": "36001.00",
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "择优对比" in out
    assert "方案A 单独计税" in out and "方案B 并入综合所得" in out
    assert "推荐方案A" in out  # A=4470.10 < B=4680.10，差额 −210.00
    assert "38566.67" in out  # 临界区间右端（推导复现）
    assert "[!!]" in out and "多发一元" in out  # 36001 落入陷阱区间


def test_calc_bonus_at_boundary_no_trap_warning(tmp_path, capsys):
    """奖金恰在区间左端（级距边界）不属于陷阱开区间：无 [!!] 陷阱提示。"""
    path = _write_input(
        tmp_path,
        {
            "uniform_month": {"gross": "0.00"},
            "month_count": 1,
            "bonus_income": "36000.00",
        },
    )
    assert main(["calc", "--year", "2024", "--input", path]) == 0
    out = capsys.readouterr().out
    assert "临界区间" in out  # 推导区间仍列出
    assert "多发一元" not in out  # 但 36000 不落入开区间


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
