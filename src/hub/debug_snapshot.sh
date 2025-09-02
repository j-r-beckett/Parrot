#!/bin/bash

# Debug script to retrieve and display conversation snapshots
# Usage: ./debug_snapshot.sh <snapshot_id> <database_path>

set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <snapshot_id> <database_path>"
    echo "Example: $0 a1b2c3d4-e5f6-7890-abcd-ef1234567890 /path/to/database.db"
    exit 1
fi

SNAPSHOT_ID="$1"
DATABASE_PATH="$2"

# Validate that snapshot_id is a valid UUID
if ! echo "$SNAPSHOT_ID" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
    echo "Error: '$SNAPSHOT_ID' is not a valid UUID"
    exit 1
fi

if [ ! -f "$DATABASE_PATH" ]; then
    echo "Error: Database file '$DATABASE_PATH' not found"
    exit 1
fi

echo "Retrieving snapshot: $SNAPSHOT_ID"
echo "Database: $DATABASE_PATH"
echo "----------------------------------------"

# Query the snapshot from the database
CONTEXT=$(sqlite3 "$DATABASE_PATH" "SELECT context FROM snapshots WHERE snapshot_id = '$SNAPSHOT_ID';")

if [ -z "$CONTEXT" ]; then
    echo "Error: Snapshot '$SNAPSHOT_ID' not found"
    exit 1
fi

# Pretty print the JSON context
echo "$CONTEXT" | python3 -m json.tool