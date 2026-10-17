#!/usr/bin/env bash
set -eo pipefail
set +x
umask 077
if (( $# == 0 )); then
  echo 'Usage: ./with_config.sh COMMAND [ARGS...]' >&2
  exit 2
fi
mapfile -t LAB_CONFIG_FILES < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
if (( ${#LAB_CONFIG_FILES[@]} != 1 )); then
  echo 'Expected exactly one /config/*.config file on the workshop VM.' >&2
  exit 1
fi
set -a
source "${LAB_CONFIG_FILES[0]}" >/dev/null 2>&1
set +a
exec "$@"
