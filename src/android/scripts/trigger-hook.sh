#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") EVENT_TYPE [-m MESSAGE] [-h]"
    echo "Trigger specific SMS Gateway webhook events for testing"
    echo ""
    echo "Arguments:"
    echo "  EVENT_TYPE  Type of webhook to trigger (sent, received, delivered, failed)"
    echo ""
    echo "Options:"
    echo "  -m MESSAGE  Custom message text (default: 'Test EVENT_TYPE webhook')"
    echo "  -h          Show this help message"
    echo ""
    echo "Event behaviors:"
    echo "  received  - NOMAD sends to SETTLER (triggers received on SETTLER)"
    echo "  sent      - SETTLER sends to NOMAD (triggers sent on SETTLER)"
    echo "  delivered - SETTLER sends to NOMAD (triggers delivered on SETTLER)"
    echo "  failed    - SETTLER sends to invalid number (triggers failed on SETTLER)"
    echo ""
    echo "Examples:"
    echo "  $(basename "$0") received"
    echo "  $(basename "$0") sent -m 'Custom message'"
    echo "  $(basename "$0") failed"
    exit 0
}

# Check for help flag first
for arg in "$@"; do
    if [[ "$arg" == "-h" ]]; then
        usage
    fi
done

# Check minimum arguments
if [ $# -lt 1 ]; then
    echo "Error: Missing required EVENT_TYPE argument" >&2
    usage
fi

EVENT_TYPE=$(echo "$1" | tr '[:upper:]' '[:lower:]')
shift

# Validate event type
if [[ "$EVENT_TYPE" != "sent" && "$EVENT_TYPE" != "received" && "$EVENT_TYPE" != "delivered" && "$EVENT_TYPE" != "failed" ]]; then
    echo "Error: Invalid EVENT_TYPE '$EVENT_TYPE'. Must be one of: sent, received, delivered, failed" >&2
    exit 1
fi

MESSAGE=""

# Parse optional arguments
while getopts "m:h" opt; do
    case $opt in
        m) MESSAGE="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# Set default message if not provided
if [ -z "$MESSAGE" ]; then
    MESSAGE="Test $EVENT_TYPE webhook"
fi


# Format phone numbers with country code if not present
if [[ ! "$CLANKER_SMS_GATEWAY_SETTLER_NUMBER" =~ ^\+ ]]; then
    SETTLER_NUMBER="+1$CLANKER_SMS_GATEWAY_SETTLER_NUMBER"
else
    SETTLER_NUMBER="$CLANKER_SMS_GATEWAY_SETTLER_NUMBER"
fi
if [[ ! "$CLANKER_SMS_GATEWAY_NOMAD_NUMBER" =~ ^\+ ]]; then
    NOMAD_NUMBER="+1$CLANKER_SMS_GATEWAY_NOMAD_NUMBER"
else
    NOMAD_NUMBER="$CLANKER_SMS_GATEWAY_NOMAD_NUMBER"
fi

# Device configurations
SETTLER_IP="192.168.0.16"
NOMAD_IP="192.168.0.15"

# Check both SMS Gateways are up
echo "Checking SMS Gateway health on both devices..."

# Check SETTLER
if ! curl -s -f "http://$SETTLER_IP:8080/health" > /dev/null 2>&1; then
    echo "Error: SETTLER SMS Gateway at $SETTLER_IP:8080 is not responding" >&2
    exit 1
fi
echo "SETTLER SMS Gateway is healthy"

# Check NOMAD
if ! curl -s -f "http://$NOMAD_IP:8080/health" > /dev/null 2>&1; then
    echo "Error: NOMAD SMS Gateway at $NOMAD_IP:8080 is not responding" >&2
    exit 1
fi
echo "NOMAD SMS Gateway is healthy"

# Configure SMS sending based on event type
case "$EVENT_TYPE" in
    received)
        # NOMAD sends to SETTLER (triggers received on SETTLER)
        SMS_GATEWAY_URL="http://$NOMAD_IP:8080"
        AUTH_PASSWORD="$CLANKER_SMS_GATEWAY_NOMAD_PASSWORD"
        FROM_DEVICE="NOMAD"
        FROM_NUMBER="$NOMAD_NUMBER"
        TO_NUMBER="$SETTLER_NUMBER"
        TO_DEVICE="SETTLER"
        ;;
    sent|delivered)
        # SETTLER sends to NOMAD (triggers sent/delivered on SETTLER)
        SMS_GATEWAY_URL="http://$SETTLER_IP:8080"
        AUTH_PASSWORD="$CLANKER_SMS_GATEWAY_SETTLER_PASSWORD"
        FROM_DEVICE="SETTLER"
        FROM_NUMBER="$SETTLER_NUMBER"
        TO_NUMBER="$NOMAD_NUMBER"
        TO_DEVICE="NOMAD"
        ;;
    failed)
        # SETTLER sends to invalid number (triggers failed on SETTLER)
        SMS_GATEWAY_URL="http://$SETTLER_IP:8080"
        AUTH_PASSWORD="$CLANKER_SMS_GATEWAY_SETTLER_PASSWORD"
        FROM_DEVICE="SETTLER"
        FROM_NUMBER="$SETTLER_NUMBER"
        TO_NUMBER="+15555555555"
        TO_DEVICE="INVALID"
        ;;
esac

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
  "phoneNumbers": ["$TO_NUMBER"]
}
EOF
)

echo ""
echo "Triggering $EVENT_TYPE webhook:"
echo "  From: $FROM_DEVICE ($FROM_NUMBER)"
echo "  To: $TO_DEVICE ($TO_NUMBER)"
echo "  Message: $MESSAGE"
echo ""

# Send the request using curl with basic auth
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -u "$USERNAME:$AUTH_PASSWORD" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" \
    "$SMS_GATEWAY_URL/message")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 202 ]; then
    echo "SMS sent successfully with ID: $MESSAGE_ID"
    echo ""
    echo "Expected webhook: sms:$EVENT_TYPE will be triggered on SETTLER device"
    if [ "$EVENT_TYPE" = "failed" ]; then
        echo "Note: Failed webhook may take a few seconds to trigger"
    fi
else
    echo "Error: Failed to send SMS (HTTP $HTTP_CODE)" >&2
    if [ -n "$BODY" ]; then
        echo "Response: $BODY" >&2
    fi
    exit 1
fi