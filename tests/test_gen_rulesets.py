"""生成器守门测试：data/rules/ 规则包必须与 gen_rulesets.py 重生成结果逐字节一致。

冻结产物纪律（ai-tool-project-sprint 阶段1）：改规则包必须改生成器并整目录重新生成，
禁止手改 JSON——本测试把"手改未再生成"和"生成器漂移"都拦下来。
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / "data" / "rules"
ALL_YEARS = list(range(2019, 2027))


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_rulesets", REPO_ROOT / "tools" / "gen_rulesets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return load_generator()


def test_regeneration_byte_identical(gen):
    """重生成序列化结果与仓库内文件逐字节一致（LF、键序、缩进全冻结）。"""
    for year in ALL_YEARS:
        repo_file = RULES_DIR / f"ruleset-{year}.json"
        assert repo_file.exists(), f"缺少规则包 {repo_file.name}"
        expected = gen.serialize(gen.build_ruleset(year)).encode("utf-8")
        assert repo_file.read_bytes() == expected, (
            f"{repo_file.name} 与生成器输出不一致：禁止手改冻结产物，"
            "请改 tools/gen_rulesets.py 后整目录重新生成"
        )


def test_files_on_disk_match_year_range(gen):
    files = sorted(p.name for p in RULES_DIR.glob("ruleset-*.json"))
    assert files == [f"ruleset-{y}.json" for y in ALL_YEARS]


def test_build_rejects_out_of_range_year(gen):
    with pytest.raises(ValueError):
        gen.build_ruleset(2018)
    with pytest.raises(ValueError):
        gen.build_ruleset(2027)


def test_every_value_node_has_ref_and_verified(gen):
    """生成器产物不依赖 loader 也必须自满足 schema 纪律（双保险）。"""
    for year in ALL_YEARS:
        raw = gen.build_ruleset(year)
        for path, node in gen.schema.iter_value_nodes(raw):
            assert "ref" in node, (year, path)
            assert node["status"] == "已核对", (year, path)
