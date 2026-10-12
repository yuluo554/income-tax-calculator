# HANDOFF-FINAL（项目完结快照）

> 项目：个人所得税联动计算器（系列第 12 题，个人财税工具）。M0-M6 全部完成并已公开发布。
> 快照日期：2026-10-12。发布留档（过程实录/瑕疵）见 [RELEASE-M6.md](RELEASE-M6.md)。

## 一、末态基线

| 项 | 值 |
|---|---|
| 版本 | **0.5.0**（pyproject + `incometax.__version__`） |
| 发布物基线 | tag `v0.5.0`；`src/` 与重建产物同基线（`git diff b0f066b..HEAD -- src/` 为空） |
| 测试 | pytest **157** 项全绿（收集数 dev = 干净 clone = 157） |
| 基准 | **1184** 项检查全达标（算例 4/4、税率临界 752/752、陷阱 6/6、互斥 190 拒 + 122 放行） |
| 数据 | 8 份年度规则包（2019-2026，逐字节冻结）；真值库 4 条 |
| 公开仓 | https://github.com/yuluo554/income-tax-calculator （PUBLIC / MIT / topics 8） |
| Release | https://github.com/yuluo554/income-tax-calculator/releases/tag/v0.5.0 |
| 发布附件 | `income-tax-calculator-v0.5.0-win64.zip`（41,272,855 B；sha256 `3b34f338…8136`）+ `.sha256` + `income-tax-calculator-demo.gif` |
| CI | 三作业（windows 3.8 / windows 3.12 / ubuntu 3.12）全绿；push 数 = run 数 |

## 二、发布执行记录（要点）

1. **脱敏**：首提交 QQ 邮箱经 `git filter-branch --env-filter` 全历史改写为 GitHub noreply（仓外 bundle 备份）；
   审计器 `tools/desensitize_audit.py` 入仓，tracked/history/messages/dist 四扫 0 硬门（守门测试 7 项常驻）。
2. **干净环境**：新目录 clone + 全新 venv 按 README 逐条跑通（含 `[dev,gui]`、GUI、benchmark、`[pkg]` 打包、中立目录冻结态验收）。
3. **建仓**：`gh repo create`（不带 `--push`）→ SSH push。
4. **CI 首跑抓出两处真实环境差异并修复**：Windows 管道 cp1252 编码（→ `cli._ensure_utf8_stdio`）、
   ubuntu 缺 `libEGL.so.1`（→ CI 装 Qt 系统库）；第二轮起全绿。
5. **Release**：annotated tag `v0.5.0` + `gh release create`（附件改 **ASCII 名**，避免 gh/Git Bash 剥中文）。
6. **发布后复核**：远端全新 clone 复验 + **下载产物冻结态自检**（sha256 与留档一致、退出码 0）。

## 三、复跑手册（末态自检，按序）

```bash
# 1) 测试 + 基准（每里程碑收尾两项必跑）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q                     # 期望 157 passed
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax benchmark   # 期望 1184 项全达标

# 2) 脱敏审计（发布门常驻闸门，四扫）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --selftest   # 阳性/阴性对照
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/desensitize_audit.py --mode all   # 期望 DESSENSITIZE_AUDIT_OK

# 3) 打包 + 冻结态验收
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/build_package.py --clean-build
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/verify_package.py

# 4) 发布物复核（下载远端 zip 后）
#    解压 → 运行 个人所得税联动计算器.exe --selftest <输入JSON> <结论txt>，期望退出码 0 且「自检结论：通过」

# 5) 脱敏历史终验（固定字面值为空即达标）
git log --all --format="%ae|%ce" | sort -u      # 期望唯一 GitHub noreply
```

## 四、遗留项与边界（诚实记录）

- **范围边界**：仅工资薪金 + 全年一次性奖金 + 年度汇算简化口径；经营所得、股权激励、财产租赁转让不在范围内；不对接税务接口。
- **政策时效**：规则包快照核对至 2026-10-07；2026 年度之后若有新政策需经 `tools/gen_rulesets.py` 重新核对入库（status 门控会把未核对条目挡在引擎外）。
- **未做事项**：不投稿 awesome/社区清单（决策 #4，已定稿）；不引入安装器（裸 zip，决策 #3）。
- **已知环境问题**：见 README「已知环境问题」节（PyInstaller onedir 目录完整性、3.8 版本上限、`py` 启动器绕 venv、CI offscreen）。
- **CI 门禁提示**：`actions/checkout` 必须保持 `fetch-depth: 0`（历史脱敏扫描依赖完整历史），守门测试 `test_ci_checkout_fetches_full_history` 会拦。
- **审计器自命中纪律**：新增文档/代码若写入路径形式字面值（本机用户名/工作根），会被 tracked 扫描硬拦——属**预期行为**，改占位符即可，勿放宽扫描器。

## 五、关键约定（改动前必读）

见 [HANDOFF-M6.md](HANDOFF-M6.md) 的「既定口径清单（20 条）」——退出码、门控覆盖面、schema v1、税率级距上界闭、
Decimal 全链路、零政策字面量、规则包冻结、年度口径、真值库语义、社保参数归属、3.8 兼容、数据目录定位、
calc schema、临界区间、择优口径、claims 叠加、基准命令/API、基准阈值、GUI 编排单一源、打包纪律。
**改任何一条都会打挂测试/基准，改动前先对照。**
