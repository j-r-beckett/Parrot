#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-H]"
    echo "Build and deploy sms-proxy to Android device via ADB"
    echo ""
    echo "Options:"
    echo "  -H             Show this help message"
    exit 0
}

# Parse options
while getopts "H" opt; do
    case $opt in
        H) usage ;;
        *) usage ;;
    esac
done

cd "$(dirname "$0")/.."

# Build for Android ARM64
GOOS=android GOARCH=arm64 go build -o bin/sms-proxy-android-arm64 .

# Check if sms-proxy is already running and kill it (ignore errors)
adb -s "$NOMAD_SERIAL" shell 'pkill -f sms-proxy' || true
sleep 2

# Push to sdcard first (accessible location)
adb -s "$NOMAD_SERIAL" push bin/sms-proxy-android-arm64 /sdcard/sms-proxy

# Move to /data/local/tmp and make executable
adb -s "$NOMAD_SERIAL" shell 'cp /sdcard/sms-proxy /data/local/tmp/ && chmod +x /data/local/tmp/sms-proxy'

# Start sms-proxy with password, host, and port
adb -s "$NOMAD_SERIAL" shell "cd /data/local/tmp && setsid ./sms-proxy -password '$PARROT_SMS_GATEWAY_NOMAD_PASSWORD' -host '$NOMAD_IP' -port '$SMS_PROXY_PORT' > sms-proxy.log 2>&1 < /dev/null" &

echo "Deployment complete!"
echo "Logs: adb -s $NOMAD_SERIAL shell 'cat /data/local/tmp/sms-proxy.log'"
echo "Health: curl http://$NOMAD_IP:$SMS_PROXY_PORT/health"