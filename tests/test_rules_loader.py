"""规则包加载、schema 校验与 status 门控测试。

真值来源：仓库内 data/rules/ruleset-2022.json 与 ruleset-2026.json（骨架示例包）。
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from incometax.rules import (
    DataDirNotFoundError,
    RulesetNotEffective,
    RulesetNotFoundError,
    RulesetSchemaError,
    available_years,
    effective_ruleset,
    find_data_dir,
    load_ruleset,
    status_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def write_ruleset(tmp_path: Path, raw, year: int) -> str:
    """把 raw 写为 ruleset-<year>.json；同步内嵌 year（模拟真实文件）。"""
    raw = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
    raw["year"] = year
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"ruleset-{year}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False, default=str), encoding="utf-8")
    return str(tmp_path)


def all_verified(raw):
    """把整包 status 翻转为已核对（模拟 M1 核对完成后的门控放行路径）。"""

    def walk(node):
        if isinstance(node, dict):
            if "status" in node:
                node["status"] = "已核对"
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(raw)
    return raw


def test_load_2026_structure():
    rs = load_ruleset(2026)
    assert rs.year == 2026
    assert len(rs.comprehensive_brackets) == 7
    assert len(rs.monthly_brackets) == 7
    first = rs.comprehensive_brackets[0]
    assert first.lower == Decimal(0)
    assert first.rate == Decimal("0.03")
    last = rs.comprehensive_brackets[-1]
    assert last.upper is None
    assert last.rate == Decimal("0.45")
    assert rs.monthly_standard_deduction == Decimal(5000)


def test_rate_tables_identical_across_years():
    """税率表 2019-2026 政策未变：不同年度规则包的两张表必须一致。"""
    a = load_ruleset(2022)
    b = load_ruleset(2026)
    assert a.comprehensive_brackets == b.comprehensive_brackets
    assert a.monthly_brackets == b.monthly_brackets


def test_missing_year_lists_available():
    with pytest.raises(RulesetNotFoundError) as excinfo:
        load_ruleset(1999)
    assert 2022 in excinfo.value.available
    assert 2026 in excinfo.value.available


def test_available_years():
    years = available_years()
    assert 2022 in years and 2026 in years


def test_status_report_2026_has_pending_and_verified():
    report = status_report(load_ruleset(2026))
    # 已核对：减除费用、年终奖政策、2023 提标三项数值（题目阶段查证在案）
    assert report.verified >= 5
    # 待核对：两张税率表与 41 号办法条款数值（M1 逐条挂原文后翻转）
    assert report.pending >= 10
    assert report.pending_paths == tuple(sorted(report.pending_paths))
    assert not report.all_effective


def test_effective_gating_blocks_pending():
    with pytest.raises(RulesetNotEffective) as excinfo:
        effective_ruleset(load_ruleset(2026))
    assert any("rate_tables" in p for p in excinfo.value.pending_paths)
    assert "待核对" in str(excinfo.value)


def test_gate_opens_when_all_verified(tmp_path):
    raw = all_verified(load_ruleset(2026).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rs = load_ruleset(2099, data_dir=data_dir)
    assert status_report(rs).all_effective
    assert effective_ruleset(rs) is rs


def test_missing_status_defaults_to_pending(tmp_path):
    raw = load_ruleset(2026).data
    node = raw["withholding"]["monthly_standard_deduction"]
    node.pop("status")
    data_dir = write_ruleset(tmp_path, raw, 2098)
    report = status_report(load_ruleset(2098, data_dir=data_dir))
    assert "withholding.monthly_standard_deduction" in report.pending_paths


def test_find_data_dir_explicit(tmp_path):
    (tmp_path / "rules").mkdir()
    assert find_data_dir(str(tmp_path)) == tmp_path
    with pytest.raises(DataDirNotFoundError):
        find_data_dir(str(tmp_path / "nope"))


def test_find_data_dir_env(monkeypatch, tmp_path):
    (tmp_path / "rules").mkdir()
    monkeypatch.setenv("INCOMETAX_DATA_DIR", str(tmp_path))
    assert find_data_dir() == tmp_path
    monkeypatch.setenv("INCOMETAX_DATA_DIR", str(tmp_path / "nope"))
    with pytest.raises(DataDirNotFoundError):
        find_data_dir()


def test_find_data_dir_walk_up_from_repo_root():
    data_dir = find_data_dir()
    assert (data_dir / "rules" / "ruleset-2026.json").exists()


def test_schema_missing_section(tmp_path):
    raw = load_ruleset(2026).data
    raw.pop("bonus")
    with pytest.raises(RulesetSchemaError) as excinfo:
        load_ruleset(2097, data_dir=write_ruleset(tmp_path, raw, 2097))
    assert "bonus" in str(excinfo.value)


def test_schema_year_mismatch(tmp_path):
    raw = json.loads(json.dumps(load_ruleset(2026).data, ensure_ascii=False, default=str))
    raw["year"] = 2026  # 文件名为 2099、内嵌 year=2026 → 必须报不一致
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "ruleset-2099.json").write_text(
        json.dumps(raw, ensure_ascii=False, default=str), encoding="utf-8"
    )
    with pytest.raises(RulesetSchemaError) as excinfo:
        load_ruleset(2099, data_dir=str(tmp_path))
    assert "不一致" in str(excinfo.value)


def test_schema_mutex_flag_required(tmp_path):
    raw = load_ruleset(2026).data
    raw["special_deductions"]["housing_loan_vs_rent"] = "exclusive"
    with pytest.raises(RulesetSchemaError) as excinfo:
        load_ruleset(2096, data_dir=write_ruleset(tmp_path, raw, 2096))
    assert "mutually_exclusive" in str(excinfo.value)


def test_schema_rate_table_must_be_contiguous(tmp_path):
    raw = load_ruleset(2026).data
    raw["rate_tables"]["comprehensive_annual"][3]["lower"] = 123456
    with pytest.raises(RulesetSchemaError) as excinfo:
        load_ruleset(2095, data_dir=write_ruleset(tmp_path, raw, 2095))
    assert "不相接" in str(excinfo.value)


def test_schema_value_node_requires_ref(tmp_path):
    raw = load_ruleset(2026).data
    raw["special_deductions"]["continue_education"]["academic_monthly"].pop("ref")
    with pytest.raises(RulesetSchemaError) as excinfo:
        load_ruleset(2094, data_dir=write_ruleset(tmp_path, raw, 2094))
    assert "ref" in str(excinfo.value)


def test_schema_invalid_status_rejected(tmp_path):
    raw = load_ruleset(2026).data
    raw["special_deductions"]["continue_education"]["academic_monthly"]["status"] = "大概吧"
    with pytest.raises(RulesetSchemaError) as excinfo:
        load_ruleset(2093, data_dir=write_ruleset(tmp_path, raw, 2093))
    assert "status" in str(excinfo.value)
