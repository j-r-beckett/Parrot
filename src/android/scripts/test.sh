#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-v] [-c] [-h]"
    echo "Run smsgap tests"
    echo ""
    echo "Options:"
    echo "  -v  Verbose output"
    echo "  -c  Show coverage"
    echo "  -h  Show this help message"
    exit 0
}

VERBOSE=""
COVERAGE=""

while getopts "vch" opt; do
    case $opt in
        v) VERBOSE="-v" ;;
        c) COVERAGE="-cover" ;;
        h) usage ;;
        *) usage ;;
    esac
done

cd "$(dirname "$0")/.."

echo "Running smsgap tests..."

# Run tests
if [ -n "$COVERAGE" ]; then
    go test $VERBOSE -cover -coverprofile=coverage.out .
    go tool cover -func=coverage.out
else
    go test $VERBOSE .
fi

if [ $? -eq 0 ]; then
    echo "All tests passed!"
else
    echo "Tests failed!"
    exit 1
fi