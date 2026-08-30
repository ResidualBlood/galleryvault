"use strict";

const I18N = {
  en: {
    loginSub: "Password required to access the local library.",
    searchPlaceholder: "Search library...",
    username: "Username",
    password: "Password", login: "Login", wrong: "Wrong password, please retry.",
    mustChange: "Default password in use — please change it now.",
    changePassword: "Change password", currentPassword: "Current password",
    newPassword: "New password", changePwOk: "Password changed",
    pwDefault: "Using the default password", pwConfigured: "Password configured",
    authLogin: "Account login", authRequired: "Require login",
    translationUpdate: "Translation auto-update",
    translationInterval: "Update interval (minutes, 0 = off)",
    forceUpdate: "Update now", translationStatus: "Translation status",
    transUpdated: "Translations updated",
    testTelegram: "Send test message",
    browse: "Browse", library: "Library", tags: "Tags", downloads: "Downloads",
    downloadsSub: "Download tasks.",
    favorites: "Favorites", history: "History", settings: "Settings", logout: "Logout",
    scan: "Scan library", random: "Random", readNow: "Read now", syncTags: "Sync tags",
    tagSection: "Tags", pagesSection: "Pages", details: "Details", prev: "Previous",
    next: "Next", allPages: "All pages", clearHistory: "Clear history",
    refreshFolders: "Refresh folder names", checkDownload: "Check & download",
    notConfigured: "Folders not configured or not synced yet.",
    save: "Save", testLogin: "Test login", cookieSet: "set (not shown)", cookieUnset: "not set",
    filterAll: "All", filterPending: "Pending", filterSuccess: "Success", filterFailed: "Failed",
    cancel: "Cancel", noTasks: "No download tasks.", noGalleries: "No matching galleries, click Scan.",
    noHistory: "No reading history.", noTags: "No local tags found.", clearAll: "clear all", search: "Search",
    openEh: "Open on ExHentai", ehLoginNote: "Requires ExHentai login in your browser", custom: "Custom",
    ehPublicNotice: "Public E-Hentai: ExHentai-only galleries pause tag sync and are not reclassified; switching back to exhentai.org resumes them automatically.",
    progress: "progress", loading: "Loading…", language: "中文", latest: "Latest",
    enabled: "Enabled", mode: "Mode", intervalMin: "Interval (min)",
    syncFavcats: "Sync folder names", checkNow: "Check now", saveOk: "Saved",
    checkAll: "Check all folders", favLocal: "local", favCloud: "cloud",
    favcatTag: "folder", favDate: "fav:", backToGallery: "back to gallery", postedDate: "posted:",
    unfavorite: "Unfavorite", unfavoriteFail: "Cannot unfavorite", unfavorited: "Removed from favorites",
    unfavoritedLocal: "Cloud removal failed; local record removed", confirmUnfavorite: "Remove this gallery from favorites?",
    favManage: "Manage duplicates", favManageTitle: "Favorites — duplicates",
    favManageSub: "Scan favorite folders for duplicate galleries (same work in different versions, e.g. DL / uncensored / language re-uploads).",
    favListSub: "Galleries in this favorite folder. Select and download or remove from favorites.",
    favDl: "Download selected", favDlQueued: "Download queued", favDlSkip: "already local/skipped",
    favDlOrig: "Download selected original", favDlArchive: "Archive download selected",
    downloadMissing: "Download missing items", downloadMissingStarted: "Backfilling covers & tags…",
    favStateAll: "Show all", favStateLocal: "Local only", favStateCloud: "Cloud only",
    favRemove: "Remove from favorites", confirmFavRemove: "Remove selected from favorites?",
    dupScan: "Scan duplicates", dupUnfav: "Unfavorite", dupUnfavDelete: "Unfavorite & delete local",
    dupFilterAll: "All", dupFilterLocal: "Local only", dupFilterCloud: "Cloud only",
    dupHint: "Press “Scan duplicates” to compare all favorite galleries.",
    dupNone: "No duplicate groups found.",
    dupFound: "Found", dupGroups: "groups", dupItems: "items",
    confirmDupUnfav: "Remove selected from favorites?", confirmDupDelete: "Remove from favorites and delete local copies?",
    dupDeleteFail: "Local delete failed (read-only or permission): ",
    dupIgnore: "Ignore", dupUnignore: "Restore", dupIgnored: "Ignored", dupIgnoredOk: "Group ignored",
    dupUnignoredOk: "Group restored",
    dupIgnoreSel: "Ignore selected", dupIgnoredPage: "Ignored items", dupIgnoredSub: "Groups you marked as not-duplicates. Select and restore to re-enable them.",
    dupUnignoreSel: "Restore selected",
    favCount: "Galleries (cloud/local)", favSize: "Size (cloud/local)",
    favModeIncremental: "Incremental", favModeMonitorOnly: "Monitor only", favModeForce: "Force",
    libraryRoots: "Library roots", baseUrl: "Base URL",
    cookieId: "ipb_member_id", cookieHash: "ipb_pass_hash", cookieIgneous: "igneous",
    libraryRootsHint: "Roots holding your existing gallery archives (Ehviewer exports, CBZ…). New downloads never land here; deleting a gallery removes its files here when the mount is writable.",
    downloadRootHint: "Download directory: newly downloaded ExHentai galleries are stored here and scanned automatically.",
    cookiesNote: "Cookies are never displayed after saving.",
    proxyHttp: "HTTP proxy", proxySocks5: "SOCKS5 proxy",
    downloadRoot: "Download root", concurrency: "Concurrency", pageConcurrency: "Pages in parallel", quality: "Quality",
    qualityOriginal: "Original (原图)", qualityResample: "Resample (普通)",
    archiveQuality: "Archive quality", archiveScanEnabled: "Archive large favorites on scheduled scan",
    archiveMaxPages: "Archive page threshold (0 = all)", archiveMaxPagesHint: "On scheduled favorites checks, galleries with more pages than this are downloaded via the ExHentai archive (zip) instead of page-by-page; the rest download page-by-page as usual. 0 archives everything.",
    archiveFallbackPages: "Fall back to page-by-page if archive is unavailable", archiveFallbackPagesHint: "When the archive channel cannot serve a gallery (that quality tier does not exist, GP too low, archive corrupt), download it page-by-page instead of failing. Page-by-page costs no GP but uses H@H traffic.",
    archiveTitle: "Archive download — cost preview", archiveFunds: "GP available", archiveTierOriginal: "Original", archiveTierResample: "Resample", archiveCost: "cost", archiveSize: "size", archiveUnavailable: "insufficient GP", archiveConfirm: "Start archive download", archiveNoItems: "No archives available for the selection.", archivePreviewFail: "Archive preview failed", archiveQueued: "Archive download queued", archiveUnsupported: "Some selected galleries are already local or lack a token and were skipped.",
    dlBadgeArchive: "Archive", dlBadgePages: "Page-by-page",
    dlOrig: "Download original", dlOrigArchive: "Archive-download original",
    dlOrigQueued: "Original download queued", dlOrigArchiveQueued: "Original archive download queued",
    origBadge: "Original", resampleBadge: "Resample",
    catDoujinshi: "Doujinshi", catManga: "Manga", catArtistcg: "Artist CG", catGamecg: "Game CG",
    catWestern: "Western", catNonH: "Non-H", catImageSet: "Image Set", catCosplay: "Cosplay",
    catAsianporn: "Asian Porn", catMisc: "Misc", catDeleted: "Deleted", notFavorited: "Not in favorites",
    useHah: "Use H@H", titleDisplay: "Title display", downloadTitle: "Download title (folder name)",
    imageTimeout: "Image max time (seconds)", imageWarmup: "Image slow warmup (seconds)", imageMinSpeed: "Image min speed (KB/s)",
    imageTimeoutHint: "A single image is aborted after this many seconds total. ",
    imageSlowHint: "After the warm-up window, an image averaging below the minimum speed is treated as a throttled H@H node and retried with backoff.",
    botToken: "Bot token (leave blank to keep)", chatIds: "Chat IDs (comma separated)",
    allowedIds: "Allowed user IDs (comma separated)",
    notifyLevel: "Notification level", notifyLevelSummary: "Summary (batch digest)", notifyLevelImmediate: "Immediate (every event)", notifyLevelFailuresOnly: "Failures only", notifyLevelOff: "Off", notifyLang: "Notification language", langZh: "中文", langEn: "English",
    autoSyncTags: "Auto sync tags", tagSyncInterval: "Tag sync interval (seconds)",
    tagSyncConcurrency: "Tag sync concurrency",
    generateThumbnails: "Generate thumbnails", genThumbs: "Generate now", syncAllTags: "Sync tags now",
    dupPolicy: "Duplicate-copy policy", dupPolicyHint: "When the same gallery (gid) exists under several scan roots, this decides which copy is kept automatically. All duplicates are still listed on the “Duplicate copies” page.",
    dupPolicyKeepFirst: "Keep first (already-stored copy wins)",
    dupPolicyMorePages: "Prefer more pages", dupPolicyNewer: "Prefer newer posted date",
    dupPolicyLarger: "Prefer larger size", dupPolicySmaller: "Prefer smaller size",
    dupPolicyManual: "Manual (never auto-resolve)",
    dupGalTitle: "Duplicate copies", dupGalSub: "The same gallery (gid) found under more than one scan root. Pick which copy to keep, or change the auto policy in Settings.",
    dupGalScan: "Scan library", dupGalRefresh: "Refresh",
    dupGalNone: "No duplicate copies found.", dupGalFound: "Found", dupGalGroups: "groups",
    dupGalAll: "All", dupGalOpen: "Pending", dupGalDismissed: "Dismissed",
    dupGalCurrent: "current", dupGalKeep: "Keep this copy", dupGalKeepDel: "Keep & delete others",
    dupGalDismiss: "Dismiss group", dupGalRestore: "Restore group",
    dupGalConfirmDel: "Keep this copy and DELETE the other copies from disk?",
    dupGalConfirmKeep: "Make this copy the stored one?",
    pollDefault: "Default poll interval (minutes)",
    favHint: "Enable folders to monitor; per-folder settings below.",
    testExhentai: "Test ExHentai login", cancelDl: "Cancel", error: "Error",
    retry: "Retry", retrySelected: "Retry selected", selectAll: "Select all",
    deleteDl: "Delete",
    galleryUpdates: "Gallery updates", galleryUpdatesSub: "Local galleries that ExHentai re-uploaded under a new gid. Select them and download the newest version (the old local copy is removed after the new one finishes).",
    updateSelected: "Update selected", scanNow: "Scan now", ignoreSelected: "Ignore selected",
    updOrig: "Update selected original", updArchive: "Archive update selected",
    updStateActive: "Active", updStateAll: "All", updStatePending: "Pending", updStateDownloading: "Downloading", updStateFailed: "Failed",
    updPending: "Update available", updDownloading: "Downloading", updFailed: "Failed", updIgnored: "Ignored",
    updToNewer: "→ new gid", updIgnoredPage: "Ignored updates", updNoUpdates: "No galleries with updates.",
    updScanning: "Scanning for updates", updDetectedAt: "Last scan", updUnignore: "Unignore", updUnignoreSel: "Restore selected", updNone: "No ignored updates.",
    downloading: "downloading", perPage: "per page",
    readerFit: "Fit", readerFullscreen: "Fullscreen",
    delete: "Delete", deleteGallery: "Delete gallery", deleteFiltered: "Delete filtered",
    deleteFiles: "Also delete files on disk", confirmDelete: "Delete this gallery?",
    confirmDeleteFiltered: "Delete all matching galleries?", deleted: "Deleted",
    select: "Select", clearSel: "Clear selection", deleteSel: "Delete selected",
    confirmDeleteSel: "Delete selected galleries?",
    tasks: "Background tasks", scanning: "Scanning library",     tagSyncing: "Syncing tags", thumbs: "Generating thumbnails",
    scanDone: "Scan complete", tagSyncDone: "Tag sync complete", thumbsDone: "Thumbnails complete",
    metaDone: "Metadata sync complete", completed: "done", scanned: "scanned", persisted: "persisted",
    favMetaSync: "Syncing favorite metadata", favMetaApply: "Applying favorite metadata", applied: "applied",
    deleteGalleryLog: "Delete gallery", favoritesRemoveLog: "Remove from favorites",
    tagSyncFromCache: "Tags updated from cache", tagSyncFromNetwork: "Tags synced from ExHentai",
    noTasks: "No download tasks.", dlTasks: "Download tasks",
    logs: "Logs", logsSub: "Background tasks and recent activity.",
    runningTasks: "Running now", finishedTasks: "Finished",
    noRunningTasks: "No background tasks running.", noFinishedTasks: "No finished tasks yet.",
    cancelTask: "Cancel", taskCancelling: "cancelling",
    taskSuccess: "succeeded", taskFailed: "failed", taskCancelled: "cancelled", duration: "took",
    taskRunning: "running", startedAt: "started", finishedAt: "finished",
    thumbsHint: "When enabled, thumbnails for galleries missing a cover are generated in the background.",
    scanDesc: "Scanning library folders", tagSyncDesc: "Syncing tags with ExHentai",
    thumbsDesc: "Generating thumbnails", metaDesc: "Backfilling favorite sizes & metadata",
    favCheckDesc: "Checking favorite folders", transDesc: "Updating tag translations",
    favcatTitle: "Favorites folders", favcatSub: "ExHentai favorites monitoring & auto download.",
    settingsSub: "Library, connection and background tasks.",
    welcome: "Welcome", welcomeSub: "A few quick steps to get your library up and running. You can finish each one now or skip it and come back in Settings.",
    welcomePasswordTitle: "Change the default password", welcomePasswordDesc: "Your instance is still using the built-in default password. Set a strong one now.",
    welcomeCookieTitle: "Connect ExHentai", welcomeCookieDesc: "Paste the cookies from a logged-in ExHentai browser session to enable metadata sync and downloads.",
    welcomeImportTitle: "Fill your library", welcomeImportDesc: "Scan the library folders, or check your ExHentai favorites to download what's missing.",
    welcomeImportHint: "Tip: check your ExHentai favorites first — it caches metadata (tags, sizes, posted dates) so the library scan and tag sync are much faster afterwards.",
    welcomeFinish: "Finish setup", welcomeLater: "Do this later", welcomeDone: "Done — welcome aboard!",
    stepDone: "done", stepNotDone: "pending",
    groups: { all: "All", tag: "Tags", artist: "Artists", character: "Characters", parody: "Parodies", group: "Groups", female: "Female", male: "Male", language: "Languages" },
    ns: { artist: "Artist", character: "Character", parody: "Parody", group: "Group", language: "Language", category: "Category", misc: "Tag", other: "Tag", female: "Female", male: "Male", mixed: "Mixed" },
  },
  zh: {
    loginSub: "需要密码才能访问本地画廊。",
    searchPlaceholder: "搜索画廊…",
    username: "用户名",
    password: "密码", login: "登录", wrong: "密码错误，请重试。",
    mustChange: "正在使用默认密码，请立即修改。",
    changePassword: "修改密码", currentPassword: "当前密码",
    newPassword: "新密码", changePwOk: "密码已修改",
    pwDefault: "正在使用默认密码", pwConfigured: "已配置密码",
    authLogin: "账户登录", authRequired: "需要登录",
    translationUpdate: "翻译自动更新",
    translationInterval: "更新间隔（分钟，0=关闭）",
    forceUpdate: "立即更新", translationStatus: "翻译状态",
    transUpdated: "翻译已更新",
    testTelegram: "发送测试消息",
    browse: "浏览", library: "画廊库", tags: "标签", downloads: "下载",
    downloadsSub: "下载任务。",
    favorites: "收藏夹", history: "历史", settings: "设置", logout: "退出",
    scan: "扫描库", random: "随机", readNow: "开始阅读", syncTags: "同步标签",
    tagSection: "标签", pagesSection: "页面", details: "详情", prev: "上一页",
    next: "下一页", allPages: "所有页面", clearHistory: "清空历史",
    refreshFolders: "刷新文件夹名称", checkDownload: "检查并下载",
    notConfigured: "尚未配置或同步收藏夹。",
    save: "保存", testLogin: "测试登录", cookieSet: "已设置（不回显）", cookieUnset: "未设置",
    filterAll: "全部", filterPending: "进行中", filterSuccess: "成功", filterFailed: "失败",
    cancel: "取消", noTasks: "暂无下载任务。", noGalleries: "没有匹配的画廊，请点击扫描。",
    noHistory: "暂无阅读历史。", noTags: "未找到本地标签。", clearAll: "清空标签", search: "搜索",
    openEh: "打开原站", ehLoginNote: "需浏览器已登录 ExHentai", custom: "自定义",
    ehPublicNotice: "外站 E-Hentai：里站专属画廊会暂停标签同步（不会被误判为已删除），切回 exhentai.org 后自动恢复。",
    progress: "进度", loading: "加载中…", language: "EN", latest: "最新",
    enabled: "启用", mode: "模式", intervalMin: "间隔（分钟）",
    syncFavcats: "同步收藏夹名称", checkNow: "立即检查", saveOk: "已保存",
    favCount: "画廊数（云端/本地）", favSize: "大小（云端/本地）",
    favModeIncremental: "增量下载", favModeMonitorOnly: "仅监控", favModeForce: "强制下载",
    libraryRoots: "库根目录", baseUrl: "Base URL",
    cookieId: "ipb_member_id", cookieHash: "ipb_pass_hash", cookieIgneous: "igneous",
    libraryRootsHint: "存放已有画廊归档（Ehviewer 导出、CBZ 等）。新下载的画廊不会放到这里；删除画廊时若挂载可写会一并删除这里的文件。",
    downloadRootHint: "下载目录：新从 ExHentai 下载的画廊存放于此，并自动纳入扫描。",
    cookiesNote: "Cookie 保存后不会回显。",
    proxyHttp: "HTTP 代理", proxySocks5: "SOCKS5 代理",
    downloadRoot: "下载根目录", concurrency: "并发数", pageConcurrency: "单画廊并发页数", quality: "画质",
    qualityOriginal: "原图 (Original)", qualityResample: "重采样 (Resample)",
    archiveQuality: "归档下载质量", archiveScanEnabled: "定时扫描大画廊走归档下载",
    archiveMaxPages: "归档页数阈值（0=全部归档）", archiveMaxPagesHint: "定时扫描收藏夹时，页数超过该阈值的画廊用 ExHentai 官方归档（zip）下载，其余仍逐页下载。0 表示全部走归档。",
    archiveFallbackPages: "归档不可用时降级为逐页下载", archiveFallbackPagesHint: "当归档通道无法下载该画廊（所选画质不存在、GP 不足、归档损坏）时，改为逐页下载而不是失败。逐页不消耗 GP，但会占用 H@H 流量。",
    archiveTitle: "归档下载 — 费用预览", archiveFunds: "可用 GP", archiveTierOriginal: "原图", archiveTierResample: "重采样", archiveCost: "费用", archiveSize: "大小", archiveUnavailable: "GP 不足", archiveConfirm: "开始归档下载", archiveNoItems: "所选画廊没有可用的归档。", archivePreviewFail: "归档预览失败", archiveQueued: "已加入归档下载", archiveUnsupported: "部分所选画廊已本地或缺少 token，已跳过。",
    dlBadgeArchive: "归档", dlBadgePages: "逐页",
    dlOrig: "下载原图", dlOrigArchive: "归档形式下载原图",
    dlOrigQueued: "已加入原图下载", dlOrigArchiveQueued: "已加入原图归档下载",
    origBadge: "原图", resampleBadge: "重采样",
    catDoujinshi: "同人志", catManga: "漫画", catArtistcg: "画师CG", catGamecg: "游戏CG",
    catWestern: "西方", catNonH: "非H", catImageSet: "图集", catCosplay: "Cosplay",
    catAsianporn: "亚洲色情", catMisc: "杂项", catDeleted: "已删除", notFavorited: "不在收藏夹",
    useHah: "使用 H@H", titleDisplay: "标题显示", downloadTitle: "下载标题（目录命名）",
    imageTimeout: "单图最大耗时（秒）", imageWarmup: "慢速预热窗口（秒）", imageMinSpeed: "单图最低速度（KB/s）",
    imageTimeoutHint: "单张图片下载超过该总时长即中断。",
    imageSlowHint: "超过预热窗口后，若单图平均速度低于下限，判定为 H@H 限流节点，退避后重试。",
    botToken: "Bot Token（留空保持不变）", chatIds: "Chat ID（逗号分隔）",
    allowedIds: "允许的用户 ID（逗号分隔）",
    notifyLevel: "通知级别", notifyLevelSummary: "汇总（批量摘要）", notifyLevelImmediate: "即时（每条都发）", notifyLevelFailuresOnly: "仅失败", notifyLevelOff: "关闭", notifyLang: "通知语言", langZh: "中文", langEn: "English",
    autoSyncTags: "自动同步标签", tagSyncInterval: "标签同步间隔（秒）",
    tagSyncConcurrency: "标签同步并发",
    generateThumbnails: "生成缩略图", genThumbs: "立即生成", syncAllTags: "立即同步标签",
    dupPolicy: "重复副本策略", dupPolicyHint: "同一画廊（gid）出现在多个扫描目录时，自动保留哪个副本。所有重复仍会列在「重复副本」页。",
    dupPolicyKeepFirst: "保留优先（已入库的副本优先）",
    dupPolicyMorePages: "保留页数多的", dupPolicyNewer: "保留发布日期新的",
    dupPolicyLarger: "保留体积大的", dupPolicySmaller: "保留体积小的",
    dupPolicyManual: "手动（不自动处理）",
    dupGalTitle: "重复副本", dupGalSub: "同一画廊（gid）出现在多个扫描目录中。选择要保留的副本，或在设置中更改自动策略。",
    dupGalScan: "扫描库", dupGalRefresh: "刷新",
    dupGalNone: "未发现重复副本。", dupGalFound: "发现", dupGalGroups: "组重复",
    dupGalAll: "全部", dupGalOpen: "待处理", dupGalDismissed: "已忽略",
    dupGalCurrent: "当前保留", dupGalKeep: "保留此副本", dupGalKeepDel: "保留并删除其他副本",
    dupGalDismiss: "忽略该组", dupGalRestore: "恢复该组",
    dupGalConfirmDel: "保留此副本并删除磁盘上的其他副本？",
    dupGalConfirmKeep: "将此副本设为保留副本？",
    pollDefault: "默认轮询间隔（分钟）",
    favHint: "勾选要监控的收藏夹；各收藏夹设置见下表。",
    testExhentai: "测试 ExHentai 登录", cancelDl: "取消任务", error: "错误",
    retry: "重试", retrySelected: "重试所选", selectAll: "全选",
    deleteDl: "删除",
    galleryUpdates: "更新画廊", galleryUpdatesSub: "这些本地画廊被 ExHentai 重传（换了新 gid）。勾选后下载最新版本（新版下载完成后自动删除旧版本地文件）。",
    updateSelected: "更新选中", scanNow: "立即检测", ignoreSelected: "忽略选中",
    updOrig: "更新选中原图", updArchive: "归档更新选中",
    updStateActive: "待处理", updStateAll: "全部", updStatePending: "待更新", updStateDownloading: "下载中", updStateFailed: "失败",
    updPending: "有新版", updDownloading: "下载中", updFailed: "失败", updIgnored: "已忽略",
    updToNewer: "→ 新 gid", updIgnoredPage: "已忽略的更新", updNoUpdates: "没有检测到有更新的画廊。",
    updScanning: "正在检测更新", updDetectedAt: "上次检测", updUnignore: "取消忽略", updUnignoreSel: "恢复选中", updNone: "没有已忽略的更新。",
    downloading: "下载中", perPage: "每页",
    readerFit: "适应", readerFullscreen: "全屏",
    delete: "删除", deleteGallery: "删除画廊", deleteFiltered: "删除筛选结果",
    unfavorite: "取消收藏", unfavoriteFail: "无法取消收藏", unfavorited: "已取消收藏",
    unfavoritedLocal: "云端移除失败，仅移除本地记录", confirmUnfavorite: "确定从收藏夹移除该画廊？",
    favManage: "收藏夹管理", favManageTitle: "收藏夹管理 — 查重",
    favManageSub: "扫描收藏夹中重复的画廊（同一作品的不同版本，如 DL 版 / 无修正 / 不同语言搬运）。",
    checkAll: "立即检查所有", favLocal: "本地", favCloud: "云端",
    favcatTag: "收藏夹", favDate: "收藏", backToGallery: "返回画廊", postedDate: "发布于",
    favListSub: "该收藏夹内的画廊。勾选后可下载或从收藏移除。",
    favDl: "下载所选", favDlQueued: "已加入下载", favDlSkip: "已本地/跳过",
    favDlOrig: "下载所选原图", favDlArchive: "归档下载所选",
    downloadMissing: "下载缺失项目", downloadMissingStarted: "正在补拉封面与标签…",
    favStateAll: "全部显示", favStateLocal: "仅显示本地", favStateCloud: "仅显示云端",
    favRemove: "移除收藏", confirmFavRemove: "将所选从收藏夹移除？",
    dupScan: "开始扫描重复画廊", dupUnfav: "取消收藏", dupUnfavDelete: "取消收藏并删除已下载",
    dupFilterAll: "全部", dupFilterLocal: "只显示本地", dupFilterCloud: "只显示云端",
    dupHint: "点击“开始扫描重复画廊”对比所有收藏的画廊。",
    dupNone: "未发现重复画廊。",
    dupFound: "发现", dupGroups: "组重复", dupItems: "项",
    confirmDupUnfav: "将所选从收藏夹移除？", confirmDupDelete: "将所选从收藏夹移除并删除本地副本？",
    dupDeleteFail: "本地删除失败（只读或权限不足）：",
    dupIgnore: "忽略", dupUnignore: "恢复", dupIgnored: "已忽略", dupIgnoredOk: "已忽略该组",
    dupUnignoredOk: "已恢复该组",
    dupIgnoreSel: "忽略所选", dupIgnoredPage: "已忽略项目", dupIgnoredSub: "你标记为不重复的组。勾选后点击「恢复所选」重新纳入查重。",
    dupUnignoreSel: "恢复所选",
    deleteFiles: "同时删除磁盘文件", confirmDelete: "确定删除此画廊？",
    confirmDeleteFiltered: "确定删除所有匹配的画廊？", deleted: "已删除",
    select: "选择", clearSel: "清除选择", deleteSel: "删除所选",
    confirmDeleteSel: "确定删除所选画廊？",
    tasks: "后台任务", scanning: "扫描库中", tagSyncing: "同步标签中", thumbs: "生成缩略图中",
    scanDone: "扫描完成", tagSyncDone: "标签同步完成", thumbsDone: "缩略图完成",
    metaDone: "元数据同步完成", completed: "已完成", scanned: "扫描", persisted: "入库",
    favMetaSync: "同步收藏元数据", favMetaApply: "应用收藏元数据", applied: "已应用",
    deleteGalleryLog: "删除画廊", favoritesRemoveLog: "取消收藏",
    tagSyncFromCache: "标签已从缓存更新", tagSyncFromNetwork: "标签已从 ExHentai 同步",
    noTasks: "暂无下载任务。", dlTasks: "下载任务",
    logs: "日志", logsSub: "后台任务与最近活动。",
    runningTasks: "进行中", finishedTasks: "已完成",
    noRunningTasks: "当前没有后台任务在运行。", noFinishedTasks: "暂无已完成任务。",
    cancelTask: "取消", taskCancelling: "正在取消",
    taskSuccess: "成功", taskFailed: "失败", taskCancelled: "已取消", duration: "耗时",
    taskRunning: "进行中", startedAt: "开始时间", finishedAt: "完成时间",
    thumbsHint: "开启后，后台会自动为缺少封面的画廊生成缩略图。",
    scanDesc: "正在扫描画廊目录", tagSyncDesc: "正在同步标签",
    thumbsDesc: "正在生成缩略图", metaDesc: "正在回填收藏夹大小与元数据",
    favCheckDesc: "正在检查收藏夹", transDesc: "正在更新标签翻译",
    favcatTitle: "收藏夹监控", favcatSub: "ExHentai 收藏夹监控与自动下载。",
    settingsSub: "本地库、连接与后台任务。",
    welcome: "欢迎使用", welcomeSub: "几步即可完成基本配置，让画廊库跑起来。现在完成或跳过，之后可随时在「设置」中补充。",
    welcomePasswordTitle: "修改默认密码", welcomePasswordDesc: "你的实例还在使用内置的默认密码。现在设置一个强密码。",
    welcomeCookieTitle: "连接 ExHentai", welcomeCookieDesc: "从已登录的 ExHentai 浏览器会话中粘贴 cookie，即可启用元数据同步与下载。",
    welcomeImportTitle: "填充你的画廊库", welcomeImportDesc: "扫描库目录，或检查 ExHentai 收藏夹并下载缺失的画廊。",
    welcomeImportHint: "提示：建议先「检查所有收藏夹」——它会缓存元数据（标签/大小/发布时间），之后扫描库和标签同步会快得多。",
    welcomeFinish: "完成设置", welcomeLater: "稍后再说", welcomeDone: "完成，欢迎使用！",
    stepDone: "已完成", stepNotDone: "待完成",
    groups: { all: "全部", tag: "标签", artist: "作者", character: "角色", parody: "原作", group: "社团", female: "女性", male: "男性", language: "语言" },
    ns: { artist: "作者", character: "角色", parody: "原作", group: "社团", language: "语言", category: "分类", misc: "标签", other: "标签", female: "女性", male: "男性", mixed: "男女" },
  },
};

function t(key) { return (I18N[app.lang] && I18N[app.lang][key]) || I18N.en[key] || key; }
function nsLabel(ns) { return (I18N[app.lang].ns && I18N[app.lang].ns[ns]) || ns; }
function groupLabel(key) { return (I18N[app.lang].groups && I18N[app.lang].groups[key]) || key; }
function tagText(tag) { return app.lang === "zh" ? (tag.display || tag.name) : tag.name; }
function updateLangButton() {
  const b = document.querySelector('[data-action="toggle-lang"]');
  if (b) b.textContent = t("language");
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
}

function updateBanner() {
  const el = document.getElementById("banner");
  if (!el) return;
  if (app.authenticated && app.session.must_change_password) {
    el.hidden = false;
    el.innerHTML = `<span>${esc(t("mustChange"))}</span> <a class="primary" href="#/welcome">${esc(t("changePassword"))}</a>`;
  } else {
    el.hidden = true;
    el.innerHTML = "";
  }
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

async function api(method, path, body) {
  const opts = { method, credentials: "include", headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

async function checkAuth() {
  try {
    const session = await api("GET", "/api/auth/session");
    app.authenticated = true;
    app.session = session || {};
    $topbar().hidden = false;
    updateBanner();
    // Normalise the address bar: after logging in the SPA is served at /login
    // (the middleware redirect target) but the app lives at "/"; rewrite the
    // path so the URL reads e.g. /#/browse instead of /login#/browse.
    if (location.pathname.endsWith("/login")) {
      history.replaceState(null, "", "/" + location.hash);
    }
    if (!location.hash || location.hash === "#/" || location.hash === "#/login") {
      location.hash = app.session.must_change_password ? "#/welcome" : "#/browse";
    }
    router();
  } catch (_) {
    app.authenticated = false;
    app.session = {};
    $topbar().hidden = true;
    renderLogin();
  }
}

async function doLogin(password) {
  const res = await fetch("/login", {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "password=" + encodeURIComponent(password || ""),
  });
  if (!res.ok) {
    app.authenticated = false;
    $topbar().hidden = true;
    toast(t("wrong"));
    renderLogin();
    return;
  }
  await checkAuth();
  if (!app.authenticated) toast(t("wrong"));
}

async function doLogout() {
  await fetch("/logout", { method: "POST", credentials: "include" });
  app.authenticated = false;
  $topbar().hidden = true;
  location.hash = "";
  renderLogin();
}

function parseHash() {
  let h = location.hash.replace(/^#/, "");
  if (!h) h = "/browse";
  const [path, qs] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  app.view = parts[0] || "browse";
  app.params = {};
  if (app.view === "gallery" || app.view === "reader") {
    app.params.id = /^\d+$/.test(parts[1] || "") ? parts[1] : "";
  }
  if (app.view === "reader") app.params.page = /^\d+$/.test(parts[2] || "") ? parts[2] : "0";
  if (app.view === "favorites") {
    if (parts[1] === "manage") { app.view = "favmanage"; }
    else if (parts[1] === "ignored") { app.view = "favignored"; }
    else if (/^\d+$/.test(parts[1] || "")) { app.view = "favlist"; app.params.id = parts[1]; }
  }
  if (app.view === "updates") {
    if (parts[1] === "ignored") { app.view = "updignored"; }
  }
  app.query = {};
  if (qs) for (const kv of qs.split("&")) {
    const [k, v] = kv.split("=");
    try { app.query[decodeURIComponent(k)] = decodeURIComponent(v || ""); }
    catch (e) { app.query[k.replace(/%/g, "")] = (v || "").replace(/%/g, ""); }
  }
}

function navHash(view, params = {}, query = {}) {
  let p = "/" + view;
  if (view === "favlist") { p = "/favorites/" + (params.id || app.params.id); }
  else if (params.id) p += "/" + params.id;
  if (view === "reader") p += "/" + (params.page || 0);
  const q = Object.entries(query).filter(([, v]) => v !== "" && v != null)
    .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&");
  return "#" + p + (q ? "?" + q : "");
}

function router() {
  parseHash();
  updateLangButton();
  updateBanner();
  if (!app.authenticated) { renderLogin(); return; }
  if (app.view !== "library") selGalleries.clear();
  if (app.view !== "favorites" && app.view !== "favlist" && favTimer) { clearInterval(favTimer); favTimer = null; }
  if (app.view !== "updates" && app.view !== "updignored" && updatesTimer) { clearInterval(updatesTimer); updatesTimer = null; }
  if (app.view !== "downloads" && dlTimer) { clearInterval(dlTimer); dlTimer = null; }
  if (app.view !== "logs" && logTimer) { clearInterval(logTimer); logTimer = null; }
  if (app.view !== "favlist") selFav.clear();
  if (app.view !== "favmanage" && app.view !== "favignored") { selDup.clear(); }
  if (app.view !== "reader" && readerFsActive) exitReaderFullscreen();
  stopInfinite();
  switch (app.view) {
    case "browse": renderBrowse(); break;
    case "library": renderLibrary(); break;
    case "gallery": renderGallery(); break;
    case "reader": renderReader(); break;
    case "tags": renderTags(); break;
    case "history": renderHistory(); break;
    case "downloads": renderDownloads(); break;
    case "logs": renderLogs(); break;
    case "settings": renderSettings(); break;
    case "duplicates": renderDuplicates(); break;
    case "welcome": renderWelcome(); break;
    case "favorites": renderFavorites(); break;
    case "favmanage": renderFavManage(); break;
    case "favignored": renderFavIgnored(); break;
    case "favlist": renderFavList(); break;
    case "updates": renderUpdates(); break;
    case "updignored": renderUpdateIgnored(); break;
    default: renderBrowse();
  }
  bindTagSuggest();
  bindReaderKeys();
}
