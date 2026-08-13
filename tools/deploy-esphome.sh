#!/usr/bin/env bash
#
# Deploy the rovsun ESPHome template to a network-attached ESP32-C3.
#
# The ESPHome compiler runs inside the `esphome` docker container on the
# remote host (nasomv). The device is flashed over-the-air (OTA), so no USB
# passthrough is required on either side.
#
# The custom `rovsun_a5` component is pulled from the git source defined in the
# YAML (`external_components` -> type: git, refresh: 0s), NOT from a local copy.
# So the firmware changes MUST be committed and pushed to the git remote
# (origin = github.com/JugglerMaster/rovsun-control) BEFORE running this script,
# otherwise the device flashes the stale published component.
#
# What this does:
#   1. Stage the local YAML in a writable dir on the remote host (the esphome
#      config bind-mount is not writable by the SSH user, so we use `docker cp`).
#   2. `docker cp` it into the container's /config volume.
#   3. Run `docker exec esphome esphome run ...` to compile + OTA-flash (the
#      component is fetched fresh from git on every run via refresh: 0s).
#
# Usage:
#   ./deploy-esphome.sh [yaml-name] [device-name-or-ip]
#
#   yaml-name  YAML in the repo's esphome/ dir to deploy (default: rovsun-c3.yaml).
#              Use rovsun-upstairs.yaml for the second unit.
#   device     Optional explicit IP/hostname for OTA; defaults to OTA auto-resolve.
#
# Configurable via environment:
#   NASOMV_HOST        ssh host alias / user@host   (default: nasomv)
#   ESPHOME_CONTAINER  docker container name        (default: esphome)
#
# NOTE: commit & push firmware changes to the git remote BEFORE deploying.
#
set -euo pipefail

NASOMV_HOST="${NASOMV_HOST:-nasomv}"
ESPHOME_CONTAINER="${ESPHOME_CONTAINER:-esphome}"

REPO_ESPHOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/esphome"

YAML_NAME="${1:-rovsun-c3.yaml}"
DEVICE="${2:-}"
LOCAL_YAML="${REPO_ESPHOME}/${YAML_NAME}"

if [[ ! -f "$LOCAL_YAML" ]]; then
  echo "ERROR: local yaml not found at $LOCAL_YAML" >&2
  exit 1
fi

STAGE_REMOTE="esphome-stage"
STAGE_YAML="${STAGE_REMOTE}/${YAML_NAME}"

echo ">> Staging template on ${NASOMV_HOST} ..."
ssh "$NASOMV_HOST" "rm -rf ${STAGE_REMOTE} && mkdir -p ${STAGE_REMOTE}"
scp "$LOCAL_YAML" "${NASOMV_HOST}:${STAGE_YAML}"

echo ">> Copying into ${ESPHOME_CONTAINER}:/config ..."
ssh "$NASOMV_HOST" "docker cp ${STAGE_YAML} ${ESPHOME_CONTAINER}:/config/${YAML_NAME}"

echo ">> Clearing ESPHome build cache (component is pulled fresh from git via refresh: 0s)"
ssh "$NASOMV_HOST" "docker exec ${ESPHOME_CONTAINER} bash -c 'rm -rf /config/.esphome/build/*/src/esphome/components/rovsun_a5'"

echo ">> Compiling + OTA flashing via container ..."
# --device OTA resolves the address via mDNS/DNS/MQTT and avoids the
# interactive prompt. Pass an explicit IP/name as $1 to override.
# --no-logs makes esphome exit after the OTA upload instead of attaching to
# live device logs (which would hang forever). This step takes a few minutes
# (longer on a first/clean build), so call this script with a generous timeout.
DEVICE_ARG="${DEVICE:-OTA}"
ssh "$NASOMV_HOST" "docker exec $ESPHOME_CONTAINER esphome run /config/${YAML_NAME} --device ${DEVICE_ARG} --no-logs"
