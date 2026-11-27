#!/usr/bin/env bash
# Copy the freshly built SPA (dist/) and the new nginx.conf into the shared
# test frontend container.
#
# Run by the tester only, after building on the host:
#   npm --prefix frontend ci && npm --prefix frontend run build
#   bash frontend/scripts/test-stack-sync.sh
#
# Writers must not touch the test containers; acquire the `device:gv-test`
# lease before running this. Never pass credentials: the script takes no
# password/cookie arguments.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTAINER="${GV_TEST_FRONTEND_CONTAINER:-galleryvault-test-frontend}"
HTML_DIR="/usr/share/nginx/html"
NGINX_CONF="/etc/nginx/conf.d/default.conf"

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

[[ -f "$ROOT_DIR/dist/index.html" ]] || die "未找到 $ROOT_DIR/dist/index.html；先运行 npm ci && npm run build"
[[ -f "$ROOT_DIR/nginx.conf" ]] || die "未找到 $ROOT_DIR/nginx.conf"
command -v docker >/dev/null 2>&1 || die "找不到 docker"

# Guard rail: this script is only for the disposable test stack.
[[ "$CONTAINER" == *test* ]] || die "拒绝操作非测试容器：$CONTAINER"

running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)"
[[ "$running" == "true" ]] || die "测试前端容器 $CONTAINER 未运行；先在 /mnt/Exhentai 启动测试栈并确认已持有 device:gv-test 租约"

# Drop the previous build first: stale hashed bundles must not survive a swap.
docker exec "$CONTAINER" find "$HTML_DIR" -mindepth 1 -delete
docker cp "$ROOT_DIR/dist/." "$CONTAINER:$HTML_DIR/"
docker cp "$ROOT_DIR/nginx.conf" "$CONTAINER:$NGINX_CONF"

docker exec "$CONTAINER" nginx -t
docker exec "$CONTAINER" nginx -s reload

printf 'synced %s -> %s (nginx reloaded)\n' "$ROOT_DIR/dist" "$CONTAINER"
