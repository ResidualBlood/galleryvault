#!/usr/bin/env bash
#
# scripts/monitor_prod_logs.sh
#
# Remotely collects logs from GalleryVault production containers (backend, frontend, db)
# on your_server_ip for a specified duration (default: 30 minutes).
# Monitors collector PID and directory size every 5 minutes (or adaptive interval for tests).
# Fetches archive back to local /tmp/galleryvault-prod-logs-<timestamp>/, cleans up remote,
# and triggers scripts/analyze_prod_logs.py for automated log analysis.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_HOST="${PROD_HOST:-user@your_server_ip}"
DURATION="${1:-${DURATION:-30m}}"

parse_duration_seconds() {
    local dur="$1"
    if [[ "$dur" =~ ^([0-9]+)s$ ]]; then
        echo "${BASH_REMATCH[1]}"
    elif [[ "$dur" =~ ^([0-9]+)m$ ]]; then
        echo $((${BASH_REMATCH[1]} * 60))
    elif [[ "$dur" =~ ^([0-9]+)h$ ]]; then
        echo $((${BASH_REMATCH[1]} * 3600))
    elif [[ "$dur" =~ ^[0-9]+$ ]]; then
        echo "$dur"
    else
        echo 1800
    fi
}

TOTAL_SECONDS="$(parse_duration_seconds "$DURATION")"

# Default inspection interval: 5 minutes (300s). For shorter custom durations (e.g. 10s tests),
# adapt interval so the test doesn't stall for 5 minutes.
if [ -n "${CHECK_INTERVAL:-}" ]; then
    INTERVAL="$CHECK_INTERVAL"
elif [ "$TOTAL_SECONDS" -le 10 ]; then
    INTERVAL=2
elif [ "$TOTAL_SECONDS" -le 60 ]; then
    INTERVAL=5
elif [ "$TOTAL_SECONDS" -lt 300 ]; then
    INTERVAL=30
else
    INTERVAL=300
fi

echo "======================================================================"
echo "GalleryVault Production Log Monitor & Collector"
echo "======================================================================"
echo "Target Host:        ${PROD_HOST}"
echo "Duration:           ${DURATION} (${TOTAL_SECONDS}s)"
echo "Polling Interval:   ${INTERVAL}s"
echo "Start Time:         $(date '+%Y-%m-%d %H:%M:%S')"
echo "----------------------------------------------------------------------"

# 1. Generate remote collection script locally
LOCAL_TMP_SCRIPT="$(mktemp /tmp/prod_collector.XXXXXX.sh)"
cat << 'EOF' > "$LOCAL_TMP_SCRIPT"
#!/usr/bin/env bash
set -euo pipefail

DURATION="${1:-30m}"
LOG_DIR="/tmp/galleryvault-prod-logs"
ARCHIVE_FILE="/tmp/galleryvault-prod-logs.tar.gz"

# Clean previous temporary collection files
rm -rf "$LOG_DIR" "$ARCHIVE_FILE"
mkdir -p "$LOG_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting docker log streaming (duration: ${DURATION})..."

# Stream logs for core containers in parallel
timeout "${DURATION}" docker logs -f galleryvault-backend > "${LOG_DIR}/backend.log" 2>&1 &
PID_BACKEND=$!

timeout "${DURATION}" docker logs -f galleryvault-frontend > "${LOG_DIR}/frontend.log" 2>&1 &
PID_FRONTEND=$!

timeout "${DURATION}" docker logs -f galleryvault-db > "${LOG_DIR}/db.log" 2>&1 &
PID_DB=$!

# Wait for timeouts to elapse (timeout exits with 124, ignore error)
wait "$PID_BACKEND" || true
wait "$PID_FRONTEND" || true
wait "$PID_DB" || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log streaming completed. Creating tar archive..."
tar -czf "${ARCHIVE_FILE}" -C /tmp galleryvault-prod-logs
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Archive created at ${ARCHIVE_FILE}."
EOF

# 2. Transfer collector script to production host
echo "[Step 1/5] Deploying collector script to ${PROD_HOST}:/tmp/prod_collector.sh..."
scp -q "$LOCAL_TMP_SCRIPT" "${PROD_HOST}:/tmp/prod_collector.sh"
rm -f "$LOCAL_TMP_SCRIPT"
ssh "$PROD_HOST" "chmod +x /tmp/prod_collector.sh"

# 3. Trigger remote execution via nohup and record PID
echo "[Step 2/5] Starting background collection on production server..."
ssh "$PROD_HOST" "nohup /tmp/prod_collector.sh '${DURATION}' > /tmp/collector.log 2>&1 < /dev/null & echo \$! > /tmp/prod_collector.pid"

REMOTE_PID="$(ssh "$PROD_HOST" "cat /tmp/prod_collector.pid 2>/dev/null || echo ''")"
echo "Remote collector PID: ${REMOTE_PID}"

# 4. Routine inspection loop (polling PID and directory size)
echo "[Step 3/5] Monitoring remote collection (polling every ${INTERVAL}s)..."
START_TS="$(date +%s)"
MAX_WAIT=$((TOTAL_SECONDS + 120)) # Grace period of 2 minutes

while true; do
    CURRENT_TS="$(date +%s)"
    ELAPSED=$((CURRENT_TS - START_TS))

    # Inspect remote PID status
    IS_RUNNING="$(ssh "$PROD_HOST" "if [ -f /tmp/prod_collector.pid ] && kill -0 \$(cat /tmp/prod_collector.pid 2>/dev/null) 2>/dev/null; then echo 'alive'; else echo 'dead'; fi")"

    # Inspect directory size
    DIR_SIZE="$(ssh "$PROD_HOST" "du -sh /tmp/galleryvault-prod-logs 2>/dev/null | awk '{print \$1}' || echo '0B'")"
    if [ -z "$DIR_SIZE" ]; then
        DIR_SIZE="0B"
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Inspection | Elapsed: ${ELAPSED}s / ${TOTAL_SECONDS}s | Remote PID: ${REMOTE_PID} (${IS_RUNNING}) | Current Size: ${DIR_SIZE}"

    if [ "$IS_RUNNING" != "alive" ]; then
        echo "Remote collector finished execution."
        break
    fi

    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "Warning: Timeout reached maximum wait time (${MAX_WAIT}s). Proceeding to harvest logs."
        break
    fi

    sleep "$INTERVAL"
done

# 5. Retrieve archive and clean up remote host
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOCAL_DIR="/tmp/galleryvault-prod-logs-${TIMESTAMP}"
mkdir -p "$LOCAL_DIR"

echo "[Step 4/5] Pulling log archive to local ${LOCAL_DIR}..."
scp -q "${PROD_HOST}:/tmp/galleryvault-prod-logs.tar.gz" "${LOCAL_DIR}/" || {
    echo "Error: Failed to scp log archive from ${PROD_HOST}."
    exit 1
}

# Unpack locally
tar -xzf "${LOCAL_DIR}/galleryvault-prod-logs.tar.gz" -C "${LOCAL_DIR}"
echo "Successfully extracted logs into ${LOCAL_DIR}/galleryvault-prod-logs/"

echo "Cleaning up temporary collector files on ${PROD_HOST}..."
ssh "$PROD_HOST" "rm -rf /tmp/prod_collector.sh /tmp/prod_collector.pid /tmp/collector.log /tmp/galleryvault-prod-logs /tmp/galleryvault-prod-logs.tar.gz"

# 6. Trigger offline analysis
echo "[Step 5/5] Invoking log analysis script..."
if [ -x "${SCRIPT_DIR}/analyze_prod_logs.py" ]; then
    "${SCRIPT_DIR}/analyze_prod_logs.py" "${LOCAL_DIR}/galleryvault-prod-logs"
else
    python3 "${SCRIPT_DIR}/analyze_prod_logs.py" "${LOCAL_DIR}/galleryvault-prod-logs"
fi

echo "======================================================================"
echo "Done! Local logs preserved at: ${LOCAL_DIR}"
echo "======================================================================"
