#!/bin/bash
set -e

REGISTRY=192.168.0.12:4000
RING=ppe
VERSION=0.1.0
TAG=$REGISTRY/clanker:$RING-$VERSION

docker build -t $TAG .
docker push $TAG

ssh jimmy@192.168.0.12 "mkdir -p /home/jimmy/clanker-$RING"

scp compose.yml jimmy@192.168.0.12:/home/jimmy/clanker-$RING/

ssh jimmy@192.168.0.12 "cd /home/jimmy/clanker-$RING \
  && docker compose -p clanker-$RING down \
  && docker pull $TAG \
  && docker compose up -d"
