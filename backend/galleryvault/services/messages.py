"""Telegram notification message templates (zh / en).

All Telegram notification copy lives here so the backend has exactly one place
that decides both the *language* (driven by the ``telegram_notify_lang``
setting) and the *format* (Telegram HTML: bold titles, ``<code>`` gids, and a
consistent emoji prefix per event type).

Every user-supplied value (titles, gids, errors, category names) is HTML
escaped before being interpolated, because ``send_message`` uses
``parse_mode="HTML"`` and an unescaped ``<`` / ``&`` would make Telegram reject
the whole message.

Only the outer "shell" text is translated; gallery titles come from ExHentai
and are never translated, only escaped.
"""

from __future__ import annotations

import re

LANGS = ("zh", "en")
GONE_DETAIL = "gallery deleted or not found (404)"
HOPS_DETAIL = "replacement chain exceeded maximum hops (5)."
# Single downloads list their title; larger batches only show counts for the
# success side (failures are always listed, capped to the Telegram 4096 limit).
LIST_TITLES_LIMIT = 5
MAX_MESSAGE_CHARS = 4096

_TEMPLATES: dict[str, dict[str, str]] = {
    "zh": {
        "download_ok_verb": "下载完成 ",
        "download_ok_title": "<b>{title}</b>",
        "download_ok_pages": "（{pages} 页）",
        "download_fail_verb": "下载失败 ",
        "download_fail_title": "<b>{title}</b>",
        "download_fail_detail": "：{detail}",
        "download_summary_head": "📊 下载汇总：完成 <b>{ok}</b>，失败 <b>{fail}</b>",
        "list_sep": "、",
        "download_more_failures": "… 还有 {n} 个失败未列出",
        "scan_ok": "🔎 扫库完成：新增 <b>{new}</b>，移除 <b>{removed}</b>",
        "scan_dup": "⚠️ <b>{n}</b> 组重复副本（gid <code>{gids}</code>）",
        "scan_failed": "❌ 扫库失败：{error}",
        "ellipsis": "…",
        "fav_category": "收藏夹 {name}（#{favcat}）",
        "fav_category_noname": "收藏夹 #{favcat}",
        "fav_check_failed": "⭐ {cat}：检查失败（{n} 次）",
        "fav_enqueue_failed": "⭐ {cat}：gid <code>{gid}</code> 入队失败",
        "fav_summary": "⭐ {cat}：新增 <b>{new}</b>，入队 <b>{queued}</b>",
        "bot_paused": "⏸ 下载已暂停",
        "bot_resumed": "▶️ 下载已恢复",
        "bot_status_running": "📋 下载状态：运行中",
        "bot_status_paused": "📋 下载状态：已暂停",
        "bot_queued": "📥 已入队 gid <code>{gid}</code>",
        "bot_queued_title": "📥 已入队 <b>{title}</b>（gid <code>{gid}</code>）",
        "bot_queued_updated": (
            "📥 原 gid <code>{old}</code> 已更新为 gid <code>{new}</code>，已入队 <b>{title}</b>"
        ),
        "bot_gone": "❌ <b>{title}</b>已删除或不存在（404），未入队",
        "bot_already_local": "✅ 新版已在库中：<b>{title}</b>（gid <code>{gid}</code>）",
        "bot_help": (
            "🤖 命令：\n"
            "<code>/pause</code> 暂停下载\n"
            "<code>/resume</code> 恢复下载\n"
            "<code>/status</code> 系统运行状态\n"
            "<code>/queue</code> 下载队列管理\n"
            "<code>/retry</code> &lt;id|all&gt; 重试失败任务\n"
            "<code>/cancel</code> &lt;id|gid&gt; 取消任务\n"
            "<code>/clear</code> 清理已完成任务\n"
            "<code>/stats</code> 库本数与队列摘要\n"
            "<code>/scan</code> 触发图库扫描\n"
            "<code>/storage</code> 磁盘与存储空间\n"
            "<code>/quota</code> EH 配额查询\n"
            "<code>/cookie</code> Cookie 健康检查\n"
            "<code>/tasks</code> 后台长任务列表\n"
            "<code>/kill</code> &lt;task&gt; 中断后台任务\n"
            "<code>/ping</code> 连通性测试\n"
            "<code>/help</code> 显示帮助\n"
            "直接粘贴画廊 URL 即可入队。"
        ),
        "bot_pong": "🏓 Pong！响应耗时 <b>{latency:.0f}</b> ms",
        "bot_pong_simple": "🏓 Pong！",
        "bot_status_detail": "📋 系统运行正常\n下载状态：{status}\n系统运行时间：<b>{uptime}</b>",
        "bot_cookie_valid": "🍪 E-Hentai Cookie 状态正常（有效）\n检测时间：<code>{checked_at}</code>",
        "bot_cookie_warning": "⚠️ E-Hentai Cookie 状态异常：{detail}\n检测时间：<code>{checked_at}</code>",
        "bot_cookie_invalid": "❌ E-Hentai Cookie 已失效或未登录：{detail}",
        "bot_cookie_not_configured": "⚙️ 尚未配置 E-Hentai Cookie",
        "bot_quota_ok": (
            "📊 <b>E-Hentai 配额状态</b>\n"
            "• 图像配额：<b>{current}</b> / <b>{limit}</b>\n"
            "• 剩余额度：<b>{remaining}</b>\n"
            "• GP 余额：<b>{gp}</b>"
        ),
        "bot_quota_no_gp": (
            "📊 <b>E-Hentai 配额状态</b>\n"
            "• 图像配额：<b>{current}</b> / <b>{limit}</b>\n"
            "• 剩余额度：<b>{remaining}</b>"
        ),
        "bot_quota_fail": "❌ 无法获取 E-Hentai 配额：{detail}",
        "bot_storage": (
            "💾 <b>存储空间使用情况</b>\n"
            "• 图库目录：<b>{library}</b>{lib_extra}\n"
            "• 下载缓存：<b>{downloads}</b>\n"
            "• 临时缓存：<b>{cache}</b>{cache_extra}\n"
            "• 磁盘总览：已用 <b>{disk_used}</b> / <b>{disk_total}</b>（可用 <b>{disk_free}</b>，[{bar}] <b>{disk_pct}%</b>）"
        ),
        "bot_storage_nodisk": (
            "💾 <b>存储空间使用情况</b>\n"
            "• 图库目录：<b>{library}</b>{lib_extra}\n"
            "• 下载缓存：<b>{downloads}</b>\n"
            "• 临时缓存：<b>{cache}</b>{cache_extra}"
        ),
        "bot_scan_started": "🔎 图库扫描已启动，正在后台扫描文件…",
        "bot_scan_running": "⏳ 图库扫描正在进行中…（已扫描：<b>{scanned}</b>）",
        "bot_scan_paused": "⏸ 全局下载已暂停，无法启动图库扫描",
        "bot_scan_failed": "❌ 启动图库扫描失败：{detail}",
        "bot_clear_ok": "🧹 已清理 <b>{count}</b> 条已完成的下载历史记录",
        "bot_clear_empty": "📭 没有已完成的任务需要清理",
        "bot_retry_ok": "🔄 已重新入队任务 <code>{id}</code>（gid <code>{gid}</code>）",
        "bot_retry_all_ok": "🔄 已重新入队 <b>{count}</b> 个失败的任务",
        "bot_retry_none": "📭 没有失败的任务需要重试",
        "bot_retry_not_found": "❌ 找不到任务 <code>{ident}</code> 或该任务不可重试",
        "bot_retry_usage": "用法：<code>/retry &lt;id|all&gt;</code>",
        "bot_tasks_empty": "📋 当前没有正在运行的后台长任务",
        "bot_tasks_head": "📋 <b>后台运行中的长任务</b>（共 {count} 个）：",
        "bot_tasks_line": "• <code>{task}</code>：{progress}（启动于 {started_at}）",
        "bot_kill_usage": "用法：<code>/kill &lt;task_name&gt;</code>",
        "bot_kill_ok": "🛑 已向任务 <code>{task}</code> 发送中断请求（状态：{status}）",
        "bot_kill_not_found": "❌ 找不到运行中的任务 <code>{task}</code>",
        "bot_db_not_ready": "❌ 数据库未就绪",
        "bot_dispatch_error": "执行操作时出错",
        "bot_storage_fail": "❌ 存储检查失败：{detail}",
        "bot_kill_failed": "❌ 中断任务失败：{detail}",
        "bot_btn_refresh": "🔄 刷新",
        "bot_btn_clear_done": "🧹 清理完成",
        "bot_btn_retry_all": "🔁 重试全部",
        "bot_btn_refresh_tasks": "🔄 刷新任务",
        "bot_btn_kill_task": "🛑 中断 {task}",
        "bot_btn_redownload": "🔄 重新下载",
        "bot_btn_eh_link": "🌐 EH 链接",
        "bot_btn_random_again": "🎲 换一本",
        "bot_cb_redownloading": "正在请求重新下载…",
        "bot_search_usage": "🔍 用法：<code>/search &lt;关键词或GID&gt;</code>",
        "bot_search_empty": "🔍 未找到匹配「<b>{query}</b>」的本地画廊",
        "bot_search_head": "🔍 <b>本地画廊搜索</b>（第 {page}/{total_pages} 页，共 {total} 本）：",
        "bot_search_expired": "🔍 搜索已过期，请重新发送 /search",
        "bot_info_usage": "ℹ️ 用法：<code>/info &lt;gid&gt;</code>",
        "bot_info_gid": "• <b>GID</b>：<code>{gid}</code>",
        "bot_info_category": "• <b>分类</b>：{category}",
        "bot_info_pages": "• <b>页数</b>：{pages} 页",
        "bot_info_size": "• <b>大小</b>：{size}",
        "bot_info_rating": "• <b>评分</b>：⭐ {rating}",
        "bot_info_uploader": "• <b>上传者</b>：{uploader}",
        "bot_info_tags": "• <b>标签</b>：{tags}",
        "bot_gallery_not_found": "❌ 本地未找到 GID <code>{gid}</code> 的画廊记录",
        "bot_random_empty": "📭 本地图库暂无可推荐的画廊",
        "bot_redownload_usage": "🔄 用法：<code>/redownload &lt;gid&gt;</code>",
        "bot_redownload_no_token": (
            "❌ 找不到画廊 <code>{gid}</code> 的访问 Token，"
            "请在聊天中直接发送该画廊的完整 URL 进行下载。"
        ),
        "bot_redownload_queued": "🔄 已将画廊 <b>{title}</b>（GID: <code>{gid}</code>）加入下载队列",
        "bot_fav_no_cookie": "⚠️ 尚未配置 ExHentai Cookie，无法同步云端收藏夹。",
        "bot_fav_sync_ok": "✅ 收藏夹分类同步成功，共获取到 <b>{count}</b> 个云端分类。",
        "bot_fav_sync_fail": "❌ 收藏夹同步失败：{detail}",
        "bot_fav_download_usage": "📥 用法：<code>/fav_download [favcat (0-9)]</code>",
        "bot_fav_cat_range": "分类编号必须在 0 到 9 之间",
        "bot_fav_cat_number": "分类编号必须为数字 (0-9)",
        "bot_fav_cat_one": "分类 {favcat}",
        "bot_fav_cat_all": "全部分类（{count} 个）",
        "bot_fav_download_queued": (
            "📥 已触发 <b>{cat}</b> 缺本下载任务，共将 <b>{count}</b> 本未入库画廊加入下载队列。"
        ),
        "bot_fav_download_started": "📥 已触发 <b>{cat}</b> 缺本下载与元数据补全长任务。",
        "bot_fav_check_no_service": "❌ 收藏夹服务未初始化，无法启动检查。",
        "bot_fav_check_started": "⏳ 已启动全量收藏夹检查长任务（共 <b>{count}</b> 个分类）。",
        "bot_queue_empty": "📭 队列为空（无等待 / 进行中 / 失败）",
        "bot_queue_head": "📋 下载队列：等待 <b>{pending}</b>，进行中 <b>{running}</b>，失败 <b>{failed}</b>",
        "bot_queue_line": "{status} <code>{id}</code> gid <code>{gid}</code> {title}",
        "bot_queue_more": "… 还有 {n} 条未列出",
        "bot_cancel_ok": "✅ 已取消任务 <code>{id}</code>（gid <code>{gid}</code>）",
        "bot_cancel_not_found": "❌ 找不到任务 <code>{ident}</code>",
        "bot_cancel_usage": "用法：<code>/cancel &lt;id|gid&gt;</code>",
        "bot_stats": (
            "📊 库 <b>{galleries}</b> 本；队列等待 <b>{pending}</b>，"
            "下载中 <b>{downloading}</b>，失败 <b>{failed}</b>"
        ),
        "download_gone": "❌ <b>{title}</b>已删除或不存在（404）",
        "download_updated": (
            "🔄 原 gid <code>{old}</code> → 新版 gid <code>{new}</code>，更新 <b>{title}</b>"
        ),
        "archive_start": "📦 批量归档开始：共 <b>{total}</b> 本",
        "archive_ok": "📦 归档完成 <b>{title}</b>",
        "archive_fail": "❌ 归档失败 <b>{title}</b>：{detail}",
        "archive_fail_nodetail": "❌ 归档失败 <b>{title}</b>",
        "archive_batch_ok": "📦 批量归档完成：完成 <b>{done}</b>，跳过 <b>{skipped}</b>",
        "archive_batch_fail": "❌ 批量归档结束：完成 <b>{done}</b>，跳过 <b>{skipped}</b>，失败 <b>{failed}</b>",
        "archive_summary_head": "📦 归档汇总：完成 <b>{ok}</b>，失败 <b>{fail}</b>",
        "test": "📡 Telegram 连接测试 OK",
    },
    "en": {
        "download_ok_verb": "Download complete: ",
        "download_ok_title": "<b>{title}</b>",
        "download_ok_pages": " ({pages} pages)",
        "download_fail_verb": "Download failed: ",
        "download_fail_title": "<b>{title}</b>",
        "download_fail_detail": ": {detail}",
        "download_summary_head": "📊 Download summary: <b>{ok}</b> completed, <b>{fail}</b> failed",
        "list_sep": ", ",
        "download_more_failures": "… and {n} more failures not listed",
        "scan_ok": "🔎 Library scan complete: <b>{new}</b> new, <b>{removed}</b> removed",
        "scan_dup": "⚠️ <b>{n}</b> duplicate-copy group(s) found (gid <code>{gids}</code>)",
        "scan_failed": "❌ Library scan failed: {error}",
        "ellipsis": ", …",
        "fav_category": "Favorites category {favcat} ({name})",
        "fav_category_noname": "Favorites category {favcat}",
        "fav_check_failed": "⭐ {cat}: check failed after {n} attempts",
        "fav_enqueue_failed": "⭐ {cat}: download failed for gid <code>{gid}</code>",
        "fav_summary": "⭐ {cat}: <b>{new}</b> new galleries, <b>{queued}</b> queued",
        "bot_paused": "⏸ Downloads paused",
        "bot_resumed": "▶️ Downloads resumed",
        "bot_status_running": "📋 GalleryVault downloads are running",
        "bot_status_paused": "📋 GalleryVault downloads are paused",
        "bot_queued": "📥 Queued gallery <code>{gid}</code>",
        "bot_queued_title": "📥 Queued <b>{title}</b> (gid <code>{gid}</code>)",
        "bot_queued_updated": (
            "📥 Original gid <code>{old}</code> updated to gid <code>{new}</code>, "
            "queued <b>{title}</b>"
        ),
        "bot_gone": "❌ <b>{title}</b> deleted or not found (404), not queued",
        "bot_already_local": "✅ Newer version already in library: <b>{title}</b> (gid <code>{gid}</code>)",
        "bot_help": (
            "🤖 Commands:\n"
            "<code>/pause</code> pause downloads\n"
            "<code>/resume</code> resume downloads\n"
            "<code>/status</code> show system status\n"
            "<code>/queue</code> download queue\n"
            "<code>/retry</code> &lt;id|all&gt; retry failed tasks\n"
            "<code>/cancel</code> &lt;id|gid&gt; cancel a task\n"
            "<code>/clear</code> clear completed tasks\n"
            "<code>/stats</code> library count and queue summary\n"
            "<code>/scan</code> trigger library scan\n"
            "<code>/storage</code> storage and disk usage\n"
            "<code>/quota</code> EH image quota\n"
            "<code>/cookie</code> cookie health check\n"
            "<code>/tasks</code> running background tasks\n"
            "<code>/kill</code> &lt;task&gt; cancel background task\n"
            "<code>/ping</code> connectivity test\n"
            "<code>/help</code> this help\n"
            "Paste a gallery URL to enqueue."
        ),
        "bot_pong": "🏓 Pong! Latency: <b>{latency:.0f}</b> ms",
        "bot_pong_simple": "🏓 Pong!",
        "bot_status_detail": "📋 System is running\nDownload status: {status}\nSystem uptime: <b>{uptime}</b>",
        "bot_cookie_valid": "🍪 E-Hentai cookies are healthy (valid)\nChecked: <code>{checked_at}</code>",
        "bot_cookie_warning": "⚠️ E-Hentai cookies warning: {detail}\nChecked: <code>{checked_at}</code>",
        "bot_cookie_invalid": "❌ E-Hentai cookies invalid or not logged in: {detail}",
        "bot_cookie_not_configured": "⚙️ E-Hentai cookies not configured",
        "bot_quota_ok": (
            "📊 <b>E-Hentai Quota Status</b>\n"
            "• Image quota: <b>{current}</b> / <b>{limit}</b>\n"
            "• Remaining: <b>{remaining}</b>\n"
            "• GP balance: <b>{gp}</b>"
        ),
        "bot_quota_no_gp": (
            "📊 <b>E-Hentai Quota Status</b>\n"
            "• Image quota: <b>{current}</b> / <b>{limit}</b>\n"
            "• Remaining: <b>{remaining}</b>"
        ),
        "bot_quota_fail": "❌ Failed to fetch E-Hentai quota: {detail}",
        "bot_storage": (
            "💾 <b>Storage Usage</b>\n"
            "• Library: <b>{library}</b>{lib_extra}\n"
            "• Downloads: <b>{downloads}</b>\n"
            "• Cache: <b>{cache}</b>{cache_extra}\n"
            "• Disk total: Used <b>{disk_used}</b> / <b>{disk_total}</b> (Free <b>{disk_free}</b>, [{bar}] <b>{disk_pct}%</b>)"
        ),
        "bot_storage_nodisk": (
            "💾 <b>Storage Usage</b>\n"
            "• Library: <b>{library}</b>{lib_extra}\n"
            "• Downloads: <b>{downloads}</b>\n"
            "• Cache: <b>{cache}</b>{cache_extra}"
        ),
        "bot_scan_started": "🔎 Library scan triggered, scanning files in background…",
        "bot_scan_running": "⏳ Library scan is already in progress… (scanned: <b>{scanned}</b>)",
        "bot_scan_paused": "⏸ Downloads are paused, cannot start scan",
        "bot_scan_failed": "❌ Failed to trigger library scan: {detail}",
        "bot_clear_ok": "🧹 Cleared <b>{count}</b> completed download task(s)",
        "bot_clear_empty": "📭 No completed tasks to clear",
        "bot_retry_ok": "🔄 Re-enqueued task <code>{id}</code> (gid <code>{gid}</code>)",
        "bot_retry_all_ok": "🔄 Re-enqueued <b>{count}</b> failed task(s)",
        "bot_retry_none": "📭 No failed tasks to retry",
        "bot_retry_not_found": "❌ Task <code>{ident}</code> not found or not in retryable status",
        "bot_retry_usage": "Usage: <code>/retry &lt;id|all&gt;</code>",
        "bot_tasks_empty": "📋 No background tasks currently running",
        "bot_tasks_head": "📋 <b>Running Background Tasks</b> ({count} total):",
        "bot_tasks_line": "• <code>{task}</code>: {progress} (started at {started_at})",
        "bot_kill_usage": "Usage: <code>/kill &lt;task_name&gt;</code>",
        "bot_kill_ok": "🛑 Cancellation requested for task <code>{task}</code> (status: {status})",
        "bot_kill_not_found": "❌ Running task <code>{task}</code> not found",
        "bot_db_not_ready": "❌ Database is not ready",
        "bot_dispatch_error": "Error executing action",
        "bot_storage_fail": "❌ Storage check failed: {detail}",
        "bot_kill_failed": "❌ Failed to cancel task: {detail}",
        "bot_btn_refresh": "🔄 Refresh",
        "bot_btn_clear_done": "🧹 Clear done",
        "bot_btn_retry_all": "🔁 Retry all",
        "bot_btn_refresh_tasks": "🔄 Refresh tasks",
        "bot_btn_kill_task": "🛑 Cancel {task}",
        "bot_btn_redownload": "🔄 Redownload",
        "bot_btn_eh_link": "🌐 EH link",
        "bot_btn_random_again": "🎲 Another",
        "bot_cb_redownloading": "Requesting redownload…",
        "bot_search_usage": "🔍 Usage: <code>/search &lt;keyword or GID&gt;</code>",
        "bot_search_empty": '🔍 No local galleries matching "<b>{query}</b>"',
        "bot_search_head": (
            "🔍 <b>Local gallery search</b> (page {page}/{total_pages}, {total} total):"
        ),
        "bot_search_expired": "🔍 Search expired, please send /search again",
        "bot_info_usage": "ℹ️ Usage: <code>/info &lt;gid&gt;</code>",
        "bot_info_gid": "• <b>GID</b>: <code>{gid}</code>",
        "bot_info_category": "• <b>Category</b>: {category}",
        "bot_info_pages": "• <b>Pages</b>: {pages}",
        "bot_info_size": "• <b>Size</b>: {size}",
        "bot_info_rating": "• <b>Rating</b>: ⭐ {rating}",
        "bot_info_uploader": "• <b>Uploader</b>: {uploader}",
        "bot_info_tags": "• <b>Tags</b>: {tags}",
        "bot_gallery_not_found": "❌ No local gallery with GID <code>{gid}</code>",
        "bot_random_empty": "📭 No galleries available in the local library",
        "bot_redownload_usage": "🔄 Usage: <code>/redownload &lt;gid&gt;</code>",
        "bot_redownload_no_token": (
            "❌ No access token for gallery <code>{gid}</code>. "
            "Paste the full gallery URL in chat to download."
        ),
        "bot_redownload_queued": "🔄 Queued gallery <b>{title}</b> (GID: <code>{gid}</code>)",
        "bot_fav_no_cookie": "⚠️ ExHentai cookies are not configured; cannot sync favorites.",
        "bot_fav_sync_ok": "✅ Favorite categories synced, <b>{count}</b> remote categories found.",
        "bot_fav_sync_fail": "❌ Favorite sync failed: {detail}",
        "bot_fav_download_usage": "📥 Usage: <code>/fav_download [favcat (0-9)]</code>",
        "bot_fav_cat_range": "Category number must be between 0 and 9",
        "bot_fav_cat_number": "Category number must be a digit (0-9)",
        "bot_fav_cat_one": "category {favcat}",
        "bot_fav_cat_all": "all categories ({count})",
        "bot_fav_download_queued": (
            "📥 Started missing-gallery download for <b>{cat}</b>; queued <b>{count}</b> galleries."
        ),
        "bot_fav_download_started": (
            "📥 Started missing-gallery download and metadata sync for <b>{cat}</b>."
        ),
        "bot_fav_check_no_service": "❌ Favorites service is not initialized.",
        "bot_fav_check_started": "⏳ Started a full favorites check (<b>{count}</b> categories).",
        "bot_queue_empty": "📭 Queue is empty (no pending / running / failed)",
        "bot_queue_head": (
            "📋 Download queue: <b>{pending}</b> pending, "
            "<b>{running}</b> running, <b>{failed}</b> failed"
        ),
        "bot_queue_line": "{status} <code>{id}</code> gid <code>{gid}</code> {title}",
        "bot_queue_more": "… and {n} more not listed",
        "bot_cancel_ok": "✅ Cancelled task <code>{id}</code> (gid <code>{gid}</code>)",
        "bot_cancel_not_found": "❌ Task <code>{ident}</code> not found",
        "bot_cancel_usage": "Usage: <code>/cancel &lt;id|gid&gt;</code>",
        "bot_stats": (
            "📊 Library <b>{galleries}</b>; queue pending <b>{pending}</b>, "
            "downloading <b>{downloading}</b>, failed <b>{failed}</b>"
        ),
        "download_gone": "❌ <b>{title}</b> deleted or not found (404)",
        "download_updated": (
            "🔄 Original gid <code>{old}</code> → new gid <code>{new}</code>, "
            "updating <b>{title}</b>"
        ),
        "archive_start": "📦 Batch archive started: <b>{total}</b> galleries",
        "archive_ok": "📦 Archive complete: <b>{title}</b>",
        "archive_fail": "❌ Archive failed: <b>{title}</b>: {detail}",
        "archive_fail_nodetail": "❌ Archive failed: <b>{title}</b>",
        "archive_batch_ok": "📦 Batch archive complete: <b>{done}</b> completed, <b>{skipped}</b> skipped",
        "archive_batch_fail": "❌ Batch archive finished: <b>{done}</b> completed, <b>{skipped}</b> skipped, <b>{failed}</b> failed",
        "archive_summary_head": "📦 Archive summary: <b>{ok}</b> completed, <b>{fail}</b> failed",
        "test": "📡 Telegram connection test OK",
    },
}

_TAG_RE = re.compile(r"<[^>]+>")


def normalize_lang(lang: object) -> str:
    return lang if lang in LANGS else "zh"


def esc(value: object) -> str:
    """HTML-escape a value for Telegram ``parse_mode="HTML"`` messages."""
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(lang: str, key: str) -> str:
    return _TEMPLATES[normalize_lang(lang)][key]


def bot_text(lang: str, key: str, **kwargs: object) -> str:
    """Look up a bot UI string and optionally interpolate HTML-safe values."""
    text = _t(lang, key)
    return text.format(**kwargs) if kwargs else text


def _plain_len(text: str) -> int:
    """Length of the rendered text (Telegram counts this, not HTML markup)."""
    return len(_TAG_RE.sub("", text))


# --- downloads --------------------------------------------------------------


def _entry_ok(title: str, pages: str | None, lang: str) -> str:
    text = _t(lang, "download_ok_title").format(title=esc(title))
    if pages not in (None, ""):
        text += _t(lang, "download_ok_pages").format(pages=esc(pages))
    return text


def _entry_fail(title: str, detail: str | None, lang: str) -> str:
    text = _t(lang, "download_fail_title").format(title=esc(title))
    if detail:
        text += _t(lang, "download_fail_detail").format(detail=esc(detail))
    return text


def download_ok(title: str, pages: str | None = None, lang: str = "zh") -> str:
    """Single successful-download message."""
    return "✅ " + _t(lang, "download_ok_verb") + _entry_ok(title, pages, lang)


def is_gone_detail(detail: str | None) -> bool:
    if not detail:
        return False
    text = detail.lower()
    return (
        "gallerygoneerror" in text
        or "deleted or not found" in text
        or "does not exist on exhentai" in text
    )


def download_fail(title: str, detail: str | None = None, lang: str = "zh") -> str:
    """Single failed-download message."""
    if is_gone_detail(detail):
        return _t(lang, "download_gone").format(title=esc(title))
    return "❌ " + _t(lang, "download_fail_verb") + _entry_fail(title, detail, lang)


def download_updated(old_gid: object, new_gid: object, title: str, lang: str = "zh") -> str:
    return _t(lang, "download_updated").format(old=esc(old_gid), new=esc(new_gid), title=esc(title))


def download_summary(
    ok_entries: list[tuple[str, str | None]],
    fail_entries: list[tuple[str, str | None]],
    lang: str = "zh",
) -> str:
    """Digest of a download batch; collapses into a single message."""
    ok, fail = len(ok_entries), len(fail_entries)
    if ok == 1 and fail == 0:
        return download_ok(*ok_entries[0], lang)
    if ok == 0 and fail == 1:
        return download_fail(*fail_entries[0], lang=lang)
    text = _t(lang, "download_summary_head").format(ok=ok, fail=fail)
    if ok and ok <= LIST_TITLES_LIMIT:
        text += "\n✅ " + _t(lang, "list_sep").join(
            _entry_ok(title, pages, lang) for title, pages in ok_entries
        )
    if fail:
        lines: list[str] = []
        for title, detail in fail_entries:
            if is_gone_detail(detail):
                entry = (
                    _t(lang, "download_gone").format(title=esc(title)).removeprefix("❌ ").strip()
                )
            else:
                entry = _entry_fail(title, detail, lang)
            candidate = "\n❌ " + "\n".join(lines + [entry])
            if _plain_len(text) + _plain_len(candidate) > MAX_MESSAGE_CHARS - 100:
                lines.append(
                    _t(lang, "download_more_failures").format(n=len(fail_entries) - len(lines))
                )
                break
            lines.append(entry)
        text += "\n❌ " + "\n".join(lines)
    return text


# --- library scan -----------------------------------------------------------


def scan_summary(
    persisted: int, expunged: int, duplicates: int, duplicate_gids: list[int], lang: str = "zh"
) -> str:
    text = _t(lang, "scan_ok").format(new=persisted, removed=expunged)
    if duplicates:
        gids = [str(g) for g in (duplicate_gids or [])][:5]
        shown = ", ".join(gids)
        if len(duplicate_gids or []) > 5:
            shown += _t(lang, "ellipsis")
        text += "\n" + _t(lang, "scan_dup").format(n=duplicates, gids=esc(shown))
    return text


def scan_failed(error: object, lang: str = "zh") -> str:
    return _t(lang, "scan_failed").format(error=esc(error))


# --- favorites --------------------------------------------------------------


def category_label(favcat: int, name: object = None, lang: str = "zh") -> str:
    if name:
        return _t(lang, "fav_category").format(favcat=favcat, name=esc(name))
    return _t(lang, "fav_category_noname").format(favcat=favcat)


def favorites_check_failed(favcat: int, name: object, attempts: int, lang: str = "zh") -> str:
    return _t(lang, "fav_check_failed").format(cat=category_label(favcat, name, lang), n=attempts)


def favorites_enqueue_failed(favcat: int, name: object, gid: object, lang: str = "zh") -> str:
    return _t(lang, "fav_enqueue_failed").format(
        cat=category_label(favcat, name, lang), gid=esc(gid)
    )


def favorites_summary(favcat: int, name: object, new: int, queued: int, lang: str = "zh") -> str:
    return _t(lang, "fav_summary").format(
        cat=category_label(favcat, name, lang), new=new, queued=queued
    )


# --- Telegram bot replies ---------------------------------------------------


def format_bytes(size: float | None) -> str:
    """Format bytes into a human readable string."""
    if size is None:
        return "N/A"
    try:
        val = float(size)
    except (TypeError, ValueError):
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(val) < 1024.0 or unit == "TB":
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} TB"


def bot_paused(lang: str = "zh") -> str:
    return _t(lang, "bot_paused")


def bot_resumed(lang: str = "zh") -> str:
    return _t(lang, "bot_resumed")


def bot_status(
    paused: bool,
    lang: str = "zh",
    uptime_seconds: float | None = None,
    queue_counts: dict | None = None,
) -> str:
    if isinstance(lang, (int, float)) and (
        uptime_seconds is None or isinstance(uptime_seconds, str)
    ):
        uptime_seconds, lang = float(lang), uptime_seconds or "zh"
    status_text = _t(lang, "bot_status_paused" if paused else "bot_status_running")
    if uptime_seconds is not None:
        days, rem = divmod(int(uptime_seconds), 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        if days > 0:
            uptime_str = f"{days}d {hours}h {mins}m"
        elif hours > 0:
            uptime_str = f"{hours}h {mins}m {secs}s"
        else:
            uptime_str = f"{mins}m {secs}s"
        text = _t(lang, "bot_status_detail").format(status=status_text, uptime=uptime_str)
    else:
        text = status_text
    if queue_counts:
        pending = int(queue_counts.get("pending") or 0)
        downloading = int(queue_counts.get("downloading") or queue_counts.get("running") or 0)
        failed = int(queue_counts.get("failed") or 0)
        if lang == "zh":
            if failed > 0:
                q_line = f"📥 队列：等待中 {pending}，下载中 {downloading}，失败 {failed}"
            else:
                q_line = f"📥 队列：等待中 {pending}，下载中 {downloading}"
        else:
            if failed > 0:
                q_line = f"📥 Queue: {pending} pending, {downloading} downloading, {failed} failed"
            else:
                q_line = f"📥 Queue: {pending} pending, {downloading} downloading"
        text = f"{text}\n{q_line}"
    return text


def bot_queued(gid: object, lang: str = "zh", title: object | None = None) -> str:
    if title:
        return _t(lang, "bot_queued_title").format(gid=esc(gid), title=esc(title))
    return _t(lang, "bot_queued").format(gid=esc(gid))


def bot_queued_updated(old_gid: object, new_gid: object, title: object, lang: str = "zh") -> str:
    return _t(lang, "bot_queued_updated").format(
        old=esc(old_gid), new=esc(new_gid), title=esc(title)
    )


def bot_gone(title: object, lang: str = "zh") -> str:
    return _t(lang, "bot_gone").format(title=esc(title))


def bot_already_local(gid: object, title: object, lang: str = "zh") -> str:
    return _t(lang, "bot_already_local").format(gid=esc(gid), title=esc(title))


def bot_help(lang: str = "zh") -> str:
    return _t(lang, "bot_help")


def bot_stats(
    galleries: int,
    pending: int,
    downloading: int,
    failed: int,
    lang: str = "zh",
) -> str:
    return _t(lang, "bot_stats").format(
        galleries=int(galleries),
        pending=int(pending),
        downloading=int(downloading),
        failed=int(failed),
    )


def bot_queue(
    rows: list[dict[str, object]],
    counts: dict[str, int],
    lang: str = "zh",
) -> str:
    pending = int(counts.get("pending") or 0)
    running = int(counts.get("downloading") or 0)
    failed = int(counts.get("failed") or 0)
    if pending + running + failed == 0:
        return _t(lang, "bot_queue_empty")
    text = _t(lang, "bot_queue_head").format(pending=pending, running=running, failed=failed)
    for listed, row in enumerate(rows):
        line = "\n" + _t(lang, "bot_queue_line").format(
            status=esc(row.get("status") or ""),
            id=esc(row.get("id") or ""),
            gid=esc(row.get("gid") or ""),
            title=esc(row.get("title") or ""),
        )
        if _plain_len(text) + _plain_len(line) > MAX_MESSAGE_CHARS - 80:
            remain = max(0, pending + running + failed - listed)
            text += "\n" + _t(lang, "bot_queue_more").format(n=remain)
            break
        text += line
    return text


def bot_cancel_ok(task_id: object, gid: object, lang: str = "zh") -> str:
    return _t(lang, "bot_cancel_ok").format(id=esc(task_id), gid=esc(gid))


def bot_cancel_not_found(ident: object, lang: str = "zh") -> str:
    return _t(lang, "bot_cancel_not_found").format(ident=esc(ident))


def bot_cancel_usage(lang: str = "zh") -> str:
    return _t(lang, "bot_cancel_usage")


def bot_pong(latency_ms: float | None = None, lang: str = "zh") -> str:
    if latency_ms is not None:
        return _t(lang, "bot_pong").format(latency=latency_ms)
    return _t(lang, "bot_pong_simple")


def bot_cookie_health(
    state: str,
    detail: str | None = None,
    checked_at: str | None = None,
    lang: str = "zh",
) -> str:
    if state == "not_configured":
        return _t(lang, "bot_cookie_not_configured")
    if state in ("valid", "ok"):
        return _t(lang, "bot_cookie_valid").format(checked_at=esc(checked_at or "N/A"))
    if state in ("not_logged_in", "expired"):
        return _t(lang, "bot_cookie_invalid").format(detail=esc(detail or state))
    return _t(lang, "bot_cookie_warning").format(
        detail=esc(detail or state), checked_at=esc(checked_at or "N/A")
    )


def bot_quota(
    current: int | None = None,
    limit: int | None = None,
    gp: int | str | None = None,
    detail: str | None = None,
    lang: str = "zh",
) -> str:
    if detail:
        return _t(lang, "bot_quota_fail").format(detail=esc(detail))
    has_limits = current is not None and limit is not None
    has_gp = gp is not None and str(gp).strip() != ""
    if not has_limits and not has_gp:
        return _t(lang, "bot_quota_fail").format(detail="Quota unavailable")
    if not has_limits:
        msg = (
            "📊 <b>E-Hentai 配额状态</b>\n• GP 余额：<b>{gp}</b>"
            if lang == "zh"
            else "📊 <b>E-Hentai Quota Status</b>\n• GP balance: <b>{gp}</b>"
        )
        return msg.format(gp=esc(gp))
    remaining = max(0, limit - current)
    if has_gp:
        return _t(lang, "bot_quota_ok").format(
            current=current, limit=limit, remaining=remaining, gp=esc(gp)
        )
    return _t(lang, "bot_quota_no_gp").format(current=current, limit=limit, remaining=remaining)


def bot_storage(
    library_bytes: int | None = None,
    downloads_bytes: int | None = None,
    cache_bytes: int | None = None,
    disk_total: int | None = None,
    disk_used: int | None = None,
    disk_free: int | None = None,
    cold_bytes: int | None = 0,
    lang: str = "zh",
    gallery_count: int | None = None,
    file_count: int | None = None,
    thumb_count: int | None = None,
) -> str:
    lib_s = format_bytes(library_bytes)
    dl_s = format_bytes(downloads_bytes)
    cache_s = format_bytes(cache_bytes)
    cold_s = format_bytes(cold_bytes) if (cold_bytes and cold_bytes > 0) else None

    lib_extra = ""
    if gallery_count is not None:
        if file_count is not None:
            lib_extra = (
                f" ({gallery_count} 本 / {file_count} 图)"
                if lang == "zh"
                else f" ({gallery_count} galleries / {file_count} images)"
            )
        else:
            lib_extra = (
                f" ({gallery_count} 本)" if lang == "zh" else f" ({gallery_count} galleries)"
            )

    cache_extra = ""
    if thumb_count is not None:
        cache_extra = (
            f" (约 {thumb_count} 张缩略图)" if lang == "zh" else f" (~{thumb_count} thumbs)"
        )

    if disk_total and disk_total > 0 and (disk_used is not None or disk_free is not None):
        if disk_used is not None:
            used_val = disk_used
            free_val = disk_free if disk_free is not None else max(0, disk_total - disk_used)
        else:
            free_val = disk_free  # type: ignore[assignment]
            used_val = max(0, disk_total - free_val)
        pct = round((used_val / disk_total) * 100, 1)
        pct_clamped = max(0.0, min(100.0, pct))
        filled = round(pct_clamped / 10.0)
        bar = "█" * filled + "░" * (10 - filled)
        text = _t(lang, "bot_storage").format(
            library=lib_s,
            lib_extra=lib_extra,
            downloads=dl_s,
            cache=cache_s,
            cache_extra=cache_extra,
            disk_used=format_bytes(used_val),
            disk_total=format_bytes(disk_total),
            disk_free=format_bytes(free_val),
            disk_pct=pct,
            bar=bar,
        )
    else:
        text = _t(lang, "bot_storage_nodisk").format(
            library=lib_s,
            lib_extra=lib_extra,
            downloads=dl_s,
            cache=cache_s,
            cache_extra=cache_extra,
        )
    if cold_s:
        target = (
            f"• 图库目录：<b>{lib_s}</b>{lib_extra}\n"
            if lang == "zh"
            else f"• Library: <b>{lib_s}</b>{lib_extra}\n"
        )
        cold_insert = (
            f"• 冷归档库：<b>{cold_s}</b>\n"
            if lang == "zh"
            else f"• Cold storage: <b>{cold_s}</b>\n"
        )
        if target in text:
            text = text.replace(target, target + cold_insert, 1)
        else:
            text += f"\n{cold_insert.strip()}"
    return text


def bot_scan_triggered(
    status: str,
    scanned: int | None = None,
    detail: str | None = None,
    lang: str = "zh",
) -> str:
    if status == "started":
        return _t(lang, "bot_scan_started")
    if status == "running":
        return _t(lang, "bot_scan_running").format(scanned=scanned or 0)
    if status == "paused":
        return _t(lang, "bot_scan_paused")
    return _t(lang, "bot_scan_failed").format(detail=esc(detail or status))


def bot_clear_success(count: int, lang: str = "zh") -> str:
    if count <= 0:
        return _t(lang, "bot_clear_empty")
    return _t(lang, "bot_clear_ok").format(count=count)


def bot_retry_ok(task_id: object, gid: object, lang: str = "zh") -> str:
    return _t(lang, "bot_retry_ok").format(id=esc(task_id), gid=esc(gid))


def bot_retry_all_ok(count: int, lang: str = "zh") -> str:
    if count <= 0:
        return _t(lang, "bot_retry_none")
    return _t(lang, "bot_retry_all_ok").format(count=count)


def bot_retry_none(lang: str = "zh") -> str:
    return _t(lang, "bot_retry_none")


def bot_retry_not_found(ident: object, lang: str = "zh") -> str:
    return _t(lang, "bot_retry_not_found").format(ident=esc(ident))


def bot_retry_usage(lang: str = "zh") -> str:
    return _t(lang, "bot_retry_usage")


def bot_tasks_list(tasks: list[dict[str, object]], lang: str = "zh") -> str:
    if not tasks:
        return _t(lang, "bot_tasks_empty")
    text = _t(lang, "bot_tasks_head").format(count=len(tasks))
    for item in tasks:
        task_name = esc(item.get("task") or "unknown")
        done = item.get("done")
        total = item.get("total")
        if done is not None and total is not None:
            progress = f"{done}/{total}"
        elif done is not None:
            progress = f"{done}"
        else:
            progress = esc(item.get("status") or "running")
        started = esc(item.get("started_at") or "unknown")
        line = "\n" + _t(lang, "bot_tasks_line").format(
            task=task_name, progress=progress, started_at=started
        )
        text += line
    return text


def bot_kill_usage(lang: str = "zh") -> str:
    return _t(lang, "bot_kill_usage")


def bot_kill_result(
    task: object, status: str = "cancelling", not_found: bool = False, lang: str = "zh"
) -> str:
    if not_found:
        return _t(lang, "bot_kill_not_found").format(task=esc(task))
    return _t(lang, "bot_kill_ok").format(task=esc(task), status=esc(status))


# --- misc -------------------------------------------------------------------


def test_message(lang: str = "zh") -> str:
    return _t(lang, "test")


# --- cold archive -----------------------------------------------------------


def archive_start(total: int, lang: str = "zh") -> str:
    return _t(lang, "archive_start").format(total=int(total))


def archive_ok(title: str, lang: str = "zh") -> str:
    return _t(lang, "archive_ok").format(title=esc(title))


def archive_fail(title: str, detail: str | None = None, lang: str = "zh") -> str:
    if detail:
        return _t(lang, "archive_fail").format(title=esc(title), detail=esc(detail))
    return _t(lang, "archive_fail_nodetail").format(title=esc(title))


def archive_batch_result(done: int, skipped: int, failed: int, lang: str = "zh") -> str:
    if failed > 0:
        return _t(lang, "archive_batch_fail").format(
            done=int(done), skipped=int(skipped), failed=int(failed)
        )
    return _t(lang, "archive_batch_ok").format(done=int(done), skipped=int(skipped))


def archive_summary(
    ok_entries: list[tuple[str, str | None]],
    fail_entries: list[tuple[str, str | None]],
    lang: str = "zh",
) -> str:
    ok, fail = len(ok_entries), len(fail_entries)
    if ok == 1 and fail == 0:
        return archive_ok(ok_entries[0][0], lang=lang)
    if ok == 0 and fail == 1:
        return archive_fail(fail_entries[0][0], fail_entries[0][1], lang=lang)
    text = _t(lang, "archive_summary_head").format(ok=ok, fail=fail)
    if ok and ok <= LIST_TITLES_LIMIT:
        text += "\n📦 " + _t(lang, "list_sep").join(
            _t(lang, "download_ok_title").format(title=esc(title)) for title, _ in ok_entries
        )
    if fail:
        lines: list[str] = []
        for title, detail in fail_entries:
            entry = _entry_fail(title, detail, lang)
            candidate = "\n❌ " + "\n".join(lines + [entry])
            if _plain_len(text) + _plain_len(candidate) > MAX_MESSAGE_CHARS - 100:
                lines.append(
                    _t(lang, "download_more_failures").format(n=len(fail_entries) - len(lines))
                )
                break
            lines.append(entry)
        text += "\n❌ " + "\n".join(lines)
    return text
