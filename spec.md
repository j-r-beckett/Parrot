# smsgap - SMS Gateway Proxy Specification

## Overview

smsgap is a proxy service that runs on Android devices to route SMS webhooks from the SMS Gateway for Android app to appropriate backend services.

## Problem Statement

The SMS Gateway for Android app has the following limitations:
1. Only sends webhooks to localhost over HTTP
2. Refuses to send to non-localhost addresses without HTTPS
3. Does not accept self-signed certificates

Additionally, there is a need to route SMS messages to different environments based on sender phone numbers without requiring multiple physical devices.

## Goals

1. Enable HTTP webhook forwarding to non-localhost addresses on trusted local networks
2. Implement routing logic to direct messages from specified phone numbers to PPE environment
3. Route messages from all other numbers to production environment
4. Eliminate the need for multiple phones and SIM cards for environment separation

## Architecture

### Components

- **smsgap service**: Go-based service running on the Android device
- **Deployment toolchain**: Scripts for building, deploying, and managing the service via ADB
- **Boot persistence**: Magisk-based boot script for automatic service startup

## Implementation Details

### Technology Stack
- **Language**: Go
- **Web Framework**: go-chi
- **Port**: 8000 (localhost)

### Core Functionality

#### Webhook Management
- Uses SMS Gateway local mode API (HTTP Basic Auth)
- Credentials: username "sms", password from `.env` file in repo root
- SMS Gateway expected on localhost:8080
- On startup:
  1. Check SMS Gateway health endpoint (`GET localhost:8080/health`) every second for up to 10 seconds
  2. If not available after 10 seconds, crash
  3. Get all existing webhooks (`GET /webhooks`)
  4. Delete each webhook by ID (`DELETE /webhooks/{id}`)
  5. Register new webhooks (`POST /webhooks`) with JSON body:
     ```json
     {
       "url": "http://localhost:8000/webhook/sms/received",
       "event": "sms:received"
     }
     ```
  6. Register webhooks for:
     - `sms:received`
     - `sms:sent`
     - `sms:delivered`
     - `sms:failed`

#### Client Registration
- Clients register via `/register` endpoint
- Required parameters:
  - `client_id`: Unique identifier for the client
  - `url`: Destination URL for webhook forwarding
- Optional parameters:
  - `webhook_types`: Array of webhook types to subscribe to (defaults to all)
  - `include_numbers`: Array of phone numbers to forward webhooks from (whitelist)
  - `exclude_numbers`: Array of phone numbers to NOT forward webhooks from (blacklist)
- Phone number filtering rules:
  - Cannot specify both `include_numbers` and `exclude_numbers` (returns error)
  - If neither specified, forwards webhooks from all numbers
  - Phone numbers validated with regex: `^\+?\d{10,14}$`
  - Clients self-manage ring separation (smsgap is ring-agnostic):
    - PPE clients specify `include_numbers` with their PPE phone numbers
    - Prod clients specify `exclude_numbers` with PPE phone numbers
- Clients must re-register every 60 seconds to maintain active status
- Stale clients are automatically removed after timeout

#### Webhook Processing
1. Receive webhook from SMS Gateway app
2. Immediately return 200 OK to SMS Gateway
3. Identify all registered clients subscribed to this webhook type
4. Filter clients based on phone number rules:
   - If client has `include_numbers`, only forward if sender/recipient matches
   - If client has `exclude_numbers`, skip if sender/recipient matches
   - If neither specified, forward to client
5. Create parallel forwarding tasks for each matching client
6. Each forwarding task includes automatic retry logic
7. Tasks are managed in a concurrent collection outside request lifecycle

#### Background Processes
- **Task Cleaner**: Runs every 5 seconds to remove completed forwarding tasks
- **Client Pruner**: Removes clients that haven't re-registered within timeout period
- **Webhook Repair**: Runs every 30 seconds to verify and restore missing webhooks
  - Checks if all 4 webhook types are registered
  - Re-registers any missing webhooks
  - Logs errors but does not crash on failure

### Retry Strategy
- Independent retry logic per client
- 3 linear retry attempts per failed delivery
- Prevents duplicate deliveries to successful clients
- Ensures delivery attempts to failed clients

## API/Interface

### Webhook Endpoints (from SMS Gateway)
- `POST /webhook/sms/received` - Receives SMS received events
- `POST /webhook/sms/sent` - Receives SMS sent events
- `POST /webhook/sms/delivered` - Receives SMS delivered events
- `POST /webhook/sms/failed` - Receives SMS failed events

Payload format (from SMS Gateway):
```json
{
  "deviceId": "<device-id>",
  "event": "sms:received",
  "payload": {
    "messageId": "<message-id>",
    "message": "<content>",
    "phoneNumber": "<sender/recipient>",
    "simNumber": 1,
    "receivedAt": "<timestamp>"
  }
}
```

### Client Management Endpoints
- `POST /register` - Register or refresh client registration
- `GET /health` - Service health check

Registration request:
  ```json
  {
    "client_id": "string",
    "url": "string",
    "webhook_types": ["sms:received", "sms:sent"], // optional, defaults to all
    "include_numbers": ["+1234567890"], // optional, whitelist
    "exclude_numbers": ["+0987654321"]  // optional, blacklist - error if both specified
  }
  ```

## Operational Details

### Startup Sequence
1. Check if port 8000 is available (crash if occupied)
2. Wait for SMS Gateway health check (max 10 seconds)
3. Authenticate with SMS Gateway using local mode credentials
4. Clear existing webhooks
5. Register new webhooks (crash if registration fails)
6. Start HTTP server on port 8000
7. Start background processes (task cleaner, client pruner, webhook repair)

### Graceful Shutdown
- Wait for all pending forwarding tasks to complete
- Stop accepting new requests
- Clean up resources

### Logging
- All logs output to stdout
- Structured logging for debugging and monitoring

### Health Check
- `GET /health` - Returns service health status

## Security Considerations

- Service runs on trusted local network only
- No HTTPS requirement for internal routing

## Resources

### SMS Gateway API Reference
- **OpenAPI Specification**: Available at `src/android/swagger.json`
- Provides complete API documentation for SMS Gateway for Android
- Key endpoints used by smsgap:
  - `GET /health` - Health check endpoint
  - `GET /webhooks` - List registered webhooks
  - `POST /webhooks` - Register new webhook
  - `DELETE /webhooks/{id}` - Delete webhook
  - `POST /messages` - Send SMS (used by ping.sh)

## Development Tools

### adb-run.sh
Execute commands as root on Android device via ADB using Magisk's busybox ash.

```bash
./scripts/adb-run.sh [-s SERIAL] COMMAND
```

- Runs commands in Magisk's busybox ash shell (standalone mode)
- Handles proper escaping via base64 encoding
- Requires root access via Magisk
- Example: `./scripts/adb-run.sh "ps | grep smsgap"`

### deploy.sh
Build and deploy smsgap to Android device.

```bash
./scripts/deploy.sh [-d DEPLOY_DIR]
```

- Cross-compiles Go binary for Android ARM64
- Deploys binary and boot script to device
- Default deployment directory: `/data/adb/service.d`
- Automatically restarts the service after deployment
- Kills any existing smsgap process before starting new one

### log.sh
Retrieve and display smsgap logs from Android device.

```bash
./scripts/log.sh [-t] [-n LINES] [-f LOGFILE]
```

- `-t`: Tail the log file continuously
- `-n LINES`: Number of lines to display (default: all)
- `-f LOGFILE`: Log file path (default: `/data/adb/service.d/smsgap.log`)
- Example: `./scripts/log.sh -t` to follow logs in real-time

### boot.sh
Deployed to device to manage service startup.

```bash
boot.sh [-b SECONDS]
```

- Runs automatically on boot when placed in `/data/adb/service.d`
- Waits for device boot completion
- Disables Android Doze mode
- Prevents WiFi sleep when screen is off
- Starts smsgap in background with proper logging
- Note: Port 8000 conflict handling added in development setup (step 1)
- `-b SECONDS`: Optional boot delay (default: 10, use 0 for immediate start)

### ping.sh
Send a test SMS to the SETTLER device through SMS Gateway.

```bash
./scripts/ping.sh [-m MESSAGE]
```

- `-m MESSAGE`: Custom message text (default: "Ping from smsgap")
- Uses SETTLER credentials from `.env` file in project root
- Sends SMS to the SETTLER phone number (self-message for testing)
- Triggers the following SMS Gateway webhooks:
  - `sms:sent` - When message is sent
  - `sms:delivered` - When message is delivered
  - `sms:received` - When message is received by the same device
- Note: Does not trigger `sms:failed` webhook (message succeeds)
- Useful for end-to-end testing of the SMS pipeline
- Example: `./scripts/ping.sh -m "Test message"`

## Development Strategy

### Incremental Development Approach

Development will proceed incrementally, starting with the most load-bearing features and verifying functionality at each step.

**Important**: The implementor should pause after each numbered step to verify functionality and check with stakeholders before proceeding to the next step.

### Phase 1: SMS Gateway Integration
**Goal**: Establish bidirectional communication with SMS Gateway

1. **Development Environment Setup** (v0.0)
   - Update boot.sh to handle port 8000 conflicts:
     ```bash
     if fuser -s 8000/tcp; then
         echo "[$(date)] Port 8000 in use, killing existing process" >> $LOG
         fuser -k 8000/tcp
     fi
     ```
   - This enables rapid redeployment during development
   - Verification: 
     - Deploy twice in succession, verify no port conflicts
     - Check boot.log shows "Port 8000 in use, killing existing process" on second deploy

2. **Basic HTTP Server** (v0.1)
   - Implement go-chi server on port 8000
   - Check port availability on startup (crash if occupied)
   - Add `/health` endpoint
   - Verification: `curl localhost:8000/health` returns 200

3. **SMS Gateway Health Check** (v0.2)
   - Add startup health check for SMS Gateway on port 8080
   - Implement 10-second timeout with retry
   - Verification: Service starts when SMS Gateway is running, crashes when it's not

4. **Webhook Management** (v0.3)
   - Add SMS Gateway client with basic auth
   - Implement webhook cleanup on startup
   - Register webhook for `sms:received` only
   - Add stub webhook endpoint that logs and returns 200
   - Verification: 
     - Check SMS Gateway UI shows registered webhook
     - Run `ping.sh` and verify logs show received webhook
   
4a. **Complete Webhook Registration** (v0.3a)
   - Add remaining webhook types (`sms:sent`, `sms:delivered`, `sms:failed`)
   - Add stub endpoints for each
   - Verification: Run `ping.sh` and verify all 3 triggered webhooks log

5. **Webhook Echo Test** (v0.4)
   - Parse webhook payloads
   - Log structured webhook data
   - Verification: Run `ping.sh` and confirm all fields are correctly parsed

### Phase 2: Testing Infrastructure
**Goal**: Create test suite before adding business logic

6. **Test Fixtures** (v0.5)
   - Create webhook payload fixtures from actual SMS Gateway requests
   - Set up test framework similar to src/server/tests
   - Write integration tests for webhook endpoints
   - Verification: Tests pass with captured payloads

### Phase 3: Client Management
**Goal**: Implement client registration and lifecycle

7. **Basic Client Registration** (v0.6)
   - Implement `/register` endpoint
   - Store clients in memory (no filtering yet)
   - Add client pruning (60-second timeout)
   - Verification: Register a test client, verify it appears in memory, wait 60s and verify removal

8. **Webhook Forwarding** (v0.7)
   - Forward webhooks to registered clients synchronously
   - Return 200 immediately to SMS Gateway
   - Verification: Register test HTTP server as client, run `ping.sh`, verify forwarding

### Phase 4: Advanced Features
**Goal**: Add filtering and async processing

9. **Phone Number Filtering** (v0.8)
   - Add include/exclude number lists to registration
   - Implement filtering logic in webhook processing
   - Verification: Test with multiple clients and different phone filters

10. **Async Task Management** (v0.9)
   - Move forwarding to goroutines
   - Implement concurrent task bag
   - Add task cleanup process
   - Verification: Register slow client, verify immediate 200 to SMS Gateway

11. **Retry Logic** (v1.0)
    - Add 3 linear retries for failed forwards
    - Track retry attempts per task
    - Verification: Register failing client, verify 3 attempts in logs

### Phase 5: Production Readiness

12. **Graceful Shutdown** (v1.1)
    - Wait for pending tasks on shutdown
    - Clean webhook registration on exit
    - Verification: Start forwarding, kill process, verify clean shutdown

13. **Observability** (v1.2)
    - Add structured logging
    - Add metrics/debugging endpoints
    - Verification: Run under load, verify all operations logged

### Phase 6: Low Priority Features

14. **Phone Number Validation** (v1.3)
    - Add regex validation `^\+?\d{10,14}$` for phone numbers
    - Return error on invalid numbers in registration
    - Verification: Test with various phone number formats

15. **Webhook Auto-Repair** (v1.4)
    - Implement 30-second webhook verification process
    - Re-register missing webhooks automatically
    - Verification: Manually delete webhook, verify auto-restoration

### Verification Methods

- **Manual Testing**: Use `ping.sh` for end-to-end tests
- **Log Monitoring**: Use `log.sh -t` to watch real-time behavior  
- **Unit Tests**: Run after each phase completion
- **Integration Tests**: Use fixtures to simulate SMS Gateway
- **Device Testing**: Deploy with `deploy.sh` and verify on actual device

### Success Criteria

Each phase must:
1. Pass all tests from previous phases
2. Successfully handle `ping.sh` test
3. Log all operations clearly
4. Handle errors gracefully
5. Deploy and run on device without crashes

## Deployment

The service is deployed to `/data/adb/service.d/` and runs automatically on device boot via Magisk.