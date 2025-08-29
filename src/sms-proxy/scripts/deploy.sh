#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-d DEPLOY_DIR] [-h]"
    echo "Build and deploy sms-proxy to Android device"
    echo ""
    echo "Options:"
    echo "  -d DEPLOY_DIR  Deployment directory on device (default: /data/adb/service.d)"
    echo "  -h             Show this help message"
    exit 0
}

DEPLOY_DIR="/data/adb/service.d"

# Parse options
while getopts "d:h" opt; do
    case $opt in
        d) DEPLOY_DIR="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

cd "$(dirname "$0")/.."


# Build for Android ARM64
GOOS=android GOARCH=arm64 go build -o bin/sms-proxy .

# Generate boot script from template
echo "Generating boot script from template..."
envsubst '$SETTLER_IP,$SMS_PROXY_PORT,$PRIVATE_IP' < scripts/boot.template.sh > /tmp/boot.sh

# Deploy binary and boot script to device
adb -s "$SETTLER_SERIAL" push bin/sms-proxy /data/local/tmp/sms-proxy
adb -s "$SETTLER_SERIAL" push /tmp/boot.sh /data/local/tmp/boot.sh
scripts/mgsk-run.sh "$SETTLER_SERIAL" "mv /data/local/tmp/sms-proxy $DEPLOY_DIR/sms-proxy && chmod +x $DEPLOY_DIR/sms-proxy"
scripts/mgsk-run.sh "$SETTLER_SERIAL" "mv /data/local/tmp/boot.sh $DEPLOY_DIR/boot.sh && chmod +x $DEPLOY_DIR/boot.sh"

# Create password directory and write password file
echo "Writing SMS Gateway password to /data/adb/sms-proxy/password.txt"
scripts/mgsk-run.sh "$SETTLER_SERIAL" "mkdir -p /data/adb/sms-proxy && chmod 700 /data/adb/sms-proxy"
scripts/mgsk-run.sh "$SETTLER_SERIAL" "echo '$PARROT_SMS_GATEWAY_SETTLER_PASSWORD' > /data/adb/sms-proxy/password.txt && chmod 600 /data/adb/sms-proxy/password.txt"

# Stop the old service and wait for it to exit
scripts/mgsk-run.sh "$SETTLER_SERIAL" "pkill -f sms-proxy || true"
# Wait for the process to actually exit (up to 10 seconds)
scripts/mgsk-run.sh "$SETTLER_SERIAL" "for i in \$(seq 1 10); do pgrep -f sms-proxy >/dev/null || break; sleep 1; done"
# Start the new service
scripts/mgsk-run.sh "$SETTLER_SERIAL" "$DEPLOY_DIR/boot.sh -b 0"