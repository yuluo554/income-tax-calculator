# HANDOFF-M4（跨会话交接快照）

> 用法：新会话启动提示词 `/goal 读取 "plan/HANDOFF-M4.md" 继续完成任务`（相对路径，从仓库根解析）。
> 快照日期：2026-10-07。M3（择优与扣除）已完成，下一棒 = **M4 边界扫描基准定稿**（任务清单见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §二 M4，基准设计见 [04-模块详设.md](04-模块详设.md) §四）。

## 当前进度（M3 末态）

- **择优引擎**：`engine/bonus.py::compare_bonus_schemes` 实装——方案 A（单独计税）总税负 = 工资汇算税 + 奖金单独计税税；方案 B（并入综合）= 奖金并入工资应纳税所得额重跑汇算；|差| ≤ 0.01 并列；政策到期年度（ruleset.year > valid_until）方案 A 标不可用、强制推荐方案 B。入参 `salary_settlement` 须为**不含奖金**的 SettlementReport（README 已注明）；
- **临界区间推导**：`derive_bonus_trap_intervals` + `find_trap_interval`——端点公式 `B* = (b(1−r₁)+q₁−q₂)/(1−r₂)` 由按月换算表逐边界推导，代码零字面量。**实测定稿：6 个级距边界全部产出陷阱区间**（速算扣除数不随年口径缩放），端点申报精度值依次为 38566.67 / 160500 / 318333.33 / 447500 / 706538.46 / 1120000（测试断言，非代码字面量）；首区间与穷举恢复点交叉验证一致；
- **七项专项附加**：`engine/deductions.py` 实装——`Claim`（item/children/share_ratio/kind/months/tier/only_child/monthly_amount/other_shared_amounts/self_paid_total）→ `evaluate_claims` → `DeductionsReport`（claims 逐项 + monthly_total + annual_total + settlement_only_annual_total）。分档标准全查规则包（孩数/城市档/学历 vs 职业资格/独生 vs 非独生）；房贷+租金互斥、分摊比例枚举、每人/合计上限、未知项、重复申报（继续教育按 kind 细分去重，学历+职业资格可并存）→ **违规整单拒绝**（`DeductionViolationError` 携全部违规逐条挂 ref，不产出部分结果）；
- **大病医疗链路分离**：规则包 `serious_illness.claimable_stage` 增设机器可读 `"stage": "settlement_only"`（生成器重生成 8 份，位级守门通过）；预扣链月额恒 0，汇算链按起付线/限额计算（职业资格 3600 定额同样计入汇算链）；
- **CLI calc 增补**：输入新增 `special_additional_claims` 数组（解析校验 → 退出码 2）；违规 → 2 并列条款；输出新增 专项附加申报清单块（逐项计算式+依据）、年终奖择优对比块（两方案总税负+差额+推荐）、临界区间整表 + 落入区间 `[!!]` 提示；claims 月额按申报月数逐月叠加进月度输入（附注），settlement_only 年额在汇算聚合时单独加回；
- **测试**：pytest 收集数基线 **122**（M2 为 75，只增不减）：M3 新增 test_engine_deductions.py 23 项、test_engine_bonus.py 增 13 项（择优 5 + 临界 4 + 门控 1 + 原 5 保持）、test_cli.py 增 6 项；真值 4 条对账 100% 未动；
- **CLI 实测**：bonus 36001 → 择优推荐方案 A（少缴 210）+ 陷阱 `[!!]`；三申报（子女/赡养/大病 30000）→ 清单 5000/月 + 15000 仅汇算 + 汇算应退 1500；房贷+租金 → rc 2 拒绝挂第二十条。

## M4 待办（按序）

1. `src/incometax/benchmark/` 包骨架：算例回归（复用/上收 tests/test_truth_reconciliation 的 flatten+键集对账语义）、税率级次临界、陷阱区间、扣除互斥组合四类 runner；**纯规则通路、零 API、固定输入可复现**；
2. **税率级次临界扫描**：两张税率表每个 `upper` 边界 ±ε（Decimal 精确邻域）断言 `find_bracket` 级次切换 + 税额行为（年度表边界连续/年终奖查表跳变）与机制自洽 100%；
3. **陷阱区间扫描**：6 个推导区间逐端点内外 ±0.01 断言"区间内到手变少、区间外恢复"——M3 首区间穷举测试（test_engine_bonus.py::test_trap_interval_brute_force_recovery_point）推广为全区间基准；**注意查表死区口径**（见口径 14：从实际跳档点起断言，恢复点 = 推导右端点申报精度值）；
4. **扣除互斥组合枚举**：房贷×租金全档位、分摊上限边界（每人/合计）、重复申报、未知项 → 拒绝率 100%、误放行 0；
5. **一条命令跑全基准**：建议 CLI 新增 `benchmark` 子命令（复用退出码 0/1，输出指标表；GUI M5 可复用同一 API）；或独立 `py -m incometax.benchmark`——实现时定稿并记 plan/06；
6. 指标写进 README 表格（算例 100% / 自洽 100% / 陷阱穷举一致 100% / 误放行 0）；基准纳入每里程碑收尾必跑项；
7. 可选：真值库增补官方算例（plan/06"真值库构建方式"决策预留口子；新增真值须同步补对账用例，test_all_four_cases_covered 同步扩集）；
8. 零字面量门禁扫描面扩围评估：`src/incometax/benchmark/` 新包目前不在 `test_zero_policy_literals.SCAN_FILES`（engine/+cli.py）内，建议一并收编（宁严勿松）；
9. pytest 全绿且收集数 ≥122；plan/00、05、06 回写；落 HANDOFF-M5。

## 既定口径清单（M3 增补版，动了会打挂测试/基准，改动前先对照）

1. **退出码**：0=成功 / 1=运行期失败（门控拦截、计算失败）/ 2=用法输入错误——`tests/test_cli.py` 锁定；calc 缺 `--input`=2（门控先于输入校验）；**M3 增补：扣除申报违规（互斥/分摊/上限/未知项/重复）=2**（用户可修复的输入问题，plan/06）；
2. **门控覆盖面** = 含 `value` 键的数值条目 + 两张税率表逐行；sources[] 与 desc/ref_qd 说明节点不进门控；引擎入口（monthly/settlement/bonus 原语/compare/derive/deductions）内部再次调用 `effective_ruleset()`——新增引擎模块须同样挂；
3. **schema v1**：7 级相接、末级 `upper=null`、value 节点必有 `ref`、`housing_loan_vs_rent` 必须显式 `mutually_exclusive`、status 缺失按待核对；税率行 `ref`+`ref_qd` 双出处键；**M3 增补：serious_illness.claimable_stage.stage="settlement_only"**（desc 节点不进门控）；
4. **税率级距 = 上界闭区间**（"不超过X元"）：`find_bracket` 顺序查首个 `taxable ≤ upper`；综合所得税率表边界点税额连续（速算扣除数吸收）；
5. **Decimal 全链路 + 舍入口径**：JSON `parse_float=Decimal`，rate/金额字段为字符串；金额呈现/申报两位小数 ROUND_HALF_UP（`report.MONEY_QUANT`）；年终奖商数两位仅定档、税基全额；累计应纳税所得额不舍入；
6. **零政策字面量**：`tests/test_zero_policy_literals.py` 收编 8 份规则包数值扫 engine/+cli.py（≥100 整数+小数+原样税率串，词边界；<100 豁免）；**文档字符串与注释也扫**——M3 实际在 deductions.py 注释/cli.py 输出标题写过年度数字被门禁打回，写码勿带 5000/36000/年度这类数；
7. **规则包=冻结产物**：data/rules 禁手改，改需求走 `tools/gen_rulesets.py` 整目录重生成，位级守门测试随全量跑；M3 stage 标记即走此通道；
8. **年度口径**：2019-2026 共 **8** 份；婴幼儿照护自设立纳税年度（2022）起适用（2019-2021 六项，规则包无此键→申报违规）；年终奖文档链 164/42/30 按年度挂 `ref`；
9. **真值库语义**：expected 主期望 + also_expect 隐含中间量，按"全部非 pass 字段集"对账；**不许改真值凑引擎答案**；
10. **社保参数归属**：缴费基数上下限与费率全部用户输入，`social.py` 不接收 Ruleset；
11. **Python 3.8 兼容**：无 match、无 PEP604 运行期联合类型、`Path.write_text` 无 `newline` 参数（用 `open(..., newline="\n")`）；
12. **数据目录定位顺序**：显式 --data-dir > `INCOMETAX_DATA_DIR` > `sys._MEIPASS/data` > CWD 上溯——M5 打包时冻结；
13. **calc 输入 schema v1.1**：v1 基础上新增 `special_additional_claims`（数组，字段按 item 取用：children/share_ratio/kind/months/tier/only_child/monthly_amount/other_shared_amounts/self_paid_total/note；未知字段=2）；
14. **临界区间口径**：6 边界全产出（B* > b 才有区间）；**商数两位定档产生查表死区**——实际跳档点晚于级距边界（边界+若干分内仍落左级、税后不低于锚点），穷举/基准从实际跳档点起断言，恢复点 = 推导右端点 `money(B*)`；区间为开区间（端点不属陷阱）；
15. **择优口径**：A = 工资汇算税 + 奖金单独税；B = 并入后重跑汇算；已预缴不参与比较；|差| ≤ 0.01 并列；政策到期 A 不可用强制 B；
16. **claims 与月度输入叠加口径**：月度链 = Σ用户月度输入 + Σ预扣链 claim 月额×申报月数；汇算链 = 上述聚合 + Σsettlement_only claim 年额；`settlement.*` 显式覆盖仍为最高优先（覆盖时 claim 自动贡献被取代，README 注明勿在覆盖里重复填奖金）。

## 本机环境坑（全部实测）

- `py` 是 3.8.8（`python` 是商店占位符）；跑带中文输出的命令用 `py -X utf8`；
- 全程 `PYTHONDONTWRITEBYTECODE=1`（含 pip install），出怪错先清 `__pycache__`；
- pip 被注册表系统代理污染 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- 统一用 `py -m incometax` 或 `py -X utf8 -m incometax`（Scripts 不在 PATH）；
- Git Bash heredoc/重定向与 Windows Python 路径：一律用工作区相对路径；
- 查证通道实测：`fgk.chinatax.gov.cn/zcfgk/c1000XX/cXXXXXXX/content.html` curl 直抓可用；gov.cn 政策文件库检索 API `https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary_gw|_bm&q=<urlencode>&p=1&n=10&sort=score` 可用；flk/Bing/DDG 不可用（M4 若增补官方算例真值时用）；
- git 提交邮箱已设 GitHub noreply；**首提交 1481cc8 仍含个人 QQ 邮箱** → M6 env-filter 全历史改写（勿忘）；
- `.gitignore` 的 `*.spec` 通配会在 M5 吞掉 PyInstaller spec → 届时加 `!tools/*.spec` 例外。

## M4 DoD checklist

- [ ] `benchmark/` 四类基准（算例回归/税率临界/陷阱区间/互斥组合）一条命令跑全，零 API 依赖可复现
- [ ] 阈值全达标：算例 100%、税率临界自洽 100%、陷阱区间与穷举一致 100%、互斥误放行 0
- [ ] 指标写进 README 表格；基准纳入里程碑收尾必跑项
- [ ] 真值库 4 条回归仍 100%（不改真值）；门控/冻结/零字面量/真值四类守门测试全绿
- [ ] pytest 全绿且收集数 ≥122（只增不减），基线记入 HANDOFF-M5
- [ ] plan/00、05、06 回写 ✅；HANDOFF-M5 落盘

## 关键命令速查

```bash
# 安装（新环境/依赖变更后）
NO_PROXY="*" no_proxy="*" py -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（本机纪律：PYTHONDONTWRITEBYTECODE=1）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q

# 规则包预览（全年度 0 待核对）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax rules --year 2026

# calc（输入 schema 见 README「calc 输入格式」：月度/social/bonus/claims/settlement）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax calc --year 2024 --input <calc-input.json>

# 重新生成规则包（改 tools/gen_rulesets.py 后整目录重生成）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py

# git（提交前三核对：pwd / git log -1 / git remote -v）
git add -A && git commit -m "..."
```
