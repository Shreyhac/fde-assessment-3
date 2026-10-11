#!/usr/bin/env bash
# Shreyansh Arora | 24bcs10252
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
python3 -m venv .venv || { echo "Install your OS python3-venv package, then retry."; exit 1; }
.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python run_local.py
