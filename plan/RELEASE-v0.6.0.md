# RELEASE-v0.6.0 发布留档（二次迭代）

> 记录 v0.6.0 二次迭代的收尾与发布过程：命令、结论、实测数字。留档纪律：**不回填时间线**，动作先于修正发生时如实记录。
> 上一版留档见 [RELEASE-M6.md](RELEASE-M6.md)（v0.5.0）。

## 一、发布基线

| 项 | 值 |
|---|---|
| 版本 | **0.6.0**（`pyproject.toml` + `incometax.__version__`） |
| 发布提交 | `42bae73`（`main` = `origin/main` = 该提交） |
| tag | annotated **`v0.6.0`** → tag 对象 `a82c743` → commit `42bae73`（**未移动 `v0.5.0`**） |
| Release | https://github.com/yuluo554/income-tax-calculator/releases/tag/v0.6.0（latest，非草稿/非预发布） |
| 测试 | pytest **165** 项全绿（v0.5.0 基线 157 + 本轮元数据/schema/展示 8 项） |
| 基准 | **1184** 项检查全达标（算例 4/4、税率临界 752/752、陷阱 116/116（6/6 区间）、互斥 190 拒 + 122 放行） |
| 规则集复核 | `reviewed_at=2026-10-07`、`next_review=2027-01-31`；2024-2026 沿用 2023 标准（8 份规则包顶层 `review` + 来源逐条 `reviewed_at`） |
| 运行环境 | Python **3.12**（本机 3.12.10）+ PySide6 **6.12.0** + PyInstaller **6.22.3** |

## 二、干净环境验证（发布门核心）

远端新 clone（`git clone https://github.com/yuluo554/income-tax-calculator.git` → `42bae73`，工作树干净）+ 全新 `py -3.12 -m venv`：

| 步骤 | 命令 | 结论 |
|---|---|---|
| 装依赖 | `pip install -U pip setuptools wheel` + `pip install -e ".[dev,gui]"` | ✅ PySide6 6.12.0 |
| pytest | `python -m pytest -o addopts= -q` | ✅ `165 passed in 70.73s` |
| 基准 | `python -X utf8 -m incometax benchmark` | ✅ `1184 项检查，全部达标 [OK]` |
| rules | `python -X utf8 -m incometax rules --year 2026` | ✅ `核对日期:2026-10-07；下次复核:2027-01-31` / `已核对 32 条 / 待核对 0 条` |
| 打包 | `pip install -e ".[pkg]"` + `build_package.py --clean-build` | ✅ 构建后三断言全过 |
| 冻结态 | `verify_package.py` | ✅ 中立目录自检通过（内嵌数据定位 + calc + 基准 + GUI offscreen） |

工作区（发布提交前）同样全绿：pytest `165 passed in 77.57s`、基准 1184、build 三断言、冻结态自检、`desensitize_audit --mode all` 硬门 0 / 复核项 9。

## 三、CI（推送 `42bae73` 触发，run `39250085143`）

| job | 结论 |
|---|---|
| `test (windows-latest / py3.12)` | ✅ success |
| `test (ubuntu-latest / py3.12)` | ✅ success |
| `package (windows-latest / py3.12)` | ✅ success（3m4s） |

package job 日志实测行：`165 passed in 77.74s`、`构建完成，全部断言通过`、`[OK] 打包产物在中立目录可用`。

> 说明：本轮 CI 矩阵由「windows 3.8 / windows 3.12 / ubuntu 3.12」改为「windows 3.12 / ubuntu 3.12」，并新增 package 持续门禁 job；`actions/checkout` 与 `actions/setup-python` 升 v7（实测最新 tag `v7.0.1` / `v7.0.0`）。

## 四、发布物与校验和

| 附件 | 大小 | sha256 |
|---|---|---|
| `income-tax-calculator-v0.6.0-win64.zip` | 48,629,350 B | `33f884db240abe8cb651a8c5d4c5faab6505685ab7bc1f87da86eda9d3502180` |
| `income-tax-calculator-v0.6.0-win64.zip.sha256` | 105 B | 内容 = 上列 zip 校验和 |
| `income-tax-calculator-demo.gif` | 367,377 B | `7ac21123fc33a38d1e16909d16288bb508be38785721970df0f53999ddd01286` |

**registry 直读复核**（`gh release view` / `gh api`）：三个附件名未被剥中文（全 ASCII），zip 附件 digest 与本地 zip 一致，`releases/latest` = `v0.6.0`，tag 对象解引用 = `42bae73`。

**发布 zip 本体复验**：把 zip 解压到中立目录（193 条目，顶层目录 `个人所得税联动计算器`），直接运行其中的 `个人所得税联动计算器.exe --selftest` → 退出码 0、`自检结论：通过`（calc 全链路 + 基准 1184 + GUI offscreen 冒烟）。

## 五、Release 说明五部分

已按规范写入 GitHub Release 正文：①变更摘要 ②规则集版本（复核日期/沿用范围/政策边界）③是否需要重跑历史报告（**不需要**：税率、扣除标准、真值库、退出码、基准阈值未变；仅新增元数据与展示）④校验和 ⑤已知问题（wheel 分发限制、2024-2026 未逐年度复核、GUI/exe 人工冒烟）。

## 六、已知问题与遗留

1. **wheel/PyPI 分发未做**（决策 D-4 A）：非 editable wheel 不含 `data/`，仅支持 editable 源码安装与 Release exe；README「限制」已写明，列入 backlog。
2. **2024-2026 未逐年度复核官方原文**（决策 D-2 A）：规则包如实标注「沿用 2023 标准，未取得逐年度新文件」；`next_review=2027-01-31` 用于在 30 号公告执行到期（2027-12-31）前复核。
3. **GUI 与 exe 的人工目检/双击冒烟**由使用者在 Windows 桌面执行；本轮仅 offscreen 冒烟 + 冻结态自检 + 发布 zip 本体自检。发布的演示素材（`docs/demo/` 5 PNG + GIF）已按 v0.6.0 重新生成，其中「依据面板」页可见每来源的 `核对日期：2026-10-07`。
4. 本机 `dist/` 仍保留 v0.5.0 旧发布物与 v0.6.0 构建产物（均为 gitignored，不入仓）。

## 七、与 v0.5.0 的差异（一句话）

运行下限 Python 3.8→3.12（PySide6 6.12 / PyInstaller 6.22）+ 规则包复核元数据（`reviewed_at`/`next_review`，CLI/GUI 展示核对日期）+ 文档数字对齐（`4+752+116+312=1184`）+ CI 打包持续门禁；计算结论与 v0.5.0 一致。