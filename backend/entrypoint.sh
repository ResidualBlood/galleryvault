#!/bin/sh
# Entrypoint: run as the unprivileged `app` user after making the writable
# mount roots owned by it. /library is read-only and never touched.
set -e

# asyncpg probes ~/.postgresql for client certificates; point HOME at the app
# user's home so it falls back to plain (non-SSL) connections instead of
# trying to read /root/.postgresql as an unprivileged user.
export HOME=/home/app

if [ "$(id -u)" = "0" ]; then
    # Ownership of the mount roots. The thumbnail/cache tree is chowned
    # recursively so legacy root-owned subdirectories (remote-covers, thumbs)
    # stay writable for the app user; the downloads tree is only chowned at the
    # root to keep startup fast (the app creates subdirectories as it goes).
    chown app:app /downloads 2>/dev/null || true
    chown -R app:app /gv-cache 2>/dev/null || true
    exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

alembic upgrade head
# --proxy-headers: trust the nginx reverse proxy's X-Forwarded-* so login rate
# limiting keys on the real client IP instead of the shared proxy IP.  Only the
# private docker/proxy range is allowed to rewrite forwarded headers; the login
# bucket itself keys on X-Real-IP (set by nginx, unforgeable by clients).
exec uvicorn galleryvault.app.main:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips="172.16.0.0/12,127.0.0.1"
