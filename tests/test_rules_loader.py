"""规则包加载、schema 校验与 status 门控测试。

M1 后基线：data/rules/ 为生成器产物（tools/gen_rulesets.py），2019-2026 共 8 份，
全部数值条目已核对（官方原文逐字核对，台账见 data/README.md）→ 门控放行。
门控拦截路径用 tmp 目录内合成规则包验证（宁缺勿错语义不受影响）。
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

ALL_YEARS = list(range(2019, 2027))


def write_ruleset(tmp_path: Path, raw, year: int) -> str:
    """把 raw 写为 ruleset-<year>.json；同步内嵌 year（模拟真实文件）。"""
    raw = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
    raw["year"] = year
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"ruleset-{year}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False, default=str), encoding="utf-8")
    return str(tmp_path)


def flip_one_node_pending(raw):
    """把一个数值条目翻回待核对（构造门控拦截的合成包）。"""

    def walk(node):
        if isinstance(node, dict):
            if node.get("status") == "已核对" and "value" in node:
                node["status"] = "待核对"
                return True
            for child in node.values():
                if walk(child):
                    return True
        elif isinstance(node, list):
            for child in node:
                if walk(child):
                    return True
        return False

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
    """税率表 2019-2026 政策未变：全部年度规则包的两张表必须一致。"""
    base = load_ruleset(2019)
    for year in ALL_YEARS[1:]:
        rs = load_ruleset(year)
        assert base.comprehensive_brackets == rs.comprehensive_brackets, year
        assert base.monthly_brackets == rs.monthly_brackets, year


def test_available_years_covers_full_range():
    assert available_years() == ALL_YEARS


def test_missing_year_lists_available():
    with pytest.raises(RulesetNotFoundError) as excinfo:
        load_ruleset(1999)
    assert excinfo.value.available == ALL_YEARS


def test_all_years_all_verified_and_gating_passes():
    """M1 DoD：全部年度 0 条待核对，门控放行（真实规则包验证）。"""
    for year in ALL_YEARS:
        rs = load_ruleset(year)
        report = status_report(rs)
        assert report.pending == 0, (year, report.pending_paths)
        assert report.verified > 0
        assert report.all_effective
        assert effective_ruleset(rs) is rs


def test_year_differences_match_policy_chain():
    """年度差异点：扣除项数/标准与年终奖文档链按核对结论逐年断言。"""
    r2019 = load_ruleset(2019).data["special_deductions"]
    assert "infant_care" not in r2019  # 2019-2021 六项（国发〔2022〕8号自2022-01-01实施）
    assert r2019["child_education"]["monthly_per_child"]["value"] == 1000
    assert r2019["support_elderly"]["only_child_monthly"]["value"] == 2000
    assert load_ruleset(2021).data["bonus"]["separate_tax_policy"]["valid_until"] == "2021-12-31"
    assert load_ruleset(2021).data["bonus"]["separate_tax_policy"]["ref"]["source"] == "S164"

    r2022 = load_ruleset(2022).data["special_deductions"]
    assert "infant_care" in r2022  # 国发〔2022〕8号设立，2022 纳税年度起适用
    assert r2022["infant_care"]["monthly_per_child"]["value"] == 1000
    assert load_ruleset(2022).data["bonus"]["separate_tax_policy"]["ref"]["source"] == "S42"
    assert load_ruleset(2022).data["bonus"]["separate_tax_policy"]["valid_until"] == "2023-12-31"

    for year in (2023, 2026):
        rs = load_ruleset(year).data["special_deductions"]
        assert rs["infant_care"]["monthly_per_child"]["value"] == 2000  # 国发〔2023〕13号
        assert rs["child_education"]["monthly_per_child"]["value"] == 2000
        assert rs["support_elderly"]["only_child_monthly"]["value"] == 3000
        assert rs["support_elderly"]["shared_per_child_cap"]["value"] == 1500
        bonus = load_ruleset(year).data["bonus"]["separate_tax_policy"]
        assert bonus["ref"]["source"] == "S30"
        assert bonus["valid_until"] == "2027-12-31"


def test_status_report_2026_all_verified():
    """M1 后 2026 全部已核对（原骨架期"含待核对"断言已随门控翻转废止）。"""
    report = status_report(load_ruleset(2026))
    assert report.pending == 0
    assert report.pending_paths == ()
    assert report.all_effective


def test_effective_gating_blocks_synthetic_pending(tmp_path):
    """门控拦截路径（合成包）：任一数值条目翻回待核对即拒绝生效。"""
    raw = flip_one_node_pending(load_ruleset(2026).data)
    data_dir = write_ruleset(tmp_path, raw, 2099)
    rs = load_ruleset(2099, data_dir=data_dir)
    report = status_report(rs)
    assert report.pending == 1
    assert not report.all_effective
    with pytest.raises(RulesetNotEffective) as excinfo:
        effective_ruleset(rs)
    assert len(excinfo.value.pending_paths) == 1
    assert "待核对" in str(excinfo.value)


def test_gate_opens_when_all_verified():
    """门控放行路径：真实 2026 规则包直接通过（M1 翻转后的主断言）。"""
    rs = load_ruleset(2026)
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
