# HANDOFF-M5（跨会话交接快照）

> 用法：新会话启动提示词 `/goal 读取 "plan/HANDOFF-M5.md" 继续完成任务`（相对路径，从仓库根解析）。
> 快照日期：2026-10-07。M4（边界扫描基准定稿）已完成，下一棒 = **M5 桌面交付**（PySide6 GUI + PyInstaller 打包 + 技术报告，任务清单见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §二 M5，选型见 [03-架构与技术选型.md](03-架构与技术选型.md)）。

## 当前进度（M4 末态）

- **benchmark 包**：`src/incometax/benchmark/` 共 8 模块（runner 编排 + metrics 数据类 + checks 公共断言 + 四类 runner）——`cases.py` 算例回归（flatten+键集对账语义自 tests **上收至此**，测试与基准共用同一实现；真值跨算例字段 `extra_tax_vs_bonus_<基数>` 由字段名内嵌基数动态计算，零字面量）、`rates.py` 税率级次临界（两表逐有限上界 ±0.01 精确邻域：级次切换、年度表税额连续、年终奖年口径跳变、汇算/单独计税引擎通路含商数定档死区）、`traps.py` 陷阱区间（死区逐分 + 端点内外 ±0.01 + 粗细两段穷举）、`mutex.py` 扣除互斥组合（互斥全档位/上限边界/重复/非法字段/年度适用 + 有效对照，期望放行与否全由规则包结构推导）；
- **CLI `benchmark` 子命令**：`incometax benchmark [--year YYYY]`（`--year` = 穷举深扫代表年度，缺省最新可用年度）；退出码 0 达标 / 1 未达标或门控拦截 / 2 用法错误（含数据目录/真值库缺失）；输出指标表 + 失败明细；GUI M5 复用 `run_all(data_dir, focus_year)` 同一 API；
- **实测指标（v0.4.0，全达标）**：算例 4/4；税率临界 752/752（8 年度 × 2 表 96 边界）；陷阱穷举一致 6/6（恢复点 = money(B*)）；互斥 190 违规全拒绝（误放行 0）+ 122 有效全放行（误拒 0）；合计 1184 项检查，单次运行不足 1 秒（独立公式通路纯 Decimal 循环，粗扫 1 元步长 + 恢复窗口逐分细扫——全逐分穷举约两千七百万步不可行，净额逐分非降由量化算术保证，见 plan/06 M4 决策行）；
- **守门扩围**：零字面量门禁 SCAN_FILES 收编 benchmark/ 全部 8 模块（`test_zero_policy_literals.py`，文档串与注释同扫）；**年度数字 2019-2026 本身也是规则包 token**，benchmark 源码一律不写年份数字；
- **顺带修正**：cli.py 既有 latent bug——except 子句引用 `loader.RulesetSchemaError`（该类在 `rules.schema`），schema 非法路径会 AttributeError，已改从 schema 导入（`_load_or_usage_error` 与 cmd_benchmark 两处）；
- **版本**：0.2.0 → **0.4.0**（pyproject + `__init__`，M3 曾漏升）；
- **测试**：pytest 收集基线 **129**（M3 为 122，只增不减）：M4 新增 tests/test_benchmark.py 6 项（run_all 全阈值 + focus_year 校验 + CLI 成功/未知年度 2/阈值未达标 1/门控拦截 1/缺真值库 2）；真值 4 条对账 100% 未动（test_truth_reconciliation 改从 benchmark.cases 导入 flatten，语义不变）；CLI calc 全部既有测试未动。

## M5 待办（按序）

1. `pyproject.toml` 的 `gui` extras 安装（PySide6 `>=6.4,<6.7`，3.8 兼容上限实测约束）；GUI 包骨架 `src/incometax/gui/`，**只消费引擎 API 与 `run_all()`**（禁止 GUI 层自算政策数值，零字面量门禁可顺带收编 gui/）；
2. GUI 功能面（plan/05 M5 清单）：年度切换、逐月表、年终奖择优对比 + 临界区间标红、扣除申报管理（违规整单拒绝提示）、依据面板（ref → 文号+条款渲染，复用 `report.render_ref`）、免责声明首屏；应用显示名定稿（plan/06 待定决策 #2）；
3. offscreen 测试常驻：`QT_QPA_PLATFORM=offscreen` 必须在**首次导入 PySide6 之前**设置（tests/conftest.py 顶部）；模态对话框 monkeypatch 屏蔽；
4. PyInstaller onedir 打包（`pkg` extras）：**先给 `.gitignore` 加 `!tools/*.spec` 例外**（现有 `*.spec` 通配会吞 spec 文件）；数据内嵌走 `sys._MEIPASS/data`（数据目录定位顺序见口径 12，打包后冻结不再动）；构建后断言（dist 无禁区成分、内嵌规则包/真值与仓库对账）；exe 附安装器与否定稿（plan/06 待定决策 #3）；
5. 技术报告 `docs/技术报告.md`：版本化规则集设计 / 临界区间机制推导 / 依据联动三主题；
6. 演示 GIF/截图产出；exe 在中立目录可用实测；
7. pytest 全绿且收集数 ≥129；基准 `incometax benchmark` 全达标复跑；plan/00、05、06 回写；落 HANDOFF-M6。

## 既定口径清单（M4 增补版，动了会打挂测试/基准，改动前先对照）

1. **退出码**：0=成功 / 1=运行期失败（门控拦截、计算失败、基准未达标）/ 2=用法输入错误（含扣除申报违规）——`tests/test_cli.py` + `tests/test_benchmark.py` 锁定；calc/benchmark 缺参=2（门控先于输入校验）；
2. **门控覆盖面** = 含 `value` 键的数值条目 + 两张税率表逐行；sources[] 与 desc/ref_qd 说明节点不进门控；引擎入口（monthly/settlement/bonus 原语/compare/derive/deductions）内部再次调用 `effective_ruleset()`——新增引擎模块须同样挂；基准内门控拦截原样上抛（rc 1）；
3. **schema v1**：7 级相接、末级 `upper=null`、value 节点必有 `ref`、`housing_loan_vs_rent` 必须显式 `mutually_exclusive`、status 缺失按待核对；税率行 `ref`+`ref_qd` 双出处键；serious_illness.claimable_stage.stage="settlement_only"（desc 节点不进门控）；
4. **税率级距 = 上界闭区间**（"不超过X元"）：`find_bracket` 顺序查首个 `taxable ≤ upper`；综合所得税率表边界点税额连续（速算扣除数吸收）；
5. **Decimal 全链路 + 舍入口径**：JSON `parse_float=Decimal`，rate/金额字段为字符串；金额呈现/申报两位小数 ROUND_HALF_UP（`report.MONEY_QUANT`）；年终奖商数两位仅定档、税基全额；累计应纳税所得额不舍入；
6. **零政策字面量**：`tests/test_zero_policy_literals.py` 收编 8 份规则包全部数值扫 **engine/ + benchmark/ + cli.py**（≥100 整数+小数+原样税率串，词边界；<100 豁免）；**文档字符串与注释也扫，且年度数字 2019-2026 也是禁用 token**——写码勿带 5000/36000/15000/240/年份等任何规则包数值；
7. **规则包=冻结产物**：data/rules 禁手改，改需求走 `tools/gen_rulesets.py` 整目录重生成，位级守门测试随全量跑；
8. **年度口径**：2019-2026 共 **8** 份；婴幼儿照护自 2022 纳税年度起适用（2019-2021 六项）；年终奖文档链 164/42/30 按年度挂 `ref`；
9. **真值库语义**：expected 主期望 + also_expect 隐含中间量，按"全部非 pass 字段集"对账；**不许改真值凑引擎答案**；对账语义（flatten/键集）单一源 = `benchmark/cases.py`；
10. **社保参数归属**：缴费基数上下限与费率全部用户输入，`social.py` 不接收 Ruleset；
11. **Python 3.8 兼容**：无 match、无 PEP604 运行期联合类型、`Path.write_text` 无 `newline` 参数（用 `open(..., newline="\n")`）；
12. **数据目录定位顺序**：显式 --data-dir > `INCOMETAX_DATA_DIR` > `sys._MEIPASS/data` > CWD 上溯——M5 打包时冻结；
13. **calc 输入 schema v1.1**：months/uniform_month + social + bonus_income + special_additional_claims + settlement 覆盖；未知字段=2；
14. **临界区间口径**：6 边界全产出；商数两位定档死区宽 = 月份数 × 申报精度半分；穷举/基准从实际跳档点起断言，恢复点 = 推导右端点申报精度值 `money(B*)`；区间为开区间（精确端点不属陷阱；**money(B*) 向下取整的档位其申报精度恢复点仍属精确开区间**——第 3/5 档实测，基准按相对位置推导归属，引擎语义不改）；
15. **择优口径**：A = 工资汇算税 + 奖金单独税；B = 并入后重跑汇算；已预缴不参与比较；|差| ≤ 0.01 并列；政策到期 A 不可用强制 B；
16. **claims 与月度输入叠加口径**：月度链 = Σ用户月度输入 + Σ预扣链 claim 月额×申报月数；汇算链 = 上述聚合 + Σsettlement_only claim 年额；`settlement.*` 显式覆盖仍为最高优先；
17. **基准命令/API（M4）**：`incometax benchmark [--year]`；`run_all(data_dir=None, focus_year=None)` = CLI 与 GUI 共用；四类 runner 顺序 cases→rates→traps→mutex；真值文件缺失 = 用法错误 2；
18. **基准阈值（M4 实测快照）**：算例 4/4、税率临界 752/752（96 边界）、陷阱穷举一致 6/6、互斥误放行 0 误拒 0（190 违规/122 有效）——合计 1184 项；指标快照记 README「内置评测基准」节；**每里程碑收尾必跑**；
19. **陷阱穷举实现（M4）**：粗扫全区间（1 元步长、采样断言净额非降）+ 恢复窗口逐分细扫——净额逐分非降由量化算术保证（money 对 B 单调、每分原始增量小于半分）；穷举走独立公式通路（`_local_net`）与引擎双向对账；
20. **互斥组合期望值推导（M4）**：全部标准值取自当年规则包（per_child_cap/total_cap/threshold/max_months/tiers 数量），期望放行与否由规则包结构推导（如 infant_care 键是否存在、months 是否超包内期限）——组合矩阵零政策字面量，年度数变化自动跟随。

## 本机环境坑（全部实测）

- `py` 是 3.8.8（`python` 是商店占位符）；跑带中文输出的命令用 `py -X utf8`；
- 全程 `PYTHONDONTWRITEBYTECODE=1`（含 pip install），出怪错先清 `__pycache__`；
- pip 被注册表系统代理污染 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- 统一用 `py -m incometax` 或 `py -X utf8 -m incometax`（Scripts 不在 PATH）；
- Git Bash heredoc/重定向与 Windows Python 路径：一律用工作区相对路径；
- pytest 全量约 45-50 秒、benchmark 全量不足 1 秒（收尾两项都跑）；
- M5 装 PySide6 后若出怪错（V8 unreachable/SystemError），先清 `__pycache__` 并降级 PySide6 到 6.4.x 实测（crash-loop-rescue 技能有自救纪律）；
- 查证通道实测：`fgk.chinatax.gov.cn/zcfgk/c1000XX/cXXXXXXX/content.html` curl 直抓可用；gov.cn 政策文件库检索 API 可用；flk/Bing/DDG 不可用；
- git 提交邮箱已设 GitHub noreply；**首提交 1481cc8 仍含个人 QQ 邮箱** → M6 env-filter 全历史改写（勿忘）；
- `.gitignore` 的 `*.spec` 通配会在 M5 吞掉 PyInstaller spec → **打包前先加 `!tools/*.spec` 例外**。

## M5 DoD checklist

- [ ] GUI：年度切换/逐月表/择优对比+临界标红/扣除管理/依据面板/免责声明首屏，只消费引擎 API 与 `run_all()`
- [ ] offscreen 测试常驻（QT_QPA_PLATFORM 在首次导入 PySide6 前设置；模态对话框 monkeypatch 屏蔽）
- [ ] PyInstaller 打包 + 构建后断言（dist 无禁区成分、内嵌数据对账）；`.gitignore` 已加 `!tools/*.spec`
- [ ] 技术报告 docs/技术报告.md（版本化设计/临界推导/依据联动三主题）
- [ ] DoD：exe 在中立目录可用；GUI 测试全绿；演示 GIF/截图产出
- [ ] `incometax benchmark` 复跑全达标（1184 项）；真值库 4 条回归仍 100%（不改真值）
- [ ] pytest 全绿且收集数 ≥129（只增不减），基线记入 HANDOFF-M6
- [ ] plan/00、05、06 回写 ✅；HANDOFF-M6 落盘

## 关键命令速查

```bash
# 安装（新环境/依赖变更后）
NO_PROXY="*" no_proxy="*" py -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试 + 基准（本机纪律：PYTHONDONTWRITEBYTECODE=1；每里程碑收尾两项必跑）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax benchmark

# 规则包预览（全年度 0 待核对）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax rules --year 2026

# calc（输入 schema 见 README「calc 输入格式」：月度/social/bonus/claims/settlement）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax calc --year 2024 --input <calc-input.json>

# 重新生成规则包（改 tools/gen_rulesets.py 后整目录重生成）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py

# git（提交前三核对：pwd / git log -1 / git remote -v）
git add -A && git commit -m "..."
```
