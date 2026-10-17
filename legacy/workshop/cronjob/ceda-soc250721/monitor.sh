#!/usr/bin/env bash
set -eo pipefail
set +x
LAB_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec bash "$LAB_SCRIPT_DIR/with_config.sh" python3 "$LAB_SCRIPT_DIR/monitor.py" "$@"
