#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-t] [-n LINES] [-f LOGFILE] [-h]"
    echo "Retrieve and display smsgap logs from Android device"
    echo ""
    echo "Options:"
    echo "  -t          Tail the log file continuously"
    echo "  -n LINES    Number of lines to display (default: all)"
    echo "  -f LOGFILE  Log file path (default: /data/adb/service.d/smsgap.log)"
    echo "  -h          Show this help"
    exit 1
}

TAIL_MODE=false
LINES=""
LOGFILE="/data/adb/service.d/smsgap.log"

while getopts "tn:f:h" opt; do
    case $opt in
        t) TAIL_MODE=true ;;
        n) LINES="-n $OPTARG" ;;
        f) LOGFILE="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

SCRIPT_DIR="$(dirname "$0")"

if [ "$TAIL_MODE" = true ]; then
    echo "Tailing smsgap logs (Ctrl-C to stop)..."
    "$SCRIPT_DIR/adb-run.sh" "tail -f $LINES $LOGFILE"
else
    if [ -n "$LINES" ]; then
        "$SCRIPT_DIR/adb-run.sh" "tail $LINES $LOGFILE"
    else
        "$SCRIPT_DIR/adb-run.sh" "cat $LOGFILE"
    fi
fi
