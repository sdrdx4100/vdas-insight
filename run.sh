#!/usr/bin/env bash
# Launch the VDAS-Insight desktop application.
set -euo pipefail
cd "$(dirname "$0")"
exec python -m desktop.main "$@"
