# SMS Gateway Proxy (smsgap)

## Overview

`smsgap` is a webhook proxy service that sits between [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway) and backend servers. It runs directly on the Android device alongside SMS Gateway, providing advanced webhook management capabilities that SMS Gateway doesn't natively support.

## Architecture

```
+-------------------------------------------+
|            Android Phone                  |
|                                           |
| +------------------+                      |
| | SmsManager       |                      |
| +------------------+                      |
| | BroadcastReceiver|                      |
| +------------------+                      |
|         ^                                 |
|         |                                 |
|         v                                 |
| +------------------+     +--------------+ |
| | SMS Gateway      |---->| smsgap       | |
| | (port 8080)      |     | Webhook:     | |
| |                  |     | 127.0.0.1:*  | |
| |                  |     |              | |
| |                  |     | API:         | |
| |                  |     | host:port    | |
| +------------------+     +--------------+ |
|                                  |        |
+-------------------------------------------+
                                   |
          Forwards webhooks to registered clients
                                   |
                          +--------+--------+
                          |                 |
                          v                 v
                       +-----+           +------+
                       | PPE |           | Prod |
                       +-----+           +------+
```

### Dual Router Architecture

smsgap runs two separate HTTP servers to handle different security requirements:

1. **Webhook Server** (`127.0.0.1:random-port`): Receives webhooks from SMS Gateway. Uses a randomly assigned available port since SMS Gateway will call whatever URL smsgap registers with it.

2. **API Server** (`host:port`): Handles client registration, health checks, SMS sending, and client management. The host and port are configurable via command-line arguments.

This dual setup is necessary because SMS Gateway restricts webhook URLs to localhost (`127.0.0.1`) for security, while the API server can bind to any interface for external access.

When SMS events occur (received, sent, delivered, failed), SMS Gateway sends webhooks to the webhook server. smsgap then forwards these webhooks to all registered clients via the API server based on their subscription preferences and filtering rules.

Backend servers connect to the API server for registration and SMS sending, providing a single point of contact for both sending and receiving SMS functionality.

## Key Features

### Client Registration
Clients register with smsgap by calling the `/register` endpoint with:
- Unique client ID
- Webhook URL to receive forwarded events
- Event subscriptions (sms_received, sms_sent, sms_delivered, sms_failed)
- Optional phone number filters (include/exclude lists)

**Important**: Client registrations expire after 60 seconds of inactivity. Clients must periodically re-register (recommended every 30-45 seconds) to maintain their registration.

### Phone Number Filtering
For `sms:received` events, clients can specify:
- **Include list**: Only receive webhooks from these phone numbers
- **Exclude list**: Don't receive webhooks from these phone numbers

This enables sophisticated routing scenarios. For example, a production/PPE setup:
```json
// PPE Client Registration
{
  "id": "ppe-client",
  "webhook_url": "https://ppe.example.com/webhook",
  "sms_received": true,
  "include_received_from": ["+15551234567", "+15559876543"]  // PPE test numbers
}

// Production Client Registration  
{
  "id": "prod-client",
  "webhook_url": "https://prod.example.com/webhook",
  "sms_received": true,
  "exclude_received_from": ["+15551234567", "+15559876543"]  // Exclude PPE numbers
}
```

### Reliability Features
- **Parallel Forwarding**: Webhooks are forwarded to all clients simultaneously for optimal performance
- **Retry Logic**: Failed webhook forwards are retried 3 times with 1-second delays
- **Client Pruning**: Inactive clients (>60 seconds) are automatically removed
- **Webhook Auto-Repair**: Checks every 30 seconds that SMS Gateway webhooks are registered, re-registers if missing
- **Graceful Shutdown**: Properly cleans up webhooks and waits for pending forwards

## API Endpoints

### POST /register
Register or update a client.

**Request:**
```json
{
  "id": "client-123",
  "webhook_url": "https://example.com/webhook",
  "sms_received": true,
  "sms_sent": false,
  "sms_delivered": true,
  "sms_failed": false,
  "include_received_from": ["+15551234567"],
  "exclude_received_from": []
}
```

**Validation:**
- ID must be 1-128 characters
- Webhook URL is required (can be any non-empty string)
- Cannot specify both include and exclude lists
- Phone numbers must match `^\+?\d{10,14}$`

### GET /clients
List all registered clients with their configurations.

### GET /health
Health check endpoint that also verifies SMS Gateway connectivity.

**Response (200 OK when healthy):**
```json
{
  "status": "healthy",
  "version": "1.6",
  "timestamp": "2025-08-24T00:29:21Z",
  "sms_gateway": "healthy"
}
```

**Response (503 Service Unavailable when SMS Gateway is down):**
```json
{
  "status": "unhealthy",
  "version": "1.6",
  "timestamp": "2025-08-24T00:29:21Z",
  "sms_gateway": "unhealthy",
  "error": "failed to connect to SMS Gateway: ..."
}
```

### POST /send
Send SMS messages via SMS Gateway.

**Request:**
```json
{
  "phone_numbers": ["+15551234567", "+15559876543"],
  "message": "Hello from smsgap",
  "sim_number": 1  // Optional: 1-3, defaults to SMS Gateway's default
}
```

**Response (202 Accepted):**
Returns SMS Gateway's message status response with message ID and state information.

## Scripts Directory

The `scripts/` directory contains essential tools for managing smsgap on Android devices:

### deploy.sh
Builds and deploys smsgap to the Android device. Handles:
- Cross-compilation for Android ARM64
- Boot script generation from `boot.template.sh` using `envsubst` with `SETTLER_IP` and `SMSGAP_PORT`
- Binary and boot script deployment via ADB and Magisk
- Password file creation from environment variables
- Graceful service restart (waits for old instance to stop)

Usage: `./scripts/deploy.sh [-d DEPLOY_DIR]`

### mgsk-run.sh
Executes commands on the Android device as root using Magisk's busybox ash. Used internally by other scripts.

Usage: `./scripts/mgsk-run.sh DEVICE_SERIAL "command"`

Example: `./scripts/mgsk-run.sh "$SETTLER_SERIAL" "tail -f /data/adb/service.d/smsgap.log"`

### boot.sh
Boot script generated from `boot.template.sh` during deployment. The template uses environment variable substitution for:
- `${SETTLER_IP}`: IP address for the API server
- `${SMSGAP_PORT}`: Port for the API server

The deployed script:
- Waits for device boot completion
- Disables Doze mode
- Prevents WiFi sleep
- Kills any existing smsgap process on the port
- Starts smsgap service with configured host and port

Automatically runs on device boot when placed in `/data/adb/service.d/`.

### test.sh
Runs integration tests against a running smsgap instance.

### trigger-hook.sh
Manually triggers a webhook for testing purposes.

## Magisk Integration

smsgap runs as a system service on Android devices using [Magisk](https://topjohnwu.github.io/Magisk/guides.html). The deployment script installs `boot.sh` to `/data/adb/service.d/`, which is a special directory where Magisk automatically executes scripts on boot.

### Boot Script Execution

When Magisk runs boot scripts, it uses BusyBox's `ash` shell in standalone mode. This means:
- All standard commands (ls, rm, cat, etc.) use BusyBox applets rather than Android's toybox or system binaries
- The environment is minimal and isolated
- Scripts have root privileges
- Working directory is the script's directory

The `mgsk-run.sh` script also executes commands in this same BusyBox environment for consistency:
```bash
# This runs in BusyBox ash with root privileges
./scripts/mgsk-run.sh "$SETTLER_SERIAL" "ls -la /data/adb/service.d"
```

### Directory Structure
```
/data/adb/
+-- service.d/
|   +-- boot.sh           # Magisk boot script (runs on every boot)
|   +-- smsgap            # The compiled Go binary
|   +-- smsgap.log        # Application logs
|   +-- boot.log          # Boot script logs
+-- smsgap/
    +-- password.txt      # SMS Gateway credentials
```

## Configuration

### Password Management
SMS Gateway credentials are read from `/data/adb/smsgap/password.txt` on the device. The deploy script automatically creates this file from the `CLANKER_SMS_GATEWAY_SETTLER_PASSWORD` environment variable.

### ADB Setup
Both settler and nomad devices must be connected via [ADB wireless debugging](https://developer.android.com/tools/adb). Enable Developer Options and Wireless Debugging on both devices, then connect:

```bash
adb connect SETTLER_IP:5555
adb connect NOMAD_IP:5555  
```

### Required Environment Variables
```
CLANKER_SMS_GATEWAY_SETTLER_PASSWORD=your_settler_password
CLANKER_SMS_GATEWAY_NOMAD_PASSWORD=your_nomad_password  
SETTLER_IP=192.168.0.16     # Required for ADB access and HTTP requests
NOMAD_IP=192.168.0.15       # Required for ADB access and HTTP requests
SETTLER_SERIAL=192.168.0.16:42599  # Auto-generated from SETTLER_IP
NOMAD_SERIAL=192.168.0.15:40521    # Auto-generated from NOMAD_IP
SETTLER_IP=100.107.61.95            # Settler device Tailscale IP
NOMAD_IP=100.87.185.101             # Nomad device Tailscale IP  
SMSGAP_PORT=8000                     # Port for smsgap on both devices
```

The `SETTLER_IP` and `NOMAD_IP` variables are required so that:
- HTTP requests can be made to smsgap endpoints
- ADB device serials can be automatically inferred from connected devices

The `SETTLER_IP`/`NOMAD_IP` and `SMSGAP_PORT` variables configure where each device's API server binds:
- Use a Tailscale IP for secure, encrypted access
- Use `127.0.0.1` with a reverse proxy for TLS termination and authentication

### Configuration

smsgap accepts the following command-line arguments:
- `-host`: IP address to bind the API server to (required)
- `-port`: Port for the API server (required) 
- `-password`: SMS Gateway password (optional, uses password file if not specified)

**Security Options:**
- **Tailscale IP**: Bind to a Tailscale IP for secure, encrypted access without exposing the service publicly
- **Localhost + Reverse Proxy**: Bind to `127.0.0.1` and use a reverse proxy (nginx, Caddy) for TLS termination and authentication

**Internal Constants:**
- SMS Gateway port: 8080
- Webhook server: Random available port on 127.0.0.1
- Client timeout: 60 seconds
- Webhook check interval: 30 seconds
- Retry attempts: 3
- Retry delay: 1 second

## Development

### Building
```bash
# Build for Android
GOOS=android GOARCH=arm64 go build -o smsgap

# Build for local testing
go build -o smsgap
```

### Testing
```bash
# Run unit tests
go test ./...

# Run with coverage
go test -cover ./...

# Deploy and test on device
./scripts/deploy.sh
./scripts/test.sh
```

### Monitoring
```bash
# Watch logs in real-time
./scripts/mgsk-run.sh "$SETTLER_SERIAL" "tail -f /data/adb/service.d/smsgap.log"

# Check recent logs  
./scripts/mgsk-run.sh "$SETTLER_SERIAL" "tail -n 50 /data/adb/service.d/smsgap.log"

# Check health
curl http://192.168.0.16:8000/health

# List registered clients
curl http://192.168.0.16:8000/clients
```

## Version History

- **v0.3**: Basic webhook proxy with health checks
- **v0.6**: Added client management and pruning
- **v1.0**: Added retry logic for failed forwards
- **v1.1**: Implemented graceful shutdown
- **v1.3**: Added phone number filtering for sms:received
- **v1.4**: Added webhook auto-repair
- **v1.5**: Added SMS sending endpoint (proxy to SMS Gateway)
- **v1.6**: Health endpoint now checks SMS Gateway connectivity
- **v1.7**: Parallel webhook forwarding for better performance
- **v1.8**: Added `-password` flag for Termux/non-rooted deployment

## Non-Rooted Device Deployment 

For non-rooted devices (like nomad), smsgap can be deployed to `/data/local/tmp` via ADB.

### deploy-nomad.sh

Use the `deploy-nomad.sh` script for non-rooted deployment:
```bash
./scripts/deploy-nomad.sh
```

The script:
- Builds smsgap for Android ARM64
- Pushes binary to device via ADB
- Deploys to `/data/local/tmp` (accessible without root)
- Starts smsgap with password from command line flag
- Logs output to `/data/local/tmp/smsgap.log`

### Limitations

Non-rooted deployment limitations:
- No automatic boot startup (unlike Magisk deployment)
- Must be manually restarted after device reboot
- Runs in `/data/local/tmp` instead of `/data/adb/service.d`

## Security Considerations

- Runs as root on rooted devices (required for Magisk service)
- Runs as regular user in Termux (non-rooted devices)
- Password stored in root-only accessible file (rooted) or passed via command line (Termux)
- SMS Gateway (not smsgap) restricts its webhook URLs to `https://` or `http://127.0.0.1`
- Client IDs limited to 128 characters to prevent abuse
- Phone numbers validated against regex pattern

## SMS Gateway API Documentation

SMS Gateway for Android exposes its Swagger/OpenAPI documentation at `http://<device-ip>:8080/docs/swagger.json`. This is useful for understanding the full capabilities of SMS Gateway beyond what smsgap uses.

### Downloading the Swagger JSON

1. Get the SMS Gateway password from your environment:
```bash
echo $CLANKER_SMS_GATEWAY_SETTLER_PASSWORD
```

2. Download the Swagger JSON (replace IP and password):
```bash
curl -u sms:<password> http://192.168.0.16:8080/docs/swagger.json -o sms-gateway-swagger.json
```

3. View it with any OpenAPI viewer or import into Postman/Insomnia

The Swagger documentation includes all SMS Gateway endpoints for:
- Sending messages (`POST /messages`)
- Message history (`GET /messages`)
- Webhook management (`/webhooks`)
- Health checks (`GET /health`)
- Settings management (`/settings`)
- And more

## Troubleshooting

### Webhooks not being received
1. Check SMS Gateway is running: `curl -u sms:password http://192.168.0.16:8080/health`
2. Check smsgap logs: `./scripts/log.sh -n 50`
3. Verify webhooks are registered: `curl -u sms:password http://192.168.0.16:8080/webhooks`
4. Check client registration: `curl http://192.168.0.16:8000/clients`

### Deployment issues
1. Ensure device is connected: `adb devices`
2. Check environment variables are set: `echo $CLANKER_SMS_GATEWAY_SETTLER_PASSWORD`
3. Verify Magisk is installed and su is available
4. Check boot.log for startup errors: `adb shell su -c "cat /data/adb/service.d/boot.log"`

### Auto-repair constantly re-registering
This usually indicates SMS Gateway is losing webhooks. Check SMS Gateway logs and ensure it's not restarting frequently.