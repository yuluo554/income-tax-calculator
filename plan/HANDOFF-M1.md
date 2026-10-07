# HANDOFF-M1（跨会话交接快照）

> **【已过时，仅作历史】M1 已于 2026-10-07 收尾，续接请读 [HANDOFF-M2.md](HANDOFF-M2.md)。**
> 用法：新会话启动提示词 `/goal 读取 "plan/HANDOFF-M1.md" 继续完成任务`（相对路径，从仓库根解析）。
> 快照日期：2026-10-07。M0（计划+骨架）已完成，下一棒 = **M1 数据先行与规则包定稿**（任务清单见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §二 M1）。

## 当前进度（M0 末态）

- 计划文档 00-06 全部定稿；可运行骨架已提交：
  - `src/incometax/rules/`：schema 校验 + status 门控加载器（**真实实现**，非桩）；
  - `src/incometax/engine/`：5 个引擎模块为文档化桩（NotImplementedError，签名与设计引用就位）；
  - `data/rules/ruleset-2022.json` + `ruleset-2026.json`：骨架示例规则包（7 级税率表×2、七项扣除结构，逐条挂 ref+status）；
  - CLI（`rules` 命令可用，`calc` 为桩）、28 项 pytest 全绿、CI workflow 就位（尚未推远端，未验证）。
- pytest 收集数基线：**28**（后续里程碑收尾对比，防静默少跑）。
- CLI 五连实测退出码：`rules --year 2026`=0；`rules --year 1999`=2；`calc --year 2026`=1（门控拦截）；`--version`=0。

## M1 待办（按序）

1. 查证入库（官方原文直抓，逐字核对，摘要工具不采信）：
   - 个税法税率表一（综合所得）→ 翻转 `rate_tables.comprehensive_annual`；
   - 财税〔2018〕164 号附件 1 → 翻转 `rate_tables.monthly_converted` 与 `bonus.monthly_divisor`；
   - 国发〔2018〕41 号条款数值（七项标准/互斥/分摊）→ 翻转 special_deductions 各待核对节点；
   - 2023 提标通知**文号**（当前 S2023 标待核对）、2022 婴幼儿照护通知**文号**（S22）；
   - 确认婴幼儿照护溯及口径（2022 设立，覆盖哪些纳税年度）。
2. `tools/gen_rulesets.py`：单模板参数化生成 2019-2026 共 9 份规则包（固定输入可复现；年度差异点见 plan/05 §1.1 表）。
3. `data/truth/` 算例真值库 ≥3 条（61 号公告算例优先），逐条登记来源 URL 进 data/README.md。
4. 台账与年份覆盖表回写；`rules --year` 全年度 0 待核对。

## 既定口径清单（动了会打挂测试/基准，改动前先对照）

1. **退出码**：0=成功 / 1=运行期失败（含未实装、门控拦截）/ 2=用法输入错误——`tests/test_cli.py` 锁定；
2. **门控覆盖面** = 含 `value` 键的数值条目 + 两张税率表逐行；sources[] 与 desc 说明节点不进门控（信息展示）——改覆盖面必须同步改 `status_report` 及其测试；
3. **schema v1**：7 级相接、末级 `upper=null`、value 节点必有 `ref`、`housing_loan_vs_rent` 必须显式 `mutually_exclusive`、status 缺失按待核对；
4. **Decimal 全链路**：JSON `parse_float=Decimal`，rate 字段为字符串；引擎代码零政策数值字面量（含临界区间端点）；
5. **税率表跨年一致**：`test_rate_tables_identical_across_years` 断言 2022==2026——若发现某年度税率有变，需重构该测试为分年基线；
6. **规则包年度覆盖** 2019-2026 共 9 份，文件名 `ruleset-YYYY.json`（loader 按此解析年度）；
7. **Python 3.8 兼容**：无 match、无 PEP604 运行期联合类型、无 3.9+ API（`removeprefix` 已踩过一次，用切片）；
8. **数据目录定位顺序**：显式 --data-dir > 环境变量 `INCOMETAX_DATA_DIR` > `sys._MEIPASS/data`（PyInstaller）> CWD 上溯——M5 打包时冻结，改优先级需同步分支测试。

## 本机环境坑（全部实测）

- `py` 是 3.8.8（`python` 是商店占位符）；跑带中文输出的命令用 `py -X utf8`；
- 全程 `PYTHONDONTWRITEBYTECODE=1`（含 pip install），出怪错先清 `__pycache__`；
- pip 被注册表系统代理污染 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`（本次实测可用）；
- `incometax.exe` 装到 `...\Python38\Scripts`（不在 PATH）→ 统一用 `py -m incometax` 或 `py -X utf8 -m incometax`；
- **git 提交邮箱**：本仓库已设 `git config user.email` = GitHub noreply（282769740+yuluo554@users.noreply.github.com）；**首提交 1481cc8 仍含个人 QQ 邮箱** → M6 发布前 env-filter 全历史改写（勿忘）；
- `.gitignore` 的 `*.spec` 通配会在 M5 吞掉 PyInstaller spec → 届时加 `!tools/*.spec` 例外。

## M1 DoD checklist（M1 收尾回写，2026-10-07）

- [x] 规则包全部生成且 schema 测试通过（含跨年税率一致）——**偏差说明：原计划"9 份"系笔误，2019-2026 实为 8 个纳税年度**，覆盖面以全年度为准（plan/06 已留痕）
- [x] `rules --year YYYY`（2019-2026 全部）显示 0 条待核对（实测 rc=0）
- [x] 门控放行路径测试翻转成立（`test_gate_opens_when_all_verified` 用真实规则包验证）
- [x] 算例真值库 4 条（≥3 达标）、逐条挂来源 URL，schema 测试通过——偏差说明：61 号公告正文/解读经原文核对无数值算例，真值以"已核对官方文件数值+手工推导"构建（已查渠道记 data/README.md §三）
- [x] data/README.md 台账 + data/rules/README.md 年份覆盖表回写
- [x] 全量 pytest 全绿且收集数 39 ≥ 28（新增测试只增不减）；plan/00、05、06 状态回写

## 关键命令速查

```bash
# 安装（新环境/依赖变更后）
NO_PROXY="*" no_proxy="*" py -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（本机纪律：PYTHONDONTWRITEBYTECODE=1）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q

# 规则包预览（2026 示例；M1 后全年度应显示 0 待核对）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax rules --year 2026

# git（提交前三核对：pwd / git log -1 / git remote -v）
git add -A && git commit -m "..."
```
