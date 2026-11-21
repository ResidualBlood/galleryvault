# GalleryVault 开发文档

> 接手开发者的入口。先读项目根 `AGENTS.md`（铁律 + 环境端口 + 限流数字），再按需读本目录各篇。后端细档见 `backend/docs/DEVELOPMENT.md` 与 `backend/docs/API.md`。

| 文档 | 回答什么 |
| :--- | :--- |
| [architecture.md](architecture.md) | 模块划分、数据流、横切设计 |
| [config.md](config.md) | 环境变量/配置项名称、默认值、出处 |
| [conventions.md](conventions.md) | 写代码要遵守、能脚本校验的约定 |
| [goals.md](goals.md) | 项目定位、能力边界、非目标 |
| [pitfalls.md](pitfalls.md) | 真实踩过的坑（现象→根因→处置） |
| [release.md](release.md) | 构建/测试/CI/发布/回滚命令 |
| [testdata.md](testdata.md) | 测试数据放哪、脱敏与隔离约定 |
| [workflow.md](workflow.md) | 决策/开发记录/计划状态的写法（流程文档，通用） |

## 相邻文档

- API：`../api/README.md`（端点清单）+ `../api/galleryvault-api.yaml`（OpenAPI）。
- 页面与样式：`../ui/README.md` + `../ui/design-system.md`。
- 运维：`../ops/README.md`。
- 用户向 wiki：`../wiki/`（中英成对）。
- 计划状态：`../plan/STATUS.md`、`../plan/ROADMAP.md`。
