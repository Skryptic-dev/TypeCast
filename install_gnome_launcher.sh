#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/typecast.desktop"

mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=TypeCast
Comment=Desktop fishing typing game
Exec=$SCRIPT_DIR/run_typecast.sh
Icon=$SCRIPT_DIR/typecast.png
Terminal=false
Categories=Game;
StartupWMClass=TypeCast
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed GNOME launcher:"
echo "$DESKTOP_FILE"
echo "If TypeCast was already open, close and reopen it from the app launcher."
