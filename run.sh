#!/usr/bin/env bash
# Launch the VDAS-Insight Streamlit app.
set -euo pipefail
cd "$(dirname "$0")"
exec streamlit run app/Home.py "$@"
