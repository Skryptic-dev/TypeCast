#!/usr/bin/env bash
set -euo pipefail

echo "TypeCast Linux background input capture reads /dev/input/eventX devices."
echo "Most distros require your user to be in the input group for that."
echo
echo "This will run:"
echo "  sudo usermod -a -G input \"$USER\""
echo
read -r -p "Continue? [y/N] " answer
case "$answer" in
  y|Y|yes|YES)
    sudo usermod -a -G input "$USER"
    echo
    echo "Done. Log out and back in before running TypeCast again."
    ;;
  *)
    echo "Canceled."
    ;;
esac
