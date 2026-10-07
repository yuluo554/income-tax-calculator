# HANDOFF-M2（跨会话交接快照）

> 用法：新会话启动提示词 `/goal 读取 "plan/HANDOFF-M2.md" 继续完成任务`（相对路径，从仓库根解析）。
> 快照日期：2026-10-07。M1（数据先行与规则包定稿）已完成，下一棒 = **M2 计算引擎**（任务清单见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §二 M2）。

## 当前进度（M1 末态）

- **规则包定稿**：`data/rules/ruleset-2019..2026.json` 共 **8 份**（M0 曾写"9 份"系笔误，plan/06 已留痕），由 `tools/gen_rulesets.py` 单模板参数化生成，**全部数值条目 `已核对`、0 待核对**；
  - 8 份官方原文 curl 直抓落盘 `data/knowledge/raw/`（sha256 台账见 data/README.md §二）：61号公告+附件预扣率表一.doc+官方解读、个税法税率表一（fgk 原文图）、164号正文+附件1图、42号、30号、41号、2022-8号、2023-13号；
  - 关键定稿：溯及口径 = 婴幼儿照护 **2022 纳税年度起适用**（2019-2021 六项）；2023 提标 = 国发〔2023〕13号；速算扣除数出处 = 61号公告附件预扣率表一（税率表逐行 `ref_qd`）；年终奖文档链 164→42→30 按年度挂；41号条款 ref 两处修正（分摊=第六条、职业资格3600=第八条）；
- **真值库**：`data/truth/cases.json` 4 条（年终奖 36000/36001 临界对、累计预扣 3 个月、年度汇算），金额一律 Decimal 字符串，期望值 = 已核对官方数值+手工推导（推导式在 note），逐条挂官方 URL；
- **冻结纪律**：data/rules 为生成器冻结产物禁手改，`tests/test_gen_rulesets.py::test_regeneration_byte_identical` 逐字节守门；
- **门控翻转完成**：`test_gate_opens_when_all_verified` 用真实规则包直测放行；拦截路径改用合成包（`flip_one_node_pending`）；
- pytest 收集数基线：**39**（M0 为 28，只增不减）；CLI 实测：`rules --year 2019..2026` 全 rc=0 0 待核对，`rules --year 1999`=2，`calc --year 2026`=1（现为引擎桩"尚未实装"，门控已放行）。

## M2 待办（按序）

1. `engine/social.py`：社保公积金联动——缴费基数上下限与费率**用户输入**（plan/06 既定决策，规则包不存全国值），个人部分计入月度扣除；
2. `engine/monthly.py`：累计预扣逐月状态机（61号第六条公式，Decimal 全链路）：累计收入−免税收入−累计减除费用(5000×m)−累计专项扣除−累计专项附加扣除−其他扣除 → 预扣率表一 → 本期应预扣；余额负值暂不退税；
3. `engine/settlement.py`：年度汇算：综合所得应纳税所得额 → 税率表一（速算扣除数）→ 年应纳税额 vs 已预扣合计 → 退补税额；
4. 引擎入口只接受 `effective_ruleset()` 产物；代码零政策数值字面量（含临界端点，全部查规则包）；
5. `cli.py calc` 实装：`--year` + 输入源（交互/JSON 均可，M2 先做最小可用），输出逐月预扣表+汇算结果，每行挂 ref 条款依据；
6. 真值库回归：`data/truth/cases.json` 4 条通过率 100%（独立实现路径对账，不许改真值凑答案）；
7. pytest 全绿且收集数 ≥39；plan/00、05、06 回写；落 HANDOFF-M3。

## 既定口径清单（动了会打挂测试/基准，改动前先对照）

1. **退出码**：0=成功 / 1=运行期失败（含未实装、门控拦截）/ 2=用法输入错误——`tests/test_cli.py` 锁定；`calc`（真实年度）现命中引擎桩 → exit 1 "尚未实装"；
2. **门控覆盖面** = 含 `value` 键的数值条目 + 两张税率表逐行；sources[] 与 desc/ref_qd 说明节点不进门控——改覆盖面必须同步改 `status_report` 及其测试；
3. **schema v1**：7 级相接、末级 `upper=null`、value 节点必有 `ref`、`housing_loan_vs_rent` 必须显式 `mutually_exclusive`、status 缺失按待核对；税率行有 `ref`（级距税率）+ `ref_qd`（速算扣除数=61号预扣率表一）双出处键；
4. **Decimal 全链路**：JSON `parse_float=Decimal`，rate/金额字段为字符串；引擎代码零政策数值字面量（含临界区间端点）；
5. **规则包=冻结产物**：data/rules 禁手改，改需求走 `tools/gen_rulesets.py` 整目录重生成，`test_regeneration_byte_identical` 位级守门；生成器确定性（无时间戳/随机/set 迭代序），新增键值必须同步序列化顺序；
6. **年度口径**：2019-2026 共 **8** 份（"9 份"系 M0 笔误已修正）；婴幼儿照护 2022 纳税年度起适用（2019-2021 六项）；年终奖文档链 164(至2021-12-31)/42(至2023-12-31)/30(至2027-12-31) 按年度挂 `ref`；
7. **真值库语义**：expected 主期望 + also_expect 隐含中间量，评测按"全部非 pass 字段集"对账；金额两位小数 Decimal 字符串；年终奖÷12 商数 ROUND_HALF_UP 两位仅定档（税基用全额）；**不许改真值凑引擎答案**；
8. **税率表跨年一致**：`test_rate_tables_identical_across_years` 断言 2019-2026 全年度两张表一致——若发现某年度税率有变，需重构该测试为分年基线；
9. **Python 3.8 兼容**：无 match、无 PEP604 运行期联合类型、无 3.9+ API（`Path.write_text` 无 `newline` 参数、`removeprefix` 均已踩过，用替代写法）；
10. **数据目录定位顺序**：显式 --data-dir > 环境变量 `INCOMETAX_DATA_DIR` > `sys._MEIPASS/data`（PyInstaller）> CWD 上溯——M5 打包时冻结，改优先级需同步分支测试；
11. **社保参数归属**：缴费基数上下限与费率全部用户输入（plan/06 决策），规则包不存全国值——M2 实装 social.py 不得违反。

## 本机环境坑（全部实测）

- `py` 是 3.8.8（`python` 是商店占位符）；跑带中文输出的命令用 `py -X utf8`；
- 全程 `PYTHONDONTWRITEBYTECODE=1`（含 pip install），出怪错先清 `__pycache__`；
- pip 被注册表系统代理污染 → `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`（实测可用）；
- `incometax.exe` 装到 `...\Python38\Scripts`（不在 PATH）→ 统一用 `py -m incometax` 或 `py -X utf8 -m incometax`；
- **Git Bash `/tmp` 与 Windows Python 路径不通**——curl -o 与 py 读文件都要用工作区相对路径（M1 实测）；
- **查证通道实测**（M1）：`fgk.chinatax.gov.cn/zcfgk/c1000XX/cXXXXXXX/content.html` curl 直抓可用（附件相对路径为 `cXXXXXXX/5194838/files/...` 双层形式）；gov.cn 政策文件库检索 API `https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary_gw|_bm&q=<urlencode>&p=1&n=10&sort=score` 可用（国务院文件/部门文件，41/42/30/164/2022-8/2023-13 号均由此定位）；gov.cn zhengceku 正文页附件常为图片（官方原文图可下载后人工目验）；`sousuo.www.gov.cn` 无解读子库；广东局 `POST /search5/search/s`（siteCode=bm29190001）可用但仅返回频道聚合；Bing/DDG curl 通道不可用；flk.npc.gov.cn 是 JS 空壳；
- **git 提交邮箱**：本仓库已设 `git config user.email` = GitHub noreply（282769740+yuluo554@users.noreply.github.com）；**首提交 1481cc8 仍含个人 QQ 邮箱** → M6 发布前 env-filter 全历史改写（勿忘）；
- `.gitignore` 的 `*.spec` 通配会在 M5 吞掉 PyInstaller spec → 届时加 `!tools/*.spec` 例外。

## M2 DoD checklist

- [ ] 三引擎模块实装（monthly/social/settlement），全 Decimal、零政策字面量，签名与 plan/04 一致
- [ ] 真值库 4 条算例 CLI/引擎回归 100% 通过（不改真值）
- [ ] `calc` 命令实装：逐月预扣表 + 汇算输出 + 依据展示，退出码测试不漂移
- [ ] pytest 全绿且收集数 ≥39（只增不减），基线记入 HANDOFF-M3
- [ ] plan/00、05、06 回写 ✅；HANDOFF-M3 落盘；门控/冻结/真值三项守门测试仍绿

## 关键命令速查

```bash
# 安装（新环境/依赖变更后）
NO_PROXY="*" no_proxy="*" py -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（本机纪律：PYTHONDONTWRITEBYTECODE=1）
PYTHONDONTWRITEBYTECODE=1 py -m pytest -q

# 规则包预览（全年度 0 待核对）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 -m incometax rules --year 2026

# 重新生成规则包（改 tools/gen_rulesets.py 后整目录重生成；位级守门测试随全量跑）
PYTHONDONTWRITEBYTECODE=1 py -X utf8 tools/gen_rulesets.py

# git（提交前三核对：pwd / git log -1 / git remote -v）
git add -A && git commit -m "..."
```
