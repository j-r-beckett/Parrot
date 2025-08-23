#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-s SERIAL] COMMAND"
    echo "Run command as root on Android device via adb using Magisk's busybox ash"
    echo ""
    echo "Commands are executed in Magisk's busybox ash shell in standalone mode,"
    echo "matching the environment used by Magisk boot scripts."
    echo ""
    echo "Options:"
    echo "  -s SERIAL    Use device with given serial"
    echo "  -h           Show this help"
    exit 1
}

SERIAL=""

while getopts "s:h" opt; do
    case $opt in
        s) SERIAL="-s $OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND-1))

if [ $# -eq 0 ]; then
    echo "Error: No command specified"
    usage
fi

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
