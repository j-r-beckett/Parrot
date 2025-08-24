#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-H]"
    echo "Build and deploy smsgap to Android device via ADB"
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
GOOS=android GOARCH=arm64 go build -o bin/smsgap-android-arm64 .

# Push to sdcard first (accessible location)
adb -s "$NOMAD_SERIAL" push bin/smsgap-android-arm64 /sdcard/smsgap

# Move to /data/local/tmp and make executable
adb -s "$NOMAD_SERIAL" shell 'cp /sdcard/smsgap /data/local/tmp/ && chmod +x /data/local/tmp/smsgap'

# Check if smsgap is already running and kill it (ignore errors)
adb -s "$NOMAD_SERIAL" shell 'pkill -f smsgap' || true

# Start smsgap with password
adb -s "$NOMAD_SERIAL" shell "cd /data/local/tmp && nohup ./smsgap -password '$CLANKER_SMS_GATEWAY_NOMAD_PASSWORD' > smsgap.log 2>&1 &"

echo "Deployment complete!"
echo "Logs: adb -s $NOMAD_SERIAL shell 'cat /data/local/tmp/smsgap.log'"
echo "Health: curl http://$NOMAD_IP:8000/health"