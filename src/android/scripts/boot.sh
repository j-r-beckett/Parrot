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

# Start smsgap
echo "[$(date)] Starting smsgap service" >> $LOG
cd "$SCRIPT_DIR" && setsid ./smsgap >> smsgap.log 2>&1 < /dev/null &
echo "[$(date)] smsgap started, logging to $SCRIPT_DIR/smsgap.log" >> $LOG
