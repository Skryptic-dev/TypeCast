# TypeCast Linux Build

This folder is a self-contained Linux source bundle for TypeCast.

TypeCast can run two ways on Linux:

- **Focused mode:** click the TypeCast window and type while it is focused.
- **Background input mode:** TypeCast reads your keyboard directly from Linux `/dev/input/eventX`.

Background input mode does **not** depend on X11. It can work on X11 or Wayland because it uses Linux evdev input devices below the display server.

## Files

- `main.py` - TypeCast game.
- `typecast_config.json` - Config file. Set `keyboard_device` here.
- `find_keyboard_devices.py` - Lists likely keyboard devices.
- `run_typecast.sh` - Runs TypeCast from source.
- `find_keyboards.sh` - Runs the keyboard device finder.
- `setup_input_permissions.sh` - Optional helper to add your user to the `input` group.
- `build_linux.sh` - Optional PyInstaller build script.
- `assets/` - Editable PNG asset folders. See `assets/README.md`.

## Install Requirements

Install Python 3 and Tkinter.

Debian/Ubuntu:

```bash
sudo apt install python3 python3-tk
```

Fedora:

```bash
sudo dnf install python3 python3-tkinter
```

Arch:

```bash
sudo pacman -S python tk
```

Discord Rich Presence is optional:

```bash
python3 -m pip install pypresence
```

## Quick Run

From this folder:

```bash
chmod +x *.sh
./run_typecast.sh
```

If no keyboard device is configured, TypeCast still works while the game window is focused.

## Editable Files Must Stay Beside The Game

TypeCast looks for these editable files beside the script or executable:

- `typecast_config.json`
- `assets/`

If you build or move the game somewhere else, copy those items into the same folder as `TypeCast`.

For example, after building, this is the expected layout:

```text
release/
  TypeCast
  typecast_config.json
  assets/
```

The build script copies these into `release/` automatically. If `typecast_config.json` or `assets/` are missing from the folder you run the game from, TypeCast may fall back to bundled defaults or print a file error instead of using your edited files.

## Scene-Only Assets

If you want to replace the drawn pond/background scene, put a PNG in `assets/scenes/`.

Useful names are:

```text
assets/scenes/default.png
assets/scenes/pond.png
assets/scenes/river.png
assets/scenes/ocean.png
```

When a scene image exists, TypeCast clears the old drawn scene first, then draws your PNG. Transparent pixels in the PNG will show the window background instead of the old pond art.

## Enable Background Keyboard Input

### 1. Find Your Keyboard Device

Run:

```bash
./find_keyboards.sh
```

Look for a likely keyboard device.

Examples:

```text
/dev/input/event0
/dev/input/event4
/dev/input/by-id/usb-Example_Keyboard-event-kbd
```

If a `/dev/input/by-id/...-event-kbd` path is shown, prefer that. It is more stable than `/dev/input/event0`, because event numbers can change after reboot or unplugging devices.

### 2. Set The Device In Config

Open `typecast_config.json` and set:

```json
"keyboard_device": "/dev/input/event0"
```

or, preferably:

```json
"keyboard_device": "/dev/input/by-id/usb-YOUR_KEYBOARD-event-kbd"
```

`event0` is only an example. Use whatever `find_keyboards.sh` shows for your keyboard.

### 3. Test It

Run TypeCast from a terminal:

```bash
./run_typecast.sh
```

If it works, the Settings tab should say something like:

```text
Input capture: background capture enabled (/dev/input/event0)
```

The terminal should also print debug lines like:

```text
[TypeCast input] Trying Linux evdev keyboard device: /dev/input/event0
[TypeCast input] Opened Linux evdev keyboard device: /dev/input/event0
[TypeCast input] poll device=/dev/input/event0 focused=False events_total=12 events_since_last=4 pressed=[30]
```

If `focused=False` and `events_since_last` increases while you type in another app, background input is working.

## Fix Permission Denied

If TypeCast cannot read the device, you may see `permission denied`.

Most Linux systems protect `/dev/input/eventX`. A common fix is:

```bash
./setup_input_permissions.sh
```

Then log out and back in.

That script runs:

```bash
sudo usermod -a -G input "$USER"
```

This adds your user to the `input` group. You must log out and back in before the group change applies.

## If The Input Group Still Cannot Read Devices

Some distros do not assign keyboard event devices to the `input` group by default.

Check your device permissions:

```bash
ls -l /dev/input/event0
```

You want to see something like:

```text
crw-rw---- 1 root input ... /dev/input/event0
```

The important parts are:

- group is `input`
- group has read permission, shown by `rw-`

If the group is not `input`, your distro may need a udev rule.

Create this file:

```bash
sudo nano /etc/udev/rules.d/99-typecast-input.rules
```

Put this inside:

```udev
SUBSYSTEM=="input", KERNEL=="event[0-9]*", GROUP="input", MODE="0660"
```

Then reload udev rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and replug the keyboard, or reboot.

Then check again:

```bash
ls -l /dev/input/event0
```

Some systems already have similar rules in:

```text
/lib/udev/rules.d/50-udev-default.rules
```

For example:

```udev
SUBSYSTEM=="input", GROUP="input"
SUBSYSTEM=="input", KERNEL=="js[0-9]*", MODE="0664"
```

If your system already has a working default rule, you may only need to join the `input` group.

## Tiling Window Managers

TypeCast asks Linux window managers to treat it like a small dialog-style window and sets its window class to `TypeCast`.

Most desktop environments will handle this automatically. If you use a tiling window manager and want TypeCast to float, add a rule for the `TypeCast` class.

Examples:

```text
# i3 / Sway
for_window [class="TypeCast"] floating enable

# Hyprland
windowrule = float,class:^(TypeCast)$
```

## Troubleshooting Checklist

If background input does not work:

1. Run `./find_keyboards.sh`.
2. Confirm `keyboard_device` matches a real keyboard device.
3. Prefer `/dev/input/by-id/...-event-kbd` if available.
4. Run `ls -l YOUR_DEVICE_PATH`.
5. Confirm your user is in the `input` group:

```bash
groups
```

6. Log out and back in after changing groups.
7. Run `./run_typecast.sh` from a terminal.
8. Send the `[TypeCast input]` debug lines to me (Hazel) if it still fails.

## Build A Native Linux Executable

Install PyInstaller:

```bash
python3 -m pip install pyinstaller
```

Then:

```bash
chmod +x *.sh
./build_linux.sh
```

The executable is created at:

```text
release/TypeCast
```

The build script also copies these editable files into `release/`:

```text
release/typecast_config.json
release/assets/
release/find_keyboard_devices.py
```

Keep those beside `release/TypeCast` if you zip or share the build.
