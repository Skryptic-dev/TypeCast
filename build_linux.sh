#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "Python tkinter is required. Install python3-tk or your distro's equivalent." >&2
  exit 1
fi

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is not installed."
  echo "Install it with: python3 -m pip install pyinstaller"
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

python3 -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --windowed \
  --name TypeCast \
  --hidden-import pypresence \
  --hidden-import pypresence.presence \
  --add-data "typecast_config.json:." \
  --add-data "find_keyboard_devices.py:." \
  --add-data "typecast.png:." \
  --add-data "assets:assets" \
  --distpath "$SCRIPT_DIR/release" \
  --workpath "$SCRIPT_DIR/build" \
  --specpath "$SCRIPT_DIR/build" \
  main.py

rm -rf "$SCRIPT_DIR/build"

cp "$SCRIPT_DIR/typecast_config.json" "$SCRIPT_DIR/release/typecast_config.json"
cp "$SCRIPT_DIR/typecast_config.example.json" "$SCRIPT_DIR/release/typecast_config.example.json"
cp "$SCRIPT_DIR/find_keyboard_devices.py" "$SCRIPT_DIR/release/find_keyboard_devices.py"
rm -rf "$SCRIPT_DIR/release/assets"
cp -R "$SCRIPT_DIR/assets" "$SCRIPT_DIR/release/assets"

echo "Built $SCRIPT_DIR/release/TypeCast"
echo "Editable config and assets were copied into $SCRIPT_DIR/release/"
