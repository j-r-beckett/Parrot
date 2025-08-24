#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") DEVICE_SERIAL COMMAND"
    echo "Run command as root on Android device via adb using Magisk's busybox ash"
    echo ""
    echo "Commands are executed in Magisk's busybox ash shell in standalone mode,"
    echo "matching the environment used by Magisk boot scripts."
    echo ""
    echo "Arguments:"
    echo "  DEVICE_SERIAL  Device serial (e.g., 192.168.0.16:5555)"
    echo "  COMMAND        Command to execute"
    echo ""
    echo "Options:"
    echo "  -h             Show this help"
    exit 1
}

while getopts "h" opt; do
    case $opt in
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND-1))

if [ $# -lt 2 ]; then
    echo "Error: Device serial and command required"
    usage
fi

DEVICE_SERIAL="$1"
shift
SERIAL="-s $DEVICE_SERIAL"

# Check if device is connected
if ! adb $SERIAL shell exit 2>/dev/null; then
    echo "Error: No device connected or device not responding" >&2
    exit 1
fi

# Check if su is available
if ! adb $SERIAL shell "su -c exit" 2>/dev/null; then
    echo "Error: Root access not available on device" >&2
    exit 1
fi

# Encode as base64 to handle escaping
# Execute using Magisk's busybox ash in standalone mode
encoded=$(echo "$*" | base64 -w 0)
adb $SERIAL shell "su -c 'ASH_STANDALONE=1 /data/adb/magisk/busybox ash -c \"echo $encoded | base64 -d | ash\"'"
