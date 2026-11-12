# GalleryVault 伴侣用户脚本（userscript）

在 **E-Hentai / ExHentai 画廊页**（`/g/<gid>/<token>/`）注入一个 GalleryVault 面板：

- 库内 / 收藏 / 下载状态（`GET /api/eh/status`，只查本地库、不触达 EH）
- **下载到 GalleryVault**（质量可选：重采样 / 原图）
- **收藏到 GalleryVault**（可选 favcat 0–9）
- **在 GalleryVault 打开**（`#/online/g/<gid>/<token>`）

阅读增强**不在本脚本范围内**：脚本不实现阅读器，推荐搭配
[Comic Looms](https://github.com/MapoMagpie/comic-looms)（MIT，原 eh-view-enhance）。
我们只注入收藏 / 下载入口，不复制第三方脚本代码。

> 服务端额度：脚本的请求只落在**用户自己的 GalleryVault**，不经过 EH API，
> 因此不占服务端的 EH 页面预算；图片阅读仍由用户浏览器直连 EH。

## 安装

1. 安装脚本管理器：桌面 **Tampermonkey** 或 **Violentmonkey**。
2. 打开 `public/galleryvault-companion.user.js`（构建产物），粘贴到脚本管理器新建脚本，
   或在能访问该文件的地址上直接安装。
3. **Chrome / Edge（MV3）**：脚本管理器要求开启用户脚本权限 —— Chrome 138+
   在扩展详情页打开 **Allow User Scripts**（旧版为开启「开发者模式」），
   否则 `GM_xmlhttpRequest` 等 API 不可用。
4. 打开任意 EH 画廊页，首次会在面板里要求填写：
   - **GalleryVault 地址**：如 `http://192.168.1.10:8200`
   - **API Token**：在 GalleryVault 设置页生成（明文只显示一次）
   两者通过 `GM_setValue` 保存在脚本管理器里，不写入页面、不进日志。
5. 若被 401（Token 被撤销 / 服务重装），面板会提示「认证失败」，重新填写即可。

脚本的 `@match` 只有 `https://e-hentai.org/g/*` 与 `https://exhentai.org/g/*`。
`@connect *` 是因为自建 GalleryVault 域名/IP 不固定；脚本只会向**用户填写的地址**发请求。

## 隐私

- 不读取、不上传 EH 登录 cookie（脚本里没有任何 cookie 访问）。
- 只在用户主动点击时向 GalleryVault 发请求：`GET /api/eh/status`、
  `GET /api/favorites/categories`、`POST /api/downloads`、`POST /api/favorites/add`。
- API Token 只存在脚本存储里；渲染时不会写入 DOM，也不会打印到 console。
- 后端对 Bearer 有端点白名单（见 PLAN §3.3），其余接口一律 403。

## 移动端

| 平台 | 可用性 |
| --- | --- |
| Android | Firefox for Android（Tampermonkey / Violentmonkey）、Edge for Android（扩展商店装 Tampermonkey）可用；Kiwi Browser 已停更 |
| iOS | Safari 需装 Userscripts / Stay 扩展并逐站授权；`GM_xmlhttpRequest` / `@connect` 语义与桌面不完全一致 |

**本任务只保证桌面 Tampermonkey / Violentmonkey**；移动端属尽力而为，
真实扩展内的行为需人工验收。

## 开发

```
frontend/next/
├── userscript/
│   ├── companion.mjs        # 唯一实现（纯函数 + 面板），单元测试直接 import
│   ├── build.mjs            # 生成 public/galleryvault-companion.user.js
│   ├── vitest.config.mjs    # 本目录测试的 vitest 配置
│   └── userscript.test.ts   # 单测
├── public/galleryvault-companion.user.js   # 构建产物（提交）
└── e2e/
    ├── userscript.spec.ts
    └── fixtures/userscript/  # 脱敏样本页、GM 垫片、mock 后端
```

```bash
node userscript/build.mjs            # 重新生成 public/galleryvault-companion.user.js
node userscript/build.mjs --check    # 校验产物未漂移（单测里也有一条）
npx vitest run --config userscript/vitest.config.mjs   # 单个用户脚本单测
env GV_SHOTS=/tmp/gv-shots npm run e2e:mock -- --grep @userscript
```

> 注意：根 `vitest.config.ts` 的 `include` 目前只有 `src/**/*.test.ts`，
> 因此用户脚本单测要用上面的 `--config` 运行。把它加进根配置的 include
> （`"userscript/**/*.test.ts"`）即可让 `npm run test:unit -- userscript`
> 自动发现；该文件不在本批 scope 内，留给集成时合并。

E2E 不访问真实 EH/ExHentai：页面来自 `e2e/fixtures/userscript/gallery.html`
（裁剪脱敏样本），API 来自本地 HTTP mock，`page.exposeFunction` 代替扩展后台
执行 `GM_xmlhttpRequest`。

## 维护

- EH 改版导致面板消失时，先改 `companion.mjs` 里的 `SELECTORS`
  （`#gd5` 为详情区「Download」行，`#gn` 为标题），并同步 `e2e/fixtures/userscript/gallery.html`。
- 面板只用内联样式 + `prefers-color-scheme`，不依赖 EH 的 CSS，也不注入外部资源。
