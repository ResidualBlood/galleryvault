#!/bin/sh
# Entrypoint: run with custom PUID/PGID if specified, otherwise default to root.
# /library is read-only and never touched.
set -e

# Validate PUID/PGID: must be valid non-negative integers
TARGET_UID="${PUID:-0}"
case "$TARGET_UID" in
    ''|*[!0-9]*)
        echo "[WARN] Invalid PUID '${TARGET_UID}'; falling back to root (0)." >&2
        TARGET_UID=0
        ;;
esac

TARGET_GID="${PGID:-$TARGET_UID}"
case "$TARGET_GID" in
    ''|*[!0-9]*)
        echo "[WARN] Invalid PGID '${TARGET_GID}'; falling back to UID (${TARGET_UID})." >&2
        TARGET_GID="$TARGET_UID"
        ;;
esac

if [ "$TARGET_UID" = "0" ]; then
    # Default: run as root (no privilege dropping or chown needed)
    export HOME=/root
    mkdir -p /downloads /gv-cache/logs 2>/dev/null || true
    alembic upgrade head
    exec uvicorn galleryvault.app.main:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips="172.16.0.0/12,127.0.0.1"
fi

# Custom UID/GID requested: drop privileges if currently running as root
if [ "$(id -u)" = "0" ]; then
    export HOME=/home/app

    # Ensure group and user exist and match the requested UID/GID
    groupmod -o -g "$TARGET_GID" app 2>/dev/null || groupadd -o -g "$TARGET_GID" app 2>/dev/null || true
    usermod -o -u "$TARGET_UID" -g "$TARGET_GID" -d /home/app app 2>/dev/null || useradd -o -u "$TARGET_UID" -g "$TARGET_GID" -d /home/app -m app 2>/dev/null || true

    mkdir -p /home/app /downloads /gv-cache/logs 2>/dev/null || true
    chown "$TARGET_UID:$TARGET_GID" /home/app /downloads 2>/dev/null || true
    chown -R "$TARGET_UID:$TARGET_GID" /gv-cache/logs 2>/dev/null || true

    # Fix ownership for cache tree once per UID/GID combination
    MARKER="/gv-cache/.gv-ownership-${TARGET_UID}-${TARGET_GID}"
    if [ ! -f "$MARKER" ]; then
        chown -R "$TARGET_UID:$TARGET_GID" /gv-cache 2>/dev/null || true
        touch "$MARKER" 2>/dev/null || true
        chown "$TARGET_UID:$TARGET_GID" "$MARKER" 2>/dev/null || true
        chmod 644 "$MARKER" 2>/dev/null || true
    fi

    exec setpriv --reuid="$TARGET_UID" --regid="$TARGET_GID" --init-groups "$0" "$@"
fi

# Re-executed as the unprivileged user
export HOME=/home/app
alembic upgrade head
# --proxy-headers: trust the nginx reverse proxy's X-Forwarded-* so login rate
# limiting keys on the real client IP instead of the shared proxy IP.  Only the
# private docker/proxy range is allowed to rewrite forwarded headers; the login
# bucket itself keys on X-Real-IP (set by nginx, unforgeable by clients).
exec uvicorn galleryvault.app.main:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips="172.16.0.0/12,127.0.0.1"
