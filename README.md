# Parrot

AI assistant accessible via SMS. Send a text, get an intelligent response - no app or data connection required.

Sometimes you need AI assistance but only have SMS access. Parrot bridges that gap by connecting your phone's SMS to Claude, responding with concise answers optimized for text messaging. Parrot has access to tools for weather, navigation, web search, recipe retrieval, and (NYC only) Citi Bike station finding.

Parrot requires [SMS Gateway](https://github.com/capcom6/android-sms-gateway).

## Development

Enable pre-commit hooks: `git config core.hooksPath .githooks`

Enable direnv: `direnv allow`

Stream logs from Android device: ./scripts/mgsk-run.sh "$SERIAL" "tail -f /data/adb/service.d/sms-proxy.log
