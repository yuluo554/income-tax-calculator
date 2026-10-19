"""年度规则包生成器（M1 定稿）：单模板参数化生成 2019-2026 共 8 份 ruleset-YYYY.json。

纪律（ai-tool-project-sprint 阶段1 确定性生成）：
- 固定输入、固定键序、无时间戳、无随机数——两次运行输出逐字节一致（守门测试
  tests/test_gen_rulesets.py::test_regeneration_byte_identical 锁定）；
- 每条数值挂 ref（来源 id + 条款）+ status=已核对；条款与数值均按 2026-10-07
  官方原文逐字核对（原文快照存 data/knowledge/raw/，台账见 data/README.md）；
- 顶层 review 块记录核对日期、下次复核与依据年度：2019/2022/2023 为逐字核对年，
  其余年度沿用最近一次已核对原文（2024-2026 沿用 2023 标准，未取得逐年度新文件）；
- 写入前对每份产物跑 schema 校验与 status 门控断言（0 条待核对）。

年度差异点（核对定稿，plan/05 §1.1）：
- 2019-2021：六项专项附加扣除（无婴幼儿照护）；子女教育 1000、赡养老人 2000
  （独生）/非独生分摊总额 2000、每人上限 1000（国发〔2018〕41号 第五/二十二条）；
- 2022：增设婴幼儿照护 1000（国发〔2022〕8号，自 2022-01-01 实施 → 2022 纳税
  年度起适用）；年终奖单独计税延至 2023-12-31（财政部 税务总局公告2021年第42号）；
- 2023-2026：三项提标（国发〔2023〕13号，自 2023-01-01 实施）：婴幼儿 2000、
  子女教育 2000、赡养老人 3000（独生定额；非独生分摊总额 3000、每人上限 1500）；
  年终奖单独计税延至 2027-12-31（财政部 税务总局公告2023年第30号）。
- 不变项：减除费用 5000 元/月（61号公告第六条）；两张税率表（个税法税率表一 /
  164号附件1）；继续教育 400 元/月≤48个月、职业资格 3600 元/年（41号 第八条）；
  大病医疗 15000 起付、80000 限额、汇算时扣除（41号 第十一条）；房贷利息 1000
  元/月≤240个月（41号 第十四条）；住房租金 1500/1100/800（41号 第十七条）；
  房贷与租金互斥（41号 第二十条）；年终奖除以 12 查月度表（164号 第一条（一））。
- 速算扣除数出处：综合所得年度表挂 61号公告附件"个人所得税预扣率表一"（级距与
  税率同税率表一，速算扣除数 0/2520/16920/31920/52920/85920/181920）。
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
try:
    from incometax.rules import loader, schema
except ImportError:  # 允许未安装包时从仓库根直接运行
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from incometax.rules import loader, schema

YEARS = tuple(range(2019, 2027))

# 本轮复核口径（D-2 A）：2026-10-07 逐字核对；下次复核 2027-01-31。
# 日期只出现在生成器/数据中，src 侧一律从规则包读取（零字面量门禁）。
REVIEWED_AT = "2026-10-07"
NEXT_REVIEW = "2027-01-31"

VERIFIED = schema.STATUS_VERIFIED

# 来源 id 与官方原文 URL（抓取快照存 data/knowledge/raw/，sha256 见 data/README.md）
SOURCES = {
    "S61": {
        "doc": "国家税务总局公告2018年第61号《个人所得税扣缴申报管理办法（试行）》",
        "url": "https://fgk.chinatax.gov.cn/zcfgk/c100012/c5194838/content.html",
        "reviewed_at": REVIEWED_AT,
        "note": "累计预扣法公式、减除费用 5000 元/月、附件预扣率表一（速算扣除数）均已逐字核对",
    },
    "SLAW": {
        "doc": "中华人民共和国个人所得税法（2018年修正，2018-08-31）",
        "url": "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5193028/content.html",
        "reviewed_at": REVIEWED_AT,
        "note": "税率表一（综合所得适用）级距与税率按官方原文图逐字核对",
    },
    "S164": {
        "doc": "财税〔2018〕164号《关于个人所得税法修改后有关优惠政策衔接问题的通知》",
        "url": "https://www.gov.cn/zhengce/zhengceku/2018-12/31/content_5440172.htm",
        "reviewed_at": REVIEWED_AT,
        "note": "第一条（一）年终奖除以12查月度税率表；附件1按月换算后的综合所得税率表已逐字核对",
    },
    "S42": {
        "doc": "财政部 税务总局公告2021年第42号《关于延续实施全年一次性奖金等个人所得税优惠政策的公告》",
        "url": "https://www.gov.cn/zhengce/zhengceku/2021-12/31/content_5665897.htm",
        "reviewed_at": REVIEWED_AT,
        "note": "全年一次性奖金单独计税优惠政策执行期限延长至2023年12月31日，已逐字核对",
    },
    "S30": {
        "doc": "财政部 税务总局公告2023年第30号《关于延续实施全年一次性奖金个人所得税政策的公告》",
        "url": "https://www.gov.cn/zhengce/zhengceku/202308/content_6900595.htm",
        "reviewed_at": REVIEWED_AT,
        "note": "单独计税延续、可选并入、执行至2027-12-31，已逐字核对",
    },
    "S41": {
        "doc": "国发〔2018〕41号《个人所得税专项附加扣除暂行办法》",
        "url": "https://www.gov.cn/zhengce/zhengceku/2018-12/22/content_5351181.htm",
        "reviewed_at": REVIEWED_AT,
        "note": "七项扣除分档/互斥/分摊条款逐字核对；自2019-01-01施行（第三十二条）",
    },
    "S2022": {
        "doc": "国发〔2022〕8号《国务院关于设立3岁以下婴幼儿照护个人所得税专项附加扣除的通知》",
        "url": "https://www.gov.cn/zhengce/zhengceku/2022-03/28/content_5682013.htm",
        "reviewed_at": REVIEWED_AT,
        "note": "每孩每月1000元、分摊方式、自2022年1月1日起实施，已逐字核对",
    },
    "S2023": {
        "doc": "国发〔2023〕13号《国务院关于提高个人所得税有关专项附加扣除标准的通知》",
        "url": "https://www.gov.cn/zhengce/zhengceku/202308/content_6901207.htm",
        "reviewed_at": REVIEWED_AT,
        "note": "三项提标（婴幼儿2000/子女教育2000/赡养老人3000）自2023-01-01实施，已逐字核对",
    },
}

# 综合所得年度税率表（个税法税率表一，2018 修正后全期间未变）；
# quick_deduction 出处 = 61号公告附件预扣率表一（ref_qd）。
COMPREHENSIVE_ANNUAL = [
    (0, 36000, "0.03", 0),
    (36000, 144000, "0.10", 2520),
    (144000, 300000, "0.20", 16920),
    (300000, 420000, "0.25", 31920),
    (420000, 660000, "0.30", 52920),
    (660000, 960000, "0.35", 85920),
    (960000, None, "0.45", 181920),
]

# 按月换算后的综合所得税率表（财税〔2018〕164号 附件1，全期间未变）
MONTHLY_CONVERTED = [
    (0, 3000, "0.03", 0),
    (3000, 12000, "0.10", 210),
    (12000, 25000, "0.20", 1410),
    (25000, 35000, "0.25", 2660),
    (35000, 55000, "0.30", 4410),
    (55000, 80000, "0.35", 7160),
    (80000, None, "0.45", 15160),
]


def _rate_rows(table, source_id, clause, extra_ref_qd=False):
    rows = []
    for lower, upper, rate, quick in table:
        row = {
            "lower": lower,
            "upper": upper,
            "rate": rate,
            "quick_deduction": quick,
            "ref": {"source": source_id, "clause": clause},
        }
        if extra_ref_qd:
            row["ref_qd"] = {
                "source": "S61",
                "clause": "附件：个人所得税预扣率表一（居民个人工资、薪金所得预扣预缴适用）",
            }
        row["status"] = VERIFIED
        rows.append(row)
    return rows


def _bonus_policy(year):
    """年终奖单独计税政策：按年度挂当期有效文件（164号 → 42号 → 30号 文档链）。"""
    if year <= 2021:
        return {
            "value": "单独计税与并入综合所得可择优；按 164 号第一条（一）单独计税执行至 2021-12-31",
            "valid_from": "2019-01-01",
            "valid_until": "2021-12-31",
            "ref": {"source": "S164", "clause": "第一条（一）"},
            "status": VERIFIED,
        }
    if year == 2022:
        return {
            "value": "单独计税与并入综合所得可择优；42 号公告将 164 号单独计税政策延长至 2023-12-31",
            "valid_from": "2019-01-01",
            "valid_until": "2023-12-31",
            "ref": {"source": "S42", "clause": "第一条"},
            "status": VERIFIED,
        }
    return {
        "value": "单独计税与并入综合所得可择优；30 号公告执行至 2027-12-31",
        "valid_from": "2019-01-01",
        "valid_until": "2027-12-31",
        "ref": {"source": "S30", "clause": "第一条"},
        "status": VERIFIED,
    }


def _year_source_ids(year):
    ids = ["S61", "SLAW", "S164"]
    if year == 2022:
        ids.append("S42")
    if year >= 2023:
        ids.append("S30")
    ids.append("S41")
    if year >= 2022:
        ids.append("S2022")
    if year >= 2023:
        ids.append("S2023")
    return ids


def _year_notes(year):
    if year <= 2021:
        return (
            "首年口径：新个税法、61号公告扣缴办法、41号办法（六项专项附加扣除）"
            "自2019-01-01施行；年终奖单独计税按164号执行至2021-12-31。"
        )
    if year == 2022:
        return (
            "婴幼儿照护专项附加扣除设立（国发〔2022〕8号，自2022-01-01实施，2022纳税年度起"
            "适用，七项）；年终奖单独计税延长至2023-12-31（财政部 税务总局公告2021年第42号）。"
        )
    return (
        "三项专项附加扣除提标（国发〔2023〕13号，自2023-01-01实施）：婴幼儿照护2000、"
        "子女教育2000、赡养老人3000（非独生分摊总额3000、每人上限1500）；"
        "年终奖单独计税执行至2027-12-31（财政部 税务总局公告2023年第30号）。"
    )


def _review_block(year: int) -> dict:
    """顶层复核元数据：核对日期 / 下次复核 / 依据年度与沿用范围（D-2 A）。"""
    if year <= 2021:
        return {
            "reviewed_at": REVIEWED_AT,
            "next_review": NEXT_REVIEW,
            "basis_year": 2019,
            "carry_forward_years": [2020, 2021],
            "scope_note": "2019 官方原文逐字核对；2020-2021 沿用 2019 标准",
        }
    if year == 2022:
        return {
            "reviewed_at": REVIEWED_AT,
            "next_review": NEXT_REVIEW,
            "basis_year": 2022,
            "carry_forward_years": [],
            "scope_note": "2022 官方原文逐字核对（含婴幼儿照护设立）",
        }
    return {
        "reviewed_at": REVIEWED_AT,
        "next_review": NEXT_REVIEW,
        "basis_year": 2023,
        "carry_forward_years": [2024, 2025, 2026],
        "scope_note": "2023 官方原文逐字核对；2024-2026 沿用 2023 标准，未取得逐年度新文件",
    }


def build_ruleset(year: int) -> dict:
    """构建年度规则包（插入序即输出序，勿改动——改键序即破坏位级一致守门）。"""
    if year not in YEARS:
        raise ValueError(f"年度 {year} 不在生成范围 {YEARS}")

    child_standard = 1000 if year <= 2022 else 2000
    child_ref = (
        {"source": "S41", "clause": "第五条第一款（每个子女每月1000元）"}
        if year <= 2022
        else {"source": "S2023", "clause": "第二条（1000→2000，自2023-01-01实施）"}
    )
    elderly_only = 2000 if year <= 2022 else 3000
    elderly_only_ref = (
        {"source": "S41", "clause": "第二十二条（一）（独生子女每月2000元）"}
        if year <= 2022
        else {"source": "S2023", "clause": "第三条（2000→3000，独生子女定额）"}
    )
    elderly_total = 2000 if year <= 2022 else 3000
    elderly_total_ref = (
        {"source": "S41", "clause": "第二十二条（二）（分摊每月2000元的扣除额度）"}
        if year <= 2022
        else {"source": "S2023", "clause": "第三条（分摊每月3000元的扣除额度）"}
    )
    elderly_per_child = 1000 if year <= 2022 else 1500
    elderly_per_child_ref = (
        {"source": "S41", "clause": "第二十二条（二）（每人不超过每月1000元）"}
        if year <= 2022
        else {"source": "S2023", "clause": "第三条（每人不超过每月1500元）"}
    )

    special = {
        "housing_loan_vs_rent": "mutually_exclusive",
        "child_education": {
            "monthly_per_child": {"value": child_standard, "ref": child_ref, "status": VERIFIED},
            "scope": {
                "desc": "学前教育（年满3岁至小学入学前）至全日制学历教育，按每孩计算",
                "ref": {"source": "S41", "clause": "第五条"},
                "status": VERIFIED,
            },
            "split_mode": {
                "desc": "父母一方按扣除标准的100%扣除，或双方各按50%扣除；一个纳税年度内不能变更",
                "ref": {"source": "S41", "clause": "第六条"},
                "status": VERIFIED,
            },
        },
        "continue_education": {
            "academic_monthly": {
                "value": 400,
                "ref": {"source": "S41", "clause": "第八条（学历（学位）继续教育每月400元）"},
                "status": VERIFIED,
            },
            "academic_max_months": {
                "value": 48,
                "ref": {"source": "S41", "clause": "第八条（同一学历（学位）扣除期限不超过48个月）"},
                "status": VERIFIED,
            },
            "vocational_annual": {
                "value": 3600,
                "ref": {"source": "S41", "clause": "第八条（职业资格继续教育取得证书当年3600元）"},
                "status": VERIFIED,
            },
        },
        "serious_illness": {
            "claimable_stage": {
                "desc": "仅年度汇算清缴时扣除，预扣环节不可扣",
                # 机器可读阶段标记（plan/04 §一 schema 定稿）：引擎按此把大病医疗
                # 从预扣链剔除、仅纳入汇算链（M3 deductions.py 消费）
                "stage": "settlement_only",
                "ref": {"source": "S41", "clause": "第十一条（办理年度汇算清缴时据实扣除）"},
                "status": VERIFIED,
            },
            "deductible_threshold": {
                "value": 15000,
                "ref": {"source": "S41", "clause": "第十一条（医保目录范围内自付部分累计超过15000元）"},
                "status": VERIFIED,
            },
            "annual_cap": {
                "value": 80000,
                "ref": {"source": "S41", "clause": "第十一条（80000元限额内据实扣除）"},
                "status": VERIFIED,
            },
        },
        "housing_loan": {
            "monthly": {
                "value": 1000,
                "ref": {"source": "S41", "clause": "第十四条（首套住房贷款利息每月1000元）"},
                "status": VERIFIED,
            },
            "max_months": {
                "value": 240,
                "ref": {"source": "S41", "clause": "第十四条（扣除期限最长不超过240个月）"},
                "status": VERIFIED,
            },
        },
        "housing_rent": {
            "mutually_exclusive_with": {
                "desc": "住房贷款利息：纳税人及其配偶一个纳税年度内不能同时分别享受",
                "ref": {"source": "S41", "clause": "第二十条"},
                "status": VERIFIED,
            },
            "tiers": [
                {
                    "tier": {
                        "desc": "直辖市、省会（首府）城市、计划单列市以及国务院确定的其他城市",
                        "ref": {"source": "S41", "clause": "第十七条（一）"},
                        "status": VERIFIED,
                    },
                    "monthly": {"value": 1500, "ref": {"source": "S41", "clause": "第十七条（一）"}, "status": VERIFIED},
                },
                {
                    "tier": {
                        "desc": "市辖区户籍人口超过100万的城市",
                        "ref": {"source": "S41", "clause": "第十七条（二）"},
                        "status": VERIFIED,
                    },
                    "monthly": {"value": 1100, "ref": {"source": "S41", "clause": "第十七条（二）"}, "status": VERIFIED},
                },
                {
                    "tier": {
                        "desc": "市辖区户籍人口不超过100万的城市",
                        "ref": {"source": "S41", "clause": "第十七条（二）"},
                        "status": VERIFIED,
                    },
                    "monthly": {"value": 800, "ref": {"source": "S41", "clause": "第十七条（二）"}, "status": VERIFIED},
                },
            ],
        },
        "support_elderly": {
            "only_child_monthly": {"value": elderly_only, "ref": elderly_only_ref, "status": VERIFIED},
            "shared_total_cap": {"value": elderly_total, "ref": elderly_total_ref, "status": VERIFIED},
            "shared_per_child_cap": {"value": elderly_per_child, "ref": elderly_per_child_ref, "status": VERIFIED},
            "shared_mode": {
                "desc": "由赡养人均摊或约定分摊，也可由被赡养人指定分摊；约定或指定分摊须签订书面分摊协议，指定分摊优先于约定分摊",
                "ref": {"source": "S41", "clause": "第二十二条（二）"},
                "status": VERIFIED,
            },
        },
    }

    if year >= 2022:
        infant_per_child = 1000 if year == 2022 else 2000
        infant_ref = (
            {"source": "S2022", "clause": "第一条（每个婴幼儿每月1000元）"}
            if year == 2022
            else {"source": "S2023", "clause": "第一条（1000→2000，自2023-01-01实施）"}
        )
        special["infant_care"] = {
            "monthly_per_child": {"value": infant_per_child, "ref": infant_ref, "status": VERIFIED},
            "scope": {
                "desc": "照护3岁以下婴幼儿子女的相关支出",
                "ref": {"source": "S2022", "clause": "第一条"},
                "status": VERIFIED,
            },
            "split_mode": {
                "desc": "父母一方按扣除标准的100%扣除，或双方各按50%扣除；一个纳税年度内不能变更",
                "ref": {"source": "S2022", "clause": "第二条"},
                "status": VERIFIED,
            },
            "effective_from": {
                "desc": "自2022年1月1日起实施（2022纳税年度起适用）",
                "ref": {"source": "S2022", "clause": "第四条"},
                "status": VERIFIED,
            },
        }

    sources = []
    for sid in _year_source_ids(year):
        meta = SOURCES[sid]
        sources.append(
            {
                "id": sid,
                "doc": meta["doc"],
                "url": meta["url"],
                "status": VERIFIED,
                "reviewed_at": meta["reviewed_at"],
                "note": meta["note"],
            }
        )

    return {
        "schema_version": 1,
        "year": year,
        "review": _review_block(year),
        "notes": _year_notes(year),
        "sources": sources,
        "withholding": {
            "monthly_standard_deduction": {
                "value": 5000,
                "ref": {
                    "source": "S61",
                    "clause": "第六条（累计减除费用按照5000元/月乘以当年截至本月任职受雇月份数计算）",
                },
                "status": VERIFIED,
            }
        },
        "rate_tables": {
            "comprehensive_annual": _rate_rows(
                COMPREHENSIVE_ANNUAL, "SLAW", "税率表一（综合所得适用）", extra_ref_qd=True
            ),
            "monthly_converted": _rate_rows(
                MONTHLY_CONVERTED, "S164", "附件1：按月换算后的综合所得税率表"
            ),
        },
        "bonus": {
            "separate_tax_policy": _bonus_policy(year),
            "monthly_divisor": {
                "value": 12,
                "ref": {"source": "S164", "clause": "第一条（一）（以全年一次性奖金收入除以12个月得到的数额查表）"},
                "status": VERIFIED,
            },
        },
        "special_deductions": special,
    }


def serialize(ruleset: dict) -> str:
    """确定性序列化：固定键序 + 2 空格缩进 + LF 结尾（禁时间戳/随机）。"""
    return json.dumps(ruleset, ensure_ascii=False, indent=2) + "\n"


def write_all(out_dir: Path, years=YEARS) -> list:
    """生成并写入规则包；写入前逐份 schema 校验 + 门控断言 0 待核对。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for year in years:
        ruleset = build_ruleset(year)
        schema.validate_ruleset(ruleset, expected_year=year)
        report = loader.status_report(loader.Ruleset(year=year, data=ruleset, path=out_dir / f"ruleset-{year}.json"))
        if report.pending != 0:
            raise AssertionError(f"年度 {year} 存在 {report.pending} 条待核对条目：{report.pending_paths}")
        path = out_dir / f"ruleset-{year}.json"
        # py3.8 兼容：Path.write_text 无 newline 参数，强制 LF 用 open()
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(serialize(ruleset))
        written.append(path)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 2019-2026 年度规则包（确定性，位级可复现）")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "rules"), help="输出目录（默认 data/rules）")
    parser.add_argument("--years", default=",".join(str(y) for y in YEARS), help="逗号分隔年度列表")
    args = parser.parse_args(argv)
    years = [int(y) for y in args.years.split(",")]
    written = write_all(Path(args.out_dir), years=years)
    for path in written:
        print(f"written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
