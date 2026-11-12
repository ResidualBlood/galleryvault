#!/usr/bin/env bash
# Restore the legacy frontend (and its nginx.conf) into the shared test
# frontend container. Only needed for the upgrade / rollback drills and for
# verifying a hotfix to the old UI; the normal state from Batch 2 on is the new
# frontend.
#
# Run by the tester only, holding the `device:gv-test` lease. Takes no
# password/cookie arguments.
#
# Legacy files are read from the parent of this project root. While the new app
# lives in frontend/next/ that is frontend/; after the cutover the legacy files
# are deleted and this script refuses to run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LEGACY_DIR="$(cd "$ROOT_DIR/.." && pwd)"
CONTAINER="${GV_TEST_FRONTEND_CONTAINER:-galleryvault-test-frontend}"
HTML_DIR="/usr/share/nginx/html"
NGINX_CONF="/etc/nginx/conf.d/default.conf"

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

# `assets/core.js` exists only in the legacy bundle; it is the marker that the
# old frontend is still on disk (the cutover deletes it).
[[ -f "$LEGACY_DIR/assets/core.js" ]] || die "旧前端文件不在 $LEGACY_DIR（切换批已删除旧版，无法恢复）"
for file in index.html sw.js manifest.webmanifest nginx.conf; do
    [[ -f "$LEGACY_DIR/$file" ]] || die "缺少旧前端文件 $LEGACY_DIR/$file"
done
command -v docker >/dev/null 2>&1 || die "找不到 docker"

[[ "$CONTAINER" == *test* ]] || die "拒绝操作非测试容器：$CONTAINER"

running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)"
[[ "$running" == "true" ]] || die "测试前端容器 $CONTAINER 未运行；先在 /mnt/Exhentai 启动测试栈并确认已持有 device:gv-test 租约"

docker exec "$CONTAINER" find "$HTML_DIR" -mindepth 1 -delete
docker cp "$LEGACY_DIR/index.html" "$CONTAINER:$HTML_DIR/index.html"
docker cp "$LEGACY_DIR/sw.js" "$CONTAINER:$HTML_DIR/sw.js"
docker cp "$LEGACY_DIR/manifest.webmanifest" "$CONTAINER:$HTML_DIR/manifest.webmanifest"
docker cp "$LEGACY_DIR/assets" "$CONTAINER:$HTML_DIR/assets"
docker cp "$LEGACY_DIR/nginx.conf" "$CONTAINER:$NGINX_CONF"

docker exec "$CONTAINER" nginx -t
docker exec "$CONTAINER" nginx -s reload

printf 'restored legacy %s -> %s (nginx reloaded)\n' "$LEGACY_DIR" "$CONTAINER"
