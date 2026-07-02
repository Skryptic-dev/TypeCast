import os
import re
from pathlib import Path


INPUT_DEVICES = Path("/proc/bus/input/devices")
DEV_INPUT = Path("/dev/input")
DEV_INPUT_BY_ID = DEV_INPUT / "by-id"


def parse_input_devices():
    if not INPUT_DEVICES.exists():
        return []

    blocks = INPUT_DEVICES.read_text(encoding="utf-8", errors="replace").strip().split("\n\n")
    devices = []
    for block in blocks:
        name = "Unknown device"
        handlers = ""
        phys = ""
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("H: Handlers="):
                handlers = line.split("=", 1)[1].strip()
            elif line.startswith("P: Phys="):
                phys = line.split("=", 1)[1].strip()

        event_match = re.search(r"\bevent\d+\b", handlers)
        if not event_match:
            continue

        event_name = event_match.group(0)
        is_keyboard = "kbd" in handlers.split()
        devices.append(
            {
                "name": name,
                "phys": phys,
                "event": event_name,
                "path": DEV_INPUT / event_name,
                "is_keyboard": is_keyboard,
                "handlers": handlers,
            }
        )
    return devices


def by_id_links_for(path):
    if not DEV_INPUT_BY_ID.exists():
        return []
    links = []
    try:
        for link in DEV_INPUT_BY_ID.iterdir():
            if not link.is_symlink():
                continue
            try:
                if link.resolve() == path.resolve():
                    links.append(link)
            except OSError:
                continue
    except OSError:
        return []
    return sorted(links)


def can_read(path):
    return os.access(path, os.R_OK)


def main():
    devices = parse_input_devices()
    keyboard_devices = [device for device in devices if device["is_keyboard"]]
    other_devices = [device for device in devices if not device["is_keyboard"]]

    if not devices:
        print("No /dev/input event devices found.")
        print("This script is intended for Linux systems with /proc/bus/input/devices.")
        return

    print("Likely keyboard devices:")
    if not keyboard_devices:
        print("  None marked with the kbd handler.")
    for device in keyboard_devices:
        print_device(device)

    if other_devices:
        print()
        print("Other event devices:")
        for device in other_devices:
            print_device(device)

    print()
    print("Use the path from a likely keyboard device in typecast_config.json:")
    print('  "keyboard_device": "/dev/input/eventX"')
    print()
    print("If permission is denied, add your user to the input group, then log out and back in:")
    print("  sudo usermod -a -G input $USER")


def print_device(device):
    path = device["path"]
    readable = "readable" if can_read(path) else "permission denied"
    print(f"  {path} ({readable})")
    print(f"    name: {device['name']}")
    if device["phys"]:
        print(f"    phys: {device['phys']}")
    links = by_id_links_for(path)
    if links:
        print("    stable paths:")
        for link in links:
            print(f"      {link}")
    print(f"    handlers: {device['handlers']}")


if __name__ == "__main__":
    main()
