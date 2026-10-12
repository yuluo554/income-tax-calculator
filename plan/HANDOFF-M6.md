# HANDOFF-M6（跨会话交接快照）

> 用法：新会话启动提示词 `/goal 读取 "plan/HANDOFF-M6.md" 继续完成任务`（相对路径，从仓库根解析）。
> 快照日期：2026-10-07。M5（桌面交付）已完成，下一棒 = **M6 脱敏发布 GitHub + Release + 收尾固化**（任务清单见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §二 M6）。

## 当前进度（M5 末态）

- **GUI 包** `src/incometax/gui/` 共 9 模块：`app.py`（入口 + `--data-dir` / `--selftest` 参数）、`main_window.py`（免责首屏 → 主界面，`APP_TITLE="个人所得税联动计算器"`，四个功能页 + 年度下拉）、`input_panel.py`（逐月表 + 社保 + 年终奖 + 申报管理）、`claim_dialog.py`（七项申报编辑，按项目切字段页）、`results_panel.py`（社保/清单/逐月表/汇算/奖金择优 + 临界红字横幅）、`ref_panel.py`（来源图例 + 本次依据清单，复用 `report.render_ref`）、`benchmark_panel.py`（复用 `run_all()`）、`selftest.py`（冻结态自检）、`__main__.py`。**GUI 只消费引擎 API，零政策数值字面量**（门禁 SCAN_FILES 已收编 gui/）；
- **编排上收**：`engine/pipeline.py`（`compute_full_calc` + `CalcRequest`/`CalcResult`）自 `cli.cmd_calc` 上收，CLI 与 GUI 共用同一编排（CLI 行为不变，129 项迁移前全绿）；`deductions.ITEM_LABELS` 上收展示名；
- **offscreen 测试常驻**：`tests/conftest.py` 顶部设 `QT_QPA_PLATFORM=offscreen`（先于任何 PySide6 导入）；`tests/test_gui.py` **20 项**；模态框经 `MainWindow._show_error/_show_info` monkeypatch 屏蔽；
- **打包**：`tools/incometax.spec`（入仓，`.gitignore` 已加 `!tools/*.spec` 例外）+ `tools/build_package.py`（PyInstaller 5.13.2，onedir **平铺布局**，产物 `dist/个人所得税联动计算器/`）。构建后断言三连：dist 无禁区成分（无 `.py`/缓存/测试/plan）、内嵌 `data/rules` 与 `data/truth` 逐文件 sha256 与仓库对账、PySide6 就位且无被排除重依赖（numpy/pandas/matplotlib/scipy）；
- **冻结态验收**：`tools/verify_package.py` 在**临时中立目录**调用 `exe --selftest <输入> <输出>`（exe 窗口程序无控制台，结论经文本文件回传），实测：内嵌数据定位（断言路径落 dist 内、非仓库 data/）+ calc 全链路 + 1184 项基准全达标 + GUI offscreen 冒烟，退出码 0；
- **技术报告** `docs/技术报告.md`（版本化规则集 / 临界区间推导 / 依据联动三主题，含 6 边界陷阱区间表与实测指标）；
- **演示素材** `docs/demo/`：5 张 PNG（免责首屏/计算输入/结果与临界标红/依据面板/内置基准）+ `演示.gif`（`tools/make_demo_assets.py` offscreen 渲染；offscreen 无字体需显式注册系统中文体 Microsoft YaHei）；
- **CI** `.github/workflows/ci.yml`：extras 改 `[dev,gui]` + `QT_QPA_PLATFORM=offscreen` + 增跑 `python -m incometax benchmark`；
- **版本**：0.4.0 → **0.5.0**（pyproject + `__init__`）；
- **测试**：pytest 收集基线 **149**（M4 为 129，只增不减）——M5 新增 `tests/test_gui.py` 20 项（含 selftest 端到端、篡改年度切换、临界标红、违规整单拒绝、社保联动入表、基准页、申报对话框 build_claim）；
- **实测指标**：benchmark 1184 项全达标（算例 4/4、税率临界 752/752、陷阱 6/6、互斥 190 拒 + 122 放行）；真值 4 条未动 100%。

## M6 待办（按序）

1. **干净环境验证**：新目录 clone + 全新 venv 按 README 逐条一次跑通（含 `[dev,gui]` 装 PySide6、GUI 启动、benchmark、打包）；pytest 收集数与 dev 一致（**149**）；
2. **脱敏审计**：仓库无个人隐私/密钥/内部路径（四步扫描）+ 构建产物扫描 + **提交元数据邮箱**——首提交 1481cc8 仍含个人 QQ 邮箱，用 `git filter-repo`/`git-filter-branch` env-filter 全历史改写为 GitHub noreply（`282769740+yuluo554@users.noreply.github.com`），改写后三扫全 0（`git log --format=%ae` / `%ce` 无 QQ 邮箱）；
3. **建仓**：`gh repo create`（不带 `--push`）→ SSH push；token 无 workflow scope 的实录路径（计划文档已记）；**CI 首跑绿**（push 数 = run 数对账），确认 windows 3.8/3.12 + ubuntu 3.12 全过（3.8 在 ubuntu 支持存疑，按实况调整矩阵）；
4. **Release**：附 `dist/个人所得税联动计算器/` 打成的 zip（**M5 决策 #3 定稿 = 裸 zip + RELEASE 说明，不用 Inno Setup**）+ 演示 GIF；README 状态行转正（去"开发中"）；设置 repo topics；
5. **收尾固化**：plan 全量回写（00/05/06 M6 勾选 + 待定决策 #1 仓库名、#4 投稿清零）；缓议项清零。

## 既定口径清单（M5 增补版，动了会打挂测试/基准，改动前先对照）

1. **退出码**（CLI 冻结）：0=成功 / 1=运行期失败（门控拦截、计算失败、基准未达标）/ 2=用法输入错误（含扣除申报违规）——`tests/test_cli.py` + `tests/test_benchmark.py` 锁定；
2. **门控覆盖面** = 含 `value` 键的数值条目 + 两张税率表逐行；引擎入口（monthly/settlement/bonus 原语/compare/derive/deductions/**pipeline 内各调用**）内部再次调 `effective_ruleset()`——新增引擎模块须同样挂；基准内门控拦截原样上抛（rc 1）；
3. **schema v1**：7 级相接、末级 `upper=null`、value 节点必有 `ref`、`housing_loan_vs_rent` 必须显式 `mutually_exclusive`、status 缺失按待核对；税率行 `ref`+`ref_qd` 双出处键；`serious_illness.claimable_stage.stage="settlement_only"`（desc 节点不进门控）；
4. **税率级距 = 上界闭区间**：`find_bracket` 顺序查首个 `taxable ≤ upper`；综合所得税率表边界点税额连续（速算扣除数吸收）；
5. **Decimal 全链路 + 舍入口径**：JSON `parse_float=Decimal`；金额呈现/申报两位小数 ROUND_HALF_UP（`report.MONEY_QUANT`）；年终奖商数两位仅定档、税基全额；累计应纳税所得额不舍入；**GUI 金额输入一律 QLineEdit + Decimal 解析**（不用浮点控件）；
6. **零政策字面量**：`tests/test_zero_policy_literals.py` 收编 8 份规则包全部数值扫 **engine/ + benchmark/ + gui/ + cli.py**（≥100 整数+小数+原样税率串，词边界；<100 豁免）；**文档字符串与注释也扫，且年度数字 2019-2026 也是禁用 token**；
7. **规则包=冻结产物**：data/rules 禁手改，改需求走 `tools/gen_rulesets.py` 整目录重生成，位级守门测试随全量跑；
8. **年度口径**：2019-2026 共 **8** 份；婴幼儿照护自 2022 纳税年度起适用（2019-2021 六项）；年终奖文档链 164/42/30 按年度挂 `ref`；
9. **真值库语义**：expected 主期望 + also_expect 隐含中间量，按"全部非 pass 字段集"对账；**不许改真值凑引擎答案**；对账语义单一源 = `benchmark/cases.py`；
10. **社保参数归属**：缴费基数上下限与费率全部用户输入，`social.py` 不接收 Ruleset；
11. **Python 3.8 兼容**：无 match、无 PEP604 运行期联合类型、`Path.write_text` 无 `newline` 参数（用 `open(..., newline="\n")`）；**PySide6 `<6.7`（3.8 上限）、PyInstaller 5.13.2（3.8 pin，6.x 有 modulegraph dis 崩溃实录）**；
12. **数据目录定位顺序**：显式 --data-dir > `INCOMETAX_DATA_DIR` > `sys._MEIPASS/data` > CWD 上溯——M5 已冻结，打包后内嵌数据只读不再动；
13. **calc 输入 schema v1.1**：months/uniform_month + social + bonus_income + special_additional_claims + settlement 覆盖；未知字段=2；**GUI 同 schema 语义**（空单元格=0、社保四项全填或全空）；
14. **临界区间口径**：6 边界全产出；商数两位定档死区宽 = 月份数 × 申报精度半分；区间为开区间；恢复点 = `money(B*)`；第 3/5 档实测恢复点仍属精确开区间（基准按相对位置推导归属，引擎语义不改）；
15. **择优口径**：A = 工资汇算税 + 奖金单独税；B = 并入后重跑汇算；已预缴不参与比较；|差| ≤ 0.01 并列；政策到期 A 不可用强制 B；
16. **claims 与月度输入叠加口径**：月度链 = Σ用户月度输入 + Σ预扣链 claim 月额×申报月数；汇算链 = 上述聚合 + Σsettlement_only claim 年额；`settlement.*` 显式覆盖最高优先；
17. **基准命令/API**：`incometax benchmark [--year]`；`run_all(data_dir=None, focus_year=None)` = CLI 与 GUI 共用；四类 runner 顺序 cases→rates→traps→mutex；真值文件缺失 = 用法错误 2；
18. **基准阈值（M5 复跑快照）**：算例 4/4、税率临界 752/752（96 边界）、陷阱穷举一致 6/6、互斥误放行 0 误拒 0（190 违规/122 有效）——合计 **1184 项**；指标快照记 README「内置评测基准」节与 docs/技术报告；**每里程碑收尾必跑**；
19. **GUI 编排单一源（M5）**：GUI 与 CLI 都经 `engine.pipeline.compute_full_calc`，**禁止 GUI 层自算政策数值**——新功能加在引擎/编排层，前端只渲染 Report；
20. **打包纪律（M5）**：`.gitignore` 有 `!tools/*.spec` 例外（spec 入仓）；构建后断言不过即判构建失败；`dist/`、`build/` 均被忽略不入仓；发布产物在中立目录实测通过才算 DoD（`tools/verify_package.py`）。

## 本机环境坑（全部实测）

- `py` 是 3.8.8（`python` 是商店占位符）；跑带中文输出的命令用 `py -X utf8`；
- 全程 `PYTHONDONTWRITEBYTECODE=1`（含 pip install），出怪错先清 `__pycache__`；
- pip 被注册表系统代理污染 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`；
- 统一用 `py -m incometax` 或 `py -X utf8 -m incometax`（Scripts 不在 PATH）；GUI 用 `py -m incometax.gui`；
- **GUI 测试**：必须 `QT_QPA_PLATFORM=offscreen`（conftest 已兜底）；顶层窗口未 show 时 `isVisible()` 恒 False → 断言用 `isHidden()`/文本；
- **offscreen 截图无字体** → 渲染成方框；`tools/make_demo_assets.py` 已注册 Microsoft YaHei（`C:\Windows\Fonts\msyh.ttc`）；
- **PyInstaller**：5.13.2 在 3.8 实测可用，onedir 为**平铺布局**（6.x 才有 `_internal/`）；打包耗时约 15 秒（本机）；exe 为窗口程序（`console=False`）无控制台输出 → 自检结论走文件回传；
- pytest 全量约 55-65 秒（含 GUI 20 项）、benchmark 全量不足 1 秒（收尾两项都跑）；
- M5 装 PySide6 后未出怪错；若出（V8 unreachable/SystemError），先清 `__pycache__` 并降级 PySide6 到 6.4.x 实测（crash-loop-rescue 技能有自救纪律）；
- Git Bash heredoc/重定向与 Windows Python 路径：一律用工作区相对路径；
- **git 提交邮箱已设 GitHub noreply；首提交 1481cc8 仍含个人 QQ 邮箱 → M6 全历史 env-filter 改写（勿忘）**。

## M6 DoD checklist

- [ ] 干净环境：新目录 clone + 全新 venv 按 README 逐条一次跑通；pytest 收集数 = 149
- [ ] 脱敏审计：源码/构建产物/提交元数据三扫全 0（QQ 邮箱经 env-filter 全历史改写）
- [ ] 建仓 + CI 首跑绿（push 数 = run 数）
- [ ] Release：exe（裸 zip）+ 演示 GIF；README 状态行转正；topics
- [ ] DoD：GitHub 公开可访问、CI 绿、release 就位、plan 全量回写（含待定决策 #1/#4 清零）

## 关键命令速查

```bash
# 安装（新环境/依赖变更后）
NO_PROXY="*" no_proxy="*" py -m pip install -e ".[dev,gui]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试 + 基准（本机纪律：PYTHONDONTWRITEBYTECODE=1；每里程碑收尾两项必跑）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax benchmark

# GUI（开发态）
PYTHONDONTWRITEBYTECODE=1 py -m incometax.gui

# 打包 + 冻结态验收（M5 交付物）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/build_package.py --clean-build
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/verify_package.py

# 重新生成规则包（改 tools/gen_rulesets.py 后整目录重生成）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py

# 演示素材重生成
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/make_demo_assets.py

# git（提交前三核对：pwd / git log -1 / git remote -v）
git add -A && git commit -m "..."
```
