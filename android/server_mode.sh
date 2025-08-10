# This script is executed automatically by Busybox ash
# (e.g. /data/adb/magisk/busybox ash -o standalone /data/adb/service.d/server_mode.sh)

SCRIPT_PATH="$0"
SCRIPT_NAME=$(basename "$SCRIPT_PATH" .sh)
LOG_FILE="/data/local/tmp/$SCRIPT_NAME.log"
echo "[$(date)] Executing boot script $SCRIPT_PATH" >> $LOG_FILE

# Wait for boot
while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 1; done
sleep 5

# Disable Doze
dumpsys deviceidle disable

DOZE_EVIDENCE=$(dumpsys deviceidle | grep -E "mDeepEnabled|mLightEnabled")
echo "Doze disabled. Evidence: $DOZE_EVIDENCE (expected mLightEnabled=false and mDeepEnabled=false)" >> $LOG_FILE

# Prevent WiFi from sleeping when screen is off
settings put global wifi_sleep_policy 2

WIFI_POLICY=$(settings get global wifi_sleep_policy)
echo "Wifi sleep disabled. Evidence: wifi policy=$WIFI_POLICY (expected: 2)" >> $LOG_FILE
