# RELEASE-M6 发布留档

> 记录 M6 脱敏发布全过程：命令、结论、实测数据、瑕疵与决策。留档纪律：**不回填时间线**，
> 动作先于修正发生时如实记录。敏感字面值一律以占位符指代，不复述原文。

## 一、发布基线

| 项 | 值 |
|---|---|
| 版本 | 0.5.0（pyproject + `incometax.__version__`） |
| 发布源码基线 | M5 末态提交 `77c8b75`（M6 发布准备后 `src/` 与 `77c8b75` 逐文件一致，`git diff 77c8b75..HEAD -- src/` 为空） |
| 测试 | pytest **156** 项全绿（M5 基线 149 + M6 脱敏守门 7） |
| 基准 | 1184 项检查全达标（算例 4/4、税率临界 752/752、陷阱 6/6、互斥 190 拒 + 122 放行） |
| 数据 | 8 份年度规则包（2019-2026）逐字节冻结；真值库 4 条 |

## 二、干净环境验证（发布门核心）

新目录 clone + 全新 `py -m venv`，逐条照 README 快速开始执行：

| 步骤 | 命令 | 结论 |
|---|---|---|
| 建克隆 | `git clone <repo> _clean-itc` | ✅ 8 提交，历史邮箱全为 noreply |
| 建 venv | `py -m venv .venv` + `python -m pip install -U pip setuptools wheel` | ✅ pip 20.2.3 → 25.0.1，setuptools 75.3.4 |
| 装依赖 | `python -m pip install -e ".[dev,gui]"` | ⚠️ 首跑失败 → 重跑成功（环境级随机，见 §五 瑕疵 1） |
| pytest | `python -m pytest` | ✅ 全绿，收集 **156**（与 dev 一致） |
| 基准 | `python -m incometax benchmark` | ✅ 1184 项全达标 |
| rules | `python -m incometax rules --year 2026` | ✅ 门控放行 |
| GUI | offscreen 导入 + 建主窗口 | ✅ 标题「个人所得税联动计算器 v0.5.0」 |
| 打包 | `python -m pip install -e ".[pkg]"` + `tools/build_package.py --clean-build` | ✅ 构建后三断言全过 |
| 冻结态 | `tools/verify_package.py` | ✅ 中立目录自检通过（内嵌数据定位 + calc + 基准 + GUI 冒烟） |
| 脱敏 | `tools/desensitize_audit.py --mode all` | ✅ 硬门 0 |

**干净环境 vs dev 收集数对账**：dev 156 = 干净 clone 156，逐项无缺失；无 `importorskip` 静默跳过
（PyYAML 已进 dev extra，缺依赖会硬失败而非跳过）。

> **计数演进说明（如实记录，不改早前数值）**：本节干净环境验证执行于 CI 修复**之前**，当时基线为
> 156（M5 的 149 + M6 脱敏守门 7）。CI 首跑修复编码缺陷时新增 1 项回归测试
> （`test_cli_prints_cjk_under_non_utf8_console`），末态基线为 **157**；发布后对 GitHub clone 的复验
> 收集数 = 157 全绿（见 §九）。两处数值均为各自时点的真实记录。

## 三、脱敏审计（四步 + 产物本体扫描）

审计器入仓：`tools/desensitize_audit.py`（`--selftest` 阳性/阴性对照、`--mode tracked|history|messages|dist|all`）。
输出只报「文件:行号 [类别] x次数」，不复述敏感串原文，报告可随仓留档。

| 扫描面 | 命令 | 结果 |
|---|---|---|
| 跟踪文件名 | mode=tracked | ✅ 无 `.env`/`.key`/secret/token 类 |
| 内容级（跟踪树） | mode=tracked | ✅ 硬门 0 |
| 全历史 blob | mode=history | ✅ 硬门 0（8 提交全遍历，附检索通道探活防静默空扫） |
| 提交信息 | mode=messages | ✅ 硬门 0 |
| 产物本体 | mode=dist | ✅ 硬门 0（163 文件字节扫描） |
| 提交元数据邮箱 | `git log --format=%ae\|%ce --all` | ✅ 全部 GitHub noreply |

**复核项（人工豁免，均非泄漏面）**：`C:\Windows\Fonts` 系统字体路径（`tools/make_demo_assets.py` 3 处、
HANDOFF 速查 1 处）；`plan/06` "系列第 N 题" 表述（前作均已公开，`gh api users/yuluo554/repos` 核实）。

### 提交元数据改写（发布前置盲区）

- 旧邮箱仅在**提交元数据**，blob 级诊断确认历史树中无旧邮箱字面值（`git rev-list --all` × `git grep -lF` 全空）；
- 处置：`git filter-branch --env-filter`（author + committer 同改）→ `rm -rf .git/refs/original` →
  `git reflog expire --expire=now --all` → `git gc --prune=now --aggressive`；
- 改写前仓外备份：`git bundle create ../_backup-itc-<时间戳>.bundle --all`（1.35 MB）；
- 改写后验证：`git log --all --format=%ae|%ce` 仅剩 noreply 一种，旧邮箱计数 0。

## 四、发布物

| 产物 | 值 |
|---|---|
| Release | https://github.com/yuluo554/income-tax-calculator/releases/tag/v0.5.0 |
| tag | annotated `v0.5.0`（指向发布留档提交） |
| 附件 zip | `income-tax-calculator-v0.5.0-win64.zip`（41,272,855 字节） |
| 附件 sha256 | `income-tax-calculator-v0.5.0-win64.zip.sha256`（105 字节） |
| 附件演示 | `income-tax-calculator-demo.gif` |
| SHA256（zip） | `3b34f338f3db2718a687771c23dbc3300278dd906e9aeb858db08eac07818136` |
| 产物基线 | 提交 `b0f066b`（含 CI 编码修复；重建前 sha256 `2f8898…3e7a` 作废） |

> **附件名一律 ASCII**（`income-tax-calculator-…`）：实测 `gh release create` 在 Git Bash 下
> 会把中文文件名**剥成** `-v0.5.0-win64.zip`（丢前缀）与 `default.gif`（整名回退）——
> 附件已上传但名不可读、README 链接对不上。故仓库内 exe/目录保留中文名，仅**发布附件**用 ASCII。

**发布 zip 冻结态复验**：解压到中立目录（树外临时目录）→ `exe --selftest` 退出码 0，
内嵌数据定位落解压目录内（非仓库）、calc 全链路、基准 1184 全达标、GUI offscreen 冒烟通过。
产物本体按字节扫描：本机用户目录签名、本地工作根签名、本地目录名 均 0 命中（163 文件）。

## 五、瑕疵如实记录

1. **干净 venv 首跑 editable 安装失败**：报 `pkgutil.extend_path` → `str.join` 类型错误
   （`descriptor 'join' for 'str' objects doesn't apply to a 'tuple_iterator'`），
   **同命令立即重跑即成功**——判为环境级随机（`crash-loop-rescue` 判别节），非仓库缺陷；
   未改代码、未放宽任何门槛。
2. **审计器自命中（两处，已处置）**：首版扫描器源码注释含真实路径形式字面值，
   被自身正则命中（"扫描器必须过自己的扫描"）；改为片段拼接构造模式后归零。
3. **历史扫描静默空扫（已处置）**：首版 `git grep pat rev1 rev2 ...` 把多 revision 当 pathspec，
   返回 0 行造成"全历史干净"假象；改为逐提交迭代，并加"检索通道探活"断言（连已知串都搜不到即硬失败）。
4. **M5 遗留：CI 未配 `fetch-depth: 0`**：默认浅克隆会让 CI 里的历史脱敏扫描退化为空跑；
   已补 `fetch-depth: 0` 并加守门断言 `test_ci_checkout_fetches_full_history`。
5. **`gh release create` 在 Git Bash 下剥中文附件名**：首发附件名变成 `-v0.5.0-win64.zip`（丢前缀）
   与 `default.gif`（整名回退）——附件已上传但名不可读、README 链接对不上。处置：删除 release + tag，
   附件改 ASCII 名（`income-tax-calculator-v0.5.0-win64.zip` / `income-tax-calculator-demo.gif`）重建；
   仓库内 exe/目录仍保留中文名（中文文件名只在 gh CLI 传参环节丢失，不影响产物本体）。
6. **CI 首跑红灯（非缺陷，如实记录）**：见 §六；修两处环境差异后第二轮起全绿。

## 六、建仓与 CI 首跑（实录）

- `gh repo create income-tax-calculator --public`（**不带 `--push`**）→ 成功
- `git remote add origin git@github.com:yuluo554/income-tax-calculator.git` → `git push -u origin main`（**SSH 通路**）
  - push 成功；CI workflow 被正常识别并触发（`gh api .../actions/workflows` 显示 `CI active`）——
    SSH push 携带 workflow 文件，未受 token 缺 `workflow` scope 影响（本机 `gh` token scopes = `gist, read:org, repo`）
- **CI 首跑（run 38270783646）三作业全红**，两处为真实环境差异（发布门实测抓出，非仓库逻辑缺陷）：

| 失败面 | 现象 | 根因 | 处置 |
|---|---|---|---|
| windows × {3.8, 3.12} · Run benchmark | `UnicodeEncodeError: 'charmap' codec ...` | CI 管道 stdout 为 **cp1252**（本机开发用 `py -X utf8` 掩盖） | `cli.main` 入口 `_ensure_utf8_stdio`：按现编码探针决定是否切 UTF-8（cp936 中文控制台保持不动）；加回归测试 |
| ubuntu × 3.12 · Run tests | `ImportError: libEGL.so.1: cannot open shared object file` | 裸 runner 缺 Qt 运行期系统库（offscreen 亦需加载） | CI 增 Linux 步骤安装 `libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1` |

修复提交 `b0f066b` 推送后再跑（**第二轮 run 38271827840：三作业全绿** —— windows/3.8、windows/3.12、ubuntu/3.12），
push 数 = run 数对账（2 次 push → 2 轮 CI，均触发）；pytest 本机 157 全绿（+1 回归测试）。
**教训**：开发机 UTF-8 环境与中文控制台掩盖了编码缺口，只有陌生 CI 环境暴露——这正是干净环境/首跑门禁的价值。

## 七、发布物（src 变更后已重建）

> 说明：CI 修复改了 `src/incometax/cli.py`，按纪律 **改源码后必须重建产物**（冻结包内嵌运行时），
> §四 的 sha256 已更新为重建后数值（旧值 `2f8898…3e7a` 作废）。

重建后复验：`tools/verify_package.py` 中立目录自检通过 + 发布 zip 解压复验通过 + 产物本体扫描 0 命中。

## 八、待定决策清零

- #1 GitHub 仓库名：`income-tax-calculator`（发布用纯净名）
- #4 是否投稿社区清单：不投稿

## 九、发布后复核（对远端终态）

| 检查 | 命令/方法 | 结果 |
|---|---|---|
| 远端全新 clone | `git clone git@github.com:yuluo554/income-tax-calculator.git` | ✅ 106 文件、tag `v0.5.0` 就位 |
| 历史邮箱三扫（clone 内） | `git log --format=%ae\|%ce --all` | ✅ 唯一 noreply |
| 全量测试（clone 内全新 venv） | `pytest` + `--collect-only` | ✅ 157 收集、全绿 |
| 基准（clone 内） | `python -m incometax benchmark` | ✅ 1184 项全达标 |
| 脱敏四扫（clone 内） | `tools/desensitize_audit.py --mode all` | ✅ 硬门 0 |
| README 渲染 | `gh api .../readme -H Accept:…html` | ✅ 标题/表格×2/GIF/下载节/评测表均渲染 |
| Release 附件下载 | HTTP 302→200 + `gh release download` | ✅ zip 41,272,855 字节，**sha256 与留档一致** |
| **下载产物冻结态自检** | 解压远端下载的 zip → `exe --selftest` | ✅ 退出码 0，内嵌数据落解压目录、calc 全链路、基准 1184 达标、GUI 冒烟通过 |
| 仓库元信息 | `gh repo view` | ✅ `PUBLIC`、MIT、topics 8 项、latestRelease = v0.5.0 |
| CI 轮数对账 | `gh run list` | ✅ push 数 = run 数 |

**结论**：远端终态 = 已验证的发布物基线（tag `v0.5.0` 指向发布留档提交；发布后回写以小提交跟进，不迁 tag）。
