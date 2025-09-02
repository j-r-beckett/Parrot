#!/bin/bash

# Debug script to retrieve and display interaction details
# Usage: ./debug_interaction.sh <interaction_id> [database_path]

set -e

DEFAULT_DATABASE_PATH=".db/interactions.db"

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Usage: $0 <interaction_id> [database_path]"
    echo "Example: $0 a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    exit 1
fi

INTERACTION_ID="$1"
DATABASE_PATH="${2:-$DEFAULT_DATABASE_PATH}"

# Validate that interaction_id is a valid UUID
if ! echo "$INTERACTION_ID" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
    echo "Error: '$INTERACTION_ID' is not a valid UUID"
    exit 1
fi

if [ ! -f "$DATABASE_PATH" ]; then
    echo "Error: Database file '$DATABASE_PATH' not found"
    exit 1
fi

echo "Retrieving interaction: $INTERACTION_ID"
echo "Database: $DATABASE_PATH"
echo "----------------------------------------"

# Query the interaction from the database
MESSAGES=$(sqlite3 "$DATABASE_PATH" "SELECT messages FROM interactions WHERE id = '$INTERACTION_ID';")

if [ -z "$MESSAGES" ]; then
    echo "Error: Interaction '$INTERACTION_ID' not found"
    exit 1
fi

# Pretty print the JSON messages
echo "$MESSAGES" | python3 -m json.tool