#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-m MESSAGE] [-h]"
    echo "Send a test SMS to the SETTLER device through SMS Gateway"
    echo ""
    echo "Options:"
    echo "  -m MESSAGE  Custom message text (default: 'Ping from smsgap')"
    echo "  -h          Show this help message"
    exit 0
}

MESSAGE="Ping from smsgap"

while getopts "m:h" opt; do
    case $opt in
        m) MESSAGE="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# Load environment variables from project root
ENV_FILE="$(dirname "$0")/../../../.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE" >&2
    exit 1
fi

# Parse the .env file for SETTLER credentials
SETTLER_PASSWORD=$(grep "^CLANKER_SMS_GATEWAY_SETTLER_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2)
SETTLER_NUMBER=$(grep "^CLANKER_SMS_GATEWAY_SETTLER_NUMBER=" "$ENV_FILE" | cut -d'=' -f2)

if [ -z "$SETTLER_PASSWORD" ] || [ -z "$SETTLER_NUMBER" ]; then
    echo "Error: Could not find SETTLER credentials in .env file" >&2
    exit 1
fi

# Format phone number with country code if not present
if [[ ! "$SETTLER_NUMBER" =~ ^\+ ]]; then
    SETTLER_NUMBER="+1$SETTLER_NUMBER"
fi

# SMS Gateway configuration
SMS_GATEWAY_URL="http://192.168.0.16:8080"
USERNAME="sms"

# Generate a unique message ID
MESSAGE_ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$(date +%s)-$$")

# Create the JSON payload
JSON_PAYLOAD=$(cat <<EOF
{
  "id": "$MESSAGE_ID",
  "textMessage": {
    "text": "$MESSAGE"
  },
  "phoneNumbers": ["$SETTLER_NUMBER"]
}
EOF
)

echo "Sending SMS to $SETTLER_NUMBER via SMS Gateway..."
echo "Message: $MESSAGE"

# Send the request using curl with basic auth
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -u "$USERNAME:$SETTLER_PASSWORD" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" \
    "$SMS_GATEWAY_URL/message")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 202 ]; then
    echo "Success! SMS sent with ID: $MESSAGE_ID"
    if [ -n "$BODY" ]; then
        echo "Response: $BODY"
    fi
else
    echo "Error: Failed to send SMS (HTTP $HTTP_CODE)" >&2
    if [ -n "$BODY" ]; then
        echo "Response: $BODY" >&2
    fi
    exit 1
fi