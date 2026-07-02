#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to update from GitHub." >&2
  echo "Install git with your distro package manager, then run this again." >&2
  exit 1
fi

if [ ! -d "$SCRIPT_DIR/.git" ]; then
  echo "This folder is not a git clone." >&2
  echo "Clone the GitHub repo first, or run git pull manually from your clone." >&2
  exit 1
fi

git pull --ff-only

if [ ! -f "$SCRIPT_DIR/typecast_config.json" ] && [ -f "$SCRIPT_DIR/typecast_config.example.json" ]; then
  cp "$SCRIPT_DIR/typecast_config.example.json" "$SCRIPT_DIR/typecast_config.json"
  echo "Created local typecast_config.json from typecast_config.example.json"
fi

echo "TypeCast is up to date."
