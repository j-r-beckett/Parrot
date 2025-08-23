# This script is executed automatically by Busybox ash
# (e.g. /data/adb/magisk/busybox ash -o standalone /data/adb/service.d/server_mode.sh)

SCRIPT_PATH="$0"
SCRIPT_NAME=$(basename "$SCRIPT_PATH" .sh)
LOG_BASENAME="/data/local/tmp/$SCRIPT_NAME"
LOG="$LOG_BASENAME.log"

echo "Writing logs to $LOG"
echo "[$(date)] Executing boot script $SCRIPT_PATH" >> $LOG

# Wait for boot
while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 1; done
sleep 5

# Disable Doze
dumpsys deviceidle disable

# Prevent WiFi from sleeping when screen is off
settings put global wifi_sleep_policy 2

# Use netcat to forward from device localhost to the server
DEVICE_PORT=8000
SERVER_PORT=8000
SERVER_HOST=192.168.0.19

echo "Opening tunnel from 127.0.0.1:$DEVICE_PORT to $SERVER_HOST:$SERVER_PORT" >> $LOG

nc --help >> $LOG 2&>1

if netstat -tuln 2>/dev/null | grep -q ":$DEVICE_PORT "; then
    echo "A process is already listening on port $DEVICE_PORT" >> $LOG
    if echo " $@ " | grep -q " --force " || echo " $@ " | grep -q " -f "; then
        echo "Killing the process listening on port $DEVICE_PORT" >> $LOG
        fuser -k $DEVICE_PORT/tcp
        PORT_OPEN=1
    else
        PORT_OPEN=0
    fi
else
    echo "Port $DEVICE_PORT is open" >> $LOG
    PORT_OPEN=1
fi

if [ "$PORT_OPEN" = "1" ]; then
    echo "Starting netcat" >> $LOG
    NETCAT_LOG="$LOG_BASENAME.nc.log"
    echo "[$(date)] Starting netcat log" >> $NETCAT_LOG
    nc -lk -p $DEVICE_PORT -e ash -c "exec nc $SERVER_HOST $SERVER_PORT" >> $NETCAT_LOG 2&>1 &
    PID=$!
    echo "netcat started with PID: $PID. Log file path: $NETCAT_LOG" >> $LOG
else
    echo "Unable to open tunnel" >> $LOG
fi
