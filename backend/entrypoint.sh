#!/bin/sh
# Entrypoint: run as the unprivileged `app` user after making the writable
# mount roots owned by it. /library is read-only and never touched.
set -e

# asyncpg probes ~/.postgresql for client certificates; point HOME at the app
# user's home so it falls back to plain (non-SSL) connections instead of
# trying to read /root/.postgresql as an unprivileged user.
export HOME=/home/app

if [ "$(id -u)" = "0" ]; then
    # Ownership of the mount roots only (not recursive), so the app user can
    # create download/thumbnail directories. Failures (read-only mounts,
    # restricted filesystems) are ignored.
    chown app:app /downloads /gv-cache 2>/dev/null || true
    exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

alembic upgrade head
exec uvicorn galleryvault.app.main:app --host 0.0.0.0 --port 8001
