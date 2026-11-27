---
task: be-deps-dependabot-44-48
date: 2026-11-27
kind: chore
source: Dependabot PR #44-#48（5 个依赖下限升级，目标 dev，CI test 均通过）；用户「处理那些 PR」
tickets: ["#44", "#45", "#46", "#47", "#48"]
commits: []
decisions: []
docs: []
verified: []
unverified: []
---

# be-deps-dependabot-44-48 合并 #44-#48 依赖下限升级

## 改了什么

把 5 个 Dependabot PR 的依赖下限提升合并为一个提交，上限与其它依赖不动：

| PR | 依赖 | 旧下限 | 新下限 |
| --- | --- | --- | --- |
| #44 | `ruff`（dev 组） | `>=0.17.2` | `>=0.17.5` |
| #45 | `alembic` | `>=1.20.0` | `>=1.20.1` |
| #46 | `pytest`（dev 组） | `>=9.1.1` | `>=9.2.0` |
| #47 | `pytest-asyncio`（dev 组） | `>=1.4.0` | `>=1.5.0` |
| #48 | `pydantic-settings` | `>=2.16.1` | `>=2.16.3` |

- `backend/pyproject.toml:12` `pydantic-settings>=2.16.3,<3`；
  `:16` `alembic>=1.20.1,<2`；
  `:28` dev 组 `pytest>=9.2.0,<10`、`pytest-asyncio>=1.5.0,<2`、`ruff>=0.17.5,<1`。
- `backend/requirements.txt:3` `pydantic-settings>=2.16.3,<3`；`:7` `alembic>=1.20.1,<2`。
- 上限（`<1` / `<2` / `<3` / `<10`）全部保持不变；`pytest-cov`、`pytest-xdist`、`pre-commit`、
  `import-linter` 等未在 PR 内的依赖不动。

## 为什么

5 个 PR 各自只改一行下限，逐个合入会生成 5 个噪音提交并制造重复的 pyproject/requirements 冲突；
沿用 2026-11-11 Dependabot #39-#43 的先例合为一个提交，语义不变、回退粒度一致。
`pyproject.toml` 的 ruff 规则集注释本就按 0.17.5 生成，提升下限后与 `[tool.ruff.lint]` 的实际规则集一致。

## 验证

- `grep -q 'ruff>=0.17.5,<1' backend/pyproject.toml` → 退出码 0
- `grep -q 'pytest>=9.2.0,<10' backend/pyproject.toml` → 退出码 0
- `grep -q 'pytest-asyncio>=1.5.0,<2' backend/pyproject.toml` → 退出码 0
- `alembic>=1.20.1,<2` / `pydantic-settings>=2.16.3,<3` 在两文件各出现 1 次（合计各 2 次）→ 退出码 0
- `python3 -c "import tomllib;tomllib.load(open('backend/pyproject.toml','rb'))"` → 退出码 0
- 解析校验：用 `packaging.requirements.Requirement` 解析 pyproject 22 条 + requirements.txt 14 条全部通过，
  两文件共有依赖的约束集合逐条一致 → 退出码 0

## 缺口与后续

- 只改了下限声明，未在本机重装依赖；`ruff`/`pytest`/`pytest-asyncio`/`alembic`/`pydantic-settings`
  新版本下的实际运行由各自 PR 的 CI test 覆盖，本任务未重跑后端测试。
- 未关闭 Dependabot PR：按任务约定由主控在推送后处理（Dependabot 通常在下限被 dev 覆盖后自动标记）。
- `CHANGELOG.md` 未更新：本批次 scope 只含两个依赖文件与本记录，changelog 由发版流程汇总。
