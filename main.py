import ctypes
import json
import os
import random
import struct
import subprocess
import sys
import time
import tkinter as tk
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from typing import List

try:
    import winreg
except ImportError:
    winreg = None

try:
    from pypresence.presence import Presence
except ImportError:
    Presence = None

APP_DIR = Path(sys.argv[0]).resolve().parent
APP_NAME = "TypeCast"
EMBEDDED_DISCORD_CLIENT_ID = "1509267518274146335"
STARTUP_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
IS_WINDOWS = sys.platform.startswith("win")
ACTIVE_DESKTOP_MODE = not IS_WINDOWS
THEME_NAMES = (
    "Light",
    "Dark",
    "High Contrast",
    "Catppuccin Mocha",
    "Soothing Blue",
    "Soothing Purple",
    "Pink",
    "Green",
    "Cozy Blue",
    "Cozy Purple",
    "Custom",
)
THEME_MENU_LABELS = (
    "Classic - Light",
    "Classic - Dark",
    "Accessibility - High Contrast",
    "Soothing - Catppuccin Mocha",
    "Soothing - Blue",
    "Soothing - Purple",
    "Cozy - Pink",
    "Cozy - Green",
    "Cozy - Blue",
    "Cozy - Purple",
    "Custom",
)
THEME_LABEL_TO_NAME = dict(zip(THEME_MENU_LABELS, THEME_NAMES))
THEME_NAME_TO_LABEL = {name: label for label, name in THEME_LABEL_TO_NAME.items()}
GAME_SCALE_LABELS = ("0.5x", "0.75x", "1x", "1.25x", "1.5x", "1.75x", "2x")
MENU_SCALE_LABELS = ("0.5x", "0.75x", "1x", "1.25x", "1.5x", "1.75x", "2x")
SCALE_VALUES = {
    "0.5x": 0.5,
    "0.75x": 0.75,
    "1x": 1.0,
    "1.25x": 1.25,
    "1.5x": 1.5,
    "1.75x": 1.75,
    "2x": 2.0,
}


def user_data_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base_dir:
        return Path(base_dir) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def bundled_app_dir():
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return APP_DIR


def app_search_paths():
    paths = [APP_DIR]
    cwd = Path.cwd()
    if cwd not in paths:
        paths.append(cwd)
    parent = APP_DIR.parent
    if parent not in paths:
        paths.append(parent)
    bundled = bundled_app_dir()
    if bundled not in paths:
        paths.append(bundled)
    return paths


def find_app_file(filename):
    for directory in app_search_paths():
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return APP_DIR / filename


def user_data_file(filename):
    return user_data_dir() / filename


def unique_paths(paths):
    unique = []
    seen = set()
    for path in paths:
        try:
            key = path.resolve()
        except OSError:
            key = path.absolute()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def legacy_save_candidates():
    paths = [user_data_file("save.json")]
    for directory in app_search_paths():
        paths.append(directory / "typecast_save.json")
        paths.append(directory / "save.json")
    return [path for path in unique_paths(paths) if path != SAVE_FILE]


def load_save_data(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def save_progress_score(data):
    inventory = data.get("inventory", [])
    equipment_levels = data.get("equipment_levels", {})
    return (
        safe_int(data.get("total_keystrokes", 0))
        + safe_int(data.get("banked_keys", 0))
        + safe_int(data.get("coins", 0))
        + safe_int(data.get("backpack_level", 0)) * 1000
        + safe_int(data.get("banked_upgrade_level", 0)) * 1000
        + safe_int(data.get("autosell_level", 0)) * 1000
        + (len(inventory) if isinstance(inventory, list) else 0) * 100
        + (
            sum(safe_int(level) for level in equipment_levels.values())
            if isinstance(equipment_levels, dict)
            else 0
        )
        * 1000
    )


def find_save_to_load():
    current_data = load_save_data(SAVE_FILE) if SAVE_FILE.exists() else None
    if current_data is not None:
        return SAVE_FILE, current_data

    candidates = []
    for path in legacy_save_candidates():
        if not path.exists():
            continue
        data = load_save_data(path)
        if data is None:
            continue
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            modified_at = 0
        candidates.append((save_progress_score(data), modified_at, path, data))

    if not candidates:
        return None, None

    _, _, path, data = max(candidates, key=lambda item: (item[0], item[1]))
    return path, data


def migrate_save_to_user_data(source_path, data):
    if source_path == SAVE_FILE:
        return
    try:
        SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SAVE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


SAVE_FILE = user_data_file("typecast_save.json")
CONFIG_FILE = find_app_file("typecast_config.json")
ICON_FILE = find_app_file("typecast.png")
ASSET_DIR = find_app_file("assets")
TICK_MS = 120
KEY_POLL_MS = 35
DISCORD_UPDATE_MS = 15000
ALWAYS_ON_TOP_REASSERT_DELAYS_MS = (100, 1000, 3000, 8000, 15000, 30000)
AUTOSAVE_SECONDS = 10
AUTO_CAST_SECONDS = 2.5
AUTOSELL_SECONDS = 180
INFO_PANEL_HIDE_SECONDS = 4.0
IDLE_ZZ_SECONDS = 600
OVERFLOW_AUTOSELL_RATE = 0.10
TREASURE_CHEST_CHANCE = 0.015
TREASURE_CHEST_MIN_FISH_BETWEEN = 12
TREASURE_CHEST_STROKES = 2600
TREASURE_CHEST_MAX_REWARD = 5000
BLESSING_EVENT_CHANCE = 0.012
BLESSING_KEYSTROKE_USE_MULTIPLIER = 3.0
BLESSING_KEYSTROKE_USE_CAP = 2000
BLESSING_LUCK_CATCH_DIVISOR = 80
BLESSING_LUCK_CATCH_CAP = 12
RELIC_DROP_CHANCE = 0.07
POTION_DROP_CHANCE = 0.10
POTION_DURATION_SECONDS = 900
RELIC_INTERVAL_SECONDS = 300
OFFLINE_RELIC_PAYOUT_RATE = 0.25
TRANSPARENT_COLOR = "#ff00ff"
KEYBOARD_KEYS = [vk for vk in range(8, 256) if vk not in (16, 17, 18, 91, 92, 93)]
BASE_OVERLAY_WIDTH = 320
MINIMIZED_OVERLAY_HEIGHT = 80
MINIMIZED_VERTICAL_OVERLAY_WIDTH = 88
MINIMIZED_VERTICAL_OVERLAY_HEIGHT = 320
FULL_OVERLAY_HEIGHT = 236


class WindowsKeyPoller:
    def __init__(self):
        self.status_text = "Input capture: background capture enabled (Windows keyboard API)"
        self.user32 = getattr(ctypes, "windll").user32

    def current_keys(self):
        current = set()
        for vk in KEYBOARD_KEYS:
            if self.user32.GetAsyncKeyState(vk) & 0x8000:
                current.add(vk)
        return current

    def close(self):
        pass


class EmptyKeyPoller:
    def __init__(self, reason="global keyboard capture unavailable"):
        self.status_text = f"Input capture: focused window only ({reason})"

    def current_keys(self):
        return set()

    def close(self):
        pass


class LinuxEvdevKeyPoller:
    EVENT_TYPE_KEY = 1
    KEY_UP = 0
    KEY_DOWN = 1
    KEY_REPEAT = 2
    EVENT_FORMAT = "llHHI"
    EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

    def __init__(self, device_path):
        self.device_path = str(device_path)
        print(f"[TypeCast input] Trying Linux evdev keyboard device: {self.device_path}", flush=True)
        self.fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
        self.pressed = set()
        self.events_seen = 0
        self.last_error = ""
        self.status_text = f"Input capture: background capture enabled ({self.device_path})"
        print(f"[TypeCast input] Opened Linux evdev keyboard device: {self.device_path}", flush=True)

    def current_keys(self):
        while True:
            try:
                data = os.read(self.fd, self.EVENT_SIZE * 64)
            except BlockingIOError:
                break
            except OSError as exc:
                self.last_error = str(exc)
                print(f"[TypeCast input] Error reading {self.device_path}: {exc}", flush=True)
                break
            if not data:
                break
            event_count = len(data) // self.EVENT_SIZE
            for index in range(event_count):
                chunk = data[index * self.EVENT_SIZE:(index + 1) * self.EVENT_SIZE]
                _seconds, _microseconds, event_type, code, value = struct.unpack(self.EVENT_FORMAT, chunk)
                if event_type != self.EVENT_TYPE_KEY:
                    continue
                self.events_seen += 1
                if value in (self.KEY_DOWN, self.KEY_REPEAT):
                    self.pressed.add(code)
                elif value == self.KEY_UP:
                    self.pressed.discard(code)
        return set(self.pressed)

    def close(self):
        if self.fd is None:
            return
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None


def create_key_poller():
    if ACTIVE_DESKTOP_MODE:
        return EmptyKeyPoller("active desktop mode")
    return EmptyKeyPoller("background capture disabled")


def create_background_key_poller():
    if IS_WINDOWS:
        return WindowsKeyPoller()
    return EmptyKeyPoller(f"unsupported platform {sys.platform}")


BASE_FISH = [
    {"name": "Minnow", "strokes": 12, "value": 4, "weight": 35, "color": "#9bd3ff"},
    {"name": "Pond Smelt", "strokes": 14, "value": 5, "weight": 34, "color": "#b7dcff"},
    {"name": "Pebble Darter", "strokes": 16, "value": 6, "weight": 32, "color": "#b8e6d7"},
    {"name": "Creek Chub", "strokes": 18, "value": 7, "weight": 30, "color": "#a7c9d9"},
    {"name": "Bluegill", "strokes": 22, "value": 8, "weight": 26, "color": "#75b8ff"},
    {"name": "Mudskipper", "strokes": 26, "value": 10, "weight": 24, "color": "#b79269"},
    {"name": "Sunfish", "strokes": 30, "value": 12, "weight": 22, "color": "#ffd36f"},
    {"name": "Silver Shiner", "strokes": 34, "value": 14, "weight": 20, "color": "#d7eef5"},
    {"name": "Perch", "strokes": 42, "value": 18, "weight": 18, "color": "#f5c84c"},
    {"name": "Rock Bass", "strokes": 52, "value": 24, "weight": 16, "color": "#8bc184"},
    {"name": "Speckled Trout", "strokes": 62, "value": 30, "weight": 14, "color": "#d6bd8a"},
    {"name": "Koi", "strokes": 70, "value": 34, "weight": 10, "color": "#ff9b63"},
    {"name": "Lantern Guppy", "strokes": 82, "value": 42, "weight": 9, "color": "#ffce7d"},
    {"name": "Emerald Pike", "strokes": 94, "value": 52, "weight": 8, "color": "#59c48c"},
    {"name": "Moon Trout", "strokes": 120, "value": 72, "weight": 6, "color": "#c7b8ff"},
    {"name": "Crimson Snapper", "strokes": 145, "value": 92, "weight": 5, "color": "#ff6e75"},
    {"name": "Opal Carp", "strokes": 165, "value": 110, "weight": 4.5, "color": "#d9f4ff"},
    {"name": "Glass Eel", "strokes": 190, "value": 125, "weight": 3, "color": "#b8fff2"},
    {"name": "Ghost Mackerel", "strokes": 215, "value": 155, "weight": 2.6, "color": "#d6e8ff"},
    {"name": "Velvet Sturgeon", "strokes": 245, "value": 190, "weight": 2.2, "color": "#8b7aa8"},
    {"name": "Thunderfin Tuna", "strokes": 300, "value": 270, "weight": 1.4, "color": "#6cc8ff"},
    {"name": "Ruby Gar", "strokes": 360, "value": 350, "weight": 1.1, "color": "#e84964"},
    {"name": "Frostbite Cod", "strokes": 430, "value": 460, "weight": 0.9, "color": "#b9efff"},
    {"name": "Gilded Catfish", "strokes": 520, "value": 610, "weight": 0.7, "color": "#f6c85f"},
    {"name": "Crown Salmon", "strokes": 650, "value": 900, "weight": 0.38, "color": "#ffdf6e"},
    {"name": "Astral Marlin", "strokes": 820, "value": 1250, "weight": 0.28, "color": "#8da2ff"},
    {"name": "Sunken Kingfish", "strokes": 1050, "value": 1800, "weight": 0.2, "color": "#d6a54c"},
    {"name": "Dragonfin Koi", "strokes": 1350, "value": 2600, "weight": 0.14, "color": "#ff8f3d"},
]

SPOT_FISH_BY_SPOT = {
    "pond": [
        {"name": "Dock Minnow", "strokes": 12, "value": 4, "weight": 35, "color": "#9bd3ff"},
        {"name": "Pebble Darter", "strokes": 18, "value": 7, "weight": 26, "color": "#b8e6d7"},
        {"name": "Sunlit Bluegill", "strokes": 30, "value": 12, "weight": 18, "color": "#75b8ff"},
        {"name": "Old Pond Carp", "strokes": 52, "value": 24, "weight": 10, "color": "#d8b56d"},
        {"name": "Dragonfly Koi", "strokes": 82, "value": 42, "weight": 4, "color": "#ff9b63"},
    ],
    "creek": [
        {"name": "Mossfin Chub", "strokes": 32, "value": 18, "weight": 35, "color": "#7fcf91"},
        {"name": "Fernstripe Dace", "strokes": 44, "value": 26, "weight": 26, "color": "#9bd9a7"},
        {"name": "Riverstone Sculpin", "strokes": 62, "value": 38, "weight": 18, "color": "#8da487"},
        {"name": "Willow Trout", "strokes": 88, "value": 62, "weight": 10, "color": "#bdd98f"},
        {"name": "Emerald Creek Pike", "strokes": 130, "value": 110, "weight": 4, "color": "#44b877"},
    ],
    "pier": [
        {"name": "Lantern Anchovy", "strokes": 90, "value": 72, "weight": 35, "color": "#a9c8ff"},
        {"name": "Tideglass Smelt", "strokes": 120, "value": 105, "weight": 26, "color": "#bfe7ff"},
        {"name": "Moonwake Trout", "strokes": 170, "value": 165, "weight": 18, "color": "#c7b8ff"},
        {"name": "Starboard Mackerel", "strokes": 240, "value": 260, "weight": 10, "color": "#7aa2f7"},
        {"name": "Silver Pier Marlin", "strokes": 350, "value": 460, "weight": 4, "color": "#d7eef5"},
    ],
    "halloween": [
        {"name": "Candycorn Guppy", "strokes": 145, "value": 135, "weight": 35, "color": "#ffb347"},
        {"name": "Pumpkinseed Perch", "strokes": 195, "value": 210, "weight": 26, "color": "#f08332"},
        {"name": "Lantern Eel", "strokes": 280, "value": 340, "weight": 18, "color": "#ffce7d"},
        {"name": "Haunted Catfish", "strokes": 390, "value": 560, "weight": 10, "color": "#8b7aa8"},
        {"name": "Ghoulfin Gar", "strokes": 560, "value": 920, "weight": 4, "color": "#b36dff"},
    ],
    "cute": [
        {"name": "Sugarbubble Minnow", "strokes": 260, "value": 280, "weight": 35, "color": "#ffbde2"},
        {"name": "Macaron Molly", "strokes": 350, "value": 430, "weight": 26, "color": "#bde7ff"},
        {"name": "Cotton Candy Koi", "strokes": 500, "value": 700, "weight": 18, "color": "#f7a6d8"},
        {"name": "Sprinklefin Trout", "strokes": 700, "value": 1150, "weight": 10, "color": "#ffd6f1"},
        {"name": "Heartscale Sturgeon", "strokes": 980, "value": 1850, "weight": 4, "color": "#ff8fc7"},
    ],
    "garden": [
        {"name": "Lily Pad Loach", "strokes": 190, "value": 220, "weight": 35, "color": "#98d98e"},
        {"name": "Lotus Guppy", "strokes": 260, "value": 340, "weight": 26, "color": "#f7a6c8"},
        {"name": "Bamboo Koi", "strokes": 370, "value": 560, "weight": 18, "color": "#d8c27a"},
        {"name": "Pearlblossom Carp", "strokes": 520, "value": 920, "weight": 10, "color": "#ffe1f0"},
        {"name": "Imperial Garden Koi", "strokes": 760, "value": 1500, "weight": 4, "color": "#ff7f5a"},
    ],
    "abyss": [
        {"name": "Gloomfin Tetra", "strokes": 520, "value": 760, "weight": 35, "color": "#3b5a71"},
        {"name": "Abyss Lanternfish", "strokes": 720, "value": 1200, "weight": 26, "color": "#8fffea"},
        {"name": "Voidscale Eel", "strokes": 1020, "value": 1950, "weight": 18, "color": "#536070"},
        {"name": "Deepcurrent Sturgeon", "strokes": 1450, "value": 3200, "weight": 10, "color": "#6c88ff"},
        {"name": "Crown of the Abyss", "strokes": 2100, "value": 5400, "weight": 4, "color": "#d8f6ff"},
    ],
    "lava": [
        {"name": "Cinder Guppy", "strokes": 850, "value": 1400, "weight": 35, "color": "#ff8f2f"},
        {"name": "Emberfin Snapper", "strokes": 1200, "value": 2200, "weight": 26, "color": "#e84964"},
        {"name": "Basalt Catfish", "strokes": 1700, "value": 3600, "weight": 18, "color": "#6a4b3a"},
        {"name": "Magma Sturgeon", "strokes": 2400, "value": 6000, "weight": 10, "color": "#ff5a2f"},
        {"name": "Volcanic Dragonfish", "strokes": 3500, "value": 10000, "weight": 4, "color": "#ffd166"},
    ],
}

FISH_VARIANTS = [
    {"rarity": "Common", "stroke_mult": 0.75, "value_mult": 0.55, "weight_mult": 1.0},
    {"rarity": "Uncommon", "stroke_mult": 1.0, "value_mult": 1.0, "weight_mult": 0.42},
    {"rarity": "Rare", "stroke_mult": 1.45, "value_mult": 2.2, "weight_mult": 0.16},
    {"rarity": "Epic", "stroke_mult": 2.1, "value_mult": 5.0, "weight_mult": 0.055},
]
SPARKLE_FISH_RARITIES = {"Epic", "Secret", "Ultra Rare"}
SPARKLE_RARITY_COLORS = {
    "Epic": "#e7b8ff",
    "Secret": "#d8f6ff",
    "Ultra Rare": "#fff0a6",
}
PRIDE_SKIN_CHANCE = 0.08
HAPPY_FISH_COLLECTION = "Happy Fish"

PRIDE_FISH_SKINS = [
    {"id": "queer", "name": "Queer Fish", "colors": ["#e40303", "#ff8c00", "#ffed00", "#008026", "#24408e", "#732982"], "body_colors": ["#e40303", "#ff8c00", "#ffed00", "#008026", "#24408e", "#732982"], "tail_colors": ["#732982", "#24408e", "#008026"], "top_fin": "#ff8c00", "bottom_fin": "#24408e"},
    {"id": "progress_pride", "name": "Progress Pride Fish", "colors": ["#e40303", "#ff8c00", "#ffed00", "#008026", "#24408e", "#732982", "#ffffff", "#f5a9b8", "#5bcefa", "#784f17", "#000000"], "body_colors": ["#e40303", "#ff8c00", "#ffed00", "#008026", "#24408e", "#732982"], "tail_colors": ["#5bcefa", "#f5a9b8", "#ffffff", "#784f17"], "top_fin": "#f5a9b8", "bottom_fin": "#5bcefa"},
    {"id": "trans", "name": "Trans Fish", "colors": ["#5bcefa", "#f5a9b8", "#ffffff", "#f5a9b8", "#5bcefa"], "body_colors": ["#5bcefa", "#f5a9b8", "#ffffff", "#f5a9b8", "#5bcefa"], "tail_colors": ["#5bcefa", "#ffffff", "#f5a9b8"], "top_fin": "#f5a9b8", "bottom_fin": "#5bcefa"},
    {"id": "nonbinary", "name": "Nonbinary Fish", "colors": ["#fff430", "#ffffff", "#9c59d1", "#000000"], "body_colors": ["#fff430", "#ffffff", "#9c59d1", "#000000"], "tail_colors": ["#000000", "#9c59d1", "#fff430"], "top_fin": "#fff430", "bottom_fin": "#9c59d1"},
    {"id": "lesbian", "name": "Lesbian Fish", "colors": ["#d52d00", "#ef7627", "#ff9a56", "#ffffff", "#d162a4", "#b55690", "#a30262"], "body_colors": ["#ef7627", "#ff9a56", "#ffffff", "#d162a4", "#a30262"], "tail_colors": ["#d52d00", "#ef7627", "#a30262"], "top_fin": "#ff9a56", "bottom_fin": "#b55690"},
    {"id": "gay", "name": "Gay Fish", "colors": ["#078d70", "#26ceaa", "#98e8c1", "#ffffff", "#7bade2", "#5049cc", "#3d1a78"], "body_colors": ["#078d70", "#26ceaa", "#98e8c1", "#ffffff", "#7bade2", "#5049cc"], "tail_colors": ["#078d70", "#3d1a78", "#5049cc"], "top_fin": "#26ceaa", "bottom_fin": "#7bade2"},
    {"id": "bisexual", "name": "Bisexual Fish", "colors": ["#d60270", "#d60270", "#9b4f96", "#0038a8", "#0038a8"], "body_colors": ["#d60270", "#9b4f96", "#0038a8"], "tail_colors": ["#0038a8", "#9b4f96", "#d60270"], "top_fin": "#d60270", "bottom_fin": "#0038a8"},
    {"id": "pansexual", "name": "Pansexual Fish", "colors": ["#ff1b8d", "#ffd900", "#1bb3ff"], "body_colors": ["#ff1b8d", "#ffd900", "#1bb3ff"], "tail_colors": ["#ff1b8d", "#ffd900"], "top_fin": "#ffd900", "bottom_fin": "#1bb3ff"},
    {"id": "asexual", "name": "Asexual Fish", "colors": ["#000000", "#a3a3a3", "#ffffff", "#800080"], "body_colors": ["#2b2b2b", "#a3a3a3", "#ffffff", "#800080"], "tail_colors": ["#000000", "#800080"], "top_fin": "#a3a3a3", "bottom_fin": "#800080"},
]
PRIDE_FISH_BY_ID = {skin["id"]: skin for skin in PRIDE_FISH_SKINS}

HIGH_LUCK_FISH = [
    {"name": "Nullfin", "rarity": "Secret", "strokes": 1800, "value": 4200, "weight": 0.07, "color": "#536070", "min_luck": 7},
    {"name": "Clockwork Coelacanth", "rarity": "Secret", "strokes": 2400, "value": 6800, "weight": 0.045, "color": "#b58b55", "min_luck": 8},
    {"name": "The One That Got Away", "rarity": "Secret", "strokes": 3200, "value": 10500, "weight": 0.025, "color": "#aee7ff", "min_luck": 9},
    {"name": "Nebula Leviathan", "rarity": "Ultra Rare", "strokes": 5000, "value": 22000, "weight": 0.012, "color": "#b36dff", "min_luck": 10},
    {"name": "Keyboard Kraken", "rarity": "Ultra Rare", "strokes": 7500, "value": 42000, "weight": 0.006, "color": "#7df6d4", "min_luck": 11},
    {"name": "Eternal Wishfish", "rarity": "Ultra Rare", "strokes": 10000, "value": 80000, "weight": 0.003, "color": "#fff2a6", "min_luck": 12},
]


def build_fish_table():
    fish_table = []
    for spot_id, spot_fish in SPOT_FISH_BY_SPOT.items():
        for fish in spot_fish:
            for variant in FISH_VARIANTS:
                fish_table.append(
                    {
                        "name": fish["name"],
                        "rarity": variant["rarity"],
                        "strokes": max(1, round(fish["strokes"] * variant["stroke_mult"])),
                        "value": max(1, round(fish["value"] * variant["value_mult"])),
                        "weight": fish["weight"] * variant["weight_mult"],
                        "color": fish["color"],
                        "spot_id": spot_id,
                    }
                )
    fish_table.extend({**fish, "spot_id": "global"} for fish in HIGH_LUCK_FISH)
    return fish_table


FISH_TABLE = build_fish_table()


def fish_display_name(fish):
    return f"{fish['rarity']} {fish['name']}"


def hooked_fish_display_name(fish):
    if getattr(fish, "kind", "fish") == "chest":
        return fish.name
    if getattr(fish, "kind", "fish") == "blessing":
        return fish.name
    return f"{fish.rarity} {fish.name}"


def fish_inventory_display_name(fish):
    rarity = fish.get("rarity", "") if isinstance(fish, dict) else ""
    name = fish.get("name", "") if isinstance(fish, dict) else ""
    if fish_is_blessing(fish):
        slot = fish.get("blessing_slot", "") if isinstance(fish, dict) else ""
        bonus = fish.get("blessing_bonus", 0) if isinstance(fish, dict) else 0
        return f"Stored Blessing: {name} ({blessing_effect_label(slot, bonus)})"
    return f"{rarity} {name}"


def asset_slug(value):
    value = str(value).strip().lower()
    slug = []
    previous_dash = False
    for character in value:
        if character.isalnum():
            slug.append(character)
            previous_dash = False
        elif not previous_dash:
            slug.append("_")
            previous_dash = True
    return "".join(slug).strip("_") or "asset"


def fish_is_blessing(fish):
    if isinstance(fish, dict):
        return fish.get("kind", "fish") == "blessing"
    return getattr(fish, "kind", "fish") == "blessing"


def blessing_effect_label(slot, bonus):
    try:
        bonus = float(bonus)
    except (TypeError, ValueError):
        bonus = 0.0
    if slot == "rod":
        return f"{int(round(bonus * 100))}% fewer keys"
    if slot == "head":
        return f"+{int(round(bonus * 100))}% accuracy"
    if slot == "body":
        return f"+{int(round(bonus))} luck"
    if slot == "legs":
        return f"+{int(round(bonus * 100))}% Cast Token chance"
    return "blessing"


def fish_collection_key(rarity, name):
    return f"{rarity}|{name}"


def happy_fish_collection_key(skin_id):
    return f"{HAPPY_FISH_COLLECTION}|{skin_id}"


def apply_pride_skin(fish, skin):
    if not skin:
        return fish
    colors = [color for color in skin.get("colors", []) if isinstance(color, str)]
    if not colors:
        return fish
    fish.skin_id = skin["id"]
    fish.skin_name = skin["name"]
    fish.skin_colors = colors
    body_colors = [color for color in skin.get("body_colors", colors) if isinstance(color, str)]
    fish.color = body_colors[len(body_colors) // 2] if body_colors else colors[len(colors) // 2]
    return fish


def apply_random_pride_skin(fish):
    if random.random() < PRIDE_SKIN_CHANCE:
        apply_pride_skin(fish, random.choice(PRIDE_FISH_SKINS))
    return fish


EQUIPMENT_SLOTS = ("rod", "head", "body", "legs")

EQUIPMENT_TRACKS = {
    "rod": [
        {"name": "Bamboo Rod", "price": 0, "stroke_mult": 1.0},
        {"name": "Pine Rod", "price": 90, "stroke_mult": 0.98},
        {"name": "Oak Rod", "price": 240, "stroke_mult": 0.96},
        {"name": "Braided Rod", "price": 650, "stroke_mult": 0.94},
        {"name": "Copper Reel Rod", "price": 1500, "stroke_mult": 0.92},
        {"name": "Tideglass Rod", "price": 3600, "stroke_mult": 0.90},
        {"name": "Silverline Rod", "price": 8500, "stroke_mult": 0.87},
        {"name": "Moonlit Rod", "price": 19000, "stroke_mult": 0.84},
        {"name": "Deepcurrent Rod", "price": 42000, "stroke_mult": 0.81},
        {"name": "Starforged Rod", "price": 90000, "stroke_mult": 0.77},
        {"name": "Abyssal Rod", "price": 190000, "stroke_mult": 0.73},
        {"name": "Aurora Rod", "price": 390000, "stroke_mult": 0.68},
        {"name": "Mythwater Rod", "price": 780000, "stroke_mult": 0.60},
        {"name": "Eternal Cast Rod", "price": 1500000, "stroke_mult": 0.50},
    ],
    "head": [
        {"name": "Bare Head", "price": 0, "accuracy": 0.0},
        {"name": "Canvas Cap", "price": 120, "accuracy": 0.002},
        {"name": "Bucket Hat", "price": 320, "accuracy": 0.004},
        {"name": "Captain Cap", "price": 900, "accuracy": 0.006},
        {"name": "Rain Brim", "price": 2200, "accuracy": 0.009},
        {"name": "Pearl Pin Hat", "price": 5200, "accuracy": 0.012},
        {"name": "Moonhook Hood", "price": 12500, "accuracy": 0.016},
        {"name": "Star Sailor Hat", "price": 30000, "accuracy": 0.02},
        {"name": "Crown of Tides", "price": 72000, "accuracy": 0.026},
        {"name": "Deepsea Halo", "price": 170000, "accuracy": 0.032},
        {"name": "Legend's Tricorn", "price": 400000, "accuracy": 0.04},
        {"name": "Eternal Angler Crown", "price": 950000, "accuracy": 0.05},
    ],
    "body": [
        {"name": "Plain Tee", "price": 0, "luck": 0},
        {"name": "Dock Vest", "price": 140, "luck": 1},
        {"name": "Rain Slicker", "price": 380, "luck": 2},
        {"name": "River Jacket", "price": 1050, "luck": 3},
        {"name": "Stormcoat", "price": 2600, "luck": 4},
        {"name": "Pearlscale Coat", "price": 6200, "luck": 5},
        {"name": "Moonwake Parka", "price": 15000, "luck": 6},
        {"name": "Starwoven Jacket", "price": 36000, "luck": 7},
        {"name": "Abyssal Coat", "price": 86000, "luck": 8},
        {"name": "Aurora Slicker", "price": 205000, "luck": 9},
        {"name": "Legend's Greatcoat", "price": 480000, "luck": 10},
        {"name": "Eternal Tide Robe", "price": 1150000, "luck": 12},
    ],
    "legs": [
        {"name": "Denim Pants", "price": 0, "banked_bonus": 0.0},
        {"name": "Dock Shorts", "price": 130, "banked_bonus": 0.02},
        {"name": "River Waders", "price": 350, "banked_bonus": 0.03},
        {"name": "Reinforced Waders", "price": 980, "banked_bonus": 0.04},
        {"name": "Storm Boots", "price": 2400, "banked_bonus": 0.05},
        {"name": "Pearlscale Waders", "price": 5800, "banked_bonus": 0.06},
        {"name": "Moonwake Boots", "price": 14000, "banked_bonus": 0.07},
        {"name": "Starstep Waders", "price": 34000, "banked_bonus": 0.08},
        {"name": "Abyssal Greaves", "price": 82000, "banked_bonus": 0.09},
        {"name": "Aurora Waders", "price": 195000, "banked_bonus": 0.10},
        {"name": "Legend's Sea Boots", "price": 460000, "banked_bonus": 0.11},
        {"name": "Eternal Current Greaves", "price": 1100000, "banked_bonus": 0.12},
    ],
}

DEFAULT_EQUIPMENT_LEVELS = {slot: 0 for slot in EQUIPMENT_SLOTS}

ROD_VISUALS = [
    {"body": "#8b5f36", "highlight": "#c48a4f", "shadow": "#4f3520", "handle": "#3b2b21", "wrap": "#6f4d2f", "metal": "#7b8b92", "reel": "#dfe8e6", "line": "#435b64", "bands": (), "gem": None, "glow": None, "width": 7},
    {"body": "#9b6b3b", "highlight": "#d29a5d", "shadow": "#56391f", "handle": "#3e2c1f", "wrap": "#7a5735", "metal": "#7f9098", "reel": "#e2ebe8", "line": "#435b64", "bands": ("#416f4f",), "gem": None, "glow": None, "width": 7},
    {"body": "#7c5634", "highlight": "#bd8249", "shadow": "#48311f", "handle": "#34251d", "wrap": "#8a6040", "metal": "#84949c", "reel": "#dde6e4", "line": "#405761", "bands": ("#9b6d3f", "#6b4428"), "gem": None, "glow": None, "width": 8},
    {"body": "#76513c", "highlight": "#c29165", "shadow": "#3e2b22", "handle": "#30231d", "wrap": "#c9a46b", "metal": "#8797a0", "reel": "#e3ebe9", "line": "#3e5660", "bands": ("#c9a46b", "#80543e"), "gem": None, "glow": None, "width": 8},
    {"body": "#8f5330", "highlight": "#d4864f", "shadow": "#4a2c1d", "handle": "#33231c", "wrap": "#c66a3d", "metal": "#bd7a43", "reel": "#2b3138", "line": "#4b5e66", "bands": ("#bd7a43", "#e0a05d"), "gem": None, "glow": None, "width": 8},
    {"body": "#3a7e8f", "highlight": "#8ed8e4", "shadow": "#214750", "handle": "#25333a", "wrap": "#b9f0ef", "metal": "#86aeba", "reel": "#e5fbff", "line": "#77b8c5", "bands": ("#d4fbff", "#5aaebe"), "gem": "#9df5ff", "glow": "#6ee7f3", "width": 8},
    {"body": "#5f7285", "highlight": "#d9edf7", "shadow": "#344252", "handle": "#2d3035", "wrap": "#b8cbd6", "metal": "#c6d5dd", "reel": "#eff8fb", "line": "#9fb7c4", "bands": ("#e6f5fb", "#91a7b6"), "gem": None, "glow": None, "width": 8},
    {"body": "#334a78", "highlight": "#a9c9ff", "shadow": "#1d2a46", "handle": "#242635", "wrap": "#d7e5ff", "metal": "#9eb2d2", "reel": "#172235", "line": "#b4cfff", "bands": ("#e6edff", "#6f91c7"), "gem": "#dce8ff", "glow": "#8db5ff", "width": 8},
    {"body": "#234d63", "highlight": "#79d7e7", "shadow": "#132d3c", "handle": "#1d2b33", "wrap": "#4ee0d5", "metal": "#6aa3b1", "reel": "#0f2530", "line": "#6ad6df", "bands": ("#4ee0d5", "#2d7890"), "gem": "#5ff0df", "glow": "#2fd0c5", "width": 9},
    {"body": "#4c3677", "highlight": "#e8c3ff", "shadow": "#271d3f", "handle": "#2b2435", "wrap": "#ffd166", "metal": "#bba0dc", "reel": "#201830", "line": "#d8b5ff", "bands": ("#ffd166", "#b36dff"), "gem": "#fff2a6", "glow": "#d280ff", "width": 9},
    {"body": "#232b3d", "highlight": "#7d8ca3", "shadow": "#10141f", "handle": "#181922", "wrap": "#4a536a", "metal": "#5b6678", "reel": "#0e1018", "line": "#697790", "bands": ("#7d8ca3", "#30394d"), "gem": "#536070", "glow": "#65738c", "width": 9},
    {"body": "#437a83", "highlight": "#d7fff4", "shadow": "#223f48", "handle": "#253238", "wrap": "#a7ffe6", "metal": "#8ec9ce", "reel": "#17343a", "line": "#b8fff0", "bands": ("#a7ffe6", "#f7a6d8"), "gem": "#f7a6d8", "glow": "#7df6d4", "width": 9},
    {"body": "#356ca4", "highlight": "#f5ffdb", "shadow": "#1c3654", "handle": "#233040", "wrap": "#fff2a6", "metal": "#9dcbe8", "reel": "#112b45", "line": "#d8f6ff", "bands": ("#fff2a6", "#7df6d4", "#b36dff"), "gem": "#aee7ff", "glow": "#aee7ff", "width": 10},
    {"body": "#f0d785", "highlight": "#fff8cf", "shadow": "#7b5b2a", "handle": "#2b251a", "wrap": "#ffffff", "metal": "#e7eef4", "reel": "#293044", "line": "#fff2a6", "bands": ("#fff8cf", "#aee7ff", "#f7a6d8"), "gem": "#ffffff", "glow": "#fff2a6", "width": 10},
]

BACKPACK_UPGRADES = [
    {"level": 1, "slots": 10, "price": 60},
    {"level": 2, "slots": 12, "price": 180},
    {"level": 3, "slots": 14, "price": 520},
    {"level": 4, "slots": 16, "price": 1400},
    {"level": 5, "slots": 18, "price": 3600},
    {"level": 6, "slots": 20, "price": 9200},
    {"level": 7, "slots": 22, "price": 24000},
    {"level": 8, "slots": 24, "price": 62000},
    {"level": 9, "slots": 28, "price": 160000},
    {"level": 10, "slots": 32, "price": 420000},
    {"level": 11, "slots": 36, "price": 900000},
    {"level": 12, "slots": 40, "price": 2000000},
    {"level": 13, "slots": 44, "price": 4500000},
    {"level": 14, "slots": 48, "price": 10000000},
    {"level": 15, "slots": 54, "price": 22000000},
    {"level": 16, "slots": 60, "price": 48000000},
    {"level": 17, "slots": 66, "price": 100000000},
    {"level": 18, "slots": 72, "price": 220000000},
    {"level": 19, "slots": 80, "price": 480000000},
    {"level": 20, "slots": 88, "price": 1050000000},
    {"level": 21, "slots": 96, "price": 2300000000},
]

BANKED_KEY_UPGRADES = [
    {"name": "Focus Matrix", "cost": 10000, "mult": 1.15, "discount": 0.04},
    {"name": "Surge Cache", "cost": 30000, "mult": 1.35, "discount": 0.09},
    {"name": "Flow Accelerator", "cost": 90000, "mult": 1.5, "discount": 0.16},
    {"name": "Hypercharge", "cost": 270000, "mult": 1.85, "discount": 0.25},
    {"name": "Quantum Shift", "cost": 800000, "mult": 2.25, "discount": 0.35},
    {"name": "Temporal Cascade", "cost": 2400000, "mult": 3.75, "discount": 0.44},
    {"name": "Eternal Velocity", "cost": 9000000, "mult": 6.00, "discount": 0.50},
]

AUTOSALE_UPGRADES = [
    {"name": "Auto Sell Module I", "price": 1200, "percent": 25},
    {"name": "Auto Sell Module II", "price": 10000, "percent": 50},
    {"name": "Auto Sell Module III", "price": 50888, "percent": 75},
    {"name": "Auto Sell Module IV", "price": 100000, "percent": 100},
]

FISHING_SPOTS = [
    {"id": "pond", "name": "Starter Pond", "description": "The classic quiet pond.", "cost_type": "free", "cost": 0},
    {"id": "creek", "name": "Mossy Creek", "description": "Soft reeds and moving green water.", "cost_type": "coins", "cost": 2500},
    {"id": "pier", "name": "Moonlit Pier", "description": "A calm night scene with cool blue water.", "cost_type": "banked_keys", "cost": 25000},
    {"id": "halloween", "name": "Pumpkin Marsh", "description": "A spooky little pond with autumn colors.", "cost_type": "collection", "cost": 35},
    {"id": "cute", "name": "Candy Cove", "description": "A soft pastel pond with a cheerful feel.", "cost_type": "coins", "cost": 75000},
    {"id": "garden", "name": "Koi Garden", "description": "A cozy garden pond for dedicated collectors.", "cost_type": "collection", "cost": 25},
    {"id": "abyss", "name": "Abyssal Pool", "description": "A deep glowing pool for master anglers.", "cost_type": "collection", "cost": 80},
    {"id": "lava", "name": "Lava Springs", "description": "A molten endgame fishing spot.", "cost_type": "achievements", "cost": "all"},
]

RELICS = [
    {"id": "driftwood_charm", "name": "Driftwood Charm", "rarity": "Common", "keys": 15, "weight": 84},
    {"id": "copper_shell", "name": "Copper Shell", "rarity": "Common", "coins": 15, "weight": 84},
    {"id": "tideglass_icon", "name": "Tideglass Icon", "rarity": "Rare", "keys": 55, "weight": 15},
    {"id": "gilded_scale", "name": "Gilded Scale", "rarity": "Rare", "coins": 55, "weight": 15},
    {"id": "sunken_star", "name": "Sunken Star", "rarity": "Secret", "keys": 150, "weight": 1},
    {"id": "crown_of_the_deep", "name": "Crown of the Deep", "rarity": "Secret", "coins": 150, "weight": 1},
]

POTIONS = [
    {"id": "typing_tonic", "name": "Typing Tonic", "rarity": "Common", "keys": 25, "weight": 70},
    {"id": "coin_draught", "name": "Coin Draught", "rarity": "Common", "coins": 25, "weight": 70},
    {"id": "storm_phial", "name": "Storm Phial", "rarity": "Rare", "keys": 90, "weight": 24},
    {"id": "gilded_vial", "name": "Gilded Vial", "rarity": "Rare", "coins": 90, "weight": 24},
    {"id": "deep_current_elixir", "name": "Deep Current Elixir", "rarity": "Secret", "keys": 220, "weight": 3},
    {"id": "sunken_gold_elixir", "name": "Sunken Gold Elixir", "rarity": "Secret", "coins": 220, "weight": 3},
]

BLESSING_VISITORS = [
    {
        "id": "turtle",
        "name": "Ancient Turtle",
        "slot": "rod",
        "description": "Rod blessing",
        "color": "#7fb383",
        "min_strokes": 220,
        "max_strokes": 620,
        "min_bonus": 0.06,
        "max_bonus": 0.12,
    },
    {
        "id": "squid",
        "name": "Inkveil Squid",
        "slot": "head",
        "description": "Accuracy blessing",
        "color": "#9b7cff",
        "min_strokes": 260,
        "max_strokes": 700,
        "min_bonus": 0.015,
        "max_bonus": 0.03,
    },
    {
        "id": "manatee",
        "name": "Gentle Manatee",
        "slot": "body",
        "description": "Luck blessing",
        "color": "#9eb7ad",
        "min_strokes": 300,
        "max_strokes": 820,
        "min_bonus": 3,
        "max_bonus": 5,
    },
    {
        "id": "eel",
        "name": "Stormglass Eel",
        "slot": "legs",
        "description": "Cast Token blessing",
        "color": "#6ee7f3",
        "min_strokes": 240,
        "max_strokes": 680,
        "min_bonus": 0.06,
        "max_bonus": 0.12,
    },
]
BLESSING_VISITOR_BY_ID = {visitor["id"]: visitor for visitor in BLESSING_VISITORS}

ACHIEVEMENTS = [
    {"id": "first_catch", "name": "First Bite", "description": "Catch your first fish."},
    {"id": "collection_common", "name": "Common Catalog", "description": "Complete the Common collection log section."},
    {"id": "collection_uncommon", "name": "Uncommon Archive", "description": "Complete the Uncommon collection log section."},
    {"id": "collection_rare", "name": "Rare Records", "description": "Complete the Rare collection log section."},
    {"id": "collection_epic", "name": "Epic Ledger", "description": "Complete the Epic collection log section."},
    {"id": "collection_secret", "name": "Secret Files", "description": "Complete the Secret collection log section."},
    {"id": "collection_ultra_rare", "name": "Ultra Rare Vault", "description": "Complete the Ultra Rare collection log section."},
    {"id": "collection_all", "name": "Master Angler", "description": "Complete the whole collection log."},
    {"id": "play_15m", "name": "Settling In", "description": "Play for 15 minutes."},
    {"id": "play_1h", "name": "Gone Fishing", "description": "Play for 1 hour."},
    {"id": "play_8h", "name": "Full Shift", "description": "Play for 8 hours."},
    {"id": "play_24h", "name": "No Sleep, Just Reels", "description": "Play for 24 hours."},
    {"id": "play_69h", "name": "Nice Cast", "description": "Play for 69 hours.", "secret": True},
    {"id": "play_100h", "name": "Centennial Angler", "description": "Play for 100 hours."},
    {"id": "play_250h", "name": "Permanent Dock Lease", "description": "Play for 250 hours."},
    {"id": "keys_10000", "name": "Keyboard Current", "description": "Reach 10,000 total keys."},
    {"id": "keys_100000", "name": "Key Tide", "description": "Reach 100,000 total keys."},
    {"id": "keys_1000000", "name": "Million-Key Migration", "description": "Reach 1,000,000 total keys."},
    {"id": "keys_10000000", "name": "Ten Million Tides", "description": "Reach 10,000,000 total keys."},
    {"id": "banked_50000", "name": "Rainy Day Fund", "description": "Earn 50,000 Cast Tokens."},
    {"id": "banked_100000", "name": "Token Reservoir", "description": "Hold 100,000 Cast Tokens."},
    {"id": "banked_1000000", "name": "Cast Token Treasury", "description": "Hold 1,000,000 Cast Tokens."},
    {"id": "coins_10000", "name": "Coin Purse", "description": "Hold 10,000 coins."},
    {"id": "coins_1000000", "name": "Treasure Chest", "description": "Hold 1,000,000 coins."},
    {"id": "coins_10000000", "name": "Gilded Harbor", "description": "Hold 10,000,000 coins."},
    {"id": "backpack_10", "name": "Room for More", "description": "Reach backpack level 10."},
    {"id": "backpack_15", "name": "Portable Pier", "description": "Reach backpack level 15."},
    {"id": "backpack_max", "name": "Pocket Ocean", "description": "Max out the backpack."},
    {"id": "autosell", "name": "Hands-Free Market", "description": "Install an Auto Sell Module."},
    {"id": "first_relic", "name": "Strange Keepsake", "description": "Find your first relic."},
    {"id": "all_relic_types", "name": "Curator of the Deep", "description": "Own every relic type."},
    {"id": "fish_clicks_10", "name": "Poke the Pond", "description": "Click Catches 10 times.", "secret": True},
    {"id": "fish_clicks_100", "name": "Certified Splash Inspector", "description": "Click Catches 100 times.", "secret": True},
    {"id": "cat_pets_1", "name": "Aphrodite Approves", "description": "Pet Aphrodite, The TypeCat.", "secret": True},
    {"id": "cat_pets_100", "name": "TypeCat's Chosen", "description": "Pet Aphrodite, The TypeCat, 100 times.", "secret": True},
    {"id": "banked_upgrade_max", "name": "Stored Storm", "description": "Max out Cast Token upgrades."},
    {"id": "equipment_all_5", "name": "Proper Kit", "description": "Upgrade all equipment slots to level 5."},
    {"id": "equipment_all_10", "name": "Masterwork Kit", "description": "Upgrade all equipment slots to level 10."},
    {"id": "equipment_all_max", "name": "Best in Slot", "description": "Max out every equipment slot."},
    {"id": "spots_all", "name": "World Tour", "description": "Unlock every fishing spot."},
]


@dataclass
class HookedFish:
    name: str
    rarity: str
    strokes: int
    value: int
    color: str
    kind: str = "fish"
    progress: float = 0.0
    spot_id: str = ""
    blessing_id: str = ""
    blessing_slot: str = ""
    blessing_bonus: float = 0.0
    skin_id: str = ""
    skin_name: str = ""
    skin_colors: list = field(default_factory=list)

    @classmethod
    def from_roll(cls, stroke_multiplier, luck_bonus, spot_id="pond"):
        fish_pool = [fish for fish in FISH_TABLE if fish.get("spot_id") in (spot_id, "global")]
        if not fish_pool:
            fish_pool = [fish for fish in FISH_TABLE if fish.get("spot_id") in ("pond", "global")]
        weights = [adjusted_fish_weight(fish, luck_bonus) for fish in fish_pool]
        if not any(weight > 0 for weight in weights):
            fish_pool = [fish for fish in fish_pool if not fish.get("min_luck")]
            weights = [adjusted_fish_weight(fish, luck_bonus) for fish in fish_pool]
        fish = random.choices(fish_pool, weights=weights, k=1)[0]
        hooked = cls(
            fish["name"],
            fish["rarity"],
            max(1, round(fish["strokes"] * stroke_multiplier)),
            fish["value"],
            fish["color"],
            spot_id=fish.get("spot_id", spot_id),
        )
        apply_random_pride_skin(hooked)
        return hooked


@dataclass
class FishBubble:
    x: float
    y: float
    size: float
    rise: float
    drift: float
    delay: float
    born: float
    life: float


@dataclass
class ResourceDelta:
    resource: str
    amount: int
    born: float
    life: float = 1.25


def adjusted_fish_weight(fish, luck_bonus):
    if luck_bonus < fish.get("min_luck", 0):
        return 0
    rarity = fish["rarity"]
    if rarity == "Common":
        modifier = max(0.25, 1 - luck_bonus * 0.11)
    elif rarity == "Uncommon":
        modifier = 1 + luck_bonus * 0.08
    elif rarity == "Rare":
        modifier = 1 + luck_bonus * 0.18
    elif rarity == "Epic":
        modifier = 1 + luck_bonus * 0.28
    elif rarity == "Legendary":
        modifier = 1 + luck_bonus * 0.42
    elif rarity == "Secret":
        modifier = 1 + luck_bonus * 0.62
    else:
        modifier = 1 + luck_bonus * 0.85
    return fish["weight"] * modifier


class TypeCast(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TypeCast")
        self.app_icon = self.load_app_icon()
        if self.app_icon:
            self.iconphoto(True, self.app_icon)
        self.geometry(f"{BASE_OVERLAY_WIDTH}x{FULL_OVERLAY_HEIGHT}+80+80")
        self.resizable(False, False)
        self.apply_linux_window_hints(self)
        if ACTIVE_DESKTOP_MODE:
            self.configure(bg="#eaf8ff")
        else:
            self.overrideredirect(True)
            self.configure(bg=TRANSPARENT_COLOR)
            self.attributes("-topmost", True)
            self.attributes("-transparentcolor", TRANSPARENT_COLOR)

        self.coins = 0
        self.total_keystrokes = 0
        self.backpack_level = 0
        self.inventory_limit = 8
        self.inventory = []
        self.collection_log = {}
        self.achievements_unlocked = set()
        self.unlocked_fishing_spots = {"pond"}
        self.selected_fishing_spot = "pond"
        self.equipment_levels = DEFAULT_EQUIPMENT_LEVELS.copy()
        self.hooked_fish = None
        self.cast_started_at = time.time()
        self.last_message = "Casting..."
        self.fish_clicks = 0
        self.cat_pets = 0
        self.fish_since_last_treasure_chest = TREASURE_CHEST_MIN_FISH_BETWEEN
        self.pressed_keys = set()
        self.last_input_debug_at = 0.0
        self.last_input_debug_events_seen = 0
        self.key_poller = create_key_poller()
        self.input_status_text = tk.StringVar(value=self.key_poller.status_text)
        self.focus_key_fallback_enabled = isinstance(self.key_poller, EmptyKeyPoller)
        self.focus_key_capture_bound = False
        self.background_key_capture_enabled = tk.BooleanVar(value=False)
        self.background_key_capture_consent_granted = False
        self.drag_start = None
        self.menu = None
        self.menu_drag_start = None
        self.resource_deltas: List[ResourceDelta] = []
        self.refresh_scheduled = False
        self.menu_offset_x = 0
        self.menu_offset_y = 0
        self.window_x = 80
        self.window_y = 80
        self.selected_monitor_index = 0
        self.monitor_options = self.available_monitors()
        self.monitor_var = tk.StringVar(value=self.monitor_label_for_index(self.selected_monitor_index))
        self.menu_docked = True
        self.menu_docked_var = tk.BooleanVar(value=True)
        self.minimized = False
        self.compact_vertical_var = tk.BooleanVar(value=False)
        self.rod_pull = 0.0
        self.fish_bubbles: List[FishBubble] = []
        self.last_player_activity_at = time.time()
        self.autosell_level = 0
        self.last_autosell_at = time.time()
        self.relics = {}
        self.stored_potions = {}
        self.potions = []
        self.active_blessings = {}
        self.last_relic_payout_at = time.time()
        self.event_log = []
        self.started_at = int(time.time())
        self.total_played_seconds = 0.0
        self.play_timer_started_at = time.time()
        self.last_save_at = time.time()
        self.transparency = 1.0
        self.transparency_percent = tk.DoubleVar(value=100)
        self.transparency_text = tk.StringVar(value="100%")
        self.dark_theme = False
        self.theme_name = "Light"
        self.theme_var = tk.StringVar(value=THEME_NAME_TO_LABEL[self.theme_name])
        self.custom_primary_color = "#5d91c8"
        self.custom_secondary_color = "#cbe3ff"
        custom_theme_defaults = self.load_config().get("custom_theme", {})
        if isinstance(custom_theme_defaults, dict):
            primary_default = str(custom_theme_defaults.get("content_accent", self.custom_primary_color)).strip()
            secondary_default = str(custom_theme_defaults.get("content_select_bg", self.custom_secondary_color)).strip()
            if self.valid_hex_color(primary_default):
                self.custom_primary_color = primary_default
            if self.valid_hex_color(secondary_default):
                self.custom_secondary_color = secondary_default
        self.custom_theme_frame = None
        self.custom_primary_button = None
        self.custom_secondary_button = None
        self.game_scale = 1.0
        self.menu_scale = 1.0
        self.game_scale_var = tk.StringVar(value="1x")
        self.menu_scale_var = tk.StringVar(value="1x")
        self.always_on_top = not ACTIVE_DESKTOP_MODE
        self.always_on_top_var = tk.BooleanVar(value=self.always_on_top)
        self.game_info_panel_pinned = tk.BooleanVar(value=False)
        self.game_info_panel_visible = True
        self.last_info_panel_hover_at = time.time()
        self.content_bg = "#ffffff"
        self.content_fg = "#1c1c1c"
        self.content_select_bg = "#d0d0d0"
        self.content_border = "#c9d2ce"
        self.content_accent = "#88a9a2"
        self.collection_caught_fg = "#247a3d"
        self.collection_missing_fg = "#a33a3a"
        self.collection_header_fg = "#4b625d"
        self.content_listboxes = []
        self.asset_images = {}
        self.attributes("-alpha", self.transparency)
        self.discord = None
        self.discord_enabled = False
        self.discord_status_text = tk.StringVar(value="Discord Rich Presence: disabled")
        self.discord_presence_enabled = tk.BooleanVar(value=True)
        self.start_with_windows_var = tk.BooleanVar(value=False)

        self.coins_text = tk.StringVar(value="0")
        self.strokes_text = tk.StringVar(value="0")
        self.inventory_text = tk.StringVar(value="0 / 8")
        self.autosell_countdown_text = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="Casting...")
        self.fish_text = tk.StringVar(value="No fish on the line yet.")
        self.progress_text = tk.StringVar(value="0 / 0")
        self.play_time_text = tk.StringVar(value="0s")
        self.collection_text = tk.StringVar(value="Collection 0 / 0")
        self.achievements_text = tk.StringVar(value="Achievements 0 / 0")
        self.gear_text = tk.StringVar(value="")
        self.backpack_text = tk.StringVar(value="")
        self.autosell_text = tk.StringVar(value="")
        self.banked_upgrade_text = tk.StringVar(value="")
        self.fishing_spot_text = tk.StringVar(value="")
        self.relic_text = tk.StringVar(value="Relics: none")
        self.potion_text = tk.StringVar(value="Potions: none")
        self.blessing_text = tk.StringVar(value="Blessings: none")
        self.menu_dock_text = tk.StringVar(value="Attached")
        self.banked_keys = 0
        self.banked_keys_text = tk.StringVar(value="0")
        self.banked_upgrade_level = 0
        self.log_list = None
        self.relic_list = None
        self.potion_list = None

        self.debug_click_timestamps = []
        self.debug_tab_enabled = False
        self.debug_selected_fish = tk.StringVar(value=fish_display_name(FISH_TABLE[0]))
        self.debug_selected_skin = tk.StringVar(value=PRIDE_FISH_SKINS[0]["name"])
        self.debug_selected_collection = tk.StringVar(value="Common")
        self.debug_selected_relic = tk.StringVar(value=RELICS[0]["name"])
        self.debug_selected_potion = tk.StringVar(value=POTIONS[0]["name"])
        self.debug_shop_prices_bypassed = tk.BooleanVar(value=False)
        self.active_menu_tab = "Inventory"
        self.menu_tab_frames = {}
        self.menu_tab_buttons = {}
        self.quit_confirm_pending = False
        self.quit_button = None

        if IS_WINDOWS:
            self.sync_start_with_windows_setting()
        self.load()
        self.configure_input_capture()
        self.apply_game_scale()
        self.update_discord_presence()
        self.build_overlay()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(TICK_MS, self.tick)
        self.after(KEY_POLL_MS, self.poll_keyboard)
        self.schedule_always_on_top_reasserts()
        if IS_WINDOWS:
            self.after(700, self.prompt_background_key_capture_on_startup)

    def build_overlay(self):
        width, height = self.overlay_size()
        bg = self.theme_palette()["bg"] if ACTIVE_DESKTOP_MODE else TRANSPARENT_COLOR
        self.overlay = tk.Canvas(self, width=width, height=height, bg=bg, highlightthickness=0)
        self.overlay.pack(fill="both", expand=True)
        self.overlay.bind("<Button-1>", self.on_overlay_press)
        self.overlay.bind("<B1-Motion>", self.on_overlay_drag)
        self.overlay.bind("<ButtonRelease-1>", self.on_overlay_release)
        self.overlay.bind("<Button-3>", self.on_overlay_right_click)
        self.overlay.bind("<Motion>", self.on_overlay_motion)
        self.overlay.bind("<Leave>", self.on_overlay_leave)
        self.draw_overlay()

    def load_app_icon(self):
        if not ICON_FILE.exists():
            return None
        try:
            return tk.PhotoImage(file=str(ICON_FILE))
        except tk.TclError:
            return None

    def apply_linux_window_hints(self, window):
        if not ACTIVE_DESKTOP_MODE:
            return
        try:
            window.tk.call("wm", "class", window._w, "TypeCast")
        except tk.TclError:
            pass
        try:
            window.attributes("-type", "dialog")
        except tk.TclError:
            pass

    def asset_image(self, *parts):
        if self.game_scale != 1.0:
            return None
        key = tuple(str(part) for part in parts)
        if key in self.asset_images:
            return self.asset_images[key]
        path = ASSET_DIR.joinpath(*key)
        if not path.exists():
            self.asset_images[key] = None
            return None
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            image = None
        self.asset_images[key] = image
        return image

    def draw_asset_image(self, canvas, x, y, *parts, anchor="center", tags=None):
        image = self.asset_image(*parts)
        if image is None:
            return False
        canvas.create_image(x, y, image=image, anchor=anchor, tags=tags)
        return True

    def draw_first_asset_image(self, canvas, x, y, candidates, anchor="center", tags=None):
        for parts in candidates:
            if self.draw_asset_image(canvas, x, y, *parts, anchor=anchor, tags=tags):
                return True
        return False

    def has_asset_image(self, candidates):
        return any(self.asset_image(*parts) is not None for parts in candidates)

    def build_menu(self):
        if self.menu and self.menu.winfo_exists():
            self.menu.lift()
            return

        self.content_listboxes.clear()
        self.menu_docked_var.set(self.menu_docked)
        self.update_menu_dock_text()
        self.menu = tk.Toplevel(self)
        self.menu.title("TypeCast")
        if self.app_icon:
            self.menu.iconphoto(True, self.app_icon)
        self.apply_linux_window_hints(self.menu)
        self.menu.overrideredirect(True)
        self.position_menu(force=True)
        self.menu.attributes("-topmost", True)
        self.menu.attributes("-alpha", self.transparency)
        self.apply_always_on_top()
        self.menu.protocol("WM_DELETE_WINDOW", self.close_menu)

        style = ttk.Style(self.menu)
        self.apply_theme(style)

        root = ttk.Frame(self.menu, padding=self.scaled_menu_value(8), borderwidth=1, relief="solid")
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(6, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        top.columnconfigure(0, weight=1)
        header_label = ttk.Label(top, text="TypeCast", style="Header.TLabel")
        header_label.grid(row=0, column=0, sticky="w")
        header_label.bind("<ButtonPress-1>", self.on_menu_press)
        header_label.bind("<B1-Motion>", self.on_menu_drag)
        header_label.bind("<ButtonRelease-1>", self.on_menu_release)
        top.bind("<ButtonPress-1>", self.on_menu_press)
        top.bind("<B1-Motion>", self.on_menu_drag)
        top.bind("<ButtonRelease-1>", self.on_menu_release)
        ttk.Button(top, textvariable=self.menu_dock_text, command=self.toggle_menu_dock).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(top, text="Hide", command=self.close_menu).grid(row=0, column=2, padx=(8, 0))
        self.quit_button = ttk.Button(top, text="Quit", command=self.confirm_quit)
        self.quit_button.grid(row=0, column=3, padx=(8, 0))

        stat_row = ttk.Frame(root)
        stat_row.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        self.coins_label = ttk.Label(stat_row, text="Coins")
        self.coins_label.pack(side="left")
        self.coins_label.bind("<Button-1>", self.handle_debug_secret_click)
        ttk.Label(stat_row, textvariable=self.coins_text, font=("Segoe UI", self.scaled_menu_value(10), "bold")).pack(side="left", padx=(4, 16))
        ttk.Label(stat_row, text="Cast Tokens").pack(side="left")
        ttk.Label(stat_row, textvariable=self.banked_keys_text, font=("Segoe UI", self.scaled_menu_value(10), "bold")).pack(side="left", padx=(4, 16))
        ttk.Label(stat_row, textvariable=self.inventory_text).pack(side="right")
        ttk.Label(stat_row, textvariable=self.autosell_countdown_text, style="Subtle.TLabel").pack(side="right", padx=(0, 12))

        ttk.Label(root, textvariable=self.status_text, font=("Segoe UI", self.scaled_menu_value(10), "bold")).grid(row=2, column=0, sticky="w")
        ttk.Label(root, textvariable=self.fish_text).grid(row=3, column=0, sticky="w", pady=(1, 3))
        self.progress = ttk.Progressbar(root, maximum=1)
        self.progress.grid(row=4, column=0, sticky="ew")
        ttk.Label(root, textvariable=self.progress_text, style="Subtle.TLabel").grid(row=5, column=0, sticky="w", pady=(2, 6))

        tabs = ttk.Frame(root, style="Content.TFrame")
        tabs.grid(row=6, column=0, sticky="nsew")
        tabs.columnconfigure(1, weight=1)
        tabs.rowconfigure(0, weight=1)
        tab_nav = ttk.Frame(tabs, style="Content.TFrame")
        tab_nav.grid(row=0, column=0, sticky="ns", padx=(0, 6))
        tab_content = ttk.Frame(tabs, style="Content.TFrame")
        tab_content.grid(row=0, column=1, sticky="nsew")
        tab_content.columnconfigure(0, weight=1)
        tab_content.rowconfigure(0, weight=1)
        self.menu_tab_frames = {}
        self.menu_tab_buttons = {}

        def add_menu_tab(name):
            frame = ttk.Frame(tab_content, padding=6, style="Content.TFrame")
            frame.grid(row=0, column=0, sticky="nsew")
            button = ttk.Button(tab_nav, text=name, width=self.scaled_menu_value(11), style="Tab.TButton", command=lambda tab_name=name: self.show_menu_tab(tab_name))
            button.pack(fill="x", pady=(0, 4))
            self.menu_tab_frames[name] = frame
            self.menu_tab_buttons[name] = button
            return frame

        inventory_tab = add_menu_tab("Inventory")
        potions_tab = add_menu_tab("Potions") if self.player_has_potions() else None
        relics_tab = add_menu_tab("Relics") if self.player_has_relics() else None
        shop_tab = add_menu_tab("Shop")
        stats_tab = add_menu_tab("Stats")
        collection_tab = add_menu_tab("Collection")
        achievements_tab = add_menu_tab("Achievements")
        log_tab = add_menu_tab("Log")
        settings_tab = add_menu_tab("Settings")
        info_tab = add_menu_tab("Info")

        if self.debug_tab_enabled:
            debug_tab = add_menu_tab("Debug")
            ttk.Label(debug_tab, text="Resources").pack(anchor="w", pady=(0, 4))
            debug_resource_grid = ttk.Frame(debug_tab)
            debug_resource_grid.pack(fill="x", pady=(0, 8))
            for column in range(3):
                debug_resource_grid.columnconfigure(column, weight=1)
            ttk.Button(debug_resource_grid, text="+1000 Coins", command=lambda: self.debug_add_coins(1000)).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 4))
            ttk.Button(debug_resource_grid, text="+10000 Coins", command=lambda: self.debug_add_coins(10000)).grid(row=1, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(debug_resource_grid, text="+1000 Total Keys", command=lambda: self.debug_add_total_keys(1000)).grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(0, 4))
            ttk.Button(debug_resource_grid, text="+10000 Total Keys", command=lambda: self.debug_add_total_keys(10000)).grid(row=1, column=1, sticky="ew", padx=(0, 6))
            ttk.Button(debug_resource_grid, text="+1000 Cast Tokens", command=lambda: self.debug_add_banked_keys(1000)).grid(row=0, column=2, sticky="ew", pady=(0, 4))
            ttk.Button(debug_resource_grid, text="+10000 Cast Tokens", command=lambda: self.debug_add_banked_keys(10000)).grid(row=1, column=2, sticky="ew")

            ttk.Checkbutton(debug_tab, text="Bypass Shop Prices", variable=self.debug_shop_prices_bypassed, command=self.on_debug_shop_prices_toggle, style="Content.TCheckbutton").pack(anchor="w", pady=(4, 0))

            ttk.Label(debug_tab, text="Actions").pack(anchor="w", pady=(8, 4))
            debug_action_row = ttk.Frame(debug_tab)
            debug_action_row.pack(fill="x")
            ttk.Button(debug_action_row, text="Skip Fish", command=self.debug_skip_fish).pack(side="left", fill="x", expand=True, padx=(0, 6))
            ttk.Button(debug_action_row, text="1 Key Left", command=self.debug_set_one_key_left).pack(side="left", fill="x", expand=True, padx=(0, 6))
            ttk.Button(debug_action_row, text="AFK", command=self.debug_trigger_afk).pack(side="left", fill="x", expand=True)

            ttk.Label(debug_tab, text="Spawn Fish").pack(anchor="w", pady=(8, 4))
            spawn_frame = ttk.Frame(debug_tab)
            spawn_frame.pack(fill="x")
            blessing_names = [f"Blessing: {visitor['name']}" for visitor in BLESSING_VISITORS]
            fish_names = ["Treasure Chest"] + blessing_names + [fish_display_name(fish) for fish in FISH_TABLE]
            self.debug_spawn_menu = ttk.Combobox(spawn_frame, values=fish_names, textvariable=self.debug_selected_fish, state="readonly")
            self.debug_spawn_menu.pack(side="left", fill="x", expand=True)
            ttk.Button(spawn_frame, text="Spawn", command=self.debug_spawn_fish).pack(side="left", padx=(8, 0))

            ttk.Label(debug_tab, text="Apply Skin").pack(anchor="w", pady=(8, 4))
            skin_frame = ttk.Frame(debug_tab)
            skin_frame.pack(fill="x")
            skin_names = [skin["name"] for skin in PRIDE_FISH_SKINS]
            self.debug_skin_menu = ttk.Combobox(skin_frame, values=skin_names, textvariable=self.debug_selected_skin, state="readonly")
            self.debug_skin_menu.pack(side="left", fill="x", expand=True)
            ttk.Button(skin_frame, text="Apply", command=self.debug_apply_selected_skin).pack(side="left", padx=(8, 0))

            ttk.Label(debug_tab, text="Add Relic").pack(anchor="w", pady=(8, 4))
            relic_frame = ttk.Frame(debug_tab)
            relic_frame.pack(fill="x")
            relic_names = [relic["name"] for relic in RELICS]
            self.debug_relic_menu = ttk.Combobox(relic_frame, values=relic_names, textvariable=self.debug_selected_relic, state="readonly")
            self.debug_relic_menu.pack(side="left", fill="x", expand=True)
            ttk.Button(relic_frame, text="Add", command=self.debug_add_selected_relic).pack(side="left", padx=(8, 0))

            ttk.Label(debug_tab, text="Add Potion").pack(anchor="w", pady=(8, 4))
            potion_frame = ttk.Frame(debug_tab)
            potion_frame.pack(fill="x")
            potion_names = [potion["name"] for potion in POTIONS]
            self.debug_potion_menu = ttk.Combobox(potion_frame, values=potion_names, textvariable=self.debug_selected_potion, state="readonly")
            self.debug_potion_menu.pack(side="left", fill="x", expand=True)
            ttk.Button(potion_frame, text="Add", command=self.debug_add_selected_potion).pack(side="left", padx=(8, 0))

            ttk.Label(debug_tab, text="Complete Collection Section").pack(anchor="w", pady=(8, 4))
            collection_debug_frame = ttk.Frame(debug_tab)
            collection_debug_frame.pack(fill="x")
            collection_sections = ["Common", "Uncommon", "Rare", "Epic", "Secret", "Ultra Rare", HAPPY_FISH_COLLECTION, "All"]
            self.debug_collection_menu = ttk.Combobox(collection_debug_frame, values=collection_sections, textvariable=self.debug_selected_collection, state="readonly")
            self.debug_collection_menu.pack(side="left", fill="x", expand=True)
            ttk.Button(collection_debug_frame, text="Complete", command=self.debug_complete_collection_section).pack(side="left", padx=(8, 0))

            ttk.Label(debug_tab, text="Unlock Systems").pack(anchor="w", pady=(8, 4))
            unlock_debug_frame = ttk.Frame(debug_tab)
            unlock_debug_frame.pack(fill="x")
            ttk.Button(unlock_debug_frame, text="Unlock All Spots", command=self.debug_unlock_all_fishing_spots).pack(side="left", padx=(0, 8))
            ttk.Button(unlock_debug_frame, text="Complete All Achievements", command=self.debug_complete_all_achievements).pack(side="left")

        self.inventory_list = tk.Listbox(inventory_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(7), activestyle="dotbox")
        self.inventory_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.inventory_list)
        inv_buttons = ttk.Frame(inventory_tab)
        inv_buttons.pack(fill="x", pady=(5, 0))
        ttk.Button(inv_buttons, text="Sell Selected", command=self.sell_selected).pack(side="left", padx=(0, 8))
        ttk.Button(inv_buttons, text="Sell All", command=self.sell_all).pack(side="left")

        if potions_tab is not None:
            self.potion_list = tk.Listbox(potions_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(9), activestyle="dotbox")
            self.potion_list.pack(fill="both", expand=True)
            self.content_listboxes.append(self.potion_list)
            ttk.Button(potions_tab, text="Use Selected", command=self.use_selected_potion).pack(fill="x", pady=(5, 0))
        else:
            self.potion_list = None

        if relics_tab is not None:
            self.relic_list = tk.Listbox(relics_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(9), activestyle="dotbox")
            self.relic_list.pack(fill="both", expand=True)
            self.content_listboxes.append(self.relic_list)
            ttk.Button(relics_tab, text="Trade Up Selected", command=self.trade_up_selected_relic).pack(fill="x", pady=(5, 0))
        else:
            self.relic_list = None

        ttk.Label(collection_tab, textvariable=self.collection_text, style="Content.TLabel").pack(anchor="w", pady=(0, 4))
        self.collection_list = tk.Listbox(collection_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(9), activestyle="dotbox")
        self.collection_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.collection_list)

        ttk.Label(achievements_tab, textvariable=self.achievements_text, style="Content.TLabel").pack(anchor="w", pady=(0, 4))
        self.achievements_list = tk.Listbox(achievements_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(9), activestyle="dotbox")
        self.achievements_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.achievements_list)

        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)
        log_frame = ttk.Frame(log_tab, style="Content.TFrame")
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical")
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_list = tk.Listbox(
            log_frame,
            width=self.scaled_menu_value(54),
            height=self.scaled_menu_value(15),
            activestyle="dotbox",
            yscrollcommand=log_scrollbar.set,
        )
        self.log_list.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.configure(command=self.log_list.yview)
        self.content_listboxes.append(self.log_list)

        shop_sections = ttk.Notebook(shop_tab)
        shop_sections.pack(fill="both", expand=True)
        upgrades_shop_tab = ttk.Frame(shop_sections, padding=4, style="Content.TFrame")
        spots_shop_tab = ttk.Frame(shop_sections, padding=4, style="Content.TFrame")
        shop_sections.add(upgrades_shop_tab, text="Upgrades")
        shop_sections.add(spots_shop_tab, text="Spots")

        ttk.Label(upgrades_shop_tab, text="Equipment", style="Content.TLabel").pack(anchor="w")
        self.shop_list = tk.Listbox(upgrades_shop_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(4))
        self.shop_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.shop_list)
        ttk.Button(upgrades_shop_tab, text="Buy Equipment Upgrade", command=self.buy_equipment_upgrade).pack(fill="x", pady=(5, 0))
        ttk.Label(upgrades_shop_tab, text="Backpack", style="Content.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Label(upgrades_shop_tab, textvariable=self.backpack_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w", pady=(1, 2))
        self.backpack_list = tk.Listbox(upgrades_shop_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(2))
        self.backpack_list.pack(fill="x")
        self.content_listboxes.append(self.backpack_list)
        ttk.Button(upgrades_shop_tab, text="Buy Backpack Upgrade", command=self.buy_backpack_upgrade).pack(fill="x", pady=(5, 0))

        ttk.Label(upgrades_shop_tab, text="Auto Sell Module", style="Content.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Label(upgrades_shop_tab, textvariable=self.autosell_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w", pady=(1, 2))
        self.autosell_list = tk.Listbox(upgrades_shop_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(2))
        self.autosell_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.autosell_list)
        ttk.Button(upgrades_shop_tab, text="Buy Auto Sell Upgrade", command=self.buy_autosell_upgrade).pack(fill="x", pady=(5, 0))

        ttk.Label(upgrades_shop_tab, text="Cast Tokens", style="Content.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Label(upgrades_shop_tab, textvariable=self.banked_upgrade_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w", pady=(1, 2))
        self.banked_upgrade_list = tk.Listbox(upgrades_shop_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(2))
        self.banked_upgrade_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.banked_upgrade_list)
        ttk.Button(upgrades_shop_tab, text="Purchase Cast Token Upgrade", command=self.buy_banked_upgrade).pack(fill="x", pady=(5, 0))

        ttk.Label(spots_shop_tab, text="Fishing Spots", style="Content.TLabel").pack(anchor="w")
        ttk.Label(spots_shop_tab, textvariable=self.fishing_spot_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w", pady=(1, 4))
        self.fishing_spot_list = tk.Listbox(spots_shop_tab, width=self.scaled_menu_value(54), height=self.scaled_menu_value(8))
        self.fishing_spot_list.pack(fill="both", expand=True)
        self.content_listboxes.append(self.fishing_spot_list)
        spot_buttons = ttk.Frame(spots_shop_tab, style="Content.TFrame")
        spot_buttons.pack(fill="x", pady=(5, 0))
        ttk.Button(spot_buttons, text="Buy Spot", command=self.buy_selected_fishing_spot).pack(side="left", padx=(0, 8))
        ttk.Button(spot_buttons, text="Use Spot", command=self.select_fishing_spot).pack(side="left")

        stat_grid = ttk.Frame(stats_tab, style="Content.TFrame")
        stat_grid.pack(fill="x", pady=(0, 6))
        stat_grid.columnconfigure(1, weight=1)
        ttk.Label(stat_grid, text="Coins", style="Content.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(stat_grid, textvariable=self.coins_text, font=("Segoe UI", self.scaled_menu_value(11), "bold"), style="Content.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(stat_grid, text="Total Keys", style="Content.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(3, 0))
        ttk.Label(stat_grid, textvariable=self.strokes_text, font=("Segoe UI", self.scaled_menu_value(11), "bold"), style="Content.TLabel").grid(row=1, column=1, sticky="w", pady=(3, 0))
        ttk.Label(stat_grid, text="Play Time", style="Content.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(3, 0))
        ttk.Label(stat_grid, textvariable=self.play_time_text, font=("Segoe UI", self.scaled_menu_value(11), "bold"), style="Content.TLabel").grid(row=2, column=1, sticky="w", pady=(3, 0))
        ttk.Label(stats_tab, textvariable=self.inventory_text, style="Content.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(stats_tab, textvariable=self.backpack_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w", pady=(0, 4))
        ttk.Label(stats_tab, textvariable=self.gear_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w")
        ttk.Label(stats_tab, textvariable=self.blessing_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w", pady=(4, 0))
        ttk.Label(stats_tab, text="Equipment", style="Content.TLabel").pack(anchor="w", pady=(10, 4))
        self.equipment_text = tk.StringVar(value="")
        ttk.Label(stats_tab, textvariable=self.equipment_text, style="Content.Subtle.TLabel", wraplength=360).pack(anchor="w")

        info_sections = ttk.Notebook(info_tab)
        info_sections.pack(fill="both", expand=True)
        info_wrap = self.scaled_menu_value(350)

        def add_info_tab(name, sections):
            tab = ttk.Frame(info_sections, padding=6, style="Content.TFrame")
            info_sections.add(tab, text=name)
            for index, (title, body) in enumerate(sections):
                ttk.Label(tab, text=title, style="Content.TLabel").pack(anchor="w", pady=((0 if index == 0 else 8), 2))
                ttk.Label(tab, text=body, style="Content.Subtle.TLabel", wraplength=info_wrap).pack(anchor="w")
            return tab

        add_info_tab(
            "Basics",
            [
                (
                    "How TypeCast works",
                    "TypeCast casts automatically. On Windows it can count background typing if enabled; on Linux and other platforms, keep the game window focused and type there to reel in fish. The main screen shows the current fish, progress, and your inventory space.",
                ),
                (
                    "Your goal",
                    "Catch fish, sell them for coins, and buy upgrades that make future catches easier to manage. Collection logs, achievements, fishing spots, and a few hidden surprises give you long-term goals to chase.",
                ),
                (
                    "Opening the menu",
                    "Right-click anywhere on the game window to open or close the menu. You can also left-click the small menu icon in the lower-right corner.",
                ),
                (
                    "Compact mode",
                    "Right-click the small menu icon to shrink TypeCast into a compact progress bar. Right-click it again to return to the full game screen.",
                ),
            ],
        )
        add_info_tab(
            "Inventory",
            [
                (
                    "Holding fish",
                    "Caught fish go into your inventory if there is room. Sell selected fish or sell everything from the Inventory tab when you are ready to cash out.",
                ),
                (
                    "When inventory is full",
                    "If your backpack is full, extra fish are overflow sold for 10% of their normal sell value. This keeps you from earning nothing, but backpack upgrades and regular selling still matter.",
                ),
                (
                    "Collection credit",
                    "Fish count for your collection log when you catch them, even if they are overflow sold because your backpack is full.",
                ),
                (
                    "Spot collections",
                    "Most fish live in a specific fishing spot. To complete the full collection, unlock every spot and fish in each one. The Collection tab shows each fish's location.",
                ),
            ],
        )
        add_info_tab(
            "Shop",
            [
                (
                    "Upgrades",
                    "The Upgrades section sells equipment, backpack space, auto sell modules, and Cast Token upgrades. Select an item in a list, then use the matching buy button.",
                ),
                (
                    "Fishing spots",
                    "The Spots section unlocks new fishing locations. Each spot has its own themed fish pool, and harder-to-unlock spots have more valuable catches.",
                ),
                (
                    "Unlock costs",
                    "Some shop items cost coins, while others may ask for Cast Tokens, collection progress, achievements, or a mix of requirements.",
                ),
            ],
        )
        add_info_tab(
            "Systems",
            [
                (
                    "Cast Tokens",
                    "Cast Tokens build up while TypeCast is casting and there is no fish on the line. Cast Token upgrades can improve reeling progress and shop discounts. Blue popups show Cast Token changes, while green and red popups show other gains and spending.",
                ),
                (
                    "Auto sell",
                    "Once unlocked, auto sell periodically sells part of your inventory every 3 minutes. The timer appears near your fish counter and at the top of the menu.",
                ),
                (
                    "Treasure chests",
                    "Rarely, something heavier than a fish may surface. It takes a pile of keys to open, but the contents can be worth the wait.",
                ),
                (
                    "Potions",
                    "Treasure chests can drop temporary potions. Stored potions appear in the Potions tab; use one when you want its coins or Cast Tokens effect to run for 15 minutes.",
                ),
                (
                    "Visitor blessings",
                    "Rare visitors can surface instead of a fish. Complete their keystroke challenge to store a blessing in a backpack trophy slot, then use Sell Selected on that blessing when you want to activate it. Rod, accuracy, and Cast Token blessings last for a scaled number of keystrokes; luck blessings last for a scaled number of catches.",
                ),
                (
                    "Relics",
                    "Some discoveries only explain themselves after you find one. When that happens, a new Inventory tab appears with what it does and how many you own.",
                ),
                (
                    "Progress tracking",
                    "The Collection, Achievements, and Log tabs track what you have discovered, completed, earned, and unlocked over time.",
                ),
            ],
        )
        status_info_tab = add_info_tab(
            "Settings",
            [
                (
                    "Display options",
                    "Settings let you change themes, transparency, game scale, menu scale, monitor selection, menu attachment, and whether the windows stay on top.",
                ),
                (
                    "Startup and Discord",
                    "You can choose whether TypeCast starts with Windows and whether Discord Rich Presence is enabled.",
                ),
            ],
        )
        ttk.Label(status_info_tab, textvariable=self.discord_status_text, style="Content.Subtle.TLabel", wraplength=info_wrap).pack(anchor="w", pady=(10, 0))
        ttk.Label(status_info_tab, textvariable=self.input_status_text, style="Content.Subtle.TLabel", wraplength=info_wrap).pack(anchor="w", pady=(4, 0))

        ttk.Label(settings_tab, text="Appearance", style="Content.TLabel").pack(anchor="w")
        ttk.Label(settings_tab, text="Transparency", style="Content.Subtle.TLabel").pack(anchor="w", pady=(8, 0))
        slider_frame = ttk.Frame(settings_tab, style="Content.TFrame")
        slider_frame.pack(fill="x", pady=(3, 6))
        ttk.Scale(slider_frame, from_=20, to=100, variable=self.transparency_percent, command=self.on_transparency_change, style="Content.Horizontal.TScale").pack(side="left", fill="x", expand=True)
        ttk.Label(slider_frame, textvariable=self.transparency_text, width=6, style="Content.TLabel").pack(side="left", padx=(8, 0))
        ttk.Label(settings_tab, text="Theme", style="Content.Subtle.TLabel").pack(anchor="w", pady=(6, 2))
        self.theme_menu = ttk.Combobox(settings_tab, values=THEME_MENU_LABELS, textvariable=self.theme_var, state="readonly", width=28)
        self.theme_menu.pack(anchor="w", fill="x", pady=(0, 6))
        self.theme_menu.bind("<<ComboboxSelected>>", self.on_theme_selected)
        self.custom_theme_frame = ttk.Frame(settings_tab, style="Content.TFrame")
        self.custom_theme_frame.pack(anchor="w", fill="x", pady=(0, 6))
        self.custom_primary_button = tk.Button(self.custom_theme_frame, command=lambda: self.choose_custom_theme_color("primary"))
        self.custom_primary_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.custom_secondary_button = tk.Button(self.custom_theme_frame, command=lambda: self.choose_custom_theme_color("secondary"))
        self.custom_secondary_button.pack(side="left", fill="x", expand=True)
        self.update_custom_theme_controls()
        scale_frame = ttk.Frame(settings_tab, style="Content.TFrame")
        scale_frame.pack(fill="x", pady=(0, 6))
        scale_frame.columnconfigure(1, weight=1)
        scale_frame.columnconfigure(3, weight=1)
        ttk.Label(scale_frame, text="Game Scale", style="Content.Subtle.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        game_scale_menu = ttk.Combobox(scale_frame, values=GAME_SCALE_LABELS, textvariable=self.game_scale_var, state="readonly", width=7)
        game_scale_menu.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        game_scale_menu.bind("<<ComboboxSelected>>", self.on_game_scale_selected)
        ttk.Label(scale_frame, text="Menu Scale", style="Content.Subtle.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6))
        menu_scale_menu = ttk.Combobox(scale_frame, values=MENU_SCALE_LABELS, textvariable=self.menu_scale_var, state="readonly", width=7)
        menu_scale_menu.grid(row=0, column=3, sticky="ew")
        menu_scale_menu.bind("<<ComboboxSelected>>", self.on_menu_scale_selected)
        monitor_frame = ttk.Frame(settings_tab, style="Content.TFrame")
        monitor_frame.pack(fill="x", pady=(0, 6))
        monitor_frame.columnconfigure(1, weight=1)
        ttk.Label(monitor_frame, text="Monitor", style="Content.Subtle.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.refresh_monitor_options()
        monitor_menu = ttk.Combobox(monitor_frame, values=[monitor["label"] for monitor in self.monitor_options], textvariable=self.monitor_var, state="readonly", width=18)
        monitor_menu.grid(row=0, column=1, sticky="ew")
        monitor_menu.bind("<<ComboboxSelected>>", self.on_monitor_selected)
        ttk.Checkbutton(settings_tab, text="Always on Top", variable=self.always_on_top_var, command=self.toggle_always_on_top, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(settings_tab, text="Attach Menu to Game Window", variable=self.menu_docked_var, command=self.on_menu_dock_setting_toggle, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(settings_tab, text="Vertical Compact Mode", variable=self.compact_vertical_var, command=self.on_compact_vertical_toggle, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(settings_tab, text="Pin Game Info Panel", variable=self.game_info_panel_pinned, command=self.toggle_game_info_panel_pin, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
        if IS_WINDOWS:
            ttk.Checkbutton(settings_tab, text="Start with Windows", variable=self.start_with_windows_var, command=self.on_start_with_windows_toggle, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
            ttk.Checkbutton(settings_tab, text="Enable Background Key Capture", variable=self.background_key_capture_enabled, command=self.on_background_key_capture_toggle, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
        ttk.Label(settings_tab, textvariable=self.input_status_text, style="Content.Subtle.TLabel", wraplength=info_wrap).pack(anchor="w", fill="x", pady=(0, 6))
        ttk.Checkbutton(settings_tab, text="Enable Discord Rich Presence", variable=self.discord_presence_enabled, command=self.on_discord_presence_toggle, style="Content.TCheckbutton").pack(anchor="w", pady=(0, 6))
        ttk.Button(settings_tab, text="Reconnect Discord", command=self.reconnect_discord_presence).pack(anchor="w", pady=(0, 6))
        ttk.Button(settings_tab, text="Reset Save", style="Danger.TButton", command=self.confirm_reset_save).pack(anchor="w")

        self.apply_content_listbox_colors()
        if self.active_menu_tab not in self.menu_tab_frames:
            self.active_menu_tab = "Inventory"
        self.show_menu_tab(self.active_menu_tab)
        self.refresh_all()
        self.position_menu(force=True)

    def close_menu(self):
        self.reset_quit_confirmation()
        if self.menu and self.menu.winfo_exists():
            self.menu.destroy()
        self.menu = None
        self.menu_drag_start = None
        self.menu_tab_frames = {}
        self.menu_tab_buttons = {}
        self.quit_button = None
        self.log_list = None
        self.relic_list = None
        self.potion_list = None

    def reset_quit_confirmation(self):
        self.quit_confirm_pending = False
        if self.quit_button is not None and self.quit_button.winfo_exists():
            self.quit_button.configure(text="Quit", style="TButton")

    def confirm_quit(self):
        if self.quit_confirm_pending:
            self.on_close()
            return
        self.quit_confirm_pending = True
        if self.quit_button is not None and self.quit_button.winfo_exists():
            self.quit_button.configure(text="Confirm Quit", style="ConfirmQuit.TButton")
        self.after(3500, self.reset_quit_confirmation)

    def show_menu_tab(self, name):
        if name not in self.menu_tab_frames:
            return
        self.reset_quit_confirmation()
        self.active_menu_tab = name
        self.menu_tab_frames[name].tkraise()
        for tab_name, button in self.menu_tab_buttons.items():
            if button.winfo_exists():
                button.configure(style="Selected.Tab.TButton" if tab_name == name else "Tab.TButton")

    def toggle_menu(self):
        if self.menu and self.menu.winfo_exists():
            self.close_menu()
        else:
            self.build_menu()

    def update_menu_dock_text(self):
        self.menu_dock_text.set("Detach" if self.menu_docked else "Attach")

    def toggle_menu_dock(self):
        self.menu_docked = not self.menu_docked
        self.menu_docked_var.set(self.menu_docked)
        self.update_menu_dock_text()
        if self.menu and self.menu.winfo_exists() and not self.menu_docked:
            self.menu.update_idletasks()
            self.menu_offset_x = self.menu.winfo_x()
            self.menu_offset_y = self.menu.winfo_y()
        self.position_menu(force=True)
        self.save()

    def on_menu_dock_setting_toggle(self):
        self.menu_docked = self.menu_docked_var.get()
        self.update_menu_dock_text()
        if self.menu and self.menu.winfo_exists() and not self.menu_docked:
            self.menu.update_idletasks()
            self.menu_offset_x = self.menu.winfo_x()
            self.menu_offset_y = self.menu.winfo_y()
        self.position_menu(force=True)
        self.save()

    def position_menu(self, force=False):
        if not self.menu or not self.menu.winfo_exists():
            return
        self.menu.update_idletasks()
        overlay_width = self.winfo_width() or self.winfo_reqwidth()
        overlay_height = self.winfo_height() or self.winfo_reqheight()
        menu_width = self.menu.winfo_width() or self.menu.winfo_reqwidth()
        menu_height = self.menu.winfo_height() or self.menu.winfo_reqheight()
        work_left, work_top, work_right, work_bottom = self.work_area_bounds()
        overlay_x = self.winfo_x()
        overlay_y = self.winfo_y()
        if not self.menu_docked:
            x = self.menu_offset_x
            y = self.menu_offset_y
            if x == 0 and y == 0:
                x = overlay_x + overlay_width + 10
                y = overlay_y
            x = max(work_left, min(x, max(work_left, work_right - menu_width)))
            y = max(work_top, min(y, max(work_top, work_bottom - menu_height)))
            self.menu_offset_x = x
            self.menu_offset_y = y
            self.menu.geometry(f"+{x}+{y}")
            return
        x = overlay_x + (overlay_width - menu_width) // 2
        y = overlay_y - menu_height
        if y < work_top:
            y = overlay_y + overlay_height
        x = max(work_left, min(x, max(work_left, work_right - menu_width)))
        y = max(work_top, min(y, max(work_top, work_bottom - menu_height)))
        self.menu.geometry(f"+{x}+{y}")

    def on_menu_press(self, event):
        if not self.menu or not self.menu.winfo_exists():
            return
        if self.menu_docked:
            self.menu_drag_start = None
            return
        self.menu_drag_start = (event.x_root, event.y_root, self.menu.winfo_x(), self.menu.winfo_y())

    def on_menu_drag(self, event):
        if self.menu_docked or not self.menu_drag_start:
            return
        start_x, start_y, menu_x, menu_y = self.menu_drag_start
        new_x = menu_x + event.x_root - start_x
        new_y = menu_y + event.y_root - start_y
        self.menu_offset_x = new_x
        self.menu_offset_y = new_y
        self.position_menu()

    def on_menu_release(self, event):
        if self.menu and self.menu.winfo_exists() and not self.menu_docked:
            self.menu_offset_x = self.menu.winfo_x()
            self.menu_offset_y = self.menu.winfo_y()
            self.save()
        self.menu_drag_start = None

    def enable_debug_tab(self):
        if self.debug_tab_enabled:
            return
        self.debug_tab_enabled = True
        self.last_message = "Debug tab unlocked!"
        self.refresh_all()
        if self.menu and self.menu.winfo_exists():
            self.close_menu()
            self.build_menu()

    def handle_debug_secret_click(self, event=None):
        now = time.time()
        self.debug_click_timestamps = [ts for ts in self.debug_click_timestamps if now - ts <= 10]
        self.debug_click_timestamps.append(now)
        if len(self.debug_click_timestamps) >= 5:
            self.enable_debug_tab()
        return "break"

    def add_resource_delta(self, resource, amount):
        amount = int(amount)
        if amount == 0:
            return
        now = time.time()
        for delta in reversed(self.resource_deltas):
            if delta.resource == resource and (delta.amount > 0) == (amount > 0) and now - delta.born <= 0.35:
                delta.amount += amount
                delta.born = now
                return
        self.resource_deltas.append(ResourceDelta(resource, amount, now))
        self.resource_deltas = self.resource_deltas[-12:]

    def change_coins(self, amount):
        self.coins += int(amount)
        self.add_resource_delta("coins", amount)

    def change_keys(self, amount):
        self.total_keystrokes += int(amount)
        self.add_resource_delta("keys", amount)

    def change_banked_keys(self, amount):
        self.banked_keys += int(amount)
        self.add_resource_delta("banked_keys", amount)

    def add_log_entry(self, message):
        timestamp = time.strftime("%H:%M")
        self.event_log.insert(0, f"{timestamp} - {message}")
        self.event_log = self.event_log[:80]

    def debug_add_coins(self, amount=1000):
        self.change_coins(amount)
        self.last_message = f"Cheat: added {amount} coins."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def debug_add_total_keys(self, amount=1000):
        self.change_keys(amount)
        self.last_message = f"Cheat: added {amount} total keys."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def debug_add_banked_keys(self, amount=1000):
        self.change_banked_keys(amount)
        self.last_message = f"Cheat: added {amount} Cast Tokens."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def debug_add_selected_relic(self):
        selected_relic = self.debug_selected_relic.get()
        for relic in RELICS:
            if relic["name"] == selected_relic:
                self.add_relic(relic)
                self.last_message = f"Cheat: added relic {relic['name']}."
                self.refresh_all()
                return
        self.last_message = f"Cheat: relic '{selected_relic}' not found."
        self.refresh_all()

    def debug_add_selected_potion(self):
        selected_potion = self.debug_selected_potion.get()
        for potion in POTIONS:
            if potion["name"] == selected_potion:
                self.add_potion(potion)
                self.last_message = f"Cheat: added potion {potion['name']}."
                self.refresh_all()
                return
        self.last_message = f"Cheat: potion '{selected_potion}' not found."
        self.refresh_all()

    def debug_skip_fish(self):
        if not self.hooked_fish:
            self.last_message = "No fish to skip."
            self.refresh_all()
            return
        self.hooked_fish = None
        self.cast_started_at = time.time()
        self.last_message = "Cheat: skipped the current fish."
        self.refresh_all()

    def debug_set_one_key_left(self):
        if not self.hooked_fish:
            self.last_message = "Cheat: no active catch to advance."
            self.refresh_all()
            return
        self.hooked_fish.progress = max(0, self.hooked_fish.strokes - 1)
        self.last_message = f"Cheat: {hooked_fish_display_name(self.hooked_fish)} needs 1 more key."
        self.refresh_all()

    def debug_trigger_afk(self):
        if not self.hooked_fish:
            fish = FISH_TABLE[0]
            self.hooked_fish = HookedFish(
                name=fish["name"],
                rarity=fish["rarity"],
                strokes=max(1, round(fish["strokes"] * self.stroke_multiplier())),
                value=fish["value"],
                color=fish["color"],
                spot_id=fish.get("spot_id", self.selected_fishing_spot),
            )
            self.cast_started_at = time.time()
        self.last_player_activity_at = time.time() - IDLE_ZZ_SECONDS
        self.last_message = "Cheat: triggered AFK animation."
        self.refresh_all()

    def debug_spawn_fish(self):
        selected_fish = self.debug_selected_fish.get()
        if selected_fish == "Treasure Chest":
            self.hooked_fish = HookedFish(
                name="Treasure Chest",
                rarity="Treasure",
                strokes=TREASURE_CHEST_STROKES,
                value=0,
                color="#c9823b",
                kind="chest",
            )
            self.cast_started_at = time.time()
            self.last_message = "Cheat: spawned Treasure Chest."
            self.refresh_all()
            return
        blessing_prefix = "Blessing: "
        if selected_fish.startswith(blessing_prefix):
            selected_blessing = selected_fish[len(blessing_prefix):]
            for visitor in BLESSING_VISITORS:
                if visitor["name"] == selected_blessing:
                    self.hooked_fish = self.create_blessing_visitor_hook(visitor)
                    self.cast_started_at = time.time()
                    self.last_message = f"Cheat: spawned {visitor['name']} blessing."
                    self.refresh_all()
                    return
        for fish in FISH_TABLE:
            if fish_display_name(fish) == selected_fish:
                self.hooked_fish = HookedFish(
                    name=fish["name"],
                    rarity=fish["rarity"],
                    strokes=max(1, round(fish["strokes"] * self.stroke_multiplier())),
                    value=fish["value"],
                    color=fish["color"],
                    spot_id=fish.get("spot_id", self.selected_fishing_spot),
                )
                self.hooked_fish.progress = 0
                self.cast_started_at = time.time()
                self.last_message = f"Cheat: spawned {selected_fish}."
                self.refresh_all()
                return
        self.last_message = f"Cheat: fish '{selected_fish}' not found."
        self.refresh_all()

    def debug_apply_selected_skin(self):
        if not self.hooked_fish:
            self.last_message = "Cheat: no current fish to skin."
            self.refresh_all()
            return
        if self.hooked_fish.kind != "fish":
            self.last_message = "Cheat: skins can only be applied to fish."
            self.refresh_all()
            return
        selected_skin = self.debug_selected_skin.get()
        for skin in PRIDE_FISH_SKINS:
            if skin["name"] == selected_skin:
                apply_pride_skin(self.hooked_fish, skin)
                self.last_message = f"Cheat: applied {skin['name']} skin."
                self.refresh_all()
                return
        self.last_message = f"Cheat: skin '{selected_skin}' not found."
        self.refresh_all()

    def debug_complete_collection_section(self):
        selected_section = self.debug_selected_collection.get()
        completed = 0
        if selected_section == HAPPY_FISH_COLLECTION:
            for skin in PRIDE_FISH_SKINS:
                key = happy_fish_collection_key(skin["id"])
                entry = self.collection_log.setdefault(key, {"count": 0, "best_value": 0})
                if safe_int(entry.get("count", 0)) <= 0:
                    completed += 1
                entry["count"] = max(1, safe_int(entry.get("count", 0)))
            self.last_message = f"Cheat: completed {HAPPY_FISH_COLLECTION} collection ({completed} new)."
            self.refresh_all()
            return
        for fish in FISH_TABLE:
            if selected_section != "All" and fish["rarity"] != selected_section:
                continue
            key = fish_collection_key(fish["rarity"], fish["name"])
            entry = self.collection_log.setdefault(key, {"count": 0, "best_value": 0})
            if safe_int(entry.get("count", 0)) <= 0:
                completed += 1
            entry["count"] = max(1, safe_int(entry.get("count", 0)))
            entry["best_value"] = max(safe_int(entry.get("best_value", 0)), safe_int(fish.get("value", 0)))
        self.last_message = f"Cheat: completed {selected_section} collection ({completed} new)."
        self.refresh_all()

    def debug_unlock_all_fishing_spots(self):
        self.unlocked_fishing_spots = {spot["id"] for spot in FISHING_SPOTS}
        self.last_message = "Cheat: unlocked all fishing spots."
        self.refresh_all()

    def debug_complete_all_achievements(self):
        self.achievements_unlocked = {achievement["id"] for achievement in ACHIEVEMENTS}
        self.last_message = "Cheat: completed all achievements."
        self.refresh_all()

    def roll_next_hooked_fish(self):
        if (
            self.fish_since_last_treasure_chest >= TREASURE_CHEST_MIN_FISH_BETWEEN
            and random.random() < TREASURE_CHEST_CHANCE
        ):
            self.fish_since_last_treasure_chest = 0
            return HookedFish(
                "Treasure Chest",
                "Treasure",
                TREASURE_CHEST_STROKES,
                0,
                "#c9823b",
                "chest",
            )
        if random.random() < BLESSING_EVENT_CHANCE:
            return self.roll_blessing_visitor()
        return HookedFish.from_roll(self.stroke_multiplier(), self.luck_bonus(), self.selected_fishing_spot)

    def roll_blessing_visitor(self):
        return self.create_blessing_visitor_hook(random.choice(BLESSING_VISITORS))

    def create_blessing_visitor_hook(self, visitor):
        strokes = random.randint(visitor["min_strokes"], visitor["max_strokes"])
        span = max(1, visitor["max_strokes"] - visitor["min_strokes"])
        power = (strokes - visitor["min_strokes"]) / span
        bonus = visitor["min_bonus"] + (visitor["max_bonus"] - visitor["min_bonus"]) * power
        if visitor["slot"] == "body":
            bonus = round(bonus)
        else:
            bonus = round(bonus, 3)
        return HookedFish(
            visitor["name"],
            "Blessing",
            strokes,
            0,
            visitor["color"],
            "blessing",
            blessing_id=visitor["id"],
            blessing_slot=visitor["slot"],
            blessing_bonus=bonus,
        )

    def tick(self):
        if self.hooked_fish is None and time.time() - self.cast_started_at >= self.auto_cast_seconds():
            self.hooked_fish = self.roll_next_hooked_fish()
            if self.hooked_fish.kind == "chest":
                self.last_message = "Treasure chest surfaced!"
            elif self.hooked_fish.kind == "blessing":
                self.last_message = f"{self.hooked_fish.name} surfaced with a blessing!"
            else:
                self.last_message = "Fish on!"
            self.refresh_all()
        if self.autosell_level > 0 and time.time() - self.last_autosell_at >= AUTOSELL_SECONDS and self.inventory:
            self.perform_autosell()
        self.process_relic_payouts()
        if self.cleanup_active_blessings():
            self.refresh_all()
        self.update_game_info_panel_visibility()
        if time.time() - self.last_save_at >= AUTOSAVE_SECONDS:
            self.save()
        if self.rod_pull > 0:
            self.rod_pull = max(0.0, self.rod_pull - 0.25)
        self.autosell_countdown_text.set(self.autosell_countdown_text_value())
        self.draw_overlay()
        self.after(TICK_MS, self.tick)

    def poll_keyboard(self):
        current = self.key_poller.current_keys()
        self.debug_linux_input_poll(current)

        for vk in current - self.pressed_keys:
            self.add_keystroke()
        self.pressed_keys = current
        self.after(KEY_POLL_MS, self.poll_keyboard)

    def debug_linux_input_poll(self, current):
        if not ACTIVE_DESKTOP_MODE or not isinstance(self.key_poller, LinuxEvdevKeyPoller):
            return
        now = time.time()
        new_events = self.key_poller.events_seen - self.last_input_debug_events_seen
        should_log = new_events > 0 or now - self.last_input_debug_at >= 5.0
        if not should_log:
            return
        focused_widget = self.focus_get()
        focused = focused_widget is not None
        current_keys = sorted(current)
        print(
            "[TypeCast input] "
            f"poll device={self.key_poller.device_path} "
            f"focused={focused} "
            f"focused_widget={type(focused_widget).__name__ if focused_widget else 'None'} "
            f"events_total={self.key_poller.events_seen} "
            f"events_since_last={new_events} "
            f"pressed={current_keys}",
            flush=True,
        )
        if self.key_poller.last_error:
            print(f"[TypeCast input] last read error: {self.key_poller.last_error}", flush=True)
        self.last_input_debug_at = now
        self.last_input_debug_events_seen = self.key_poller.events_seen

    def on_focused_key_press(self, event):
        self.add_keystroke()

    def set_focused_key_capture(self, enabled):
        if enabled and not self.focus_key_capture_bound:
            self.bind_all("<KeyPress>", self.on_focused_key_press)
            self.focus_key_capture_bound = True
        elif not enabled and self.focus_key_capture_bound:
            self.unbind_all("<KeyPress>")
            self.focus_key_capture_bound = False

    def configure_input_capture(self):
        if self.key_poller:
            self.key_poller.close()
        self.pressed_keys.clear()

        if ACTIVE_DESKTOP_MODE:
            device_path = self.linux_keyboard_device_path()
            if device_path:
                try:
                    self.key_poller = LinuxEvdevKeyPoller(device_path)
                except OSError as exc:
                    print(f"[TypeCast input] Failed to open Linux evdev device {device_path}: {exc}", flush=True)
                    self.key_poller = EmptyKeyPoller(f"evdev unavailable: {exc.strerror or type(exc).__name__}")
            else:
                print("[TypeCast input] No keyboard_device configured; using focused-window input only.", flush=True)
                self.key_poller = create_key_poller()
        elif IS_WINDOWS and self.background_key_capture_enabled.get() and self.background_key_capture_consent_granted:
            try:
                self.key_poller = create_background_key_poller()
            except Exception as exc:
                self.background_key_capture_enabled.set(False)
                self.key_poller = EmptyKeyPoller(f"background capture unavailable: {exc}")
        else:
            if not IS_WINDOWS:
                self.background_key_capture_enabled.set(False)
                self.background_key_capture_consent_granted = False
            self.key_poller = create_key_poller()

        self.focus_key_fallback_enabled = isinstance(self.key_poller, EmptyKeyPoller)
        self.set_focused_key_capture(self.focus_key_fallback_enabled)
        self.input_status_text.set(self.key_poller.status_text)

    def linux_keyboard_device_path(self):
        if IS_WINDOWS:
            return ""
        config = self.load_config()
        value = config.get("keyboard_device") or config.get("linux_keyboard_device") or ""
        value = str(value).strip()
        if not value:
            return ""
        return value

    def ask_background_key_capture_consent(self):
        return messagebox.askyesno(
            "Background Key Capture",
            "Background key capture lets TypeCast count key presses while you use other apps.\n\n"
            "TypeCast only counts key presses for gameplay. It does not save typed characters, key names, or text input.\n\n"
            "Windows does not provide a separate permission prompt for this. You can turn this off again in Settings at any time.\n\n"
            "Enable background key capture?",
            parent=self.menu if self.menu is not None else self,
        )

    def prompt_background_key_capture_on_startup(self):
        if self.background_key_capture_enabled.get():
            return
        if not self.ask_background_key_capture_consent():
            self.configure_input_capture()
            return
        self.background_key_capture_consent_granted = True
        self.background_key_capture_enabled.set(True)
        self.configure_input_capture()
        self.save()

    def setup_discord_presence(self):
        if not self.discord_presence_enabled.get():
            self.discord_status_text.set("Discord Rich Presence: disabled")
            return False
        client_id = self.discord_client_id()
        if Presence is None:
            message = "Discord Rich Presence: pypresence is not installed"
            self.discord_status_text.set(message)
            return False
        if not client_id:
            self.ensure_config_file()
            message = "Discord Rich Presence: add client_id to typecast_config.json"
            self.discord_status_text.set(message)
            return False
        try:
            self.close_discord_presence()
            self.discord = Presence(client_id)
            self.discord.connect()
        except Exception as exc:
            self.discord = None
            self.discord_enabled = False
            message = f"Discord Rich Presence: waiting for Discord. Open the Discord desktop app, then use Reconnect Discord. Retrying automatically. ({type(exc).__name__})"
            self.discord_status_text.set(message)
            return False
        self.discord_enabled = True
        message = "Discord Rich Presence: connected"
        self.discord_status_text.set(message)
        return True

    def close_discord_presence(self):
        if self.discord:
            try:
                self.discord.close()
            except Exception:
                pass
        self.discord = None
        self.discord_enabled = False

    def reconnect_discord_presence(self):
        self.close_discord_presence()
        if not self.discord_presence_enabled.get():
            self.discord_presence_enabled.set(True)
        self.discord_status_text.set("Discord Rich Presence: reconnecting...")
        if not self.setup_discord_presence():
            return
        self.update_discord_presence_now()

    def discord_client_id(self):
        config = self.load_config()
        value = config.get("discord_client_id", "")
        client_id = str(value).strip()
        return client_id or EMBEDDED_DISCORD_CLIENT_ID

    def load_config(self):
        if not CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def ensure_config_file(self):
        if CONFIG_FILE.exists():
            return
        data = {
            "discord_client_id": "",
            "note": "Create a Discord app, copy its Application ID, and paste it as discord_client_id.",
            "keyboard_device": "",
            "keyboard_device_note": "Linux optional: run python find_keyboard_devices.py, then set this to /dev/input/eventX or a stable /dev/input/by-id path for background capture. The user needs permission to read that device, commonly via the input group.",
            "custom_theme": {
                "bg": "#eef6ff",
                "fg": "#18314f",
                "sub_fg": "#526d8e",
                "danger_fg": "#9b1c3d",
                "button_bg": "#d8eaff",
                "button_hover": "#f8fcff",
                "button_pressed": "#bfd9f5",
                "button_selected": "#c8e0fb",
                "button_border": "#8ca9c9",
                "button_light": "#ffffff",
                "button_dark": "#b3c8de",
                "root_border": "#afc2d6",
                "trough": "#d3e3f3",
                "content_bg": "#fbfdff",
                "content_fg": "#18314f",
                "content_select_bg": "#cbe3ff",
                "content_border": "#c1d3e6",
                "content_accent": "#5d91c8",
                "collection_caught_fg": "#247a4a",
                "collection_missing_fg": "#a33a4f",
                "collection_header_fg": "#526d8e"
            },
        }
        try:
            CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def update_discord_presence(self):
        if self.discord_presence_enabled.get() and not (self.discord_enabled and self.discord):
            self.setup_discord_presence()
        if self.discord_enabled and self.discord:
            self.update_discord_presence_now()
        self.after(DISCORD_UPDATE_MS, self.update_discord_presence)

    def update_discord_presence_now(self):
        if not (self.discord_enabled and self.discord):
            return
        fish_line = "Casting for fish"
        state_line = self.discord_fishing_spot_text()
        if self.hooked_fish:
            fish_line = "Opening a treasure chest" if self.hooked_fish.kind == "chest" else f"Reeling a {self.hooked_fish.name}"
        if self.player_is_inactive():
            fish_line = "Inactive - Gone fishin'"
            state_line = "zz... the fish are sleeping"
        try:
            self.discord.update(
                details=fish_line,
                state=state_line,
                start=self.started_at,
                large_image="typecast",
                large_text="TypeCast",
            )
            self.discord_status_text.set("Discord Rich Presence: connected")
        except Exception as exc:
            self.close_discord_presence()
            message = f"Discord Rich Presence: disconnected. Retrying automatically. ({type(exc).__name__})"
            self.discord_status_text.set(message)

    def discord_fishing_spot_text(self):
        spot = self.fishing_spot_by_id(self.selected_fishing_spot)
        return f"Casting at {spot['name']}"

    def schedule_refresh(self, delay_ms=35):
        if self.refresh_scheduled:
            return
        self.refresh_scheduled = True
        self.after(delay_ms, self.run_scheduled_refresh)

    def run_scheduled_refresh(self):
        self.refresh_scheduled = False
        self.refresh_all()

    def add_keystroke(self):
        self.mark_player_activity()
        self.change_keys(1)
        completed_catch = False
        if self.hooked_fish:
            if self.hooked_fish.kind == "chest":
                self.hooked_fish.progress += 1
                self.last_message = "Opening treasure chest..."
            elif self.hooked_fish.kind == "blessing":
                self.hooked_fish.progress += 1
                self.last_message = f"Securing {self.hooked_fish.name}'s blessing..."
            else:
                progress = 1
                if random.random() < self.accuracy_chance():
                    progress += 1
                    self.last_message = "Accurate keystroke! +2"
                self.hooked_fish.progress += progress * self.banked_progress_multiplier() * self.rod_blessing_progress_multiplier()
            if self.hooked_fish.progress >= self.hooked_fish.strokes:
                completed_catch = True
                if self.hooked_fish.kind == "chest":
                    self.open_treasure_chest()
                elif self.hooked_fish.kind == "blessing":
                    self.catch_blessing_visitor()
                else:
                    self.catch_fish()
        else:
            banked_key_gain = 1
            if random.random() < self.banked_key_bonus():
                banked_key_gain += 1
            self.change_banked_keys(banked_key_gain)
            self.last_message = "Earned a Cast Token while casting."

        blessing_uses_changed = self.consume_blessing_keystroke()
        self.rod_pull = 3.0
        if completed_catch and blessing_uses_changed:
            self.refresh_all()
        if not completed_catch:
            self.schedule_refresh(35 if self.minimized else 45)

    def open_treasure_chest(self):
        chest = self.hooked_fish
        if chest is None:
            return
        reward_type = random.choice(("coins", "Cast Tokens"))
        amount = random.randint(250, TREASURE_CHEST_MAX_REWARD)
        relic = self.roll_treasure_relic()
        potion = self.roll_treasure_potion()
        self.hooked_fish = None
        self.cast_started_at = time.time()
        if reward_type == "coins":
            self.change_coins(amount)
        else:
            self.change_banked_keys(amount)
        self.last_message = f"Opened a treasure chest: +{amount} {reward_type}!"
        discoveries = []
        if relic:
            self.add_relic(relic)
            discoveries.append(f"{relic['rarity']} relic: {relic['name']}")
        if potion:
            self.add_potion(potion)
            discoveries.append(f"{potion['rarity']} potion: {potion['name']}")
        if discoveries:
            self.last_message = f"Opened a treasure chest: +{amount} {reward_type} and found {'; '.join(discoveries)}."
        self.add_log_entry(self.last_message)

    def cut_treasure_chest_line(self):
        if self.hooked_fish is None or self.hooked_fish.kind != "chest":
            return
        self.hooked_fish = None
        self.cast_started_at = time.time()
        self.last_message = "Cut the line on the treasure chest."
        self.add_log_entry(self.last_message)
        self.refresh_all()
        self.refresh_all()

    def catch_blessing_visitor(self):
        visitor_fish = self.hooked_fish
        if visitor_fish is None:
            return
        self.hooked_fish = None
        self.cast_started_at = time.time()
        if self.stored_blessing_count() >= self.blessing_trophy_slots():
            self.last_message = f"No trophy slot open: {visitor_fish.name}'s blessing slipped away."
            self.add_log_entry(self.last_message)
            self.refresh_all()
            return
        self.inventory.append(asdict(visitor_fish))
        self.last_message = f"Stored {visitor_fish.name}'s blessing. Sell it when you want to activate it."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def activate_blessing_fish(self, visitor_fish):
        visitor = BLESSING_VISITOR_BY_ID.get(visitor_fish.blessing_id, {})
        slot = visitor_fish.blessing_slot or visitor.get("slot", "")
        try:
            bonus = float(visitor_fish.blessing_bonus)
        except (TypeError, ValueError):
            bonus = 0.0
        if slot == "body":
            bonus = int(round(bonus))
        uses = self.blessing_use_count(visitor_fish.strokes, slot)
        current = self.active_blessings.get(slot)
        if current:
            try:
                current_bonus = float(current.get("bonus", 0))
            except (TypeError, ValueError):
                current_bonus = 0
            bonus = max(current_bonus, bonus)
            if slot == "body":
                uses += safe_int(current.get("remaining_catches", 0), 0)
                uses = min(BLESSING_LUCK_CATCH_CAP, uses)
            else:
                uses += safe_int(current.get("remaining_uses", 0), 0)
                uses = min(BLESSING_KEYSTROKE_USE_CAP, uses)
        remaining_key = "remaining_catches" if slot == "body" else "remaining_uses"
        self.active_blessings[slot] = {
            "visitor_id": visitor_fish.blessing_id,
            "name": visitor_fish.name,
            "slot": slot,
            "bonus": bonus,
            "strokes": visitor_fish.strokes,
            remaining_key: uses,
        }
        use_label = f"{uses} catches" if slot == "body" else f"{uses} keystrokes"
        self.last_message = f"Blessing active: {visitor_fish.name} grants {self.blessing_effect_text(slot, bonus)} for the next {use_label}."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def activate_stored_blessing(self, fish):
        try:
            blessing_bonus = float(fish.get("blessing_bonus", 0.0))
        except (TypeError, ValueError):
            blessing_bonus = 0.0
        visitor_fish = HookedFish(
            name=str(fish.get("name", "Visitor")),
            rarity=str(fish.get("rarity", "Blessing")),
            strokes=max(1, safe_int(fish.get("strokes", 1), 1)),
            value=safe_int(fish.get("value", 0), 0),
            color=str(fish.get("color", "#7fb383")),
            kind="blessing",
            progress=safe_int(fish.get("progress", 0), 0),
            spot_id=str(fish.get("spot_id", "")),
            blessing_id=str(fish.get("blessing_id", "")),
            blessing_slot=str(fish.get("blessing_slot", "")),
            blessing_bonus=blessing_bonus,
        )
        self.activate_blessing_fish(visitor_fish)

    def roll_treasure_relic(self):
        if random.random() >= RELIC_DROP_CHANCE:
            return None
        weights = [relic["weight"] for relic in RELICS]
        return random.choices(RELICS, weights=weights, k=1)[0]

    def roll_treasure_potion(self):
        if random.random() >= POTION_DROP_CHANCE:
            return None
        weights = [potion["weight"] for potion in POTIONS]
        return random.choices(POTIONS, weights=weights, k=1)[0]

    def add_relic(self, relic):
        relic_id = relic["id"]
        self.relics[relic_id] = safe_int(self.relics.get(relic_id, 0)) + 1
        self.add_log_entry(f"Relic acquired: {relic['rarity']} {relic['name']}.")

    def add_potion(self, potion):
        potion_id = potion["id"]
        self.stored_potions[potion_id] = safe_int(self.stored_potions.get(potion_id, 0)) + 1
        self.add_log_entry(f"Potion acquired: {potion['rarity']} {potion['name']}.")

    def activate_potion(self, potion):
        expires_at = time.time() + POTION_DURATION_SECONDS
        self.potions.append({"id": potion["id"], "expires_at": expires_at})
        self.add_log_entry(f"Potion active: {potion['rarity']} {potion['name']} for 15 minutes.")

    def owned_potions_in_display_order(self):
        return [potion for potion in POTIONS if safe_int(self.stored_potions.get(potion["id"], 0)) > 0]

    def selected_potion(self):
        if not self.potion_list or not self.potion_list.winfo_exists():
            return None
        selection = self.potion_list.curselection()
        if not selection:
            messagebox.showinfo("Potions", "Select a potion first.", parent=self.menu)
            return None
        owned_potions = self.owned_potions_in_display_order()
        index = selection[0]
        if index >= len(owned_potions):
            messagebox.showinfo("Potions", "Select a stored potion to use.", parent=self.menu)
            return None
        return owned_potions[index]

    def use_selected_potion(self):
        potion = self.selected_potion()
        if not potion:
            return
        potion_id = potion["id"]
        count = safe_int(self.stored_potions.get(potion_id, 0))
        if count <= 0:
            self.last_message = f"No {potion['name']} potions available."
            self.refresh_all()
            return
        if count == 1:
            self.stored_potions.pop(potion_id, None)
        else:
            self.stored_potions[potion_id] = count - 1
        self.activate_potion(potion)
        self.last_message = f"Used {potion['name']}. {self.potion_effect_text(potion)} for 15 minutes."
        self.refresh_all()

    def relic_by_id(self, relic_id):
        for relic in RELICS:
            if relic["id"] == relic_id:
                return relic
        return None

    def potion_by_id(self, potion_id):
        for potion in POTIONS:
            if potion["id"] == potion_id:
                return potion
        return None

    def relic_key_rate(self):
        total = 0
        for relic_id, count in self.relics.items():
            relic = self.relic_by_id(relic_id)
            if relic:
                total += safe_int(relic.get("keys", 0)) * safe_int(count)
        return total

    def relic_coin_rate(self):
        total = 0
        for relic_id, count in self.relics.items():
            relic = self.relic_by_id(relic_id)
            if relic:
                total += safe_int(relic.get("coins", 0)) * safe_int(count)
        return total

    def cleanup_active_potions(self):
        now = time.time()
        before = len(self.potions)
        active_potions = []
        for potion in self.potions:
            try:
                expires_at = float(potion.get("expires_at", 0))
            except (AttributeError, TypeError, ValueError):
                continue
            if expires_at > now and self.potion_by_id(potion.get("id")):
                active_potions.append({"id": potion.get("id"), "expires_at": expires_at})
        self.potions = active_potions
        return len(self.potions) != before

    def potion_key_rate(self):
        self.cleanup_active_potions()
        total = 0
        for active_potion in self.potions:
            potion = self.potion_by_id(active_potion.get("id"))
            if potion:
                total += safe_int(potion.get("keys", 0))
        return total

    def potion_coin_rate(self):
        self.cleanup_active_potions()
        total = 0
        for active_potion in self.potions:
            potion = self.potion_by_id(active_potion.get("id"))
            if potion:
                total += safe_int(potion.get("coins", 0))
        return total

    def process_relic_payouts(self):
        elapsed = time.time() - self.last_relic_payout_at
        intervals = int(elapsed // RELIC_INTERVAL_SECONDS)
        if intervals <= 0:
            return
        self.last_relic_payout_at += intervals * RELIC_INTERVAL_SECONDS
        relic_key_rate = self.relic_key_rate()
        relic_coin_rate = self.relic_coin_rate()
        potion_key_rate = self.potion_key_rate()
        potion_coin_rate = self.potion_coin_rate()
        key_rate = relic_key_rate + potion_key_rate
        coin_rate = relic_coin_rate + potion_coin_rate
        if key_rate <= 0 and coin_rate <= 0:
            return
        gained_keys = key_rate * intervals
        gained_coins = coin_rate * intervals
        self.change_banked_keys(gained_keys)
        self.change_coins(gained_coins)
        gains = []
        if gained_keys:
            gains.append(f"{gained_keys} Cast Tokens")
        if gained_coins:
            gains.append(f"{gained_coins} coins")
        if (relic_key_rate or relic_coin_rate) and (potion_key_rate or potion_coin_rate):
            source = "Relics and potions"
        elif potion_key_rate or potion_coin_rate:
            source = "Potions"
        else:
            source = "Relics"
        self.last_message = f"{source} generated {' and '.join(gains)}."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def process_offline_relic_payouts(self, saved_relic_payout_at, offline_until):
        elapsed = max(0.0, offline_until - saved_relic_payout_at)
        intervals = int(elapsed // RELIC_INTERVAL_SECONDS)
        self.last_relic_payout_at = time.time()
        if intervals <= 0:
            return

        key_rate = self.relic_key_rate()
        coin_rate = self.relic_coin_rate()
        if key_rate <= 0 and coin_rate <= 0:
            return

        gained_keys = int(key_rate * intervals * OFFLINE_RELIC_PAYOUT_RATE)
        gained_coins = int(coin_rate * intervals * OFFLINE_RELIC_PAYOUT_RATE)
        self.change_banked_keys(gained_keys)
        self.change_coins(gained_coins)
        gains = []
        if gained_keys:
            gains.append(f"{gained_keys} Cast Tokens")
        if gained_coins:
            gains.append(f"{gained_coins} coins")
        if gains:
            self.last_message = f"Offline relics generated {' and '.join(gains)}."
            self.add_log_entry(self.last_message)
            self.refresh_all()

    def catch_fish(self):
        fish = self.hooked_fish
        if fish is None:
            return
        self.consume_blessing_catch("body")
        self.hooked_fish = None
        self.cast_started_at = time.time()
        self.fish_since_last_treasure_chest += 1
        if self.regular_inventory_count() >= self.inventory_limit:
            earned = self.overflow_autosell_value(fish.value)
            self.change_coins(earned)
            self.record_collection_fish(fish.rarity, fish.name, fish.value)
            self.record_happy_fish(fish)
            self.last_message = f"Inventory full: overflow-sold {hooked_fish_display_name(fish)} for {earned} coins."
            self.add_log_entry(self.last_message)
            self.refresh_all()
            return
        self.inventory.append(asdict(fish))
        self.record_collection_fish(fish.rarity, fish.name, fish.value)
        self.record_happy_fish(fish)
        self.last_message = f"Caught a {hooked_fish_display_name(fish)}!"
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def blessing_use_count(self, strokes, slot):
        strokes = max(1, safe_int(strokes, 1))
        if slot == "body":
            return max(1, min(BLESSING_LUCK_CATCH_CAP, round(strokes / BLESSING_LUCK_CATCH_DIVISOR)))
        return max(1, min(BLESSING_KEYSTROKE_USE_CAP, round(strokes * BLESSING_KEYSTROKE_USE_MULTIPLIER)))

    def overflow_autosell_value(self, value):
        return max(1, int(value * OVERFLOW_AUTOSELL_RATE))

    def record_collection_fish(self, rarity, name, value=0):
        key = fish_collection_key(rarity, name)
        entry = self.collection_log.get(key)
        if not isinstance(entry, dict):
            entry = {"count": 0, "best_value": 0}
        entry["count"] = safe_int(entry.get("count", 0)) + 1
        entry["best_value"] = max(safe_int(entry.get("best_value", 0)), safe_int(value, 0))
        self.collection_log[key] = entry

    def record_happy_fish(self, fish):
        skin_id = getattr(fish, "skin_id", "")
        if not skin_id or skin_id not in PRIDE_FISH_BY_ID:
            return
        key = happy_fish_collection_key(skin_id)
        entry = self.collection_log.get(key)
        if not isinstance(entry, dict):
            entry = {"count": 0, "best_value": 0}
        entry["count"] = safe_int(entry.get("count", 0)) + 1
        entry["best_value"] = max(safe_int(entry.get("best_value", 0)), safe_int(getattr(fish, "value", 0), 0))
        self.collection_log[key] = entry

    def normalize_collection_log(self, data):
        collection = {}
        saved_collection = data.get("collection_log", {})
        if isinstance(saved_collection, dict):
            for key, entry in saved_collection.items():
                if not isinstance(key, str) or "|" not in key:
                    continue
                if isinstance(entry, dict):
                    count = safe_int(entry.get("count", 0))
                    best_value = safe_int(entry.get("best_value", 0))
                else:
                    count = safe_int(entry)
                    best_value = 0
                if count > 0:
                    collection[key] = {"count": count, "best_value": best_value}

        for fish in data.get("inventory", []):
            if not isinstance(fish, dict):
                continue
            rarity = fish.get("rarity")
            name = fish.get("name")
            if rarity and name:
                key = fish_collection_key(str(rarity), str(name))
                entry = collection.setdefault(key, {"count": 0, "best_value": 0})
                entry["count"] = max(1, safe_int(entry.get("count", 0)))
                entry["best_value"] = max(safe_int(entry.get("best_value", 0)), safe_int(fish.get("value", 0)))
            skin_id = str(fish.get("skin_id", "")).strip()
            if skin_id in PRIDE_FISH_BY_ID:
                key = happy_fish_collection_key(skin_id)
                entry = collection.setdefault(key, {"count": 0, "best_value": 0})
                entry["count"] = max(1, safe_int(entry.get("count", 0)))
                entry["best_value"] = max(safe_int(entry.get("best_value", 0)), safe_int(fish.get("value", 0)))
        return collection

    def sell_selected(self):
        index = self.selected_inventory_index()
        if index is None:
            return
        fish = self.inventory.pop(index)
        if fish_is_blessing(fish):
            self.activate_stored_blessing(fish)
            return
        self.change_coins(fish["value"])
        self.last_message = f"Sold {fish['name']} for {fish['value']} coins."
        self.refresh_all()

    def sell_all(self):
        if not self.inventory:
            return
        sold = [fish for fish in self.inventory if not fish_is_blessing(fish)]
        if not sold:
            self.last_message = "No regular fish to sell. Stored blessings are activated with Sell Selected."
            self.refresh_all()
            return
        earned = sum(fish["value"] for fish in sold)
        self.inventory = [fish for fish in self.inventory if fish_is_blessing(fish)]
        self.change_coins(earned)
        held = self.stored_blessing_count()
        if held:
            self.last_message = f"Sold the catch for {earned} coins. Stored blessings were kept."
        else:
            self.last_message = f"Sold the catch for {earned} coins."
        self.refresh_all()

    def selected_inventory_index(self):
        if not self.menu or not self.menu.winfo_exists():
            return None
        selection = self.inventory_list.curselection()
        if not selection:
            messagebox.showinfo("Inventory", "Select a fish first.", parent=self.menu)
            return None
        return selection[0]

    def shop_cost_multiplier(self):
        if self.banked_upgrade_level <= 0:
            return 1.0
        upgrade = BANKED_KEY_UPGRADES[self.banked_upgrade_level - 1]
        discount = max(0.0, min(0.50, float(upgrade.get("discount", 0.0))))
        return 1.0 - discount

    def shop_price(self, price):
        return max(1, int(round(price * self.shop_cost_multiplier())))

    def debug_shop_bypass_enabled(self):
        return bool(self.debug_shop_prices_bypassed.get())

    def on_debug_shop_prices_toggle(self):
        self.last_message = "Debug: shop prices bypassed." if self.debug_shop_bypass_enabled() else "Debug: shop prices restored."
        self.refresh_all()
        self.save()

    def should_pay_shop_cost(self):
        return not self.debug_shop_bypass_enabled()

    def buy_equipment_upgrade(self):
        index = self.shop_list.curselection()
        if not index:
            return
        upgrades = self.available_equipment_upgrades()
        if index[0] >= len(upgrades):
            return
        slot, item = upgrades[index[0]]
        price = self.shop_price(item["price"])
        if self.should_pay_shop_cost() and self.coins < price:
            self.last_message = "Not enough coins."
            self.refresh_all()
            return
        if self.should_pay_shop_cost():
            self.change_coins(-price)
        self.equipment_levels[slot] += 1
        self.last_message = f"Upgraded {slot.title()} to {item['name']} for {price} coins."
        if self.debug_shop_bypass_enabled():
            self.last_message += " (debug bypass)"
        self.refresh_all()

    def buy_backpack_upgrade(self):
        upgrade = self.next_backpack_upgrade()
        if not upgrade:
            self.last_message = "Backpack is already maxed."
            self.refresh_all()
            return
        price = self.shop_price(upgrade["price"])
        if self.should_pay_shop_cost() and self.coins < price:
            self.last_message = "Not enough coins."
            self.refresh_all()
            return
        if self.should_pay_shop_cost():
            self.change_coins(-price)
        self.backpack_level = upgrade["level"]
        self.inventory_limit = self.current_inventory_limit()
        self.last_message = f"Backpack upgraded to {upgrade['slots']} slots for {price} coins."
        if self.debug_shop_bypass_enabled():
            self.last_message += " (debug bypass)"
        self.refresh_all()

    def next_banked_upgrade(self):
        if self.banked_upgrade_level >= len(BANKED_KEY_UPGRADES):
            return None
        return BANKED_KEY_UPGRADES[self.banked_upgrade_level]

    def banked_progress_multiplier(self):
        if self.banked_upgrade_level <= 0:
            return 1.0
        return BANKED_KEY_UPGRADES[self.banked_upgrade_level - 1]["mult"]

    def buy_banked_upgrade(self):
        upgrade = self.next_banked_upgrade()
        if not upgrade:
            self.last_message = "Cast Token upgrades are already maxed."
            self.refresh_all()
            return
        if self.should_pay_shop_cost() and self.banked_keys < upgrade["cost"]:
            self.last_message = f"Need {upgrade['cost']} Cast Tokens for {upgrade['name']}."
            self.refresh_all()
            return
        if self.should_pay_shop_cost():
            self.change_banked_keys(-upgrade["cost"])
        self.banked_upgrade_level += 1
        self.last_message = f"Purchased {upgrade['name']} (+{int((upgrade['mult'] - 1) * 100)}% progress)."
        if self.debug_shop_bypass_enabled():
            self.last_message += " (debug bypass)"
        self.refresh_all()

    def next_autosell_upgrade(self):
        if self.autosell_level >= len(AUTOSALE_UPGRADES):
            return None
        return AUTOSALE_UPGRADES[self.autosell_level]

    def buy_autosell_upgrade(self):
        upgrade = self.next_autosell_upgrade()
        if not upgrade:
            self.last_message = "Auto sell module is already maxed."
            self.refresh_all()
            return
        price = self.shop_price(upgrade["price"])
        if self.should_pay_shop_cost() and self.coins < price:
            self.last_message = "Not enough coins."
            self.refresh_all()
            return
        if self.should_pay_shop_cost():
            self.change_coins(-price)
        self.autosell_level += 1
        self.last_autosell_at = time.time()
        self.last_message = f"Purchased {upgrade['name']} ({upgrade['percent']}% auto-sell)."
        if self.debug_shop_bypass_enabled():
            self.last_message += " (debug bypass)"
        self.refresh_all()

    def selected_fishing_spot_index(self):
        if not self.menu or not self.menu.winfo_exists():
            return None
        selection = self.fishing_spot_list.curselection()
        if not selection:
            messagebox.showinfo("Fishing Spots", "Select a fishing spot first.", parent=self.menu)
            return None
        return selection[0]

    def selected_fishing_spot_from_list(self):
        index = self.selected_fishing_spot_index()
        if index is None or index >= len(FISHING_SPOTS):
            return None
        return FISHING_SPOTS[index]

    def fishing_spot_cost_text(self, spot):
        cost_type = spot["cost_type"]
        if cost_type == "free":
            return "Free"
        if cost_type == "coins":
            return f"{spot['cost']} coins"
        if cost_type == "banked_keys":
            return f"{spot['cost']} Cast Tokens"
        if cost_type == "collection":
            return f"{spot['cost']} collection entries"
        if cost_type == "achievements":
            return "all non-collection achievements"
        return ""

    def can_afford_fishing_spot(self, spot):
        cost_type = spot["cost_type"]
        if cost_type == "free":
            return True
        if cost_type == "coins":
            if self.debug_shop_bypass_enabled():
                return True
            return self.coins >= spot["cost"]
        if cost_type == "banked_keys":
            if self.debug_shop_bypass_enabled():
                return True
            return self.banked_keys >= spot["cost"]
        if cost_type == "collection":
            return self.collection_discovered_count() >= spot["cost"]
        if cost_type == "achievements":
            required_ids = self.fishing_spot_achievement_cost_ids()
            return all(achievement_id in self.achievements_unlocked for achievement_id in required_ids)
        return False

    def fishing_spot_achievement_cost_ids(self):
        return [
            achievement["id"]
            for achievement in ACHIEVEMENTS
            if not achievement["id"].startswith("collection_") and achievement["id"] != "spots_all"
        ]

    def pay_fishing_spot_cost(self, spot):
        if not self.should_pay_shop_cost():
            return
        if spot["cost_type"] == "coins":
            self.change_coins(-spot["cost"])
        elif spot["cost_type"] == "banked_keys":
            self.change_banked_keys(-spot["cost"])

    def buy_selected_fishing_spot(self):
        spot = self.selected_fishing_spot_from_list()
        if not spot:
            return
        if spot["id"] in self.unlocked_fishing_spots:
            self.last_message = f"{spot['name']} is already unlocked."
            self.refresh_all()
            return
        if not self.can_afford_fishing_spot(spot):
            self.last_message = f"Need {self.fishing_spot_cost_text(spot)} for {spot['name']}."
            self.refresh_all()
            return
        self.pay_fishing_spot_cost(spot)
        self.unlocked_fishing_spots.add(spot["id"])
        self.selected_fishing_spot = spot["id"]
        self.last_message = f"Unlocked {spot['name']}."
        if self.debug_shop_bypass_enabled():
            self.last_message += " (debug bypass)"
        self.refresh_all()

    def select_fishing_spot(self):
        spot = self.selected_fishing_spot_from_list()
        if not spot:
            return
        if spot["id"] not in self.unlocked_fishing_spots:
            self.last_message = f"Unlock {spot['name']} first."
            self.refresh_all()
            return
        self.selected_fishing_spot = spot["id"]
        self.last_message = f"Now fishing at {spot['name']}."
        self.refresh_all()
        self.draw_overlay()

    def perform_autosell(self):
        upgrade = AUTOSALE_UPGRADES[self.autosell_level - 1]
        percent = upgrade["percent"]
        regular_fish = [fish for fish in self.inventory if not fish_is_blessing(fish)]
        count = max(1, round(len(regular_fish) * percent / 100))
        sold = regular_fish[:count]
        if not sold:
            self.last_autosell_at = time.time()
            return
        earned = sum(fish["value"] for fish in sold)
        sold_ids = {id(fish) for fish in sold}
        self.inventory = [fish for fish in self.inventory if id(fish) not in sold_ids]
        self.change_coins(earned)
        self.last_autosell_at = time.time()
        self.last_message = f"Auto-sold {len(sold)} fish for {earned} coins."
        self.refresh_all()

    def relic_payout_type(self, relic):
        if safe_int(relic.get("keys", 0)) > 0:
            return "keys"
        if safe_int(relic.get("coins", 0)) > 0:
            return "coins"
        return ""

    def owned_relics_in_display_order(self):
        return [relic for relic in RELICS if safe_int(self.relics.get(relic["id"], 0)) > 0]

    def next_relic_in_series(self, relic):
        payout_type = self.relic_payout_type(relic)
        if not payout_type:
            return None
        series = [candidate for candidate in RELICS if self.relic_payout_type(candidate) == payout_type]
        for index, candidate in enumerate(series):
            if candidate["id"] == relic["id"]:
                if index + 1 < len(series):
                    return series[index + 1]
                return None
        return None

    def selected_relic(self):
        if not self.relic_list or not self.relic_list.winfo_exists():
            return None
        selection = self.relic_list.curselection()
        if not selection:
            messagebox.showinfo("Relics", "Select a relic first.", parent=self.menu)
            return None
        owned_relics = self.owned_relics_in_display_order()
        index = selection[0]
        if index >= len(owned_relics):
            return None
        return owned_relics[index]

    def trade_up_selected_relic(self):
        relic = self.selected_relic()
        if not relic:
            return
        count = safe_int(self.relics.get(relic["id"], 0))
        if count < 3:
            self.last_message = f"Need 3 {relic['name']} relics to trade up."
            self.refresh_all()
            return
        next_relic = self.next_relic_in_series(relic)
        if not next_relic:
            self.last_message = f"{relic['name']} is already at the top of its relic series."
            self.refresh_all()
            return
        remaining = count - 3
        if remaining > 0:
            self.relics[relic["id"]] = remaining
        else:
            self.relics.pop(relic["id"], None)
        self.add_relic(next_relic)
        self.last_message = f"Traded 3 {relic['name']} for 1 {next_relic['name']}."
        self.add_log_entry(self.last_message)
        self.refresh_all()

    def format_progress_value(self, value):
        return str(int(value)) if float(value).is_integer() else f"{value:.1f}"

    def format_play_time(self, seconds):
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def format_countdown(self, seconds):
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def scale_label_for_value(self, value):
        closest = min(SCALE_VALUES.items(), key=lambda item: abs(item[1] - value))
        return closest[0]

    def scaled_menu_value(self, value):
        return max(1, int(round(value * self.menu_scale)))

    def available_monitors(self):
        if sys.platform.startswith("win"):
            class Rect(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class MonitorInfo(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", Rect),
                    ("rcWork", Rect),
                    ("dwFlags", ctypes.c_ulong),
                ]

            monitors = []
            monitor_enum_proc = ctypes.WINFUNCTYPE(
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(Rect),
                ctypes.c_long,
            )

            def callback(monitor_handle, _device_context, _rect, _data):
                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if ctypes.windll.user32.GetMonitorInfoW(monitor_handle, ctypes.byref(info)):
                    index = len(monitors) + 1
                    primary = bool(info.dwFlags & 1)
                    label = f"Monitor {index}"
                    if primary:
                        label = f"{label} (Primary)"
                    monitors.append(
                        {
                            "label": label,
                            "bounds": (info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom),
                            "work": (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom),
                            "primary": primary,
                        }
                    )
                return 1

            try:
                ctypes.windll.user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(callback), 0)
                if monitors:
                    return monitors
            except (AttributeError, OSError):
                pass

        return [
            {
                "label": "Monitor 1",
                "bounds": (0, 0, self.winfo_screenwidth(), self.winfo_screenheight()),
                "work": (0, 0, self.winfo_screenwidth(), self.winfo_screenheight()),
                "primary": True,
            }
        ]

    def monitor_label_for_index(self, index):
        if not self.monitor_options:
            return "Monitor 1"
        index = max(0, min(index, len(self.monitor_options) - 1))
        return self.monitor_options[index]["label"]

    def selected_monitor_bounds(self):
        if not self.monitor_options:
            self.monitor_options = self.available_monitors()
        if self.selected_monitor_index >= len(self.monitor_options):
            self.selected_monitor_index = 0
        return self.monitor_options[self.selected_monitor_index]["work"]

    def refresh_monitor_options(self):
        self.monitor_options = self.available_monitors()
        if self.selected_monitor_index >= len(self.monitor_options):
            self.selected_monitor_index = 0
        self.monitor_var.set(self.monitor_label_for_index(self.selected_monitor_index))

    def work_area_bounds(self):
        selected_bounds = self.selected_monitor_bounds()
        if selected_bounds:
            return selected_bounds
        if sys.platform.startswith("win"):
            class Rect(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = Rect()
            try:
                if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                    return rect.left, rect.top, rect.right, rect.bottom
            except (AttributeError, OSError):
                pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def clamp_overlay_position(self, x, y, width=None, height=None):
        if width is None or height is None:
            width, height = self.overlay_size()
        work_left, work_top, work_right, work_bottom = self.work_area_bounds()
        max_x = max(work_left, work_right - width)
        max_y = max(work_top, work_bottom - height)
        return max(work_left, min(x, max_x)), max(work_top, min(y, max_y))

    def overlay_size(self):
        width, height = self.base_overlay_size()
        return int(round(width * self.game_scale)), int(round(height * self.game_scale))

    def compact_vertical_enabled(self):
        return self.minimized and bool(self.compact_vertical_var.get())

    def base_overlay_size(self):
        if self.compact_vertical_enabled():
            return MINIMIZED_VERTICAL_OVERLAY_WIDTH, MINIMIZED_VERTICAL_OVERLAY_HEIGHT
        if self.minimized:
            return BASE_OVERLAY_WIDTH, MINIMIZED_OVERLAY_HEIGHT
        return BASE_OVERLAY_WIDTH, FULL_OVERLAY_HEIGHT

    def overlay_font(self, size, weight="normal"):
        scaled_size = max(1, int(round(size * self.game_scale)))
        if weight == "normal":
            return ("Segoe UI", scaled_size)
        return ("Segoe UI", scaled_size, weight)

    def scale_overlay_items(self):
        if self.game_scale != 1.0:
            self.overlay.scale("all", 0, 0, self.game_scale, self.game_scale)

    def click_hits_fish(self, event):
        if self.minimized or not self.hooked_fish:
            return False
        x = event.x / self.game_scale
        y = event.y / self.game_scale
        return 58 <= x <= 182 and 74 <= y <= 139

    def click_hits_cat(self, event):
        if self.minimized:
            return False
        x = event.x / self.game_scale
        y = event.y / self.game_scale
        return 232 <= x <= 306 and 54 <= y <= 150

    def spawn_fish_bubbles(self, event):
        if self.hooked_fish and self.hooked_fish.kind == "chest":
            return
        x = event.x / self.game_scale
        y = event.y / self.game_scale
        now = time.time()
        for index in range(6):
            self.fish_bubbles.append(
                FishBubble(
                    x=x + random.uniform(-10, 12),
                    y=y + random.uniform(-6, 8),
                    size=random.uniform(3.0, 6.5),
                    rise=random.uniform(18, 34),
                    drift=random.uniform(-8, 8),
                    delay=index * 0.045,
                    born=now,
                    life=random.uniform(0.62, 0.86),
                )
            )

    def draw_fish_bubbles(self, canvas, outline_color, highlight_color):
        now = time.time()
        active_bubbles: List[FishBubble] = []
        for bubble in self.fish_bubbles:
            age = now - bubble.born - bubble.delay
            if age < bubble.life:
                active_bubbles.append(bubble)
            if age < 0 or age >= bubble.life:
                continue
            progress = age / bubble.life
            size = bubble.size * (0.75 + progress * 0.55)
            x = bubble.x + bubble.drift * progress
            y = bubble.y - bubble.rise * progress
            canvas.create_oval(x - size, y - size, x + size, y + size, outline=outline_color, width=2)
            glint = max(1.2, size * 0.28)
            canvas.create_oval(x - size * 0.35, y - size * 0.45, x - size * 0.35 + glint, y - size * 0.45 + glint, fill=highlight_color, outline="")
        self.fish_bubbles = active_bubbles

    def draw_fish_sparkles(self, canvas, fish, fish_x, pond_highlight):
        if fish.kind != "fish" or fish.rarity not in SPARKLE_FISH_RARITIES:
            return

        sparkle_color = SPARKLE_RARITY_COLORS.get(fish.rarity, pond_highlight)
        soft_color = self.blend_hex_color(sparkle_color, pond_highlight, 0.42)
        phase = (time.time() * 0.75) % 1.0
        sparkle_points = (
            (65 + fish_x, 97, 0.02),
            (92 + fish_x, 84, 0.25),
            (135 + fish_x, 88, 0.48),
            (171 + fish_x, 107, 0.68),
            (164 + fish_x, 143, 0.86),
            (108 + fish_x, 151, 0.39),
            (57 + fish_x, 132, 0.61),
        )
        for x, y, offset in sparkle_points:
            twinkle = 1 - abs((((phase + offset) % 1.0) * 2) - 1)
            if twinkle < 0.18:
                continue
            size = 2.0 + twinkle * 3.4
            bob = (twinkle - 0.5) * 2.0
            line_color = sparkle_color if twinkle > 0.56 else soft_color
            width = 2 if twinkle > 0.78 else 1
            canvas.create_line(x - size, y + bob, x + size, y + bob, fill=line_color, width=width)
            canvas.create_line(x, y - size + bob, x, y + size + bob, fill=line_color, width=width)
            if twinkle > 0.72:
                small = size * 0.55
                canvas.create_line(x - small, y - small + bob, x + small, y + small + bob, fill=soft_color, width=1)
                canvas.create_line(x - small, y + small + bob, x + small, y - small + bob, fill=soft_color, width=1)

    def pride_fish_part_colors(self, fish, default_body, default_fin):
        colors = getattr(fish, "skin_colors", [])
        if not colors:
            return {
                "body": default_body,
                "tail": default_body,
                "top_fin": default_fin,
                "bottom_fin": default_fin,
            }
        skin = PRIDE_FISH_BY_ID.get(getattr(fish, "skin_id", ""))
        if skin and skin.get("body_colors"):
            body_colors = [color for color in skin.get("body_colors", []) if self.valid_hex_color(color)]
            tail_colors = [color for color in skin.get("tail_colors", body_colors) if self.valid_hex_color(color)]
            return {
                "body": body_colors[len(body_colors) // 2] if body_colors else default_body,
                "tail": tail_colors[0] if tail_colors else default_body,
                "top_fin": skin.get("top_fin", body_colors[1] if len(body_colors) > 1 else default_fin),
                "bottom_fin": skin.get("bottom_fin", body_colors[-2] if len(body_colors) > 2 else default_fin),
                "body_gradient": body_colors,
                "tail_gradient": tail_colors,
            }
        return {
            "body": colors[len(colors) // 2],
            "tail": colors[0],
            "top_fin": colors[1] if len(colors) > 1 else colors[0],
            "bottom_fin": colors[-2] if len(colors) > 2 else colors[-1],
        }

    def gradient_palette_color(self, colors, position):
        colors = [color for color in colors if self.valid_hex_color(color)]
        if not colors:
            return "#62bfb8"
        if len(colors) == 1:
            return colors[0]
        position = max(0.0, min(1.0, position))
        scaled = position * (len(colors) - 1)
        index = min(len(colors) - 2, int(scaled))
        return self.mix_hex_colors(colors[index], colors[index + 1], scaled - index)

    def draw_gradient_fish_body(self, canvas, fish_x, outline_color, colors):
        center_x = 120 + fish_x
        center_y = 118
        radius_x = 42
        radius_y = 19
        slices = 14
        for index in range(slices):
            x0 = center_x - radius_x + index * (radius_x * 2 / slices)
            x1 = center_x - radius_x + (index + 1) * (radius_x * 2 / slices)
            mid_x = (x0 + x1) / 2
            normalized = max(-1.0, min(1.0, (mid_x - center_x) / radius_x))
            half_height = radius_y * ((1 - normalized * normalized) ** 0.5)
            color = self.gradient_palette_color(colors, index / max(1, slices - 1))
            canvas.create_rectangle(x0, center_y - half_height, x1 + 0.8, center_y + half_height, fill=color, outline="")
        canvas.create_oval(center_x - radius_x, center_y - radius_y, center_x + radius_x, center_y + radius_y, outline=outline_color, width=2)

    def draw_gradient_fish_tail(self, canvas, fish_x, outline_color, colors):
        points = (86 + fish_x, 118, 50 + fish_x, 96, 56 + fish_x, 119, 50 + fish_x, 141)
        canvas.create_polygon(*points, fill=self.gradient_palette_color(colors, 0.15), outline=outline_color)
        canvas.create_polygon(83 + fish_x, 118, 53 + fish_x, 104, 56 + fish_x, 119, fill=self.gradient_palette_color(colors, 0.5), outline="")
        canvas.create_polygon(83 + fish_x, 118, 56 + fish_x, 119, 53 + fish_x, 133, fill=self.gradient_palette_color(colors, 0.88), outline="")
        canvas.create_polygon(*points, fill="", outline=outline_color)

    def mark_player_activity(self):
        self.last_player_activity_at = time.time()

    def player_is_inactive(self):
        return time.time() - self.last_player_activity_at >= IDLE_ZZ_SECONDS

    def draw_idle_zz(self, canvas, text_color):
        if self.minimized or not self.hooked_fish or not self.player_is_inactive():
            return
        phase = (time.time() * 0.55) % 1.0
        x = 152 + phase * 8
        y = 91 - phase * 10
        canvas.create_text(x, y, text="zz", anchor="center", fill=text_color, font=self.overlay_font(8, "bold"))

    def autosell_seconds_remaining(self):
        if self.autosell_level <= 0:
            return None
        elapsed = time.time() - self.last_autosell_at
        return max(0, AUTOSELL_SECONDS - elapsed)

    def autosell_countdown_text_value(self):
        remaining = self.autosell_seconds_remaining()
        if remaining is None:
            return ""
        return f"Auto {self.format_countdown(remaining)}"

    def apply_theme(self, style):
        palette = self.theme_palette()
        bg = palette["bg"]
        fg = palette["fg"]
        sub_fg = palette["sub_fg"]
        danger_fg = palette["danger_fg"]
        button_bg = palette["button_bg"]
        button_hover = palette["button_hover"]
        button_pressed = palette["button_pressed"]
        button_selected = palette["button_selected"]
        button_border = palette["button_border"]
        button_light = palette["button_light"]
        button_dark = palette["button_dark"]
        root_border = palette["root_border"]
        trough = palette["trough"]
        self.content_bg = palette["content_bg"]
        self.content_fg = palette["content_fg"]
        self.content_select_bg = palette["content_select_bg"]
        self.content_border = palette["content_border"]
        self.content_accent = palette["content_accent"]
        self.collection_caught_fg = palette["collection_caught_fg"]
        self.collection_missing_fg = palette["collection_missing_fg"]
        self.collection_header_fg = palette["collection_header_fg"]

        style.theme_use("clam")
        style.configure("TFrame", background=bg, bordercolor=root_border)
        style.configure("Content.TFrame", background=self.content_bg, bordercolor=self.content_border)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", self.scaled_menu_value(9)))
        style.configure("Content.TLabel", background=self.content_bg, foreground=self.content_fg, font=("Segoe UI", self.scaled_menu_value(9)))
        style.configure("Header.TLabel", font=("Segoe UI", self.scaled_menu_value(13), "bold"), background=bg, foreground=fg)
        style.configure("Subtle.TLabel", foreground=sub_fg, background=bg, font=("Segoe UI", self.scaled_menu_value(8)))
        style.configure("Content.Subtle.TLabel", foreground=sub_fg, background=self.content_bg, font=("Segoe UI", self.scaled_menu_value(8)))
        style.configure(
            "TButton",
            padding=(self.scaled_menu_value(7), self.scaled_menu_value(4)),
            background=button_bg,
            foreground=fg,
            borderwidth=1,
            relief="raised",
            bordercolor=button_border,
            lightcolor=button_light,
            darkcolor=button_dark,
            focuscolor=button_bg,
        )
        style.map(
            "TButton",
            background=[("pressed", button_pressed), ("active", button_hover)],
            relief=[("pressed", "sunken"), ("active", "raised")],
            bordercolor=[("pressed", button_dark), ("active", button_border)],
            foreground=[("disabled", sub_fg)],
        )
        style.configure("Tab.TButton", padding=(self.scaled_menu_value(7), self.scaled_menu_value(5)), anchor="w", background=button_bg, foreground=fg)
        style.map("Tab.TButton", background=[("pressed", button_pressed), ("active", button_hover)], relief=[("pressed", "sunken"), ("active", "raised")])
        style.configure("Selected.Tab.TButton", padding=(self.scaled_menu_value(7), self.scaled_menu_value(5)), anchor="w", background=button_selected, foreground=fg, relief="sunken")
        style.map("Selected.Tab.TButton", background=[("pressed", button_selected), ("active", button_selected)], relief=[("pressed", "sunken"), ("active", "sunken")])
        style.configure("Danger.TButton", foreground=danger_fg, padding=(self.scaled_menu_value(7), self.scaled_menu_value(4)), background=button_bg)
        style.configure(
            "ConfirmQuit.TButton",
            foreground="#ffffff",
            padding=(self.scaled_menu_value(7), self.scaled_menu_value(4)),
            background="#b32635",
            bordercolor="#7f1722",
            lightcolor="#d14a57",
            darkcolor="#66111a",
            focuscolor="#b32635",
        )
        style.map(
            "ConfirmQuit.TButton",
            background=[("pressed", "#7f1722"), ("active", "#cf3444")],
            foreground=[("pressed", "#ffffff"), ("active", "#ffffff")],
            relief=[("pressed", "sunken"), ("active", "raised")],
        )
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("Content.TCheckbutton", background=self.content_bg, foreground=self.content_fg)
        style.map("Content.TCheckbutton", background=[("active", self.content_bg)], foreground=[("active", self.content_fg)])
        style.configure("Horizontal.TScale", background=bg, troughcolor=trough, bordercolor=button_border, lightcolor=button_light, darkcolor=button_dark)
        style.configure("Content.Horizontal.TScale", background=self.content_bg, troughcolor=trough, bordercolor=self.content_border, lightcolor=button_light, darkcolor=button_dark)
        if self.menu is not None:
            self.menu.configure(bg=bg)

    def mix_hex_colors(self, first, second, amount):
        if not self.valid_hex_color(first):
            first = "#000000"
        if not self.valid_hex_color(second):
            second = "#ffffff"
        amount = max(0.0, min(1.0, float(amount)))
        mixed = []
        for index in (1, 3, 5):
            a = int(first[index : index + 2], 16)
            b = int(second[index : index + 2], 16)
            mixed.append(round(a * (1 - amount) + b * amount))
        return "#" + "".join(f"{channel:02x}" for channel in mixed)

    def custom_theme_palette(self):
        primary = self.custom_primary_color if self.valid_hex_color(self.custom_primary_color) else "#5d91c8"
        secondary = self.custom_secondary_color if self.valid_hex_color(self.custom_secondary_color) else "#cbe3ff"
        dark = self.color_text_for_background(primary) == "#ffffff"
        base = "#111820" if dark else "#ffffff"
        text = "#f6f8fb" if dark else "#172232"
        subtext = self.mix_hex_colors(text, primary, 0.35)
        return {
            "bg": self.mix_hex_colors(primary, base, 0.78),
            "fg": text,
            "sub_fg": subtext,
            "danger_fg": "#ff7b8e" if dark else "#9b1c3d",
            "button_bg": self.mix_hex_colors(secondary, base, 0.35),
            "button_hover": self.mix_hex_colors(secondary, base, 0.18),
            "button_pressed": self.mix_hex_colors(primary, base, 0.58),
            "button_selected": self.mix_hex_colors(primary, secondary, 0.35),
            "button_border": self.mix_hex_colors(primary, "#000000" if dark else "#4f6174", 0.28),
            "button_light": self.mix_hex_colors(secondary, "#ffffff", 0.35),
            "button_dark": self.mix_hex_colors(primary, "#000000", 0.55),
            "root_border": self.mix_hex_colors(primary, "#000000" if dark else "#6c7f8f", 0.32),
            "trough": self.mix_hex_colors(primary, base, 0.65),
            "content_bg": self.mix_hex_colors(secondary, base, 0.72),
            "content_fg": text,
            "content_select_bg": self.mix_hex_colors(primary, secondary, 0.45),
            "content_border": self.mix_hex_colors(primary, "#000000" if dark else "#7f8d99", 0.35),
            "content_accent": primary,
            "collection_caught_fg": "#8be08f" if dark else "#247a4a",
            "collection_missing_fg": "#ff8787" if dark else "#a33a4f",
            "collection_header_fg": subtext,
        }

    def theme_palette(self):
        palettes = {
            "Light": {
                "bg": "#f5f5f2", "fg": "#1c1c1c", "sub_fg": "#4b625d", "danger_fg": "#9b1c1c",
                "button_bg": "#f0f2ef", "button_hover": "#ffffff", "button_pressed": "#dfe5e0", "button_selected": "#dcebe7",
                "button_border": "#a7b3ae", "button_light": "#ffffff", "button_dark": "#c8d0cb", "root_border": "#bec8c4", "trough": "#dde5e1",
                "content_bg": "#ffffff", "content_fg": "#1c1c1c", "content_select_bg": "#d8ebe6", "content_border": "#c9d2ce", "content_accent": "#88a9a2",
                "collection_caught_fg": "#247a3d", "collection_missing_fg": "#a33a3a", "collection_header_fg": "#4b625d",
            },
            "Dark": {
                "bg": "#20232d", "fg": "#f8f8f2", "sub_fg": "#a8b0c2", "danger_fg": "#ff6b6b",
                "button_bg": "#343a49", "button_hover": "#3f4759", "button_pressed": "#272c38", "button_selected": "#44516a",
                "button_border": "#161922", "button_light": "#5b657b", "button_dark": "#151820", "root_border": "#11141b", "trough": "#171a22",
                "content_bg": "#2a303d", "content_fg": "#f1f1f5", "content_select_bg": "#46516a", "content_border": "#151922", "content_accent": "#6b7fa3",
                "collection_caught_fg": "#8be08f", "collection_missing_fg": "#ff8787", "collection_header_fg": "#a8b0c2",
            },
            "High Contrast": {
                "bg": "#000000", "fg": "#ffffff", "sub_fg": "#d8d8d8", "danger_fg": "#ff4d4d",
                "button_bg": "#1a1a1a", "button_hover": "#303030", "button_pressed": "#050505", "button_selected": "#003a6b",
                "button_border": "#ffffff", "button_light": "#8c8c8c", "button_dark": "#000000", "root_border": "#ffffff", "trough": "#0b0b0b",
                "content_bg": "#000000", "content_fg": "#ffffff", "content_select_bg": "#004f8f", "content_border": "#ffffff", "content_accent": "#ffff66",
                "collection_caught_fg": "#00ff66", "collection_missing_fg": "#ff4d4d", "collection_header_fg": "#ffff66",
            },
            "Catppuccin Mocha": {
                "bg": "#1e1e2e", "fg": "#cdd6f4", "sub_fg": "#a6adc8", "danger_fg": "#f38ba8",
                "button_bg": "#313244", "button_hover": "#45475a", "button_pressed": "#181825", "button_selected": "#45475a",
                "button_border": "#11111b", "button_light": "#585b70", "button_dark": "#11111b", "root_border": "#11111b", "trough": "#181825",
                "content_bg": "#242438", "content_fg": "#cdd6f4", "content_select_bg": "#45475a", "content_border": "#11111b", "content_accent": "#89b4fa",
                "collection_caught_fg": "#a6e3a1", "collection_missing_fg": "#f38ba8", "collection_header_fg": "#cba6f7",
            },
            "Soothing Blue": {
                "bg": "#182232", "fg": "#d9e8ff", "sub_fg": "#9fb4d2", "danger_fg": "#ff8a9a",
                "button_bg": "#26364d", "button_hover": "#314563", "button_pressed": "#121b29", "button_selected": "#36527a",
                "button_border": "#0d1420", "button_light": "#536d91", "button_dark": "#0b111b", "root_border": "#0b111b", "trough": "#101927",
                "content_bg": "#202d42", "content_fg": "#d9e8ff", "content_select_bg": "#36527a", "content_border": "#0d1420", "content_accent": "#7ba7e6",
                "collection_caught_fg": "#9be6b2", "collection_missing_fg": "#ff8a9a", "collection_header_fg": "#9fc5ff",
            },
            "Soothing Purple": {
                "bg": "#241d32", "fg": "#eadfff", "sub_fg": "#b8a7d6", "danger_fg": "#ff8fb1",
                "button_bg": "#352b4d", "button_hover": "#453866", "button_pressed": "#1b1428", "button_selected": "#503f78",
                "button_border": "#130d1d", "button_light": "#6b5a91", "button_dark": "#110b1a", "root_border": "#110b1a", "trough": "#191225",
                "content_bg": "#2d2540", "content_fg": "#eadfff", "content_select_bg": "#503f78", "content_border": "#130d1d", "content_accent": "#b69cff",
                "collection_caught_fg": "#a7e8b1", "collection_missing_fg": "#ff8fb1", "collection_header_fg": "#d3bcff",
            },
            "Pink": {
                "bg": "#fff0f6", "fg": "#3a1828", "sub_fg": "#8a536a", "danger_fg": "#a01846",
                "button_bg": "#ffd9e8", "button_hover": "#fff7fb", "button_pressed": "#f4bfd4", "button_selected": "#f8bfd8",
                "button_border": "#d790ac", "button_light": "#ffffff", "button_dark": "#e8a9c2", "root_border": "#e7aac2", "trough": "#f7cfe0",
                "content_bg": "#fffafd", "content_fg": "#3a1828", "content_select_bg": "#ffd1e4", "content_border": "#efbdd1", "content_accent": "#d85f9b",
                "collection_caught_fg": "#2d7b4a", "collection_missing_fg": "#c43f72", "collection_header_fg": "#8a536a",
            },
            "Green": {
                "bg": "#edf7ef", "fg": "#16331e", "sub_fg": "#4a6951", "danger_fg": "#9b1c1c",
                "button_bg": "#dbeee0", "button_hover": "#f6fff8", "button_pressed": "#c5dfcd", "button_selected": "#cbe8d3",
                "button_border": "#91ad99", "button_light": "#ffffff", "button_dark": "#b8cdbc", "root_border": "#adc1b2", "trough": "#d1e4d6",
                "content_bg": "#fbfffc", "content_fg": "#16331e", "content_select_bg": "#ccebd5", "content_border": "#bfd3c4", "content_accent": "#5a9a6a",
                "collection_caught_fg": "#1f7a3b", "collection_missing_fg": "#a33a3a", "collection_header_fg": "#4a6951",
            },
            "Cozy Blue": {
                "bg": "#eef6ff", "fg": "#18314f", "sub_fg": "#526d8e", "danger_fg": "#9b1c3d",
                "button_bg": "#d8eaff", "button_hover": "#f8fcff", "button_pressed": "#bfd9f5", "button_selected": "#c8e0fb",
                "button_border": "#8ca9c9", "button_light": "#ffffff", "button_dark": "#b3c8de", "root_border": "#afc2d6", "trough": "#d3e3f3",
                "content_bg": "#fbfdff", "content_fg": "#18314f", "content_select_bg": "#cbe3ff", "content_border": "#c1d3e6", "content_accent": "#5d91c8",
                "collection_caught_fg": "#247a4a", "collection_missing_fg": "#a33a4f", "collection_header_fg": "#526d8e",
            },
            "Cozy Purple": {
                "bg": "#f7f0ff", "fg": "#2f2148", "sub_fg": "#6d5a89", "danger_fg": "#9b1c55",
                "button_bg": "#eadcff", "button_hover": "#fcf8ff", "button_pressed": "#dac7f5", "button_selected": "#e0cdf8",
                "button_border": "#ab93cc", "button_light": "#ffffff", "button_dark": "#cbb9df", "root_border": "#c5b5d8", "trough": "#e3d5f3",
                "content_bg": "#fefbff", "content_fg": "#2f2148", "content_select_bg": "#e3d1ff", "content_border": "#d5c6e6", "content_accent": "#8f6bc8",
                "collection_caught_fg": "#287a47", "collection_missing_fg": "#aa3f72", "collection_header_fg": "#6d5a89",
            },
        }
        if self.theme_name == "Custom":
            return self.custom_theme_palette()
        return palettes.get(self.theme_name, palettes["Light"])

    def valid_hex_color(self, value):
        value = str(value).strip()
        if len(value) != 7 or not value.startswith("#"):
            return False
        try:
            int(value[1:], 16)
        except ValueError:
            return False
        return True

    def theme_is_dark(self):
        if self.theme_name in ("Dark", "High Contrast", "Catppuccin Mocha", "Soothing Blue", "Soothing Purple"):
            return True
        if self.theme_name != "Custom":
            return False
        bg = self.theme_palette().get("bg", "#ffffff")
        if not self.valid_hex_color(bg):
            return False
        red = int(bg[1:3], 16)
        green = int(bg[3:5], 16)
        blue = int(bg[5:7], 16)
        return (red * 0.299 + green * 0.587 + blue * 0.114) < 128

    def on_transparency_change(self, value):
        if value is None:
            return
        percent = float(value)
        self.transparency = max(0.2, min(1.0, percent / 100.0))
        self.transparency_text.set(f"{int(round(percent))}%")
        try:
            self.attributes("-alpha", self.transparency)
            if self.menu and self.menu.winfo_exists():
                self.menu.attributes("-alpha", self.transparency)
            self.update_idletasks()
        except tk.TclError:
            pass
        self.save()

    def toggle_dark_theme(self):
        self.theme_name = "Dark" if self.dark_theme else "Light"
        self.theme_var.set(THEME_NAME_TO_LABEL[self.theme_name])
        self.apply_selected_theme()

    def color_text_for_background(self, color):
        if not self.valid_hex_color(color):
            return "#000000"
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
        return "#ffffff" if (red * 0.299 + green * 0.587 + blue * 0.114) < 140 else "#000000"

    def update_custom_theme_controls(self):
        if self.custom_theme_frame is None:
            return
        if self.theme_name == "Custom":
            if self.custom_primary_button is not None and not self.custom_primary_button.winfo_manager():
                self.custom_primary_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
            if self.custom_secondary_button is not None and not self.custom_secondary_button.winfo_manager():
                self.custom_secondary_button.pack(side="left", fill="x", expand=True)
        else:
            if self.custom_primary_button is not None:
                self.custom_primary_button.pack_forget()
            if self.custom_secondary_button is not None:
                self.custom_secondary_button.pack_forget()
        if self.custom_primary_button is not None:
            self.custom_primary_button.configure(
                text="Primary",
                bg=self.custom_primary_color,
                fg=self.color_text_for_background(self.custom_primary_color),
                activebackground=self.custom_primary_color,
                activeforeground=self.color_text_for_background(self.custom_primary_color),
                relief="solid",
                bd=1,
                font=("Segoe UI", self.scaled_menu_value(9), "bold"),
            )
        if self.custom_secondary_button is not None:
            self.custom_secondary_button.configure(
                text="Secondary",
                bg=self.custom_secondary_color,
                fg=self.color_text_for_background(self.custom_secondary_color),
                activebackground=self.custom_secondary_color,
                activeforeground=self.color_text_for_background(self.custom_secondary_color),
                relief="solid",
                bd=1,
                font=("Segoe UI", self.scaled_menu_value(9), "bold"),
            )

    def choose_custom_theme_color(self, color_slot):
        initial_color = self.custom_primary_color if color_slot == "primary" else self.custom_secondary_color
        _, selected_color = colorchooser.askcolor(color=initial_color, parent=self.menu or self, title=f"Choose {color_slot.title()} Color")
        if not selected_color or not self.valid_hex_color(selected_color):
            return
        if color_slot == "primary":
            self.custom_primary_color = selected_color
        else:
            self.custom_secondary_color = selected_color
        self.theme_name = "Custom"
        self.theme_var.set(THEME_NAME_TO_LABEL[self.theme_name])
        self.apply_selected_theme()
        self.save()

    def on_theme_selected(self, event=None):
        selected_theme = self.theme_var.get()
        if selected_theme in THEME_LABEL_TO_NAME:
            selected_theme = THEME_LABEL_TO_NAME[selected_theme]
        self.theme_name = selected_theme
        if self.theme_name not in THEME_NAMES:
            self.theme_name = "Light"
            self.theme_var.set(THEME_NAME_TO_LABEL[self.theme_name])
        self.apply_selected_theme()

    def apply_selected_theme(self):
        self.dark_theme = self.theme_is_dark()
        self.update_custom_theme_controls()
        if self.menu and self.menu.winfo_exists():
            style = ttk.Style(self.menu)
            self.apply_theme(style)
            self.apply_content_listbox_colors()
        else:
            self.apply_content_listbox_colors()
        if ACTIVE_DESKTOP_MODE and hasattr(self, "overlay") and self.overlay.winfo_exists():
            self.overlay.configure(bg=self.theme_palette()["bg"])
        self.draw_overlay()

    def on_game_scale_selected(self, event=None):
        self.game_scale = SCALE_VALUES.get(self.game_scale_var.get(), 1.0)
        self.apply_game_scale()

    def on_menu_scale_selected(self, event=None):
        self.menu_scale = SCALE_VALUES.get(self.menu_scale_var.get(), 1.0)
        if self.menu and self.menu.winfo_exists():
            self.close_menu()
            self.build_menu()

    def on_monitor_selected(self, event=None):
        selected_label = self.monitor_var.get()
        for index, monitor in enumerate(self.monitor_options):
            if monitor["label"] == selected_label:
                self.selected_monitor_index = index
                break
        else:
            self.selected_monitor_index = 0
            self.monitor_var.set(self.monitor_label_for_index(self.selected_monitor_index))

        width, height = self.overlay_size()
        work_left, work_top, work_right, work_bottom = self.work_area_bounds()
        self.window_x = work_left + max(0, (work_right - work_left - width) // 2)
        self.window_y = work_top + max(0, (work_bottom - work_top - height) // 2)
        self.window_x, self.window_y = self.clamp_overlay_position(self.window_x, self.window_y, width, height)
        self.geometry(f"{width}x{height}+{self.window_x}+{self.window_y}")
        self.position_menu(force=True)
        self.save()

    def apply_game_scale(self):
        width, height = self.overlay_size()
        if hasattr(self, "overlay") and self.overlay.winfo_exists():
            self.window_x = self.winfo_x()
            self.window_y = self.winfo_y()
        self.window_x, self.window_y = self.clamp_overlay_position(self.window_x, self.window_y, width, height)
        self.geometry(f"{width}x{height}+{self.window_x}+{self.window_y}")
        if hasattr(self, "overlay") and self.overlay.winfo_exists():
            self.overlay.config(width=width, height=height)
            self.draw_overlay()
        self.position_menu()

    def apply_always_on_top(self):
        self.attributes("-topmost", self.always_on_top)
        if self.menu and self.menu.winfo_exists():
            self.menu.attributes("-topmost", self.always_on_top)
        if self.always_on_top:
            self.lift()
            if self.menu and self.menu.winfo_exists():
                self.menu.lift()

    def reassert_always_on_top(self):
        if not self.always_on_top:
            return
        self.attributes("-topmost", False)
        self.attributes("-topmost", True)
        self.lift()
        if self.menu and self.menu.winfo_exists():
            self.menu.attributes("-topmost", False)
            self.menu.attributes("-topmost", True)
            self.menu.lift()

    def schedule_always_on_top_reasserts(self):
        if not self.always_on_top:
            return
        for delay in ALWAYS_ON_TOP_REASSERT_DELAYS_MS:
            self.after(delay, self.reassert_always_on_top)

    def toggle_always_on_top(self):
        self.always_on_top = self.always_on_top_var.get()
        self.apply_always_on_top()
        self.schedule_always_on_top_reasserts()
        self.save()

    def on_compact_vertical_toggle(self):
        if self.minimized:
            self.set_window_state(True)
        else:
            self.draw_overlay()
        self.save()

    def game_info_panel_bounds(self):
        return (18, 174, 302, 228)

    def pointer_over_game_info_panel(self, event):
        x = event.x / self.game_scale
        y = event.y / self.game_scale
        x0, y0, x1, y1 = self.game_info_panel_bounds()
        return x0 <= x <= x1 and y0 <= y <= y1

    def show_game_info_panel(self):
        self.last_info_panel_hover_at = time.time()
        if not self.game_info_panel_visible:
            self.game_info_panel_visible = True
            self.draw_overlay()

    def update_game_info_panel_visibility(self):
        if self.minimized or self.game_info_panel_pinned.get():
            if not self.game_info_panel_visible:
                self.game_info_panel_visible = True
                self.draw_overlay()
            return
        should_show = time.time() - self.last_info_panel_hover_at <= INFO_PANEL_HIDE_SECONDS
        if self.game_info_panel_visible != should_show:
            self.game_info_panel_visible = should_show
            self.draw_overlay()

    def toggle_game_info_panel_pin(self):
        self.game_info_panel_visible = True
        self.last_info_panel_hover_at = time.time()
        self.draw_overlay()
        self.save()

    def apply_content_listbox_colors(self):
        valid_listboxes = []
        for listbox in self.content_listboxes:
            if not getattr(listbox, "winfo_exists", None) or not listbox.winfo_exists():
                continue
            try:
                listbox.config(
                    bg=self.content_bg,
                    fg=self.content_fg,
                    selectbackground=self.content_select_bg,
                    selectforeground=self.content_fg,
                    highlightbackground=self.content_border,
                    highlightcolor=self.content_accent,
                    highlightthickness=1,
                    bd=1,
                    relief="solid",
                    font=("Segoe UI", self.scaled_menu_value(9)),
                )
                valid_listboxes.append(listbox)
            except tk.TclError:
                continue
        self.content_listboxes = valid_listboxes

    def listbox_view_state(self, listbox):
        try:
            return {
                "yview": listbox.yview(),
                "selection": listbox.curselection(),
            }
        except tk.TclError:
            return None

    def restore_listbox_view_state(self, listbox, state):
        if not state:
            return
        try:
            yview = state.get("yview", (0.0, 1.0))
            listbox.yview_moveto(yview[0])
            listbox.selection_clear(0, tk.END)
            for index in state.get("selection", ()):
                if index < listbox.size():
                    listbox.selection_set(index)
        except tk.TclError:
            pass

    def refresh_all(self):
        self.cleanup_active_blessings()
        self.cleanup_active_potions()
        self.inventory_limit = self.current_inventory_limit()
        self.update_achievements()
        discovered_count = self.collection_discovered_count()
        total_collection_count = len(FISH_TABLE)
        happy_count = self.happy_fish_discovered_count()
        self.achievements_text.set(f"Achievements {len(self.achievements_unlocked)} / {len(ACHIEVEMENTS)}")
        self.coins_text.set(str(self.coins))
        self.strokes_text.set(str(self.total_keystrokes))
        if not hasattr(self, "banked_keys_text"):
            self.banked_keys_text = tk.StringVar(value=str(self.banked_keys))
        self.banked_keys_text.set(str(self.banked_keys))
        self.play_time_text.set(self.format_play_time(self.total_played_seconds + (time.time() - self.play_timer_started_at)))
        blessing_count = self.stored_blessing_count()
        trophy_slots = self.blessing_trophy_slots()
        self.inventory_text.set(f"Inventory {self.regular_inventory_count()} / {self.inventory_limit} | Blessings {blessing_count} / {trophy_slots}")
        self.autosell_countdown_text.set(self.autosell_countdown_text_value())
        self.collection_text.set(f"Collection {discovered_count} / {total_collection_count} | {HAPPY_FISH_COLLECTION} {happy_count} / {len(PRIDE_FISH_SKINS)}")
        self.status_text.set(self.last_message)
        self.backpack_text.set(self.backpack_status_text())
        self.autosell_text.set(self.autosell_status_text())
        self.banked_upgrade_text.set(self.banked_upgrade_status_text())
        self.fishing_spot_text.set(self.fishing_spot_status_text())
        self.relic_text.set(self.relic_status_text())
        self.potion_text.set(self.potion_status_text())
        self.blessing_text.set(self.blessing_status_text())

        if self.menu and self.menu.winfo_exists():
            has_relic_tab = "Relics" in self.menu_tab_frames
            has_potions_tab = "Potions" in self.menu_tab_frames
            if self.player_has_relics() != has_relic_tab or self.player_has_potions() != has_potions_tab:
                self.close_menu()
                self.build_menu()
                return

        if self.hooked_fish:
            fish = self.hooked_fish
            if fish.kind == "chest":
                self.fish_text.set("Treasure Chest - open it for coins or Cast Tokens")
            elif fish.kind == "blessing":
                self.fish_text.set(f"{fish.name} - complete it to store {self.blessing_effect_text(fish.blessing_slot, fish.blessing_bonus)}")
            else:
                self.fish_text.set(f"{hooked_fish_display_name(fish)} worth {fish.value} coins")
            progress_label = self.format_progress_value(fish.progress)
            self.progress_text.set(f"{progress_label} / {fish.strokes} keystrokes")
        else:
            self.fish_text.set("Casting automatically...")
            self.progress_text.set("0 / 0")

        if self.menu and self.menu.winfo_exists():
            listbox_states = {
                self.inventory_list: self.listbox_view_state(self.inventory_list),
                self.collection_list: self.listbox_view_state(self.collection_list),
                self.achievements_list: self.listbox_view_state(self.achievements_list),
                self.shop_list: self.listbox_view_state(self.shop_list),
                self.backpack_list: self.listbox_view_state(self.backpack_list),
                self.banked_upgrade_list: self.listbox_view_state(self.banked_upgrade_list),
                self.autosell_list: self.listbox_view_state(self.autosell_list),
                self.fishing_spot_list: self.listbox_view_state(self.fishing_spot_list),
            }
            if self.log_list is not None and self.log_list.winfo_exists():
                listbox_states[self.log_list] = self.listbox_view_state(self.log_list)
            if self.relic_list is not None and self.relic_list.winfo_exists():
                listbox_states[self.relic_list] = self.listbox_view_state(self.relic_list)
            if self.potion_list is not None and self.potion_list.winfo_exists():
                listbox_states[self.potion_list] = self.listbox_view_state(self.potion_list)

            if self.hooked_fish:
                self.progress.configure(maximum=self.hooked_fish.strokes, value=self.hooked_fish.progress)
            else:
                self.progress.configure(maximum=1, value=0)

            self.inventory_list.delete(0, tk.END)
            for fish in self.inventory:
                if fish_is_blessing(fish):
                    self.inventory_list.insert(tk.END, f"{fish_inventory_display_name(fish)} - sell selected to activate")
                else:
                    self.inventory_list.insert(tk.END, f"{fish_inventory_display_name(fish)} - {fish['value']} coins")

            if self.log_list is not None and self.log_list.winfo_exists():
                self.log_list.delete(0, tk.END)
                if self.event_log:
                    for entry in self.event_log:
                        self.log_list.insert(tk.END, entry)
                else:
                    self.log_list.insert(tk.END, "No events yet.")

            if self.relic_list is not None and self.relic_list.winfo_exists():
                self.relic_list.delete(0, tk.END)
                for relic in RELICS:
                    count = safe_int(self.relics.get(relic["id"], 0))
                    if count <= 0:
                        continue
                    next_relic = self.next_relic_in_series(relic)
                    trade_text = " | Trade ready" if count >= 3 and next_relic else ""
                    if count >= 3 and next_relic is None:
                        trade_text = " | Top tier"
                    self.relic_list.insert(tk.END, f"{relic['rarity']} {relic['name']} x{count} - {self.relic_effect_text(relic, count)}{trade_text}")

            if self.potion_list is not None and self.potion_list.winfo_exists():
                self.potion_list.delete(0, tk.END)
                for potion in self.owned_potions_in_display_order():
                    count = safe_int(self.stored_potions.get(potion["id"], 0))
                    self.potion_list.insert(tk.END, f"{potion['rarity']} {potion['name']} x{count} - {self.potion_effect_text(potion)}")
                active_potions = sorted(self.potions, key=lambda potion: float(potion.get("expires_at", 0)))
                if self.owned_potions_in_display_order() and active_potions:
                    self.potion_list.insert(tk.END, "")
                for active_potion in active_potions:
                    potion = self.potion_by_id(active_potion.get("id"))
                    if not potion:
                        continue
                    remaining = max(0, int(float(active_potion.get("expires_at", 0)) - time.time()))
                    self.potion_list.insert(tk.END, f"Active: {potion['rarity']} {potion['name']} - {self.potion_effect_text(potion)} - {self.format_play_time(remaining)} left")

            self.collection_list.delete(0, tk.END)
            rarity_order = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Secret", "Ultra Rare"]
            fish_by_rarity = {rarity: [] for rarity in rarity_order}
            for fish in FISH_TABLE:
                fish_by_rarity.setdefault(fish["rarity"], []).append(fish)

            for rarity, rarity_fish in fish_by_rarity.items():
                if not rarity_fish:
                    continue
                if self.collection_list.size() > 0:
                    self.collection_list.insert(tk.END, "")
                header_index = self.collection_list.size()
                caught_in_rarity = sum(
                    1
                    for fish in rarity_fish
                    if safe_int(self.collection_log.get(fish_collection_key(fish["rarity"], fish["name"]), {}).get("count", 0)) > 0
                )
                self.collection_list.insert(tk.END, f"{rarity.upper()} {caught_in_rarity}/{len(rarity_fish)}")
                self.collection_list.itemconfig(header_index, fg=self.collection_header_fg)

                for fish in rarity_fish:
                    key = fish_collection_key(fish["rarity"], fish["name"])
                    entry = self.collection_log.get(key)
                    row_index = self.collection_list.size()
                    spot_id = fish.get("spot_id", "")
                    spot_text = ""
                    if spot_id == "global":
                        spot_text = " | any spot"
                    elif spot_id:
                        spot_text = f" | {self.fishing_spot_by_id(spot_id)['name']}"
                    if entry:
                        count = safe_int(entry.get("count", 0))
                        best_value = safe_int(entry.get("best_value", 0))
                        value_text = f" | best {best_value} coins" if best_value else ""
                        self.collection_list.insert(tk.END, f"  {fish['name']} x{count}{value_text}{spot_text}")
                        self.collection_list.itemconfig(row_index, fg=self.collection_caught_fg)
                    else:
                        self.collection_list.insert(tk.END, f"  {fish['name']}{spot_text}")
                        self.collection_list.itemconfig(row_index, fg=self.collection_missing_fg)

            happy_caught = sum(
                1
                for skin in PRIDE_FISH_SKINS
                if safe_int(self.collection_log.get(happy_fish_collection_key(skin["id"]), {}).get("count", 0)) > 0
            )
            if self.collection_list.size() > 0:
                self.collection_list.insert(tk.END, "")
            header_index = self.collection_list.size()
            self.collection_list.insert(tk.END, f"{HAPPY_FISH_COLLECTION.upper()} {happy_caught}/{len(PRIDE_FISH_SKINS)}")
            self.collection_list.itemconfig(header_index, fg=self.collection_header_fg)
            for skin in PRIDE_FISH_SKINS:
                key = happy_fish_collection_key(skin["id"])
                entry = self.collection_log.get(key)
                row_index = self.collection_list.size()
                if entry:
                    count = safe_int(entry.get("count", 0))
                    best_value = safe_int(entry.get("best_value", 0))
                    value_text = f" | best {best_value} coins" if best_value else ""
                    self.collection_list.insert(tk.END, f"  {skin['name']} x{count}{value_text}")
                    self.collection_list.itemconfig(row_index, fg=self.collection_caught_fg)
                else:
                    self.collection_list.insert(tk.END, f"  {skin['name']}")
                    self.collection_list.itemconfig(row_index, fg=self.collection_missing_fg)

            self.achievements_list.delete(0, tk.END)
            for achievement in ACHIEVEMENTS:
                unlocked = achievement["id"] in self.achievements_unlocked
                row_index = self.achievements_list.size()
                prefix = "Unlocked" if unlocked else "Locked"
                name = achievement["name"]
                description = achievement["description"]
                if achievement.get("secret") and not unlocked:
                    name = "???"
                    description = "Secret achievement"
                self.achievements_list.insert(tk.END, f"{prefix} - {name} - {description}")
                self.achievements_list.itemconfig(
                    row_index,
                    fg=self.collection_caught_fg if unlocked else self.collection_header_fg,
                )

            self.shop_list.delete(0, tk.END)
            upgrades = self.available_equipment_upgrades()
            if upgrades:
                for slot, item in upgrades:
                    effect = self.item_effect_text(slot, item)
                    price = self.shop_price(item['price'])
                    self.shop_list.insert(
                        tk.END,
                        f"{slot.title()} Lv {self.equipment_levels[slot] + 1} - {item['name']} - {price} coins - {effect}",
                    )
            else:
                self.shop_list.insert(tk.END, "All equipment maxed")

            self.backpack_list.delete(0, tk.END)
            upgrade = self.next_backpack_upgrade()
            if upgrade:
                self.backpack_list.insert(
                    tk.END,
                    f"Level {upgrade['level']} - {upgrade['slots']} slots - {self.shop_price(upgrade['price'])} coins",
                )
            else:
                self.backpack_list.insert(tk.END, "Max backpack reached - 96 slots")

            self.banked_upgrade_list.delete(0, tk.END)
            next_upgrade = self.next_banked_upgrade()
            if next_upgrade:
                next_discount = round(max(0.0, min(0.50, float(next_upgrade.get("discount", 0.0)))) * 100)
                self.banked_upgrade_list.insert(
                    tk.END,
                    f"Next: {next_upgrade['name']} - {next_upgrade['cost']} Cast Tokens - {next_upgrade['mult']:.2f}x, -{next_discount}% shop costs",
                )
            else:
                self.banked_upgrade_list.insert(tk.END, "Cast Token upgrades maxed")

            self.autosell_list.delete(0, tk.END)
            next_autosell = self.next_autosell_upgrade()
            if next_autosell:
                self.autosell_list.insert(
                    tk.END,
                    f"Next: {next_autosell['name']} - {self.shop_price(next_autosell['price'])} coins - {next_autosell['percent']}% inventory",
                )
            else:
                self.autosell_list.insert(tk.END, "Auto sell module maxed")

            self.fishing_spot_list.delete(0, tk.END)
            for spot in FISHING_SPOTS:
                selected_marker = " [active]" if spot["id"] == self.selected_fishing_spot else ""
                if spot["id"] in self.unlocked_fishing_spots:
                    self.fishing_spot_list.insert(tk.END, f"Unlocked - {spot['name']}{selected_marker} - {spot['description']}")
                else:
                    self.fishing_spot_list.insert(tk.END, f"Locked - {spot['name']} - {self.fishing_spot_cost_text(spot)}")

            for listbox, state in listbox_states.items():
                self.restore_listbox_view_state(listbox, state)

        equipment_lines = []
        for slot in EQUIPMENT_SLOTS:
            item = self.current_equipment_item(slot)
            equipment_lines.append(f"{slot.title()} Lv {self.equipment_levels[slot]} - {item['name']} - {self.item_effect_text(slot, item)}")
        if hasattr(self, "equipment_text"):
            self.equipment_text.set("\n".join(equipment_lines))
        reduction = round((1 - self.stroke_multiplier()) * 100)
        accuracy = self.accuracy_chance() * 100
        banked_bonus = round(self.banked_key_bonus() * 100)
        self.gear_text.set(
            f"Gear: {reduction}% fewer keystrokes | +{self.luck_bonus()} fish luck | "
            f"{accuracy:.1f}% accuracy | +{banked_bonus}% extra Cast Tokens"
        )

    def collection_discovered_count(self):
        fish_keys = {fish_collection_key(fish["rarity"], fish["name"]) for fish in FISH_TABLE}
        return sum(1 for key, entry in self.collection_log.items() if key in fish_keys and safe_int(entry.get("count", 0)) > 0)

    def happy_fish_discovered_count(self):
        return sum(
            1
            for skin in PRIDE_FISH_SKINS
            if safe_int(self.collection_log.get(happy_fish_collection_key(skin["id"]), {}).get("count", 0)) > 0
        )

    def collection_rarity_progress(self, rarity):
        rarity_fish = [fish for fish in FISH_TABLE if fish["rarity"] == rarity]
        caught = sum(
            1
            for fish in rarity_fish
            if safe_int(self.collection_log.get(fish_collection_key(fish["rarity"], fish["name"]), {}).get("count", 0)) > 0
        )
        return caught, len(rarity_fish)

    def collection_rarity_complete(self, rarity):
        caught, total = self.collection_rarity_progress(rarity)
        return total > 0 and caught >= total

    def play_time_now(self):
        return self.total_played_seconds + (time.time() - self.play_timer_started_at)

    def achievement_unlocked(self, achievement_id):
        criteria = {
            "first_catch": lambda: self.collection_discovered_count() >= 1,
            "collection_common": lambda: self.collection_rarity_complete("Common"),
            "collection_uncommon": lambda: self.collection_rarity_complete("Uncommon"),
            "collection_rare": lambda: self.collection_rarity_complete("Rare"),
            "collection_epic": lambda: self.collection_rarity_complete("Epic"),
            "collection_secret": lambda: self.collection_rarity_complete("Secret"),
            "collection_ultra_rare": lambda: self.collection_rarity_complete("Ultra Rare"),
            "collection_all": lambda: self.collection_discovered_count() >= len(FISH_TABLE),
            "play_15m": lambda: self.play_time_now() >= 15 * 60,
            "play_1h": lambda: self.play_time_now() >= 60 * 60,
            "play_8h": lambda: self.play_time_now() >= 8 * 60 * 60,
            "play_24h": lambda: self.play_time_now() >= 24 * 60 * 60,
            "play_69h": lambda: self.play_time_now() >= 69 * 60 * 60,
            "play_100h": lambda: self.play_time_now() >= 100 * 60 * 60,
            "play_250h": lambda: self.play_time_now() >= 250 * 60 * 60,
            "keys_10000": lambda: self.total_keystrokes >= 10000,
            "keys_100000": lambda: self.total_keystrokes >= 100000,
            "keys_1000000": lambda: self.total_keystrokes >= 1000000,
            "keys_10000000": lambda: self.total_keystrokes >= 10000000,
            "banked_50000": lambda: self.banked_keys >= 50000,
            "banked_100000": lambda: self.banked_keys >= 100000,
            "banked_1000000": lambda: self.banked_keys >= 1000000,
            "coins_10000": lambda: self.coins >= 10000,
            "coins_1000000": lambda: self.coins >= 1000000,
            "coins_10000000": lambda: self.coins >= 10000000,
            "backpack_10": lambda: self.backpack_level >= 10,
            "backpack_15": lambda: self.backpack_level >= 15,
            "backpack_max": lambda: self.backpack_level >= len(BACKPACK_UPGRADES),
            "autosell": lambda: self.autosell_level > 0,
            "first_relic": lambda: self.player_has_relics(),
            "all_relic_types": lambda: self.owns_all_relic_types(),
            "fish_clicks_10": lambda: self.fish_clicks >= 10,
            "fish_clicks_100": lambda: self.fish_clicks >= 100,
            "cat_pets_1": lambda: self.cat_pets >= 1,
            "cat_pets_100": lambda: self.cat_pets >= 100,
            "banked_upgrade_max": lambda: self.banked_upgrade_level >= len(BANKED_KEY_UPGRADES),
            "equipment_all_5": lambda: all(level >= 5 for level in self.equipment_levels.values()),
            "equipment_all_10": lambda: all(level >= 10 for level in self.equipment_levels.values()),
            "equipment_all_max": lambda: all(self.equipment_levels[slot] >= len(EQUIPMENT_TRACKS[slot]) - 1 for slot in EQUIPMENT_SLOTS),
            "spots_all": lambda: len(self.unlocked_fishing_spots) >= len(FISHING_SPOTS),
        }
        return criteria.get(achievement_id, lambda: False)()

    def update_achievements(self):
        newly_unlocked = []
        for achievement in ACHIEVEMENTS:
            achievement_id = achievement["id"]
            if achievement_id in self.achievements_unlocked:
                continue
            if self.achievement_unlocked(achievement_id):
                self.achievements_unlocked.add(achievement_id)
                newly_unlocked.append(achievement["name"])
        if newly_unlocked:
            self.last_message = f"Achievement unlocked: {newly_unlocked[-1]}"

    def blend_hex_color(self, color, background, amount):
        amount = max(0.0, min(1.0, amount))

        def parse_hex(value):
            value = str(value).strip().lstrip("#")
            if len(value) != 6:
                return (255, 255, 255)
            try:
                return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
            except ValueError:
                return (255, 255, 255)

        fg = parse_hex(color)
        bg = parse_hex(background)
        mixed = [round(fg[index] * (1 - amount) + bg[index] * amount) for index in range(3)]
        return "#" + "".join(f"{channel:02x}" for channel in mixed)

    def panel_shadow_color(self, panel_fill):
        shadow_base = "#000000" if self.dark_theme else "#6b7b86"
        return self.blend_hex_color(shadow_base, panel_fill, 0.62 if self.dark_theme else 0.78)

    def draw_panel_shadow(self, canvas, x0, y0, x1, y1, panel_fill):
        shadow = self.panel_shadow_color(panel_fill)
        canvas.create_rectangle(x0 + 3, y0 + 4, x1 + 3, y1 + 4, fill=shadow, outline="")
        canvas.create_rectangle(x0 + 1, y0 + 2, x1 + 1, y1 + 2, fill=shadow, outline="")

    def scene_shadow_color(self, surface_color, strength=0.42):
        shadow_base = "#000000" if self.dark_theme else "#33434a"
        return self.blend_hex_color(shadow_base, surface_color, max(0.0, min(1.0, 1 - strength)))

    def draw_soft_oval_shadow(self, canvas, x0, y0, x1, y1, surface_color, strength=0.36):
        shadow = self.scene_shadow_color(surface_color, strength)
        soft_shadow = self.blend_hex_color(shadow, surface_color, 0.46)
        canvas.create_oval(x0 + 2, y0 + 3, x1 + 2, y1 + 3, fill=soft_shadow, outline="")
        canvas.create_oval(x0, y0, x1, y1, fill=shadow, outline="")

    def draw_line_shadow(self, canvas, points, surface_color, width=3, offset=(3, 4)):
        shadow = self.scene_shadow_color(surface_color, 0.28)
        shifted_points = [(x + offset[0], y + offset[1]) for x, y in points]
        canvas.create_line(shifted_points, fill=shadow, width=width, capstyle=tk.ROUND, smooth=True)

    def draw_fisher_cat(self, canvas, shoreline, stone_color):
        if self.draw_asset_image(canvas, 34, 101, "cat", "aphrodite.png"):
            return
        fur = "#20242a" if not self.dark_theme else "#14181d"
        fur_shadow = "#111418" if not self.dark_theme else "#080a0d"
        fur_light = "#f1f3ee" if not self.dark_theme else "#d8ddd7"
        white_patch = "#fafbf6" if not self.dark_theme else "#e8ece5"
        eye_gold = "#b7ad63" if not self.dark_theme else "#9f9857"
        nose_pink = "#e9a1aa" if not self.dark_theme else "#d78a96"
        outline = "#050608" if not self.dark_theme else "#020304"
        existing_items = set(canvas.find_all())

        self.draw_soft_oval_shadow(canvas, 3, 132, 80, 158, shoreline, 0.26)
        canvas.create_oval(0, 106, 42, 151, fill=stone_color, outline=self.scene_shadow_color(stone_color, 0.34), width=1)
        canvas.create_oval(7, 111, 35, 124, fill=self.blend_hex_color("#ffffff", stone_color, 0.34), outline="")
        canvas.create_oval(17, 124, 78, 151, fill=stone_color, outline=self.scene_shadow_color(stone_color, 0.34), width=1)
        canvas.create_oval(25, 128, 65, 138, fill=self.blend_hex_color("#ffffff", stone_color, 0.28), outline="")

        canvas.create_line([(29, 133), (17, 126), (15, 116), (24, 111), (35, 118)], fill=fur, width=6, smooth=True, capstyle=tk.ROUND)
        canvas.create_oval(20, 105, 82, 145, fill=fur, outline=outline, width=2)
        canvas.create_oval(30, 118, 70, 145, fill=white_patch, outline="")
        canvas.create_oval(30, 134, 49, 145, fill=white_patch, outline=outline, width=1)
        canvas.create_oval(54, 134, 75, 145, fill=white_patch, outline=outline, width=1)
        canvas.create_arc(28, 119, 79, 146, start=188, extent=164, style=tk.ARC, outline=fur_shadow, width=2)
        canvas.create_polygon(27, 107, 33, 101, 31, 113, 38, 110, 34, 121, fill=fur, outline="")
        canvas.create_polygon(70, 108, 76, 102, 73, 114, 79, 112, 74, 122, fill=fur, outline="")

        canvas.create_oval(39, 73, 78, 111, fill=fur, outline=outline, width=2)
        canvas.create_polygon(42, 80, 45, 55, 58, 79, fill=fur, outline=outline)
        canvas.create_polygon(60, 78, 78, 57, 75, 85, fill=fur, outline=outline)
        canvas.create_polygon(47, 76, 49, 64, 55, 78, fill="#f1a9a0", outline="")
        canvas.create_polygon(65, 75, 74, 66, 71, 80, fill="#f1a9a0", outline="")
        canvas.create_polygon(50, 88, 65, 88, 67, 95, 63, 106, 53, 111, 45, 103, 46, 95, fill=white_patch, outline="")
        canvas.create_oval(43, 92, 57, 109, fill=white_patch, outline="")
        canvas.create_oval(58, 92, 72, 109, fill=white_patch, outline="")
        canvas.create_oval(48, 85, 56, 93, fill=eye_gold, outline=outline, width=1)
        canvas.create_oval(65, 84, 73, 92, fill=eye_gold, outline=outline, width=1)
        canvas.create_oval(51, 87, 54, 92, fill=outline, outline="")
        canvas.create_oval(68, 86, 71, 91, fill=outline, outline="")
        canvas.create_polygon(56, 95, 62, 95, 59, 99, fill="#111111", outline=outline)
        canvas.create_polygon(56, 95, 62, 95, 59, 97, fill=nose_pink, outline="")
        canvas.create_arc(50, 98, 59, 106, start=210, extent=95, style=tk.ARC, outline=outline, width=1)
        canvas.create_arc(59, 98, 68, 106, start=235, extent=95, style=tk.ARC, outline=outline, width=1)
        canvas.create_line(44, 96, 29, 93, fill=outline, width=1)
        canvas.create_line(44, 101, 29, 101, fill=outline, width=1)
        canvas.create_line(72, 95, 88, 90, fill=outline, width=1)
        canvas.create_line(72, 100, 90, 99, fill=outline, width=1)
        for item in canvas.find_all():
            if item not in existing_items:
                canvas.scale(item, BASE_OVERLAY_WIDTH / 2, 0, -1, 1)

    def resource_delta_position(self, resource, minimized):
        if minimized == "vertical":
            positions = {"coins": (67, 126), "keys": (67, 156), "banked_keys": (67, 186)}
        elif minimized:
            positions = {"coins": (220, 58), "keys": (78, 58), "banked_keys": (150, 58)}
        else:
            positions = {"coins": (58, 143), "keys": (130, 143), "banked_keys": (206, 143)}
        return positions.get(resource, (160, 184))

    def draw_resource_deltas(self, canvas, panel_fill, panel_outline, minimized=False):
        if not self.resource_deltas:
            return
        now = time.time()
        active_deltas = []
        lane_offsets = {"coins": 0, "keys": 0, "banked_keys": 0}
        for delta in self.resource_deltas:
            age = now - delta.born
            if age >= delta.life:
                continue
            active_deltas.append(delta)
            progress = max(0.0, min(1.0, age / delta.life))
            x, y = self.resource_delta_position(delta.resource, minimized)
            lane_index = lane_offsets.get(delta.resource, 0)
            lane_offsets[delta.resource] = lane_index + 1
            y -= lane_index * (10 if minimized == "vertical" else 12) + int(progress * 10)
            if delta.amount > 0 and delta.resource == "banked_keys":
                color = "#2478d4"
            else:
                color = "#118a45" if delta.amount > 0 else "#b32635"
            color = self.blend_hex_color(color, panel_fill, progress * 0.25)
            if minimized == "vertical":
                sign = "+" if delta.amount > 0 else ""
                text = f"{sign}{self.compact_number_text(delta.amount)}"
                text_width = max(22, len(text) * 5 + 10)
                font = self.overlay_font(7, "bold")
            else:
                text = f"{delta.amount:+,}"
                text_width = max(26, len(text) * 6 + 12)
                font = self.overlay_font(8, "bold")
            outline_color = "#102f32" if self.dark_theme else "#ffffff"
            canvas.create_rectangle(x - text_width // 2, y - 7, x + text_width // 2, y + 7, fill=panel_fill, outline=panel_outline)
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                canvas.create_text(x + ox, y + oy, text=text, anchor="center", fill=outline_color, font=font)
            canvas.create_text(x, y, text=text, anchor="center", fill=color, font=font)
        self.resource_deltas = active_deltas

    def compact_number_text(self, value):
        value = int(value)
        abs_value = abs(value)
        if abs_value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f}B"
        if abs_value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if abs_value >= 10_000:
            return f"{value / 1_000:.1f}K"
        return str(value)

    def draw_vertical_compact_overlay(self, canvas, w, h, text_panel_fill, text_panel_outline, panel_text_color, panel_subtext_color, progress_bg, menu_fill, menu_outline, autosell_countdown):
        panel_x0, panel_y0 = 8, 8
        panel_x1, panel_y1 = w - 8, h - 8
        self.draw_panel_shadow(canvas, panel_x0, panel_y0, panel_x1, panel_y1, text_panel_fill)
        canvas.create_rectangle(panel_x0, panel_y0, panel_x1, panel_y1, fill=text_panel_fill, outline=text_panel_outline)

        menu_size = 16
        menu_x0 = panel_x1 - menu_size - 7
        menu_y0 = panel_y0 + 7
        menu_x1 = menu_x0 + menu_size
        menu_y1 = menu_y0 + menu_size
        canvas.create_rectangle(menu_x0, menu_y0, menu_x1, menu_y1, fill=menu_fill, outline=menu_outline, tags=("menu",))
        for y in (menu_y0 + 4, menu_y0 + 8, menu_y0 + 12):
            canvas.create_line(menu_x0 + 4, y, menu_x1 - 4, y, fill=panel_text_color, width=2, tags=("menu",))

        if self.hooked_fish:
            fish = self.hooked_fish
            progress = fish.progress / fish.strokes
            title = hooked_fish_display_name(fish)
            status_line = f"{self.format_progress_value(fish.progress)}/{fish.strokes}"
        else:
            left = self.auto_cast_seconds() - (time.time() - self.cast_started_at)
            self.last_message = f"Casting... {max(left, 0):.1f}s"
            self.status_text.set(self.last_message)
            progress = max(0.0, min(1.0, 1 - max(left, 0) / self.auto_cast_seconds()))
            title = "Casting..."
            status_line = f"Bite {max(left, 0):.1f}s"

        if len(title) > 24:
            title = f"{title[:21]}..."

        title_width = int((w - 20) * self.game_scale)
        canvas.create_text(panel_x0 + 9, panel_y0 + 30, text=title, anchor="nw", fill=panel_text_color, font=self.overlay_font(8, "bold"), width=title_width)
        canvas.create_text(w // 2, panel_y0 + 76, text=status_line, anchor="center", fill=panel_subtext_color, font=self.overlay_font(8, "bold"), width=title_width)

        bar_x0, bar_y0 = w // 2 - 11, 96
        bar_x1, bar_y1 = w // 2 + 11, h - 88
        canvas.create_rectangle(bar_x0, bar_y0, bar_x1, bar_y1, fill=progress_bg, outline=menu_outline)
        fill_y0 = bar_y1 - int((bar_y1 - bar_y0) * progress)
        canvas.create_rectangle(bar_x0, fill_y0, bar_x1, bar_y1, fill="#4aa7a1", outline="")

        stat_y = h - 76
        stat_width = int((w - 18) * self.game_scale)
        compact_stats = [
            f"C {self.compact_number_text(self.coins)}",
            f"F {self.regular_inventory_count()}/{self.inventory_limit}",
            f"CT {self.compact_number_text(self.banked_keys)}",
        ]
        if autosell_countdown:
            compact_stats.append(f"AS {autosell_countdown}")
        for index, line in enumerate(compact_stats[:4]):
            canvas.create_text(w // 2, stat_y + index * 14, text=line, anchor="center", fill=panel_subtext_color, font=self.overlay_font(7), width=stat_width)

        self.draw_resource_deltas(canvas, text_panel_fill, text_panel_outline, minimized="vertical")

    def draw_hooked_fish_asset(self, canvas, fish, fish_x):
        if fish.kind == "chest":
            return self.draw_first_asset_image(
                canvas,
                120 + fish_x,
                124,
                (("chest", "treasure_chest.png"), ("fish", "treasure_chest.png")),
            )
        if fish.kind == "blessing":
            blessing_id = asset_slug(fish.blessing_id or fish.name)
            return self.draw_first_asset_image(
                canvas,
                119 + fish_x,
                119,
                (
                    ("blessings", f"{blessing_id}.png"),
                    ("fish", f"blessing_{blessing_id}.png"),
                    ("blessings", "default.png"),
                ),
            )

        rarity_slug = asset_slug(fish.rarity)
        name_slug = asset_slug(fish.name)
        skin_slug = asset_slug(fish.skin_id or fish.skin_name) if getattr(fish, "skin_id", "") or getattr(fish, "skin_name", "") else ""
        candidates = []
        if skin_slug:
            candidates.append(("fish", "skins", f"{skin_slug}.png"))
        candidates.extend(
            (
                ("fish", "names", f"{name_slug}.png"),
                ("fish", "rarity", f"{rarity_slug}.png"),
                ("fish", "default.png"),
            )
        )
        return self.draw_first_asset_image(canvas, 120 + fish_x, 118, candidates)

    def draw_overlay(self):
        canvas = self.overlay
        canvas.delete("all")
        w, h = self.base_overlay_size()

        if self.dark_theme:
            main_fill = "#2b2f3b"
            main_outline = "#566277"
            detail_outline = "#5f7187"
            text_color = "#f1f1f5"
            subtext_color = "#9aa4b5"
            panel_fill = "#2e3646"
            progress_bg = "#38445a"
            menu_fill = "#2a303d"
            menu_outline = "#556074"
        else:
            main_fill = "#eaf8ff"
            main_outline = "#d7edf7"
            detail_outline = "#c7e6f2"
            text_color = "#173533"
            subtext_color = "#4b625d"
            panel_fill = "#f7fbf8"
            progress_bg = "#dbe9e4"
            menu_fill = "#f7fbf8"
            menu_outline = "#78928d"

        pond_fill = "#243447" if self.dark_theme else "#cfe5f1"
        pond_outline = "#4f6c80" if self.dark_theme else "#7d9db1"
        ripple_color = "#3b5a71" if self.dark_theme else "#d7ecf4"
        palette = self.theme_palette()
        menu_fill = palette["button_bg"]
        menu_outline = palette["button_border"]
        progress_bg = palette["trough"]
        text_panel_fill = palette["content_bg"]
        text_panel_outline = palette["content_border"]
        panel_text_color = palette["content_fg"]
        panel_subtext_color = palette["sub_fg"]
        autosell_countdown = self.autosell_countdown_text_value()
        spot_style = self.fishing_spot_scene_style()

        if self.compact_vertical_enabled():
            self.draw_vertical_compact_overlay(
                canvas,
                w,
                h,
                text_panel_fill,
                text_panel_outline,
                panel_text_color,
                panel_subtext_color,
                progress_bg,
                menu_fill,
                menu_outline,
                autosell_countdown,
            )
            self.scale_overlay_items()
            return

        if self.minimized:
            panel_x0, panel_y0 = 14, 12
            panel_x1, panel_y1 = w - 14, 68
            self.draw_panel_shadow(canvas, panel_x0, panel_y0, panel_x1, panel_y1, text_panel_fill)
            canvas.create_rectangle(panel_x0, panel_y0, panel_x1, panel_y1, fill=text_panel_fill, outline=text_panel_outline)

            menu_size = 14
            menu_x0 = panel_x1 - menu_size - 8
            menu_y0 = panel_y0 + 8
            menu_x1 = menu_x0 + menu_size
            menu_y1 = menu_y0 + menu_size
            canvas.create_rectangle(menu_x0, menu_y0, menu_x1, menu_y1, fill=menu_fill, outline=menu_outline, tags=("menu",))
            for y in (menu_y0 + 3, menu_y0 + 7, menu_y0 + 11):
                canvas.create_line(menu_x0 + 3, y, menu_x1 - 3, y, fill=panel_text_color, width=2, tags=("menu",))

            if self.hooked_fish:
                fish = self.hooked_fish
                progress = fish.progress / fish.strokes
                title = hooked_fish_display_name(fish)
                status_line = f"{self.format_progress_value(fish.progress)} / {fish.strokes} keys"
            else:
                left = self.auto_cast_seconds() - (time.time() - self.cast_started_at)
                self.last_message = f"Casting... {max(left, 0):.1f}s"
                self.status_text.set(self.last_message)
                progress = max(0.0, min(1.0, 1 - max(left, 0) / self.auto_cast_seconds()))
                title = "Casting..."
                status_line = f"Next bite in {max(left, 0):.1f}s"

            title_max_width = int((menu_x0 - panel_x0 - 18) * self.game_scale)
            if len(title) > 30:
                title = f"{title[:27]}..."

            bar_x0, bar_y0 = panel_x0 + 12, panel_y0 + 28
            bar_x1, bar_y1 = panel_x1 - 12, bar_y0 + 8
            canvas.create_text(panel_x0 + 12, panel_y0 + 9, text=title, anchor="nw", fill=panel_text_color, font=self.overlay_font(9, "bold"), width=title_max_width)
            canvas.create_rectangle(bar_x0, bar_y0, bar_x1, bar_y1, fill=progress_bg, outline=menu_outline)
            canvas.create_rectangle(bar_x0, bar_y0, bar_x0 + int((bar_x1 - bar_x0) * progress), bar_y1, fill="#4aa7a1", outline="")
            canvas.create_text(panel_x0 + 12, panel_y0 + 41, text=status_line, anchor="nw", fill=panel_subtext_color, font=self.overlay_font(8))
            stats_line = f"{self.coins} coins | {self.regular_inventory_count()}/{self.inventory_limit}"
            if autosell_countdown:
                stats_line = f"{stats_line} | {autosell_countdown}"
            canvas.create_text(panel_x1 - 12, panel_y0 + 41, text=stats_line, anchor="ne", fill=panel_subtext_color, font=self.overlay_font(8))
            self.draw_resource_deltas(canvas, text_panel_fill, text_panel_outline, minimized=True)
            self.scale_overlay_items()
            return

        pond_fill = spot_style["pond_fill"]
        pond_outline = spot_style["pond_outline"]
        ripple_color = spot_style["ripple_color"]
        pond_shadow = spot_style["pond_shadow"]
        pond_inner = spot_style["pond_inner"]
        pond_highlight = spot_style["pond_highlight"]
        shoreline = spot_style["shoreline"]
        reed_color = spot_style["reed_color"]
        stone_color = spot_style["stone_color"]
        scene_y_offset = -12

        self.draw_soft_oval_shadow(canvas, 31, 92, 278, 178, pond_shadow, 0.32)
        canvas.create_oval(36, 87, 273, 174, fill=pond_shadow, outline="")
        canvas.create_oval(39, 85, 271, 171, fill=self.blend_hex_color("#000000", shoreline, 0.84 if self.dark_theme else 0.9), outline="")
        canvas.create_oval(42, 82, 268, 168, fill=shoreline, outline=pond_outline, width=2)
        canvas.create_oval(47, 88, 263, 164, fill=self.blend_hex_color("#000000", pond_fill, 0.78 if self.dark_theme else 0.86), outline="")
        canvas.create_oval(50, 91, 260, 160, fill=pond_fill, outline="")
        canvas.create_oval(62, 103, 250, 164, fill=self.blend_hex_color("#000000", pond_fill, 0.82 if self.dark_theme else 0.9), outline="")
        canvas.create_oval(72, 99, 230, 146, fill=pond_inner, outline="")
        canvas.create_oval(91, 104, 214, 131, fill=self.blend_hex_color("#ffffff", pond_inner, 0.72 if self.dark_theme else 0.56), outline="")
        if self.hooked_fish:
            shadow_pulse = 1 + (time.time() % 0.7) * 4
            shadow_fish_x = 12
            if self.hooked_fish.kind == "chest":
                shadow_chest_w = 64
                shadow_chest_x = 68 + shadow_fish_x + (110 - shadow_chest_w) // 2
                shadow_chest_y = 108
                self.draw_soft_oval_shadow(canvas, shadow_chest_x - 8, shadow_chest_y + 26, shadow_chest_x + shadow_chest_w + 8, shadow_chest_y + 42, pond_fill, 0.36)
            else:
                self.draw_soft_oval_shadow(canvas, 72 + shadow_fish_x - shadow_pulse * 0.7, 130 - shadow_pulse * 0.15, 166 + shadow_fish_x + shadow_pulse * 0.7, 148 + shadow_pulse * 0.25, pond_fill, 0.18)
        canvas.create_arc(58, 96, 256, 153, start=6, extent=168, style=tk.ARC, outline=ripple_color, width=3)
        canvas.create_arc(78, 107, 230, 151, start=12, extent=156, style=tk.ARC, outline=pond_highlight, width=2)
        canvas.create_arc(100, 116, 203, 148, start=12, extent=150, style=tk.ARC, outline=ripple_color, width=2)
        for x0, y0, x1, y1 in ((63, 151, 76, 158), (236, 146, 251, 154), (48, 124, 59, 130)):
            self.draw_soft_oval_shadow(canvas, x0 + 1, y0 + 3, x1 + 3, y1 + 5, shoreline, 0.24)
            canvas.create_oval(x0, y0, x1, y1, fill=stone_color, outline="")
            canvas.create_oval(x0 + 2, y0 + 1, x1 - 3, y0 + 3, fill=self.blend_hex_color("#ffffff", stone_color, 0.42), outline="")
        self.draw_line_shadow(canvas, [(41, 105), (35, 88), (38, 108)], shoreline, width=2, offset=(3, 3))
        self.draw_line_shadow(canvas, [(263, 105), (276, 84), (270, 109)], shoreline, width=2, offset=(3, 3))
        canvas.create_line([(41, 105), (35, 88), (38, 108)], fill=reed_color, width=2, smooth=True)
        canvas.create_line([(263, 105), (276, 84), (270, 109)], fill=reed_color, width=2, smooth=True)
        if spot_style["accent"] == "moon":
            canvas.create_oval(226, 17, 250, 41, fill="#22314f" if self.dark_theme else "#d9e8fb", outline="")
            canvas.create_oval(230, 21, 246, 37, fill="#dce8ff", outline="")
            canvas.create_oval(234, 25, 237, 28, fill="#b7c7e4", outline="")
            canvas.create_oval(239, 30, 242, 33, fill="#c0cdeb", outline="")
            canvas.create_oval(241, 23, 243, 25, fill="#b7c7e4", outline="")
            canvas.create_line([(72, 92), (98, 86)], fill=pond_highlight, width=2, smooth=True)
        elif spot_style["accent"] == "flowers":
            for fx, fy in ((55, 142), (248, 134), (72, 94)):
                canvas.create_oval(fx - 3, fy - 3, fx + 3, fy + 3, fill="#f7a6c8", outline="")
        elif spot_style["accent"] == "glow":
            for gx, gy in ((82, 111), (213, 129), (155, 96)):
                canvas.create_oval(gx - 2, gy - 2, gx + 2, gy + 2, fill="#8fffea", outline="")
        elif spot_style["accent"] == "creek":
            canvas.create_line([(55, 113), (103, 101), (151, 109), (206, 98), (253, 107)], fill=pond_highlight, width=2, smooth=True)
        elif spot_style["accent"] == "pumpkins":
            canvas.create_oval(226, 24, 242, 41, fill="#e07b2f", outline="#7a3619", width=2)
            canvas.create_oval(237, 24, 251, 41, fill="#c95d28", outline="#7a3619", width=2)
            canvas.create_oval(231, 22, 247, 42, fill="#f08332", outline="#7a3619", width=2)
            canvas.create_line(238, 19, 240, 24, fill="#5b3a1d", width=2)
            canvas.create_oval(234, 30, 237, 33, fill="#2b1710", outline="")
            canvas.create_oval(243, 30, 246, 33, fill="#2b1710", outline="")
            for px, py in ((64, 145), (247, 138)):
                canvas.create_oval(px - 6, py - 4, px + 6, py + 5, fill="#e07b2f", outline="#7a3619")
                canvas.create_line(px, py - 6, px, py - 2, fill="#5b3a1d", width=2)
        elif spot_style["accent"] == "hearts":
            for hx, hy in ((76, 101), (238, 133)):
                canvas.create_oval(hx - 4, hy - 3, hx, hy + 1, fill="#f7a6d8", outline="")
                canvas.create_oval(hx, hy - 3, hx + 4, hy + 1, fill="#f7a6d8", outline="")
                canvas.create_polygon(hx - 5, hy, hx + 5, hy, hx, hy + 7, fill="#f7a6d8", outline="")
        elif spot_style["accent"] == "lava":
            canvas.create_line([(66, 126), (105, 117), (146, 128), (190, 113), (235, 124)], fill=pond_highlight, width=3, smooth=True)
            for sx, sy in ((82, 94), (219, 101), (152, 88)):
                canvas.create_oval(sx - 2, sy - 2, sx + 2, sy + 2, fill="#ffd166", outline="")

        scene_asset_candidates = (
            ("scenes", f"{asset_slug(self.selected_fishing_spot)}.png"),
            ("scenes", "default.png"),
        )
        if self.has_asset_image(scene_asset_candidates):
            scene_clear = self.theme_palette()["bg"] if ACTIVE_DESKTOP_MODE else TRANSPARENT_COLOR
            canvas.create_rectangle(0, 0, w, 174, fill=scene_clear, outline="")
        self.draw_first_asset_image(
            canvas,
            0,
            0,
            scene_asset_candidates,
            anchor="nw",
        )

        if self.hooked_fish:
            pond_progress = max(0.0, min(1.0, self.hooked_fish.progress / self.hooked_fish.strokes))
            ring_track = self.blend_hex_color(ripple_color, pond_fill, 0.45)
            ring_fill = self.blend_hex_color(self.content_accent, pond_highlight, 0.45)
            ring_bbox = (38, 79, 272, 175)
            ring_start = 0
            canvas.create_arc(*ring_bbox, start=ring_start, extent=-360, style=tk.ARC, outline=ring_track, width=3)
            if pond_progress > 0:
                canvas.create_arc(*ring_bbox, start=ring_start, extent=-360 * pond_progress, style=tk.ARC, outline=ring_fill, width=4)

        rod_offset = -int(round(self.rod_pull))
        rod_level = max(0, min(self.equipment_levels.get("rod", 0), len(ROD_VISUALS) - 1))
        rod_style = ROD_VISUALS[rod_level]
        rod_shadow = rod_style["shadow"]
        rod_body = rod_style["body"]
        rod_highlight = rod_style["highlight"]
        metal = rod_style["metal"]
        line_color = rod_style["line"]
        handle = rod_style["handle"]
        rod_width = rod_style["width"]
        rod_points = (42, 72 + rod_offset, 177, 38 + rod_offset)

        self.draw_line_shadow(canvas, [(42, 72 + rod_offset), (177, 38 + rod_offset)], shoreline, width=rod_width + 4, offset=(4, 5))
        self.draw_line_shadow(canvas, [(34, 80 + rod_offset), (62, 72 + rod_offset)], shoreline, width=13, offset=(4, 5))
        self.draw_soft_oval_shadow(canvas, 84, 63 + rod_offset, 108, 84 + rod_offset, shoreline, 0.24)
        if rod_style["glow"]:
            canvas.create_line(40, 74 + rod_offset, 178, 37 + rod_offset, fill=rod_style["glow"], width=rod_width + 7, capstyle=tk.ROUND)
        canvas.create_line(39, 77 + rod_offset, 176, 39 + rod_offset, fill=rod_shadow, width=rod_width + 3, capstyle=tk.ROUND)
        canvas.create_line(*rod_points, fill=rod_body, width=rod_width, capstyle=tk.ROUND)
        canvas.create_line(46, 69 + rod_offset, 159, 40 + rod_offset, fill=rod_highlight, width=2, capstyle=tk.ROUND)
        canvas.create_line(34, 80 + rod_offset, 62, 72 + rod_offset, fill=handle, width=12, capstyle=tk.ROUND)
        canvas.create_line(37, 76 + rod_offset, 63, 69 + rod_offset, fill=rod_style["wrap"], width=4, capstyle=tk.ROUND)
        for index, band_color in enumerate(rod_style["bands"]):
            bx = 71 + index * 29
            by = 64 - index * 8 + rod_offset
            canvas.create_line(bx - 5, by + 5, bx + 7, by + 2, fill=band_color, width=3, capstyle=tk.ROUND)
        canvas.create_oval(84, 58 + rod_offset, 106, 80 + rod_offset, fill=rod_style["reel"], outline=metal, width=2)
        canvas.create_oval(90, 64 + rod_offset, 100, 74 + rod_offset, fill=metal, outline="")
        canvas.create_line(101, 70 + rod_offset, 116, 80 + rod_offset, fill=metal, width=3, capstyle=tk.ROUND)
        for gx, gy in ((126, 51), (153, 43), (176, 39)):
            canvas.create_oval(gx - 3, gy - 3 + rod_offset, gx + 3, gy + 3 + rod_offset, outline=metal, width=2)
        if rod_style["gem"]:
            canvas.create_oval(171, 34 + rod_offset, 181, 44 + rod_offset, fill=rod_style["gem"], outline=metal, width=1)
            canvas.create_oval(174, 36 + rod_offset, 177, 39 + rod_offset, fill="#ffffff", outline="")
        if rod_level >= 9:
            sparkle_color = rod_style["gem"] or rod_highlight
            canvas.create_line(137, 43 + rod_offset, 137, 49 + rod_offset, fill=sparkle_color, width=1)
            canvas.create_line(134, 46 + rod_offset, 140, 46 + rod_offset, fill=sparkle_color, width=1)
        canvas.create_line(176, 39 + rod_offset, 218, 115 + rod_offset, fill=line_color, width=2)
        self.draw_soft_oval_shadow(canvas, 210, 120 + rod_offset, 227, 129 + rod_offset, pond_fill, 0.26)
        canvas.create_oval(211, 111 + rod_offset, 225, 125 + rod_offset, fill="#e34f4f", outline="#702929", width=2)
        canvas.create_oval(215, 114 + rod_offset, 220, 119 + rod_offset, fill="#ffd1d1", outline="")
        self.draw_first_asset_image(
            canvas,
            108,
            60 + rod_offset,
            (("rod", f"level_{rod_level}.png"), ("rod", "default.png")),
        )
        self.draw_asset_image(canvas, 218, 118 + rod_offset, "rod", "bobber.png")
        self.draw_fisher_cat(canvas, shoreline, stone_color)

        if self.hooked_fish:
            fish = self.hooked_fish
            progress = fish.progress / fish.strokes
            pulse = 1 + (time.time() % 0.7) * 4
            fish_x = 12
            fish_outline = "#102f32" if self.dark_theme else "#21413e"
            fin_color = "#3f9f98" if self.dark_theme else "#62bfb8"
            canvas.create_arc(68 + fish_x - pulse, 92 - pulse, 178 + fish_x + pulse, 149 + pulse, start=205, extent=132, style=tk.ARC, outline=pond_highlight, width=2)
            fish_asset_drawn = self.draw_hooked_fish_asset(canvas, fish, fish_x)
            if fish_asset_drawn:
                pass
            elif fish.kind == "chest":
                chest_w = 64
                chest_x = 68 + fish_x + (110 - chest_w) // 2
                chest_y = 108
                canvas.create_oval(chest_x - 7, chest_y + 25, chest_x + chest_w + 7, chest_y + 40, fill=pond_inner, outline=pond_highlight, width=1)
                canvas.create_rectangle(chest_x, chest_y + 13, chest_x + chest_w, chest_y + 34, fill="#9b5f2b", outline="#4e2c18", width=2)
                canvas.create_arc(chest_x, chest_y - 2, chest_x + chest_w, chest_y + 28, start=0, extent=180, style=tk.PIESLICE, fill="#c9823b", outline="#4e2c18", width=2)
                canvas.create_rectangle(chest_x + 2, chest_y + 27, chest_x + chest_w - 2, chest_y + 33, fill=self.blend_hex_color("#000000", "#9b5f2b", 0.72), outline="")
                canvas.create_arc(chest_x + 5, chest_y + 2, chest_x + chest_w - 5, chest_y + 18, start=0, extent=180, style=tk.ARC, outline=self.blend_hex_color("#ffffff", "#c9823b", 0.48), width=2)
                canvas.create_rectangle(chest_x + 28, chest_y + 6, chest_x + 36, chest_y + 34, fill="#f0c35a", outline="#6d4a1f", width=1)
                canvas.create_rectangle(chest_x, chest_y + 20, chest_x + chest_w, chest_y + 26, fill="#6f3f20", outline="")
                canvas.create_rectangle(chest_x + 28, chest_y + 18, chest_x + 36, chest_y + 27, fill="#ffe08a", outline="#6d4a1f", width=1)
                canvas.create_oval(chest_x + 31, chest_y + 21, chest_x + 33, chest_y + 23, fill="#6d4a1f", outline="")
            elif fish.kind == "blessing":
                visitor = BLESSING_VISITOR_BY_ID.get(fish.blessing_id, {})
                visitor_color = visitor.get("color", fish.color)
                glow_color = self.blend_hex_color("#ffffff", visitor_color, 0.35)
                shadow_color = self.blend_hex_color("#000000", visitor_color, 0.72)
                center_x = 119 + fish_x
                center_y = 119
                canvas.create_oval(center_x - 52 - pulse, center_y + 14, center_x + 52 + pulse, center_y + 34, fill=self.blend_hex_color("#000000", pond_fill, 0.8), outline="")
                if fish.blessing_id == "squid":
                    canvas.create_oval(center_x - 32 - pulse, center_y - 20 - pulse, center_x + 32 + pulse, center_y + 18 + pulse, fill=visitor_color, outline=fish_outline, width=2)
                    for tx in (-22, -10, 2, 14, 26):
                        canvas.create_line(center_x + tx, center_y + 13, center_x + tx - 8, center_y + 32, fill=shadow_color, width=3, capstyle=tk.ROUND)
                elif fish.blessing_id == "eel":
                    canvas.create_line([(center_x - 48 - pulse, center_y + 8), (center_x - 18, center_y - 6 - pulse), (center_x + 12, center_y + 10), (center_x + 46 + pulse, center_y - 4)], fill=visitor_color, width=16, smooth=True, capstyle=tk.ROUND)
                    canvas.create_line([(center_x - 43, center_y + 10), (center_x - 14, center_y - 2), (center_x + 14, center_y + 11), (center_x + 42, center_y - 2)], fill=glow_color, width=4, smooth=True, capstyle=tk.ROUND)
                elif fish.blessing_id == "turtle":
                    canvas.create_oval(center_x - 38 - pulse, center_y - 14 - pulse, center_x + 36 + pulse, center_y + 24 + pulse, fill=visitor_color, outline=fish_outline, width=2)
                    canvas.create_oval(center_x + 28, center_y - 7, center_x + 48, center_y + 11, fill=glow_color, outline=fish_outline, width=1)
                    canvas.create_arc(center_x - 24, center_y - 7, center_x + 18, center_y + 20, start=20, extent=145, style=tk.ARC, outline=shadow_color, width=2)
                else:
                    canvas.create_oval(center_x - 44 - pulse, center_y - 16 - pulse, center_x + 44 + pulse, center_y + 24 + pulse, fill=visitor_color, outline=fish_outline, width=2)
                    canvas.create_oval(center_x + 27, center_y - 5, center_x + 35, center_y + 3, fill=fish_outline, outline="")
                    canvas.create_arc(center_x - 20, center_y - 7, center_x + 24, center_y + 17, start=205, extent=115, style=tk.ARC, outline=glow_color, width=3)
            else:
                self.draw_fish_sparkles(canvas, fish, fish_x, pond_highlight)
                part_colors = self.pride_fish_part_colors(fish, fish.color, fin_color)
                if part_colors.get("body_gradient"):
                    self.draw_gradient_fish_body(canvas, fish_x, fish_outline, part_colors["body_gradient"])
                    self.draw_gradient_fish_tail(canvas, fish_x, fish_outline, part_colors.get("tail_gradient", part_colors["body_gradient"]))
                else:
                    canvas.create_oval(78 + fish_x - pulse, 99 - pulse, 162 + fish_x + pulse, 137 + pulse, fill=part_colors["body"], outline=fish_outline, width=2)
                    canvas.create_polygon(86 + fish_x, 118, 50 + fish_x, 96, 56 + fish_x, 119, 50 + fish_x, 141, fill=part_colors["tail"], outline=fish_outline)
                canvas.create_polygon(128 + fish_x, 100, 105 + fish_x, 87, 97 + fish_x, 103, fill=part_colors["top_fin"], outline=fish_outline)
                canvas.create_polygon(124 + fish_x, 136, 100 + fish_x, 148, 94 + fish_x, 133, fill=part_colors["bottom_fin"], outline=fish_outline)
                scale_highlight = self.blend_hex_color("#ffffff", part_colors["body"], 0.42)
                for scale_x, scale_y in ((104, 106), (117, 106), (98, 118), (111, 118)):
                    canvas.create_arc(scale_x + fish_x, scale_y, scale_x + fish_x + 18, scale_y + 18, start=50, extent=125, style=tk.ARC, outline=scale_highlight, width=3)
                    canvas.create_arc(scale_x + fish_x, scale_y, scale_x + fish_x + 18, scale_y + 18, start=50, extent=125, style=tk.ARC, outline=fish_outline, width=2)
                canvas.create_arc(95 + fish_x, 104, 151 + fish_x, 126, start=22, extent=150, style=tk.ARC, outline="#ffffff", width=2)
                canvas.create_oval(134 + fish_x, 112, 142 + fish_x, 120, fill=fish_outline, outline="")
                canvas.create_oval(137 + fish_x, 114, 139 + fish_x, 116, fill="#ffffff", outline="")
            label = hooked_fish_display_name(fish)
            if len(label) > 24:
                label = f"{label[:21]}..."
            progress_label = f"{self.format_progress_value(fish.progress)}/{fish.strokes}"
        else:
            left = self.auto_cast_seconds() - (time.time() - self.cast_started_at)
            self.last_message = f"Casting... {max(left, 0):.1f}s"
            self.status_text.set(self.last_message)
            label = "Casting..."
            progress_label = ""

        canvas.move("all", 0, scene_y_offset)

        self.draw_idle_zz(canvas, subtext_color)
        if self.fish_bubbles:
            bubble_outline = "#bdfaff" if self.dark_theme else "#f5ffff"
            bubble_highlight = "#f3ffff" if self.dark_theme else "#ffffff"
            self.draw_fish_bubbles(canvas, bubble_outline, bubble_highlight)

        panel_y0 = 174
        panel_y1 = 228
        if self.game_info_panel_pinned.get() or self.game_info_panel_visible:
            self.draw_panel_shadow(canvas, 18, panel_y0, w - 18, panel_y1, text_panel_fill)
            canvas.create_rectangle(18, panel_y0, w - 18, panel_y1, fill=text_panel_fill, outline=text_panel_outline)

            menu_size = 14
            menu_x0 = w - 18 - menu_size
            menu_y0 = panel_y0 + 8
            menu_x1 = w - 18
            menu_y1 = menu_y0 + menu_size
            canvas.create_rectangle(menu_x0, menu_y0, menu_x1, menu_y1, fill=menu_fill, outline=menu_outline, tags=("menu",))
            for y in (menu_y0 + 3, menu_y0 + 7, menu_y0 + 11):
                canvas.create_line(menu_x0 + 3, y, menu_x1 - 3, y, fill=panel_text_color, width=2, tags=("menu",))

            progress_column_width = 72
            progress_x = menu_x0 - 8
            label_width = max(92, progress_x - 26 - progress_column_width)
            if self.hooked_fish is not None and self.hooked_fish.kind == "chest":
                cut_x1 = menu_x0 - 8
                cut_x0 = cut_x1 - 64
                cut_y0 = panel_y0 + 7
                cut_y1 = cut_y0 + 17
                cut_fill = self.blend_hex_color(palette["danger_fg"], text_panel_fill, 0.36)
                cut_outline = self.blend_hex_color(palette["danger_fg"], text_panel_outline, 0.18)
                canvas.create_rectangle(cut_x0, cut_y0, cut_x1, cut_y1, fill=cut_fill, outline=cut_outline, tags=("cut_line",))
                canvas.create_text((cut_x0 + cut_x1) // 2, (cut_y0 + cut_y1) // 2, text="Cut Line", anchor="center", fill=panel_text_color, font=self.overlay_font(7, "bold"), tags=("cut_line",))
                progress_x = cut_x0 - 8
                label_width = max(92, progress_x - 26 - progress_column_width)

            canvas.create_text(26, panel_y0 + 8, text=label, anchor="nw", fill=panel_text_color, font=self.overlay_font(9, "bold"), width=int(label_width * self.game_scale))
            if progress_label:
                canvas.create_text(progress_x, panel_y0 + 8, text=progress_label, anchor="ne", fill=panel_text_color, font=self.overlay_font(9, "bold"))
            stats_line = f"{self.coins} coins | {self.regular_inventory_count()}/{self.inventory_limit} fish"
            if autosell_countdown:
                stats_line = f"{stats_line} | {autosell_countdown}"
            blessing_compact = self.blessing_compact_status_text()
            canvas.create_text(26, panel_y0 + 21, text=stats_line, anchor="nw", fill=panel_subtext_color, font=self.overlay_font(8))
            if blessing_compact:
                canvas.create_text(26, panel_y0 + 34, text=blessing_compact, anchor="nw", fill=panel_subtext_color, font=self.overlay_font(8), width=int((w - 52) * self.game_scale))
        self.draw_resource_deltas(canvas, text_panel_fill, text_panel_outline)
        self.scale_overlay_items()

    def fishing_spot_scene_style(self):
        styles = {
            "pond": {
                "pond_fill": "#243447" if self.dark_theme else "#cfe5f1",
                "pond_outline": "#4f6c80" if self.dark_theme else "#7d9db1",
                "ripple_color": "#3b5a71" if self.dark_theme else "#d7ecf4",
                "pond_shadow": "#172332" if self.dark_theme else "#b7ccd8",
                "pond_inner": "#2f526b" if self.dark_theme else "#bde0ee",
                "pond_highlight": "#5c7f97" if self.dark_theme else "#e7f7fb",
                "shoreline": "#304157" if self.dark_theme else "#dbe7de",
                "reed_color": "#607451" if self.dark_theme else "#7fa26e",
                "stone_color": "#566172" if self.dark_theme else "#b9c2bc",
                "accent": "none",
            },
            "creek": {
                "pond_fill": "#254f48" if self.dark_theme else "#b8e2d8",
                "pond_outline": "#587869" if self.dark_theme else "#7ba391",
                "ripple_color": "#4c7d72" if self.dark_theme else "#d9f2eb",
                "pond_shadow": "#142821" if self.dark_theme else "#a9cfc1",
                "pond_inner": "#317063" if self.dark_theme else "#99d6c9",
                "pond_highlight": "#77a99a" if self.dark_theme else "#f0fff9",
                "shoreline": "#334834" if self.dark_theme else "#d6ead8",
                "reed_color": "#7d9256" if self.dark_theme else "#6eaa68",
                "stone_color": "#5f6d63" if self.dark_theme else "#afbeb1",
                "accent": "creek",
            },
            "pier": {
                "pond_fill": "#182742" if self.dark_theme else "#b9d5f0",
                "pond_outline": "#4a638b" if self.dark_theme else "#7899bd",
                "ripple_color": "#324d79" if self.dark_theme else "#d7eaff",
                "pond_shadow": "#0d1728" if self.dark_theme else "#a9bfd8",
                "pond_inner": "#203a68" if self.dark_theme else "#96c5ec",
                "pond_highlight": "#6f91c7" if self.dark_theme else "#eff8ff",
                "shoreline": "#202a3a" if self.dark_theme else "#d8e0e9",
                "reed_color": "#53617a" if self.dark_theme else "#7890a9",
                "stone_color": "#566070" if self.dark_theme else "#b6c1cc",
                "accent": "moon",
            },
            "garden": {
                "pond_fill": "#2a665e" if self.dark_theme else "#bfeadd",
                "pond_outline": "#648b76" if self.dark_theme else "#86b69c",
                "ripple_color": "#5d9d91" if self.dark_theme else "#e0f8ef",
                "pond_shadow": "#18352f" if self.dark_theme else "#aad7c6",
                "pond_inner": "#3b8076" if self.dark_theme else "#9bdcca",
                "pond_highlight": "#8fc9bd" if self.dark_theme else "#f5fffb",
                "shoreline": "#46533d" if self.dark_theme else "#e6efd9",
                "reed_color": "#91a45f" if self.dark_theme else "#7fbf72",
                "stone_color": "#7a7465" if self.dark_theme else "#c6baa0",
                "accent": "flowers",
            },
            "halloween": {
                "pond_fill": "#3a2b4a" if self.dark_theme else "#d8bfdc",
                "pond_outline": "#78536f" if self.dark_theme else "#a87894",
                "ripple_color": "#a15c42" if self.dark_theme else "#f0b080",
                "pond_shadow": "#20152a" if self.dark_theme else "#c7aacd",
                "pond_inner": "#56365a" if self.dark_theme else "#c99fc6",
                "pond_highlight": "#e07b45" if self.dark_theme else "#ffe0ad",
                "shoreline": "#4b3025" if self.dark_theme else "#ead0b2",
                "reed_color": "#a15f2b" if self.dark_theme else "#ce7d37",
                "stone_color": "#6d5c61" if self.dark_theme else "#b9a2a8",
                "accent": "pumpkins",
            },
            "cute": {
                "pond_fill": "#8bd6df" if self.dark_theme else "#c8f3f5",
                "pond_outline": "#cc8fbe" if self.dark_theme else "#dda6ca",
                "ripple_color": "#f7b4d8" if self.dark_theme else "#fff0f8",
                "pond_shadow": "#365a69" if self.dark_theme else "#b7dee2",
                "pond_inner": "#7acbd8" if self.dark_theme else "#afeaf0",
                "pond_highlight": "#ffe7f3" if self.dark_theme else "#ffffff",
                "shoreline": "#6c5f89" if self.dark_theme else "#f5d8eb",
                "reed_color": "#c9d36c" if self.dark_theme else "#9fca78",
                "stone_color": "#d6a9c8" if self.dark_theme else "#e8bad7",
                "accent": "hearts",
            },
            "abyss": {
                "pond_fill": "#111f34" if self.dark_theme else "#9bcbdc",
                "pond_outline": "#315c75" if self.dark_theme else "#5a91a8",
                "ripple_color": "#23556c" if self.dark_theme else "#d0f8ff",
                "pond_shadow": "#07101e" if self.dark_theme else "#87b3c2",
                "pond_inner": "#143e55" if self.dark_theme else "#78bdd0",
                "pond_highlight": "#66d9d7" if self.dark_theme else "#efffff",
                "shoreline": "#1a2635" if self.dark_theme else "#d4e5ea",
                "reed_color": "#4f8f8b" if self.dark_theme else "#68aaa4",
                "stone_color": "#455362" if self.dark_theme else "#a6bbc1",
                "accent": "glow",
            },
            "lava": {
                "pond_fill": "#5a1d12" if self.dark_theme else "#d45931",
                "pond_outline": "#a64622" if self.dark_theme else "#9f3c22",
                "ripple_color": "#ff8f2f" if self.dark_theme else "#ffc15c",
                "pond_shadow": "#250b08" if self.dark_theme else "#a93a24",
                "pond_inner": "#8f2d14" if self.dark_theme else "#f06f32",
                "pond_highlight": "#ffd166" if self.dark_theme else "#ffe28a",
                "shoreline": "#2d2020" if self.dark_theme else "#6c4a3c",
                "reed_color": "#c2451b" if self.dark_theme else "#b34a27",
                "stone_color": "#3f3432" if self.dark_theme else "#6f5a52",
                "accent": "lava",
            },
        }
        return styles.get(self.selected_fishing_spot, styles["pond"])

    def on_overlay_press(self, event):
        if ACTIVE_DESKTOP_MODE:
            self.focus_force()
            self.overlay.focus_set()
        self.mark_player_activity()
        if not self.minimized and self.pointer_over_game_info_panel(event):
            self.show_game_info_panel()
        clicked = self.overlay.find_withtag(tk.CURRENT)
        if clicked and "menu" in self.overlay.gettags(clicked[0]):
            self.toggle_menu()
            self.drag_start = None
            return
        if clicked and "cut_line" in self.overlay.gettags(clicked[0]):
            self.cut_treasure_chest_line()
            self.drag_start = None
            return
        if self.click_hits_cat(event):
            self.cat_pets += 1
            self.last_message = f"You pet Aphrodite, The TypeCat. ({self.cat_pets})"
            self.refresh_all()
            self.draw_overlay()
            self.drag_start = None
            return
        if self.click_hits_fish(event):
            self.fish_clicks += 1
            self.spawn_fish_bubbles(event)
            self.refresh_all()
            self.draw_overlay()
            self.drag_start = None
            return
        self.drag_start = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())

    def on_overlay_right_click(self, event):
        if ACTIVE_DESKTOP_MODE:
            self.focus_force()
            self.overlay.focus_set()
        self.mark_player_activity()
        clicked = self.overlay.find_withtag(tk.CURRENT)
        if clicked and "menu" in self.overlay.gettags(clicked[0]):
            self.toggle_minimize()
        else:
            self.toggle_menu()

    def on_overlay_motion(self, event):
        if not self.minimized:
            self.show_game_info_panel()

    def on_overlay_leave(self, event):
        self.last_info_panel_hover_at = time.time()

    def toggle_minimize(self):
        self.close_menu()
        self.minimized = not self.minimized
        self.set_window_state(self.minimized)

    def set_window_state(self, minimized):
        x = self.winfo_x()
        y = self.winfo_y()
        self.window_x = x
        self.window_y = y
        width, height = self.overlay_size()
        self.window_x, self.window_y = self.clamp_overlay_position(x, y, width, height)
        self.geometry(f"{width}x{height}+{self.window_x}+{self.window_y}")
        self.overlay.config(width=width, height=height)
        self.position_menu()
        self.draw_overlay()

    def on_overlay_drag(self, event):
        if not self.drag_start:
            return
        start_x, start_y, window_x, window_y = self.drag_start
        new_x = window_x + event.x_root - start_x
        new_y = window_y + event.y_root - start_y
        width, height = self.overlay_size()
        new_x, new_y = self.clamp_overlay_position(new_x, new_y, width, height)
        self.window_x = new_x
        self.window_y = new_y
        self.geometry(f"+{new_x}+{new_y}")
        self.position_menu()

    def on_overlay_release(self, event):
        self.drag_start = None

    def current_equipment_item(self, slot):
        return EQUIPMENT_TRACKS[slot][self.equipment_levels[slot]]

    def available_equipment_upgrades(self):
        upgrades = []
        for slot in EQUIPMENT_SLOTS:
            next_level = self.equipment_levels[slot] + 1
            if next_level < len(EQUIPMENT_TRACKS[slot]):
                upgrades.append((slot, EQUIPMENT_TRACKS[slot][next_level]))
        return upgrades

    def current_inventory_limit(self):
        if self.backpack_level <= 0:
            return 8
        return BACKPACK_UPGRADES[self.backpack_level - 1]["slots"]

    def blessing_trophy_slots(self):
        return 1 + self.backpack_level // 5

    def stored_blessing_count(self):
        return sum(1 for fish in self.inventory if fish_is_blessing(fish))

    def regular_inventory_count(self):
        return sum(1 for fish in self.inventory if not fish_is_blessing(fish))

    def next_backpack_upgrade(self):
        if self.backpack_level >= len(BACKPACK_UPGRADES):
            return None
        return BACKPACK_UPGRADES[self.backpack_level]

    def backpack_status_text(self):
        upgrade = self.next_backpack_upgrade()
        trophy_text = f" | Blessing trophy slots {self.stored_blessing_count()} / {self.blessing_trophy_slots()}"
        if not upgrade:
            return f"Backpack level {self.backpack_level}: 96 / 96 slots{trophy_text}"
        return (
            f"Backpack level {self.backpack_level}: {self.inventory_limit} / 96 slots | "
            f"Next: {upgrade['slots']} slots for {self.shop_price(upgrade['price'])} coins{trophy_text}"
        )

    def autosell_status_text(self):
        if self.autosell_level <= 0:
            return "Current: Not installed"
        current = AUTOSALE_UPGRADES[self.autosell_level - 1]
        minutes = AUTOSELL_SECONDS // 60
        return f"Current: {current['name']} - {current['percent']}% inventory every {minutes} min"

    def banked_upgrade_status_text(self):
        if self.banked_upgrade_level <= 0:
            return "Current: Base progress (no shop discount)"
        current = BANKED_KEY_UPGRADES[self.banked_upgrade_level - 1]
        discount = round((1 - self.shop_cost_multiplier()) * 100)
        return f"Current: {current['name']} - {current['mult']:.2f}x progress, -{discount}% shop costs"

    def fishing_spot_by_id(self, spot_id):
        for spot in FISHING_SPOTS:
            if spot["id"] == spot_id:
                return spot
        return FISHING_SPOTS[0]

    def fishing_spot_status_text(self):
        spot = self.fishing_spot_by_id(self.selected_fishing_spot)
        return f"Current: {spot['name']} | Unlocked {len(self.unlocked_fishing_spots)} / {len(FISHING_SPOTS)}"

    def player_has_relics(self):
        return any(safe_int(count) > 0 for count in self.relics.values())

    def player_has_potions(self):
        self.cleanup_active_potions()
        return bool(self.potions) or any(safe_int(count) > 0 for count in self.stored_potions.values())

    def owns_all_relic_types(self):
        return all(safe_int(self.relics.get(relic["id"], 0)) > 0 for relic in RELICS)

    def relic_effect_text(self, relic, count=1):
        effects = []
        key_rate = safe_int(relic.get("keys", 0)) * count
        coin_rate = safe_int(relic.get("coins", 0)) * count
        if key_rate:
            effects.append(f"+{key_rate} Cast Tokens / 5 min")
        if coin_rate:
            effects.append(f"+{coin_rate} coins / 5 min")
        return " | ".join(effects) if effects else "quietly hums"

    def relic_status_text(self):
        key_rate = self.relic_key_rate()
        coin_rate = self.relic_coin_rate()
        if key_rate <= 0 and coin_rate <= 0:
            return "Relics: none"
        parts = []
        for relic in RELICS:
            count = safe_int(self.relics.get(relic["id"], 0))
            if count > 0:
                suffix = f" x{count}" if count > 1 else ""
                parts.append(f"{relic['name']}{suffix}")
        rates = []
        if key_rate:
            rates.append(f"+{key_rate} Cast Tokens / 5 min")
        if coin_rate:
            rates.append(f"+{coin_rate} coins / 5 min")
        return f"Relics: {', '.join(parts)} | {' | '.join(rates)}"

    def potion_effect_text(self, potion):
        effects = []
        key_rate = safe_int(potion.get("keys", 0))
        coin_rate = safe_int(potion.get("coins", 0))
        if key_rate:
            effects.append(f"+{key_rate} Cast Tokens / 5 min")
        if coin_rate:
            effects.append(f"+{coin_rate} coins / 5 min")
        return " | ".join(effects) if effects else "quietly bubbles"

    def potion_status_text(self):
        self.cleanup_active_potions()
        if not self.potions and not any(safe_int(count) > 0 for count in self.stored_potions.values()):
            return "Potions: none"
        counts = {}
        for potion_id, count in self.stored_potions.items():
            counts[potion_id] = safe_int(count)
        parts = []
        for potion in POTIONS:
            count = counts.get(potion["id"], 0)
            if count <= 0:
                continue
            suffix = f" x{count}" if count > 1 else ""
            parts.append(f"{potion['name']}{suffix} ready")
        rates = []
        key_rate = self.potion_key_rate()
        coin_rate = self.potion_coin_rate()
        if key_rate:
            rates.append(f"+{key_rate} Cast Tokens / 5 min")
        if coin_rate:
            rates.append(f"+{coin_rate} coins / 5 min")
        active_text = f"Active {' | '.join(rates)}" if rates else ""
        if parts and active_text:
            return f"Potions: {', '.join(parts)} | {active_text}"
        if parts:
            return f"Potions: {', '.join(parts)}"
        return f"Potions: {active_text}"

    def blessing_slot_name(self, slot):
        names = {
            "rod": "rod",
            "head": "accuracy",
            "body": "luck",
            "legs": "Cast Token",
        }
        return names.get(slot, "visitor")

    def blessing_effect_text(self, slot, bonus):
        bonus = float(bonus)
        if slot == "rod":
            return f"{round(bonus * 100)}% fewer keystrokes"
        if slot == "head":
            return f"+{bonus * 100:.1f}% accuracy"
        if slot == "body":
            return f"+{int(round(bonus))} fish luck"
        if slot == "legs":
            return f"+{round(bonus * 100)}% Cast Token chance"
        return "a temporary boost"

    def blessing_compact_slot_name(self, slot):
        names = {
            "rod": "Rod",
            "head": "Acc",
            "body": "Luck",
            "legs": "CT",
        }
        return names.get(slot, "Boost")

    def blessing_compact_status_text(self):
        self.cleanup_active_blessings()
        if not self.active_blessings:
            return ""
        parts = []
        for slot in EQUIPMENT_SLOTS:
            blessing = self.active_blessings.get(slot)
            if not blessing:
                continue
            remaining = self.blessing_remaining_count(blessing)
            suffix = "c" if slot == "body" else "k"
            parts.append(f"{self.blessing_compact_slot_name(slot)} {remaining}{suffix}")
        return "Blessing " + ", ".join(parts)

    def cleanup_active_blessings(self):
        expired = [slot for slot, blessing in self.active_blessings.items() if self.blessing_remaining_count(blessing) <= 0]
        for slot in expired:
            self.active_blessings.pop(slot, None)
        return bool(expired)

    def blessing_remaining_count(self, blessing):
        if not isinstance(blessing, dict):
            return 0
        slot = str(blessing.get("slot", ""))
        key = "remaining_catches" if slot == "body" else "remaining_uses"
        return safe_int(blessing.get(key, 0), 0)

    def consume_blessing_keystroke(self):
        changed = False
        for slot in ("rod", "head", "legs"):
            blessing = self.active_blessings.get(slot)
            if not blessing:
                continue
            blessing["remaining_uses"] = max(0, safe_int(blessing.get("remaining_uses", 0), 0) - 1)
            changed = True
        return self.cleanup_active_blessings() or changed

    def consume_blessing_catch(self, slot):
        blessing = self.active_blessings.get(slot)
        if not blessing:
            return False
        blessing["remaining_catches"] = max(0, safe_int(blessing.get("remaining_catches", 0), 0) - 1)
        return self.cleanup_active_blessings()

    def blessing_bonus(self, slot):
        self.cleanup_active_blessings()
        blessing = self.active_blessings.get(slot)
        if not blessing:
            return 0
        return float(blessing.get("bonus", 0))

    def blessing_status_text(self):
        self.cleanup_active_blessings()
        if not self.active_blessings:
            return "Blessings: none"
        parts = []
        for slot in EQUIPMENT_SLOTS:
            blessing = self.active_blessings.get(slot)
            if not blessing:
                continue
            remaining = self.blessing_remaining_count(blessing)
            bonus = float(blessing.get("bonus", 0))
            effect = self.blessing_effect_text(slot, bonus)
            unit = "catches" if slot == "body" else "keystrokes"
            parts.append(f"{blessing.get('name', 'Visitor')} {effect} ({remaining} {unit} left)")
        return f"Blessings: {' | '.join(parts)}"

    def stroke_multiplier(self):
        base = self.current_equipment_item("rod").get("stroke_mult", 1.0)
        return base

    def rod_blessing_progress_multiplier(self):
        bonus = self.blessing_bonus("rod")
        return 1.0 / max(0.45, 1 - bonus) if bonus > 0 else 1.0

    def luck_bonus(self):
        return self.current_equipment_item("body").get("luck", 0) + int(round(self.blessing_bonus("body")))

    def accuracy_chance(self):
        return min(0.08, self.current_equipment_item("head").get("accuracy", 0.0) + self.blessing_bonus("head"))

    def cast_multiplier(self):
        return 1.0

    def banked_key_bonus(self):
        return min(0.22, self.current_equipment_item("legs").get("banked_bonus", 0.0) + self.blessing_bonus("legs"))

    def auto_cast_seconds(self):
        return AUTO_CAST_SECONDS * self.cast_multiplier()

    def item_effect_text(self, slot, item):
        if slot == "rod":
            reduction = round((1 - item.get("stroke_mult", 1.0)) * 100)
            return f"{reduction}% fewer keystrokes"
        if slot == "head":
            return f"{item.get('accuracy', 0.0) * 100:.1f}% double-keystroke chance"
        if slot == "body":
            return f"+{item.get('luck', 0)} fish luck"
        if slot == "legs":
            bonus = round(item.get("banked_bonus", 0.0) * 100)
            return f"+{bonus}% chance for extra Cast Tokens"
        return ""

    def startup_command(self):
        if getattr(sys, "frozen", False):
            return subprocess.list2cmdline([sys.executable])
        return subprocess.list2cmdline([sys.executable, str(Path(sys.argv[0]).resolve())])

    def startup_registry_command(self):
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_PATH) as key:
                command, _ = winreg.QueryValueEx(key, APP_NAME)
                return command
        except FileNotFoundError:
            return None
        except OSError:
            return None

    def sync_start_with_windows_setting(self):
        self.start_with_windows_var.set(self.startup_registry_command() is not None)

    def set_start_with_windows(self, enabled):
        if winreg is None:
            raise OSError("Windows startup registry is not available.")
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, self.startup_command())
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass

    def on_start_with_windows_toggle(self):
        try:
            self.set_start_with_windows(self.start_with_windows_var.get())
        except OSError as exc:
            self.sync_start_with_windows_setting()
            messagebox.showerror(
                "Start with Windows",
                f"Could not update Windows startup setting: {exc}",
                parent=self.menu if self.menu is not None else self,
            )

    def on_background_key_capture_toggle(self):
        if self.background_key_capture_enabled.get():
            if not self.background_key_capture_consent_granted:
                if not self.ask_background_key_capture_consent():
                    self.background_key_capture_enabled.set(False)
                    self.configure_input_capture()
                    self.save()
                    return
                self.background_key_capture_consent_granted = True
        else:
            self.background_key_capture_consent_granted = False

        self.configure_input_capture()
        self.save()

    def on_discord_presence_toggle(self):
        if self.discord_presence_enabled.get():
            self.setup_discord_presence()
        else:
            self.close_discord_presence()
            self.discord_status_text.set("Discord Rich Presence: disabled")

    def confirm_reset_save(self):
        if not messagebox.askyesno(
            "Reset Save",
            "Reset all coins, inventory, collection log, achievements, keystrokes, backpack upgrades, and equipment upgrades?",
            parent=self.menu if self.menu is not None else self,
        ):
            return
        self.reset_save()

    def reset_save(self):
        self.coins = 0
        self.total_keystrokes = 0
        self.banked_keys = 0
        self.banked_upgrade_level = 0
        self.autosell_level = 0
        self.last_autosell_at = time.time()
        self.backpack_level = 0
        self.inventory_limit = 8
        self.inventory = []
        self.collection_log = {}
        self.achievements_unlocked = set()
        self.unlocked_fishing_spots = {"pond"}
        self.selected_fishing_spot = "pond"
        self.equipment_levels = DEFAULT_EQUIPMENT_LEVELS.copy()
        self.hooked_fish = None
        self.cast_started_at = time.time()
        self.fish_clicks = 0
        self.cat_pets = 0
        self.fish_since_last_treasure_chest = TREASURE_CHEST_MIN_FISH_BETWEEN
        self.relics = {}
        self.stored_potions = {}
        self.potions = []
        self.active_blessings = {}
        self.last_relic_payout_at = time.time()
        self.event_log = []
        self.resource_deltas = []
        self.menu_docked = True
        self.menu_docked_var.set(True)
        self.update_menu_dock_text()
        self.last_message = "Save reset. Casting..."
        for save_path in unique_paths([SAVE_FILE, *legacy_save_candidates()]):
            try:
                save_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        self.refresh_all()

    def load_equipment_levels(self, data):
        levels = DEFAULT_EQUIPMENT_LEVELS.copy()
        saved_levels = data.get("equipment_levels")
        if isinstance(saved_levels, dict):
            for slot in EQUIPMENT_SLOTS:
                level = int(saved_levels.get(slot, 0))
                levels[slot] = max(0, min(level, len(EQUIPMENT_TRACKS[slot]) - 1))
            return levels

        legacy_equipped = data.get("equipped", {})
        legacy_map = {
            "rod_bamboo": ("rod", 0),
            "rod_oak": ("rod", 2),
            "rod_starlight": ("rod", 7),
            "hat_none": ("head", 0),
            "hat_bucket": ("head", 2),
            "hat_captain": ("head", 3),
            "shirt_tee": ("body", 0),
            "shirt_slicker": ("body", 2),
            "pants_denim": ("legs", 0),
            "pants_waders": ("legs", 2),
        }
        for item_id in legacy_equipped.values():
            if item_id in legacy_map:
                slot, level = legacy_map[item_id]
                levels[slot] = max(levels[slot], level)
        return levels

    def normalize_relics(self, data):
        saved_relics = data.get("relics", {})
        if not isinstance(saved_relics, dict):
            return {}
        valid_ids = {relic["id"] for relic in RELICS}
        relics = {}
        for relic_id, count in saved_relics.items():
            relic_id = str(relic_id)
            count = safe_int(count)
            if relic_id in valid_ids and count > 0:
                relics[relic_id] = count
        return relics

    def normalize_potions(self, data):
        saved_potions = data.get("potions", [])
        if not isinstance(saved_potions, list):
            return []
        valid_ids = {potion["id"] for potion in POTIONS}
        now = time.time()
        potions = []
        for active_potion in saved_potions:
            if not isinstance(active_potion, dict):
                continue
            potion_id = str(active_potion.get("id", ""))
            if potion_id not in valid_ids:
                continue
            try:
                expires_at = float(active_potion.get("expires_at", 0))
            except (TypeError, ValueError):
                continue
            if expires_at > now:
                potions.append({"id": potion_id, "expires_at": expires_at})
        return potions

    def normalize_stored_potions(self, data):
        saved_potions = data.get("stored_potions", {})
        if not isinstance(saved_potions, dict):
            return {}
        valid_ids = {potion["id"] for potion in POTIONS}
        potions = {}
        for potion_id, count in saved_potions.items():
            potion_id = str(potion_id)
            count = safe_int(count)
            if potion_id in valid_ids and count > 0:
                potions[potion_id] = count
        return potions

    def normalize_active_blessings(self, saved_blessings):
        if not isinstance(saved_blessings, dict):
            return {}
        blessings = {}
        for slot, blessing in saved_blessings.items():
            slot = str(slot)
            if slot not in EQUIPMENT_SLOTS or not isinstance(blessing, dict):
                continue
            try:
                bonus = float(blessing.get("bonus", 0))
            except (TypeError, ValueError):
                continue
            if bonus <= 0:
                continue
            strokes = max(1, safe_int(blessing.get("strokes", 1), 1))
            if slot == "body":
                remaining = safe_int(blessing.get("remaining_catches", 0), 0)
                if remaining <= 0 and "expires_at" in blessing:
                    try:
                        if float(blessing.get("expires_at", 0)) <= time.time():
                            continue
                    except (TypeError, ValueError):
                        continue
                    remaining = self.blessing_use_count(strokes, slot)
                remaining = min(BLESSING_LUCK_CATCH_CAP, remaining)
                remaining_key = "remaining_catches"
            else:
                remaining = safe_int(blessing.get("remaining_uses", 0), 0)
                if remaining <= 0 and "expires_at" in blessing:
                    try:
                        if float(blessing.get("expires_at", 0)) <= time.time():
                            continue
                    except (TypeError, ValueError):
                        continue
                    remaining = self.blessing_use_count(strokes, slot)
                remaining = min(BLESSING_KEYSTROKE_USE_CAP, remaining)
                remaining_key = "remaining_uses"
            if remaining <= 0:
                continue
            visitor_id = str(blessing.get("visitor_id", ""))
            visitor = BLESSING_VISITOR_BY_ID.get(visitor_id, {})
            blessings[slot] = {
                "visitor_id": visitor_id,
                "name": str(blessing.get("name", visitor.get("name", "Visitor"))),
                "slot": slot,
                "bonus": int(round(bonus)) if slot == "body" else bonus,
                "strokes": strokes,
                remaining_key: remaining,
            }
        return blessings

    def normalize_hooked_fish(self, saved_fish):
        if not isinstance(saved_fish, dict):
            return None
        name = str(saved_fish.get("name", "")).strip()
        rarity = str(saved_fish.get("rarity", "")).strip()
        color = str(saved_fish.get("color", "#62bfb8")).strip() or "#62bfb8"
        kind = str(saved_fish.get("kind", "fish")).strip() or "fish"
        skin_id = str(saved_fish.get("skin_id", "")).strip()
        skin = PRIDE_FISH_BY_ID.get(skin_id)
        skin_name = ""
        skin_colors = []
        if skin:
            skin_name = skin["name"]
            saved_colors = saved_fish.get("skin_colors", skin["colors"])
            if isinstance(saved_colors, list):
                skin_colors = [str(skin_color) for skin_color in saved_colors if self.valid_hex_color(str(skin_color))]
            if not skin_colors:
                skin_colors = list(skin["colors"])
            body_colors = [str(skin_color) for skin_color in skin.get("body_colors", skin_colors) if self.valid_hex_color(str(skin_color))]
            color = body_colors[len(body_colors) // 2] if body_colors else skin_colors[len(skin_colors) // 2]
        else:
            skin_id = ""
        strokes = max(1, safe_int(saved_fish.get("strokes", 1), 1))
        value = max(0, safe_int(saved_fish.get("value", 0), 0))
        spot_id = str(saved_fish.get("spot_id", "")).strip()
        blessing_id = str(saved_fish.get("blessing_id", "")).strip()
        blessing_slot = str(saved_fish.get("blessing_slot", "")).strip()
        try:
            blessing_bonus = float(saved_fish.get("blessing_bonus", 0.0))
        except (TypeError, ValueError):
            blessing_bonus = 0.0
        try:
            progress = float(saved_fish.get("progress", 0.0))
        except (TypeError, ValueError):
            progress = 0.0
        progress = max(0.0, min(progress, strokes - 0.001))
        if not name or not rarity:
            return None
        return HookedFish(name=name, rarity=rarity, strokes=strokes, value=value, color=color, kind=kind, progress=progress, spot_id=spot_id, blessing_id=blessing_id, blessing_slot=blessing_slot, blessing_bonus=blessing_bonus, skin_id=skin_id, skin_name=skin_name, skin_colors=skin_colors)

    def load(self):
        save_path, data = find_save_to_load()
        if data is None:
            return
        migrate_save_to_user_data(save_path, data)
        self.coins = int(data.get("coins", 0))
        self.total_keystrokes = int(data.get("total_keystrokes", 0))
        self.total_played_seconds = float(data.get("total_played_seconds", 0.0))
        self.transparency = float(data.get("transparency", 1.0))
        self.transparency_percent.set(min(100, max(20, self.transparency * 100)))
        self.transparency_text.set(f"{int(round(self.transparency * 100))}%")
        custom_primary = str(data.get("custom_primary_color", self.custom_primary_color)).strip()
        custom_secondary = str(data.get("custom_secondary_color", self.custom_secondary_color)).strip()
        if self.valid_hex_color(custom_primary):
            self.custom_primary_color = custom_primary
        if self.valid_hex_color(custom_secondary):
            self.custom_secondary_color = custom_secondary
        saved_theme = str(data.get("theme", "")).strip()
        if saved_theme in THEME_NAMES:
            self.theme_name = saved_theme
        else:
            self.theme_name = "Dark" if bool(data.get("dark_theme", False)) else "Light"
        self.theme_var.set(THEME_NAME_TO_LABEL[self.theme_name])
        self.dark_theme = self.theme_is_dark()
        self.game_scale = float(data.get("game_scale", 1.0))
        self.menu_scale = float(data.get("menu_scale", 1.0))
        self.game_scale_var.set(self.scale_label_for_value(self.game_scale))
        self.menu_scale_var.set(self.scale_label_for_value(self.menu_scale))
        self.game_scale = SCALE_VALUES[self.game_scale_var.get()]
        self.menu_scale = SCALE_VALUES[self.menu_scale_var.get()]
        self.always_on_top = bool(data.get("always_on_top", self.always_on_top))
        self.always_on_top_var.set(self.always_on_top)
        self.apply_always_on_top()
        self.game_info_panel_pinned.set(bool(data.get("game_info_panel_pinned", False)))
        self.compact_vertical_var.set(bool(data.get("compact_vertical_mode", False)))
        self.debug_shop_prices_bypassed.set(bool(data.get("debug_shop_prices_bypassed", False)))
        self.game_info_panel_visible = True
        self.last_info_panel_hover_at = time.time()
        self.menu_offset_x = int(data.get("menu_offset_x", self.menu_offset_x))
        self.menu_offset_y = int(data.get("menu_offset_y", self.menu_offset_y))
        self.window_x = int(data.get("window_x", self.window_x))
        self.window_y = int(data.get("window_y", self.window_y))
        self.selected_monitor_index = max(0, safe_int(data.get("selected_monitor_index", self.selected_monitor_index)))
        self.refresh_monitor_options()
        self.menu_docked = bool(data.get("menu_docked", True))
        self.menu_docked_var.set(self.menu_docked)
        self.update_menu_dock_text()
        self.minimized = bool(data.get("minimized", self.minimized))
        self.banked_keys = int(data.get("banked_keys", 0))
        self.banked_upgrade_level = max(0, min(int(data.get("banked_upgrade_level", 0)), len(BANKED_KEY_UPGRADES)))
        self.autosell_level = max(0, min(int(data.get("autosell_level", 0)), len(AUTOSALE_UPGRADES)))
        self.last_autosell_at = float(data.get("last_autosell_at", time.time()))
        saved_relic_payout_at = float(data.get("last_relic_payout_at", time.time()))
        self.last_relic_payout_at = saved_relic_payout_at
        self.fish_clicks = max(0, safe_int(data.get("fish_clicks", 0)))
        self.cat_pets = max(0, safe_int(data.get("cat_pets", 0)))
        self.fish_since_last_treasure_chest = max(0, safe_int(data.get("fish_since_last_treasure_chest", TREASURE_CHEST_MIN_FISH_BETWEEN)))
        self.active_blessings = self.normalize_active_blessings(data.get("active_blessings", {}))
        self.discord_presence_enabled.set(bool(data.get("discord_presence_enabled", True)))
        self.background_key_capture_consent_granted = bool(data.get("background_key_capture_consent_granted", False)) if IS_WINDOWS else False
        self.background_key_capture_enabled.set(bool(data.get("background_key_capture_enabled", False)) and self.background_key_capture_consent_granted and IS_WINDOWS)
        self.backpack_level = max(0, min(int(data.get("backpack_level", 0)), len(BACKPACK_UPGRADES)))
        self.inventory_limit = self.current_inventory_limit()
        self.inventory = list(data.get("inventory", []))
        self.relics = self.normalize_relics(data)
        self.stored_potions = self.normalize_stored_potions(data)
        self.potions = self.normalize_potions(data)
        saved_log = data.get("event_log", [])
        self.event_log = [str(entry) for entry in saved_log[:80]] if isinstance(saved_log, list) else []
        self.process_offline_relic_payouts(saved_relic_payout_at, time.time())
        self.collection_log = self.normalize_collection_log(data)
        saved_achievements = data.get("achievements_unlocked", [])
        self.achievements_unlocked = set(saved_achievements) if isinstance(saved_achievements, list) else set()
        saved_spots = data.get("unlocked_fishing_spots", ["pond"])
        self.unlocked_fishing_spots = set(saved_spots) if isinstance(saved_spots, list) else {"pond"}
        self.unlocked_fishing_spots.add("pond")
        self.selected_fishing_spot = str(data.get("selected_fishing_spot", "pond"))
        if self.selected_fishing_spot not in self.unlocked_fishing_spots:
            self.selected_fishing_spot = "pond"
        self.equipment_levels = self.load_equipment_levels(data)
        self.hooked_fish = self.normalize_hooked_fish(data.get("hooked_fish"))
        if self.hooked_fish is None:
            self.cast_started_at = float(data.get("cast_started_at", time.time()))

    def save(self):
        self.total_played_seconds += time.time() - self.play_timer_started_at
        self.play_timer_started_at = time.time()
        self.cleanup_active_potions()
        hooked_fish = None
        if self.hooked_fish:
            hooked_fish = {
                "name": self.hooked_fish.name,
                "rarity": self.hooked_fish.rarity,
                "strokes": self.hooked_fish.strokes,
                "value": self.hooked_fish.value,
                "color": self.hooked_fish.color,
                "kind": self.hooked_fish.kind,
                "progress": self.hooked_fish.progress,
                "spot_id": self.hooked_fish.spot_id,
                "blessing_id": self.hooked_fish.blessing_id,
                "blessing_slot": self.hooked_fish.blessing_slot,
                "blessing_bonus": self.hooked_fish.blessing_bonus,
                "skin_id": self.hooked_fish.skin_id,
                "skin_name": self.hooked_fish.skin_name,
                "skin_colors": self.hooked_fish.skin_colors,
            }
        data = {
            "coins": self.coins,
            "total_keystrokes": self.total_keystrokes,
            "total_played_seconds": self.total_played_seconds,
            "transparency": self.transparency,
            "theme": self.theme_name,
            "dark_theme": self.dark_theme,
            "custom_primary_color": self.custom_primary_color,
            "custom_secondary_color": self.custom_secondary_color,
            "game_scale": self.game_scale,
            "menu_scale": self.menu_scale,
            "always_on_top": self.always_on_top,
            "game_info_panel_pinned": self.game_info_panel_pinned.get(),
            "compact_vertical_mode": self.compact_vertical_var.get(),
            "debug_shop_prices_bypassed": self.debug_shop_prices_bypassed.get(),
            "menu_offset_x": self.menu_offset_x,
            "menu_offset_y": self.menu_offset_y,
            "window_x": self.winfo_x(),
            "window_y": self.winfo_y(),
            "selected_monitor_index": self.selected_monitor_index,
            "menu_docked": self.menu_docked,
            "minimized": self.minimized,
            "banked_keys": self.banked_keys,
            "banked_upgrade_level": self.banked_upgrade_level,
            "autosell_level": self.autosell_level,
            "last_autosell_at": self.last_autosell_at,
            "last_relic_payout_at": self.last_relic_payout_at,
            "fish_clicks": self.fish_clicks,
            "cat_pets": self.cat_pets,
            "fish_since_last_treasure_chest": self.fish_since_last_treasure_chest,
            "active_blessings": self.active_blessings,
            "discord_presence_enabled": self.discord_presence_enabled.get(),
            "background_key_capture_enabled": self.background_key_capture_enabled.get(),
            "background_key_capture_consent_granted": self.background_key_capture_consent_granted,
            "backpack_level": self.backpack_level,
            "equipment_levels": self.equipment_levels,
            "inventory": self.inventory,
            "relics": self.relics,
            "stored_potions": self.stored_potions,
            "potions": self.potions,
            "event_log": self.event_log,
            "collection_log": self.collection_log,
            "achievements_unlocked": sorted(self.achievements_unlocked),
            "unlocked_fishing_spots": sorted(self.unlocked_fishing_spots),
            "selected_fishing_spot": self.selected_fishing_spot,
            "hooked_fish": hooked_fish,
            "cast_started_at": self.cast_started_at,
        }
        try:
            SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_file = SAVE_FILE.with_suffix(f"{SAVE_FILE.suffix}.tmp")
            temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temp_file.replace(SAVE_FILE)
            self.last_save_at = time.time()
            return True
        except OSError:
            return False

    def on_close(self):
        if self.discord:
            try:
                self.discord.close()
            except Exception:
                pass
        self.key_poller.close()
        self.save()
        self.destroy()


if __name__ == "__main__":
    app = TypeCast()
    app.mainloop()
