#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/typecast_config.json" ]; then
  if [ -f "$SCRIPT_DIR/typecast_config.example.json" ]; then
    cp "$SCRIPT_DIR/typecast_config.example.json" "$SCRIPT_DIR/typecast_config.json"
    echo "Created local typecast_config.json from typecast_config.example.json"
  else
    echo "typecast_config.json is missing, and no example config was found." >&2
    exit 1
  fi
fi

exec python3 main.py
