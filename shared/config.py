#!/usr/bin/env python3
"""
Neon Desktop — Shared Configuration Manager
Stores and loads user preferences, desktop settings, notes, and pinned apps.
"""

import os
import json

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
NOTES_FILE = os.path.join(CONFIG_DIR, "notes.txt")

DEFAULT_SETTINGS = {
    "wallpaper": "/home/nithin/Pictures/Wallpapers/Alpenglow Over Misty Mountain Peaks.png",
    "theme_mode": "Auto",
    "accent_color": "#a855f7",
    "palette_style": "Vivid",
    "transparency_blur": 70,
    "gradient_accents": True,
    "rounded_corners": 16,
    "animations": True,
    "show_window_shadows": True,
    "translucent_panels": True,
    "enable_blur": True,
    "color_frame_to_accent": True,
    "dock": {
        "position": "bottom",
        "icon_size": 28,
        "autohide": False,
        "pinned": [
            {"id": "brave-browser", "name": "Brave", "icon": "brave-desktop"},
            {"id": "kitty", "name": "Terminal", "icon": "kitty"},
            {"id": "org.kde.dolphin", "name": "Files", "icon": "org.kde.dolphin"},
            {"id": "antigravity-ide", "name": "Antigravity", "icon": "/home/nithin/.local/share/icons/antigravity-ide.png"}
        ]
    }
}

def load_settings():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                res = DEFAULT_SETTINGS.copy()
                res.update(data)
                return res
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def load_notes():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.isfile(NOTES_FILE):
        try:
            with open(NOTES_FILE, "r") as f:
                return f.read()
        except Exception:
            pass
    return "Welcome to Neon Desktop!\n- Fast, elegant, responsive\n- Double-tap Super for Wofi launcher\n- Use Settings to customize appearance"

def save_notes(content):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(NOTES_FILE, "w") as f:
        f.write(content)

