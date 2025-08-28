# This script is deployed to an Android device and executed by Magisk's busybox ash in standalone mode

set -e

usage() {
    echo "Usage: $(basename "$0") [-b SECONDS] [-h]"
    echo "Start smsgap service with system configuration"
    echo "Runs automatically on boot if placed in /data/adb/service.d"
    echo ""
    echo "Options:"
    echo "  -b SECONDS  Boot delay in seconds (default: 10, use 0 for no delay)"
    echo "  -h          Show this help message"
    exit 0
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/boot.log"
BOOT_DELAY=10

while getopts "b:h" opt; do
    case $opt in
        b) BOOT_DELAY="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

echo "Writing logs to $LOG"
echo "[$(date)] Executing boot script" >> $LOG

# Wait for device boot
while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 1; done

# Optional startup delay to make sure device boot is finished
if [ "$BOOT_DELAY" -gt 0 ]; then
    echo "[$(date)] Waiting $BOOT_DELAY seconds to ensure boot is completed" >> $LOG
    sleep $BOOT_DELAY
fi

# Disable Doze
dumpsys deviceidle disable

# Prevent WiFi from sleeping when screen is off
settings put global wifi_sleep_policy 2

# Check if port 8000 is in use and kill existing process
if ss -tln | grep -q ':8000 '; then
    echo "[$(date)] Port 8000 in use, killing existing process" >> $LOG
    # Find the PID using ss and kill it
    PID=$(ss -tlnp | grep ':8000 ' | sed -n 's/.*pid=\([0-9]*\).*/\1/p')
    if [ -n "$PID" ]; then
        echo "[$(date)] Killing process $PID using port 8000" >> $LOG
        kill -9 $PID 2>/dev/null || true
        sleep 1
    fi
fi

# Start smsgap
echo "[$(date)] Starting smsgap service" >> $LOG
cd "$SCRIPT_DIR" && setsid ./smsgap -port "${SMSGAP_PORT}" -private-ip "${PRIVATE_IP}" >> smsgap.log 2>&1 < /dev/null &
echo "[$(date)] smsgap started, logging to $SCRIPT_DIR/smsgap.log" >> $LOG
