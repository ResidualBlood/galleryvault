# GalleryVault 前端设计参考清单

- 版本：1.0（Batch 1，2026-11-12）
- 取证报告：`/tmp/opencode/gv-frontend-rewrite/inv-design-refs.md`（下列链接均取自该报告，报告记录为实际打开核实；未新造 URL）
- 使用边界：**只借鉴布局、信息层级与交互模式**，不复制第三方代码、图标、截图、字符串或字体资源；Kavita / EhViewer_CN_SXJ 为 GPL-3.0，尤其禁止复制其源码、布局 XML、样式或字符串资源。
- 视觉基线：Material Design 3 的 token 结构；品牌色与背景色沿用本仓 `frontend/assets/styles.css`，不复刻 M3 默认紫。
- 历史排除项的现状：FooIbar / EhViewer-Overhauled 仓库仍返回 HTTP 451（DMCA），不引用；**EhViewer_CN_SXJ 已按本地源码核实（`d129f20`），作为浏览页与 tag 交互参考纳入**（仅交互，GPL-3.0 边界见 §4）。

---

## 1. 界面 → 参考对象 → 参考方面 → 链接 → 许可证

| 界面 / 用途 | 参考对象 | 参考方面 | 链接 | 许可证 |
| --- | --- | --- | --- | --- |
| 应用壳 / 断点导航 | Material 3 / Android | Compact / Medium / Expanded / Large 五档与 bar / rail / drawer 选择 | https://developer.android.com/develop/ui/compose/layouts/adaptive/window-size-classes | 官方文档（站点条款） |
| 应用壳 / 断点导航 | Material 3 | 断点与布局原则 | https://m3.material.io/foundations/layout/breakpoints | 官方文档（站点条款） |
| 应用壳 / 抽屉分组 | Komga | Logo → 主区 → 固定库 → More → 管理组的抽屉顺序；选中项容器色 | https://github.com/gotson/komga/blob/master/komga-webui/src/views/HomeView.vue#L21-L140 | MIT |
| 应用壳 / 底部导航 | Material 3 | Navigation bar 的层级、选中态与高度 | https://m3.material.io/components/navigation-bar/overview | 官方文档（站点条款） |
| 应用壳 / 侧边图标轨 | Material 3 | Navigation rail 的宽度、选中态与标签 | https://m3.material.io/components/navigation-rail/overview | 官方文档（站点条款） |
| 应用壳 / 常驻抽屉 | Material 3 | Navigation drawer 的分组、选中容器与模态行为 | https://m3.material.io/components/navigation-drawer/overview | 官方文档（站点条款） |
| 本机库网格卡片 | Kavita | 未读圆点、仅未读完显示 5px 进度条、固定标题高度、右下操作菜单 | https://github.com/Kareadita/Kavita/blob/develop/UI/Web/src/app/cards/entity-card/entity-card.component.html | GPL-3.0 |
| 本机库网格卡片 | Komga | 封面四角浮层位（左上状态 / 右上标签 / 左下编辑 / 右下菜单）+ 底部进度 | https://github.com/gotson/komga/blob/master/komga-webui/src/components/ItemCard.vue#L4-L111 | MIT |
| 网格 / 列表角标 | Mihon | 用 color role 区分角标语义（未读 primary、下载 tertiary、语言） | https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/library/components/LibraryBadges.kt#L14-L42 | Apache-2.0 |
| 在线列表卡片 | JHenTai | 左封面右信息；标题 2 行 + 上传者；分类/收藏/语言/页数/半星评分/时间 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_list_card_.dart#L130-L223 | Apache-2.0 |
| 在线列表卡片 | JHenTai | 官方列表卡截图（只作为布局证据，不入库） | https://github.com/jiangtian616/JHenTai/blob/master/screenshot/mobile_v2.jpg | Apache-2.0 |
| 浏览页视图切换 / 条目字段 | EhViewer_CN_SXJ | 列表 / 网格两态字段组合；页内三视图为本仓扩展 | https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/d129f20/app/src/main/java/com/hippo/ehviewer/ui/scene/gallery/list/GalleryAdapterNew.java#L60-L68 | GPL-3.0 |
| 行内 / 浮层 tag | EhViewer_CN_SXJ | chip 只显示标签体、namespace 独立表达；条目内 tag 的聚焦呈现 | https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/d129f20/app/src/main/java/com/hippo/ehviewer/ui/scene/gallery/list/GalleryListScene.java#L794-L812 | GPL-3.0 |
| tag 点击与搜索语法 | EhViewer_CN_SXJ | 本机 / 收藏 AND 筛选；在线 `ns:"name$"` 包裹 | https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/d129f20/app/src/main/java/com/hippo/ehviewer/ui/scene/gallery/list/GalleryListScene.java#L557-L574 | GPL-3.0 |
| 筛选角标 / 跳页 | EhViewer_CN_SXJ | 生效条件数 1–9 / 9+；有页码校验范围、无页码日期跳转 | https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/d129f20/app/src/main/java/com/hippo/ehviewer/ui/scene/gallery/list/GalleryListScene.java#L1399-L1543 | GPL-3.0 |
| 详情页 | JHenTai | 封面 + 信息 → 操作行 → namespace 标签 → 缩略图 → 评论的顺序；宽窄屏信息排布 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/pages/details/details_page.dart#L210-L233 | Apache-2.0 |
| 详情页 | JHenTai | 窄屏两行 / 宽屏三行数据信息 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/pages/details/details_page.dart#L483-L560 | Apache-2.0 |
| 详情页 | JHenTai | 官方详情页截图（只作为布局证据，不入库） | https://github.com/jiangtian616/JHenTai/blob/master/screenshot/detail.png | Apache-2.0 |
| 阅读器（分页） | Mihon | 中区点按呼出上下栏；顶栏返回/标题/书签；底栏四等距图标；上下栏动画 200ms | https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/reader/appbars/ReaderAppBars.kt | Apache-2.0 |
| 阅读器（分页） | Kavita | 首页按钮 + 滑条 + 末页按钮；适高/适宽/原始；单页/双页/双页无封面/反向 | https://github.com/Kareadita/Kavita/blob/develop/UI/Web/src/app/manga-reader/_models/reader-enums.ts | GPL-3.0 |
| 阅读器（分页） | Kavita | 底栏滑条、设置面板、点按分区实现 | https://github.com/Kareadita/Kavita/blob/develop/UI/Web/src/app/manga-reader/_components/manga-reader/manga-reader.component.html | GPL-3.0 |
| 阅读器（适配档位） | Komga | Webreader 的 ScaleType / 双页 / RTL 与适配说明 | https://komga.org/docs/guides/webreader-divina | MIT |
| 阅读器（Webtoon） | JHenTai | 纵向连续、隐藏式工具栏、缩略图条 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/pages/read/layout/vertical_list/vertical_list_layout.dart | Apache-2.0 |
| 阅读器（Webtoon） | Kavita | 无限滚动渲染器 | https://github.com/Kareadita/Kavita/blob/develop/UI/Web/src/app/manga-reader/_components/infinite-scroller/infinite-scroller.component.ts | GPL-3.0 |
| 阅读器（页码浮层） | Mihon | 页码 `当前 / 总数` 的描边 + 填充可读性做法 | https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/reader/appbars/ReaderAppBars.kt | Apache-2.0 |
| 设置页 | Mihon | 分组子页、组标题、右侧值 + 箭头、顶部搜索、twoPane 浅 surface | https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/more/settings/screen/SettingsMainScreen.kt#L76-L160 | Apache-2.0 |
| 设置页（服务器级） | Komga | 左说明右控件、底部固定 Save/Reset、dirty 校验 | https://komga.org/docs/guides/server-settings | MIT |
| 设置页（主题） | Komga | 主题覆盖与暗色说明 | https://komga.org/docs/guides/theme | MIT |
| 设置页（分组参考） | Kavita | 设置 tab 枚举与 `setting-item` / `setting-switch` / `setting-select` 行布局 | https://wiki.kavitareader.com/guides/admin-settings/general/ | GPL-3.0 |
| 下载 / 任务列表 | JHenTai | 进度色 primary、暂停态高一级容器、分组底 secondary-container | https://github.com/jiangtian616/JHenTai/blob/master/screenshot/download.jpg | Apache-2.0 |
| 收藏 / 分类色 | JHenTai | 分类色常量与收藏槽位 0–9 色表 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/config/ui_config.dart#L47-L59 | Apache-2.0 |
| 收藏 / 分类色 | JHenTai | 收藏槽位映射与 `favoriteTagColor` | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/config/ui_config.dart#L104-L129 | Apache-2.0 |
| 分类 chip | JHenTai | 纯色底 + 文字色的分类标签实现 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_category_tag.dart#L38-L42 | Apache-2.0 |
| 收藏心形 | JHenTai | 心形颜色 = 画廊所在收藏槽位色 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_list_card_.dart#L280 | Apache-2.0 |
| 收藏 chip | JHenTai | 收藏槽位 chip 的底色与文字 | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/widget/eh_gallery_favorite_tag.dart#L20-L26 | Apache-2.0 |
| 标签 / namespace | LANraragi | `namespace:tag` 搜索语法与 namespace 过滤 | https://sugoi.gitbook.io/lanraragi/v/dev/basic-operations/searching | MIT |
| 标签 / namespace | LANraragi | 元数据 / namespace 说明 | https://sugoi.gitbook.io/lanraragi/v/dev/basic-operations/metadata | MIT |
| 标签 / namespace | JHenTai | namespace 分组 chip 与浅底黑字色表（暗色需重算） | https://github.com/jiangtian616/JHenTai/blob/master/lib/src/config/ui_config.dart#L66-L82 | Apache-2.0 |
| 空状态 / 错误状态 | Komga | 居中图标 + 标题 + 说明 + 主按钮的 EmptyState 结构 | https://github.com/gotson/komga/blob/master/komga-webui/src/components/EmptyState.vue | MIT |
| 空状态 / 错误状态 | Mihon | ReaderError 的错误呈现（不大面积铺红） | https://github.com/mihonapp/mihon/blob/main/app/src/main/java/eu/kanade/presentation/reader/ReaderError.kt | Apache-2.0 |
| 缩略图 / 紧凑双视图 | LANraragi | thumbnail 与 compact list 双视图、可配置 namespace 列 | https://sugoi.gitbook.io/lanraragi/v/dev/basic-operations/archives | MIT |
| 缩略图视图（截图） | LANraragi | 官方缩略图视图截图（只作为布局证据，不入库） | https://raw.githubusercontent.com/Difegue/LANraragi/dev/tools/Documentation/.gitbook/assets/archive_thumb.png | MIT |
| 阅读器覆盖层（截图） | LANraragi | 官方阅读器 + overlay 截图（只作为布局证据，不入库） | https://raw.githubusercontent.com/Difegue/LANraragi/dev/tools/Documentation/.gitbook/assets/reader_overlay.jpg | MIT |

## 2. Material Design 3 通用参考

| 主题 | 参考方面 | 链接 | 许可证 |
| --- | --- | --- | --- |
| Color roles | 角色清单与 on-* 配对语义 | https://m3.material.io/styles/color/roles | 官方文档（站点条款） |
| Color system | 色调/色阶与主题生成 | https://m3.material.io/styles/color/system/overview | 官方文档（站点条款） |
| Typography | 字族、字阶与使用场景 | https://m3.material.io/styles/typography/overview | 官方文档（站点条款） |
| Type scale tokens | 15 档字号/行高/字重/字距 | https://m3.material.io/styles/typography/type-scale-tokens | 官方文档（站点条款） |
| Shape scale tokens | 0 / 4 / 8 / 12 / 16 / 28 / full | https://m3.material.io/styles/shape/shape-scale-tokens | 官方文档（站点条款） |
| Elevation overview | 0–5 级海拔与用途 | https://m3.material.io/styles/elevation/overview | 官方文档（站点条款） |
| Elevation tokens | 各级 shadow 值 | https://m3.material.io/styles/elevation/tokens | 官方文档（站点条款） |
| State layers | hover 0.08 / focus 0.12 / pressed 0.12 / dragged 0.16 | https://m3.material.io/foundations/interaction/states/state-layers | 官方文档（站点条款） |
| Design tokens | token 分层与命名方法 | https://m3.material.io/foundations/design-tokens/overview | 官方文档（站点条款） |
| material-web type scale | 官方 SCSS 数值（本仓字阶来源） | https://github.com/material-components/material-web/blob/main/tokens/versions/v0_192/_md-sys-typescale.scss | Apache-2.0 |
| material-web shape | 官方圆角数值 | https://github.com/material-components/material-web/blob/main/tokens/versions/v0_192/_md-sys-shape.scss | Apache-2.0 |
| material-web elevation | 官方阴影数值 | https://github.com/material-components/material-web/blob/main/tokens/versions/v0_192/_md-sys-elevation.scss | Apache-2.0 |
| material-web state | 官方状态层数值（本仓采用这一套） | https://github.com/material-components/material-web/blob/main/tokens/versions/v0_192/_md-sys-state.scss | Apache-2.0 |
| material-web color roles | 官方角色清单 | https://github.com/material-components/material-web/blob/main/tokens/_md-sys-color.scss | Apache-2.0 |
| 4dp / 8dp 网格 | 间距基线 4/8/12/16/24/32/48 | https://m2.material.io/design/layout/understanding-layout.html | 官方文档（站点条款） |
| Material Symbols | 图标集（构建期内联 SVG，语义名注册表） | https://fonts.google.com/icons | Apache-2.0 |
| Material Symbols 仓库 | 图标源文件与许可证 | https://github.com/google/material-design-icons | Apache-2.0 |

## 3. 项目主页、许可证与截图来源

| 项目 | 用途 | 链接 | 许可证 |
| --- | --- | --- | --- |
| JHenTai | 在线列表、详情、阅读器、下载、设置、EH 色彩语义的主要参考 | https://github.com/jiangtian616/JHenTai | Apache-2.0 |
| JHenTai LICENSE | 许可核实 | https://github.com/jiangtian616/JHenTai/blob/master/LICENSE | Apache-2.0 |
| JHenTai 截图目录 | 布局证据（不入库） | https://github.com/jiangtian616/JHenTai/tree/master/screenshot | Apache-2.0 |
| JHenTai 连续滚动截图 | Webtoon 布局证据 | https://github.com/jiangtian616/JHenTai/blob/master/screenshot/read_continuous_scroll.png | Apache-2.0 |
| JHenTai 设置页截图 | 设置分组证据 | https://github.com/jiangtian616/JHenTai/blob/master/screenshot/setting_zh.jpg | Apache-2.0 |
| Mihon | M3 落地、角标语义、阅读器上下栏、设置子页 | https://github.com/mihonapp/mihon | Apache-2.0 |
| Mihon LICENSE | 许可核实 | https://github.com/mihonapp/mihon/blob/main/LICENSE | Apache-2.0 |
| Mihon 官网截图 | 亮/暗移动端外观证据 | https://mihon.app/home/phone.dark.webp | Apache-2.0 |
| Komga | 桌面抽屉、四角浮层、EmptyState、Webreader 适配 | https://github.com/gotson/komga | MIT |
| Komga LICENSE | 许可核实 | https://github.com/gotson/komga/blob/master/LICENSE | MIT |
| Komga Web UI 文档 | 桌面壳与阅读器说明 | https://komga.org/docs/guides/webui | MIT |
| Kavita | 卡片角标/进度、阅读器适配、设置分组 | https://github.com/Kareadita/Kavita | GPL-3.0 |
| Kavita LICENSE | 许可核实 | https://github.com/Kareadita/Kavita/blob/master/LICENSE | GPL-3.0 |
| Kavita Wiki | 设置分组与安装说明 | https://wiki.kavitareader.com/ | GPL-3.0 |
| LANraragi | namespace 搜索/列、缩略图与紧凑双视图 | https://github.com/Difegue/LANraragi | MIT |
| LANraragi LICENSE | 许可核实 | https://github.com/Difegue/LANraragi/blob/dev/COPYING | MIT |
| LANraragi 文档 | 归档、搜索、分类、主题 | https://sugoi.gitbook.io/lanraragi/v/dev | MIT |
| EhViewer_CN_SXJ | 浏览页字段组合、视图形态与 tag 交互（仅行为，不复制代码 / 资源 / 字符串） | https://github.com/xiaojieonly/Ehviewer_CN_SXJ | GPL-3.0 |
| EhViewer_CN_SXJ LICENSE | 许可核实（GPL-3.0） | https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/d129f20/LICENSE | GPL-3.0 |
| Material Symbols | 图标资源（构建期内联 SVG） | https://github.com/google/material-design-icons | Apache-2.0 |

## 4. 排除项与许可红线

1. **EhViewer 主线与 Overhauled fork**：`https://github.com/FooIbar/EhViewer`、`https://github.com/Ehviewer-Overhauled/Ehviewer` 均返回 HTTP 451（DMCA），无法核实。不引用其源码、截图或配色；EH 分类/收藏配色改用 JHenTai 常量。**EhViewer_CN_SXJ**（`xiaojieonly` 维护的 GPL-3.0 分支）已核实并纳入参考，但只允许借鉴行为与交互，不得复制源码、布局 XML、Drawable、字符串或截图。
2. **Kavita（GPL-3.0）**：只可借鉴交互与布局思路，不得复制 SCSS / HTML / TS 片段，不得把其代码并入本仓。
3. **截图与图标**：以上截图链接仅作为评审时的外部证据；仓库内 `frontend/docs/design/` 不放任何第三方 PNG/JPG/WebP/SVG。`check-design` 的验收会检查该目录无位图文件。
4. **链接维护**：参考对象或链接失效时，先报告并更新本清单，不得自行替换为未核实来源。
