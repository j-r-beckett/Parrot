#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-d DEPLOY_DIR] [-h]"
    echo "Build and deploy smsgap to Android device"
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
GOOS=android GOARCH=arm64 go build -o bin/smsgap .

# Deploy binary and boot script to device
adb push bin/smsgap /data/local/tmp/smsgap
adb push scripts/boot.sh /data/local/tmp/boot.sh
scripts/adb-run.sh "mv /data/local/tmp/smsgap $DEPLOY_DIR/smsgap && chmod +x $DEPLOY_DIR/smsgap"
scripts/adb-run.sh "mv /data/local/tmp/boot.sh $DEPLOY_DIR/boot.sh && chmod +x $DEPLOY_DIR/boot.sh"

# Restart the service by running boot.sh with no delay
scripts/adb-run.sh "pkill -f smsgap || true"
scripts/adb-run.sh "$DEPLOY_DIR/boot.sh -b 0"