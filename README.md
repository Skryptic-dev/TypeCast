# TypeCast Linux Build

This folder is a self-contained Linux source bundle for TypeCast.

TypeCast can run two ways on Linux:

- **Focused mode:** click the TypeCast window and type while it is focused.
- **Background input mode:** TypeCast reads your keyboard directly from Linux `/dev/input/eventX`.

Background input mode does **not** depend on X11. It can work on X11 or Wayland because it uses Linux evdev input devices below the display server.

## Files

- `main.py` - TypeCast game.
- `typecast_config.example.json` - Starter config copied into `typecast_config.json` on first run.
- `typecast_config.json` - Local player config. Set `keyboard_device` here. This file is ignored by git.
- `find_keyboard_devices.py` - Lists likely keyboard devices.
- `run_typecast.sh` - Runs TypeCast from source.
- `update_typecast.sh` - Pulls the latest GitHub update.
- `install_gnome_launcher.sh` - Adds a GNOME/Pop!_OS app launcher with the TypeCast window class.
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

## GitHub Setup

This folder is ready to upload as its own GitHub repo.

Upload the contents of this `linuxbuild` folder, not the parent `dist` folder. The repo should look like this:

```text
main.py
assets/
README.md
run_typecast.sh
update_typecast.sh
install_gnome_launcher.sh
typecast_config.example.json
```

Do not upload your personal `typecast_config.json`. It is ignored by `.gitignore` so each player can keep their own keyboard device and settings.

First-time install from GitHub:

```bash
git clone https://github.com/Skryptic-dev/TypeCast.git
cd TypeCast
chmod +x *.sh
./run_typecast.sh
```

After that, update with:

```bash
./update_typecast.sh
./run_typecast.sh
```

The first run creates `typecast_config.json` from `typecast_config.example.json`.

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
- `typecast_config.example.json`
- `assets/`

If you build or move the game somewhere else, copy those items into the same folder as `TypeCast`.

For example, after building, this is the expected layout:

```text
release/
  TypeCast
  typecast_config.json
  typecast_config.example.json
  assets/
```

The build script copies these into `release/` automatically. If `typecast_config.json` is missing, `run_typecast.sh` and `build_linux.sh` create it from `typecast_config.example.json`.

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

### GNOME / Pop!_OS / Pop Shell

Pop!_OS uses GNOME with Pop Shell tiling. TypeCast sets its window class to:

```text
TypeCast
```

For best GNOME/Pop!_OS behavior, install the local app launcher once:

```bash
./install_gnome_launcher.sh
```

Then close TypeCast and reopen it from the app launcher. The launcher includes:

```text
StartupWMClass=TypeCast
```

If Pop Shell tiles TypeCast and you want it floating, use one of these options:

1. Open TypeCast, then use Pop Shell's window menu or keyboard shortcuts to toggle that window to floating.
2. Open Pop Shell or GNOME extension settings and add a floating window exception for the `TypeCast` app/class.
3. If the settings UI asks for a window class, use `TypeCast`.

Pop Shell versions and extensions can label this differently, such as floating exceptions, window exceptions, or per-app tiling rules. The important identifier is always `TypeCast`.

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
release/typecast_config.example.json
release/assets/
release/find_keyboard_devices.py
```

Keep those beside `release/TypeCast` if you zip or share the build.
