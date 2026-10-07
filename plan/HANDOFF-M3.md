# HANDOFF-M3（跨会话交接快照）

> 用法：新会话启动提示词 `/goal 读取 "plan/HANDOFF-M3.md" 继续完成任务`（相对路径，从仓库根解析）。
> 快照日期：2026-10-07。M2（计算引擎）已完成，下一棒 = **M3 择优与扣除**（任务清单见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §二 M3）。

## 当前进度（M2 末态）

- **三引擎实装**：`engine/monthly.py`（61号第六条逐月状态机：累计应纳税所得额→预扣率表一→本期应预扣；负值按 0 暂不退税并记 note，负数不滚入下月）、`engine/social.py`（基数夹取+费率全用户输入，返回 total 供 monthly 并入专项扣除并回链"来自社保联动"标注）、`engine/settlement.py`（全年口径→减除费用=月度减除×12→综合所得税率表→应退/应补=已预缴−应纳税额，正=应退）；
- **bonus 原语提前**：`engine/bonus.py::compute_bonus_separate_tax` 已落地（164号第一条（一）：÷月份数 ROUND_HALF_UP 两位仅定档、税基用全额；政策有效期按规则包 valid_until 提示）；`compare_bonus_schemes` / `derive_bonus_trap_intervals` 仍为 M3 桩；
- **共享件**：`engine/report.py`（MONEY_QUANT 两位 ROUND_HALF_UP、render_ref/short_ref 依据渲染）；引擎入口各自再调 `effective_ruleset()`（红线双保险，测试覆盖）；
- **CLI calc 实装**：`calc --year YYYY --input f.json`（schema 见 README「calc 输入格式」）→ 逐月预扣表（每行挂 减除费用+级次+速算 依据）+ 社保块 + 年度汇算（应退/应补）+ 年终奖单独计税块 + 来源图例 + 免责声明；退出码：成功 0 / 门控与计算失败 1 / 用法输入 2（缺 `--input`=2，门控先于输入校验）；
- **真值对账**：`tests/test_truth_reconciliation.py` 4 条真值 expected+also_expect 全字段键集对账 100%（未改真值）；新增 `tests/test_zero_policy_literals.py` 零政策字面量门禁（收编 8 份规则包数值扫 engine/+cli.py，<100 豁免）；
- **M2 修正一处 M0 遗留错误**：税率级距官方口径 = 上界闭（"不超过X元"），`find_bracket` 已改（详见 plan/06「M2 税率级距区间语义」），schema.py Bracket 文档同步；
- pytest 收集数基线：**75**（M1 为 39，只增不减）。CLI 实测：4 条真值算例 calc 全 rc=0（withholding-3months-2019 逐月 90/合计 270+汇算全退；settlement-2024 应补 1480；bonus 36000→1080 / 36001→3390.10）；`rules --year 2019..2026` 全 rc=0。

## M3 待办（按序）

1. `engine/bonus.py` 双方案择优：方案 A（单独计税，原语已备）vs 方案 B（并入综合重跑汇算），比全年总税负，差 ≤0.01 元并列；政策到期年份方案 A 标不可用；
2. `engine/bonus.py::derive_bonus_trap_intervals` 临界区间机制性推导：端点公式 `B* = (b·(1−r₁)+q₁−q₂)/(1−r₂)`（plan/04 §3.2），由按月换算表逐边界推导，**代码零字面量**（验证锚点首区间右端 38566.67 类值由推导复现，M4 边界扫描断言）；
3. `engine/deductions.py` 七项专项附加：分档标准计算（子女/婴幼儿按孩数、租金按城市档）、房贷 vs 租金互斥校验（规则包 `housing_loan_vs_rent`）、赡养老人分摊上限校验、大病医疗 `settlement_only`（预扣链剔除、汇算链纳入——monthly 输入侧需按 stage 过滤）；
4. CLI 先行演示：择优对比输出（两方案税额+推荐+差额）、临界区间标红提示；专项附加申报清单校验输出；
5. 真值库回归保持 4 条 100%（bonus 算例此时可走 compare 路径对账 `policy: separate`）；
6. pytest 全绿且收集数 ≥75；plan/00、05、06 回写；落 HANDOFF-M4。

## 既定口径清单（M2 增补版，动了会打挂测试/基准，改动前先对照）

1. **退出码**：0=成功 / 1=运行期失败（门控拦截、计算失败）/ 2=用法输入错误——`tests/test_cli.py` 锁定；calc 缺 `--input`=2（门控在校验输入**之前**）；
2. **门控覆盖面** = 含 `value` 键的数值条目 + 两张税率表逐行；sources[] 与 desc/ref_qd 说明节点不进门控；引擎入口（monthly/settlement/bonus 原语）内部再次调用 `effective_ruleset()`——新增引擎模块须同样挂；
3. **schema v1**：7 级相接、末级 `upper=null`、value 节点必有 `ref`、`housing_loan_vs_rent` 必须显式 `mutually_exclusive`、status 缺失按待核对；税率行 `ref`+`ref_qd` 双出处键；
4. **税率级距 = 上界闭区间**（"不超过X元"）：`find_bracket` 顺序查首个 `taxable ≤ upper`（M2 定稿，M4 边界扫描的机制基准）；级距相接 ⇒ 边界点税额连续，仅年终奖查表受级距语义影响（陷阱机制本身）；
5. **Decimal 全链路 + 舍入口径**：JSON `parse_float=Decimal`，rate/金额字段为字符串；金额呈现/申报两位小数 ROUND_HALF_UP（`report.MONEY_QUANT`，非政策数值）；年终奖商数两位仅定档、税基全额；累计应纳税所得额不舍入；
6. **零政策字面量**：`tests/test_zero_policy_literals.py` 收编 8 份规则包数值扫 engine/+cli.py（≥100 整数+小数+原样税率串，词边界；<100 豁免：12=日历月数、0.01=申报精度）；**文档字符串也扫**——写注释别带 5000/36000/2026 这类数；
7. **规则包=冻结产物**：data/rules 禁手改，改需求走 `tools/gen_rulesets.py` 整目录重生成，位级守门测试随全量跑；生成器确定性（无时间戳/随机/set 迭代序）；
8. **年度口径**：2019-2026 共 **8** 份；婴幼儿照护 2022 纳税年度起适用（2019-2021 六项）；年终奖文档链 164(至2021-12-31)/42(至2023-12-31)/30(至2027-12-31) 按年度挂 `ref`；
9. **真值库语义**：expected 主期望 + also_expect 隐含中间量，评测按"全部非 pass 字段集"对账（`test_truth_reconciliation` 键集断言：真值加字段必须同步补对账，见 `test_all_four_cases_covered`）；**不许改真值凑引擎答案**；
10. **社保参数归属**：缴费基数上下限与费率全部用户输入（plan/06 D-4），`social.py` 不接收 Ruleset；
11. **Python 3.8 兼容**：无 match、无 PEP604 运行期联合类型、`Path.write_text` 无 `newline` 参数（M2 再次踩到，用 `open(..., newline="\n")`）；
12. **数据目录定位顺序**：显式 --data-dir > `INCOMETAX_DATA_DIR` > `sys._MEIPASS/data` > CWD 上溯——M5 打包时冻结；
13. **calc 输入 schema v1**：months（1-12）/ uniform_month+month_count 二选一，缺月按 0 补足并标注；social 可选；settlement 覆盖字段缺省由月度聚合；未知字段=2。

## 本机环境坑（全部实测）

- `py` 是 3.8.8（`python` 是商店占位符）；跑带中文输出的命令用 `py -X utf8`；
- 全程 `PYTHONDONTWRITEBYTECODE=1`（含 pip install），出怪错先清 `__pycache__`；
- pip 被注册表系统代理污染 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- 统一用 `py -m incometax` 或 `py -X utf8 -m incometax`（Scripts 不在 PATH）；
- Git Bash heredoc/重定向与 Windows Python 路径：一律用工作区相对路径；
- 查证通道实测（M1 沉淀，M3 校验扣除条款时用）：`fgk.chinatax.gov.cn/zcfgk/c1000XX/cXXXXXXX/content.html` curl 直抓可用；gov.cn 政策文件库检索 API `https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary_gw|_bm&q=<urlencode>&p=1&n=10&sort=score` 可用；flk/Bing/DDG 不可用；
- git 提交邮箱已设 GitHub noreply；**首提交 1481cc8 仍含个人 QQ 邮箱** → M6 env-filter 全历史改写（勿忘）；
- `.gitignore` 的 `*.spec` 通配会在 M5 吞掉 PyInstaller spec → 届时加 `!tools/*.spec` 例外。

## M3 DoD checklist

- [ ] `compare_bonus_schemes` 双方案对比 + `derive_bonus_trap_intervals` 临界区间推导（端点全由规则表推导，代码零字面量；首区间锚点与穷举一致）
- [ ] `deductions.py` 七项扣除：分档/互斥/分摊校验 + 大病 settlement_only 链路分离，误放行 0
- [ ] CLI 择优对比与临界区间演示输出可用（GUI 前的 CLI 形态）
- [ ] 真值库 4 条回归仍 100%（不改真值）；门控/冻结/零字面量/真值四类守门测试全绿
- [ ] pytest 全绿且收集数 ≥75（只增不减），基线记入 HANDOFF-M4
- [ ] plan/00、05、06 回写 ✅；HANDOFF-M4 落盘

## 关键命令速查

```bash
# 安装（新环境/依赖变更后）
NO_PROXY="*" no_proxy="*" py -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（本机纪律：PYTHONDONTWRITEBYTECODE=1）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q

# 规则包预览（全年度 0 待核对）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax rules --year 2026

# calc（输入 schema 见 README「calc 输入格式」）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax calc --year 2019 --input <calc-input.json>

# 重新生成规则包（改 tools/gen_rulesets.py 后整目录重生成）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py

# git（提交前三核对：pwd / git log -1 / git remote -v）
git add -A && git commit -m "..."
```
