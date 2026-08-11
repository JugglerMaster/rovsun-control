#!/usr/bin/env bash
#
# Deploy the rovsun ESPHome template to a network-attached ESP32-C3.
#
# The ESPHome compiler runs inside the `esphome` docker container on the
# remote host (nasomv). The device is flashed over-the-air (OTA), so no USB
# passthrough is required on either side.
#
# What this does:
#   1. Stage the local YAML and the custom `rovsun_a5` component in a
#      writable dir on the remote host (the esphome config bind-mount is not
#      writable by the SSH user, so we use `docker cp` instead of scp-direct).
#   2. `docker cp` them into the container's /config volume.
#   3. Run `docker exec esphome esphome run ...` to compile + OTA-flash.
#
# Usage:
#   ./deploy-esphome.sh [device-name-or-ip]
#
# Configurable via environment:
#   NASOMV_HOST        ssh host alias / user@host   (default: nasomv)
#   ESPHOME_CONTAINER  docker container name        (default: esphome)
#
set -euo pipefail

NASOMV_HOST="${NASOMV_HOST:-nasomv}"
ESPHOME_CONTAINER="${ESPHOME_CONTAINER:-esphome}"

REPO_ESPHOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/esphome"
LOCAL_YAML="${REPO_ESPHOME}/rovsun-c3.yaml"
LOCAL_COMPONENTS="${REPO_ESPHOME}/components"

YAML_NAME="rovsun-c3.yaml"
DEVICE="${1:-}"

if [[ ! -f "$LOCAL_YAML" ]]; then
  echo "ERROR: local yaml not found at $LOCAL_YAML" >&2
  exit 1
fi

STAGE_REMOTE="esphome-stage"
STAGE_YAML="${STAGE_REMOTE}/${YAML_NAME}"
STAGE_COMP="$(basename "$LOCAL_COMPONENTS")/rovsun_a5"

echo ">> Staging template + custom component on ${NASOMV_HOST} ..."
ssh "$NASOMV_HOST" "rm -rf ${STAGE_REMOTE} && mkdir -p ${STAGE_REMOTE}/components"
scp "$LOCAL_YAML" "${NASOMV_HOST}:${STAGE_YAML}"
scp -r "${LOCAL_COMPONENTS}/rovsun_a5" "${NASOMV_HOST}:${STAGE_REMOTE}/components/"

echo ">> Copying into ${ESPHOME_CONTAINER}:/config ..."
ssh "$NASOMV_HOST" "docker cp ${STAGE_YAML} ${ESPHOME_CONTAINER}:/config/${YAML_NAME}"
ssh "$NASOMV_HOST" "docker cp ${STAGE_REMOTE}/components/rovsun_a5 ${ESPHOME_CONTAINER}:/config/components/"

echo ">> Compiling + OTA flashing via container ..."
# --device OTA resolves the address via mDNS/DNS/MQTT and avoids the
# interactive prompt. Pass an explicit IP/name as $1 to override.
# --no-logs makes esphome exit after the OTA upload instead of attaching to
# live device logs (which would hang forever). This step takes a few minutes
# (longer on a first/clean build), so call this script with a generous timeout.
DEVICE_ARG="${DEVICE:-OTA}"
ssh "$NASOMV_HOST" "docker exec $ESPHOME_CONTAINER esphome run /config/${YAML_NAME} --device ${DEVICE_ARG} --no-logs"
