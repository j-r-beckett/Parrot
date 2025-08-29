#!/bin/bash

set -e

usage() {
    echo "Usage: $(basename "$0") [-v] [-h] RING"
    echo "Build and deploy parrot-hub Docker image"
    echo ""
    echo "Arguments:"
    echo "  RING  Deployment ring (required: prod or ppe)"
    echo ""
    echo "Options:"
    echo "  -v    Verbose output"
    echo "  -h    Show this help message"
    exit 0
}

REGISTRY=192.168.0.12:4000
VERBOSE=false

while getopts "vh" opt; do
    case $opt in
        v) VERBOSE=true ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND-1))

if [ $# -lt 1 ]; then
    echo "Error: Missing required RING argument" >&2
    usage
fi

RING="$1"

if [[ "$RING" != "prod" && "$RING" != "ppe" ]]; then
    echo "Error: Invalid RING '$RING'. Must be 'prod' or 'ppe'" >&2
    exit 1
fi

cd "$(dirname "$0")"

run_step() {
    local msg="$1"
    shift
    echo "$msg"
    if [ "$VERBOSE" = true ]; then
        if ! "$@"; then
            echo "Error: $msg failed" >&2
            exit 1
        fi
    else
        set +e  # Temporarily disable exit on error
        local error_output
        error_output=$("$@" 2>&1)
        local exit_code=$?
        set -e  # Re-enable exit on error
        
        if [ $exit_code -ne 0 ]; then
            echo "Error: $msg failed" >&2
            if [ -n "$error_output" ]; then
                echo "$error_output" >&2
            fi
            exit 1
        fi
    fi
}

export REGISTRY
export RING
export VERSION=$(grep -E '^version' pyproject.toml | cut -d'"' -f2)

if [ -z "$VERSION" ]; then
    echo "Error: Could not extract version from pyproject.toml" >&2
    exit 1
fi

TAG="$REGISTRY/parrot:$RING-$VERSION"
DEPLOY_DIR="/home/jimmy/parrot-hub-$RING"

run_step "Building Docker image: $TAG" docker build -t "$TAG" .

run_step "Pushing image to registry..." docker push "$TAG"

echo "Deploying:"
echo "  Service: parrot-hub-$RING"
echo "  Version: $VERSION"
echo "  Environment: $(echo "$RING" | tr '[:lower:]' '[:upper:]')"

if [ "$RING" = "prod" ]; then
    read -p "Continue with production deployment? [y/N]: " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled"
        exit 0
    fi
fi

run_step "Preparing deployment directory on remote server..." ssh jimmy@192.168.0.12 "mkdir -p $DEPLOY_DIR"

echo "Setting environment-specific host port..."
if [ "$RING" = "ppe" ]; then
    export PARROT_HUB_HOST_PORT="$PARROT_HUB_HOST_PORT_PPE"
elif [ "$RING" = "prod" ]; then
    export PARROT_HUB_HOST_PORT="$PARROT_HUB_HOST_PORT_PROD"
fi
echo "Port: $PARROT_HUB_HOST_PORT"

export RING

echo "Generating docker-compose configuration..."
COMPOSE_CONTENT=$(envsubst < compose.template.yml)

run_step "Deploying configuration to remote server..." ssh jimmy@192.168.0.12 "cd $DEPLOY_DIR && cat > compose.yml" <<< "$COMPOSE_CONTENT"

run_step "Stopping existing services and deploying new version..." ssh jimmy@192.168.0.12 "cd $DEPLOY_DIR \
  && docker compose -p parrot-hub-$RING down \
  && docker pull $TAG \
  && docker compose -p parrot-hub-$RING up -d"

echo "Deployment complete!"
