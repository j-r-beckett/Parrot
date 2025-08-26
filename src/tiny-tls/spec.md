# tiny-tls Specification

## Overview
tiny-tls is a CLI utility that runs as a daemon to manage TLS certificates for other services. It periodically renews certificates and notifies services of updates.

## Core Functionality
1. Periodically renew TLS certificates
2. Notify services after certificate renewal
3. Store certificates on the filesystem

## Implementation Details

### Technology Stack
- Language: Go
- Certificate generation: certmagic library
- Challenge type: DNS-01 with Cloudflare
- Storage: Filesystem (using google/renameio for atomic writes)
- Certificate expiry: renewal interval * 2 (e.g., if -r is 30d, cert expires in 60d)

### Required Arguments
#### Positional
1. `domain` - Domain name to generate certificate for
   - Must match regex: `^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9])*$`
   - Must be ≤ 253 characters

#### Named (Flags)
- `-d` - Directory where certificates should be stored
  - Creates `dir/cert.pem` and `dir/key.pem`
- `-u` - HTTP endpoint to notify of certificate reload
  - Must start with `http://`

### Optional Arguments
- `-k` - Reference to Cloudflare API key location
  - File path: Must start with `/`, `./`, `../`, or `~/`
  - Environment variable: Must match `^[A-Z][A-Z0-9_]*$`
  - Validation: File must exist and be readable, env var must not be empty
  - Default: `CLOUDFLARE_API_KEY`
- `-r` (reload interval) - How often to renew certificates
  - Format: number + suffix (30s, 5m, 2h, 7d, 3w, 6mo, 1y)
  - Default: 30d

### Behavior
- Overwrite existing certificates by default (no clobber flag needed)
- Do not hit reload URL on startup, wait for first interval
- If reload URL fails:
  - Retry up to 3 times with 1 second wait between attempts
  - Continue to next interval cycle if all retries fail (don't crash)
- Cloudflare API retries use exponential backoff:
  - Formula: `delay = min(base * (2^attempt) * (1 + random(0, 0.1)), max_delay)`
  - Base delay: 1s
  - Max delay: 24h

### Logging
- Write logs to stdout
- Format: `{date} {level} {message}`
- Levels: INFO (default), WARNING, ERROR
- Use system time zone for date formatting
- Example: `2024-01-15T10:30:45-05:00 INFO Certificate renewal started`

### Module Structure
1. **Init Module** - Handles argument parsing and validation
2. **Cert Generation Module** - Generates certificates and writes to filesystem
3. **Daemon Module** - Manages periodic renewal cycle

### Error Handling
- Invalid domain format or length: Return error
- Invalid key reference (not file path or env var): Return error
- File path doesn't exist or unreadable: Return error
- Environment variable empty: Return error
- URL doesn't start with http://: Return error