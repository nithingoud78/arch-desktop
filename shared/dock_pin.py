#!/usr/bin/env python3
"""
Neon Desktop — Pinned Apps Helper
Manages pinned applications for the bottom dock (~/.config/neon-desktop/pinned.json)
"""

import os
import json
import glob

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
PINNED_FILE = os.path.join(CONFIG_DIR, "pinned.json")

DEFAULT_PINNED = [
    {"id": "org.kde.dolphin", "name": "Files", "icon": "org.kde.dolphin", "match": ["dolphin", "org.kde.dolphin"]},
    {"id": "brave-browser", "name": "Brave", "icon": "brave-desktop", "match": ["brave-browser", "brave"]},
    {"id": "kitty", "name": "Terminal", "icon": "/home/nithin/.local/share/icons/kitty.png", "match": ["kitty"]},
    {"id": "antigravity-ide", "name": "Antigravity", "icon": "/home/nithin/.local/share/icons/antigravity-ide.png", "match": ["antigravity-ide", "antigravity"]},
    {"id": "vlc", "name": "VLC", "icon": "vlc", "match": ["vlc"]}
]

def load_pinned():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.isfile(PINNED_FILE):
        try:
            with open(PINNED_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return list(DEFAULT_PINNED)

def save_pinned(pinned):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PINNED_FILE, "w") as f:
        json.dump(pinned, f, indent=2)

def find_desktop_file(app_id):
    if os.path.isfile(app_id):
        return app_id
    clean_id = app_id
    if not clean_id.endswith(".desktop"):
        clean_id += ".desktop"
    search_dirs = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/local/share/applications",
        "/usr/share/applications"
    ]
    for d in search_dirs:
        p = os.path.join(d, clean_id)
        if os.path.isfile(p):
            return p
    base_name = os.path.basename(app_id).replace(".desktop", "").lower()
    for d in search_dirs:
        for f in glob.glob(os.path.join(d, "*.desktop")):
            if base_name == os.path.basename(f).replace(".desktop", "").lower():
                return f
    return None

def parse_desktop_file(path):
    base_id = os.path.basename(path).replace(".desktop", "")
    info = {"id": base_id, "name": "", "icon": "", "match": []}
    matches = [base_id.lower()]
    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Name=") and not info["name"]:
                info["name"] = line.split("=", 1)[1].strip()
            elif line.startswith("Icon=") and not info["icon"]:
                info["icon"] = line.split("=", 1)[1].strip()
            elif line.startswith("StartupWMClass="):
                wm = line.split("=", 1)[1].strip().lower()
                if wm and wm not in matches:
                    matches.append(wm)
    if not info["name"]:
        info["name"] = base_id
    if info["name"].lower() not in matches:
        matches.append(info["name"].lower())
    info["match"] = matches
    return info

def is_pinned(app_id):
    pinned = load_pinned()
    norm_id = app_id.replace(".desktop", "").lower()
    for item in pinned:
        if item.get("id", "").lower() == norm_id:
            return True
        if norm_id in [m.lower() for m in item.get("match", [])]:
            return True
    return False

def pin(app_id):
    pinned = load_pinned()
    if is_pinned(app_id):
        return True
    df = find_desktop_file(app_id)
    if df:
        info = parse_desktop_file(df)
    else:
        clean = app_id.replace(".desktop", "")
        info = {"id": clean, "name": clean.capitalize(), "icon": clean, "match": [clean.lower()]}
    # Resolve special cases
    if info["id"] == "kitty" or "kitty" in info["match"]:
        info["icon"] = "/home/nithin/.local/share/icons/kitty.png"
    elif info["id"] in ("org.kde.dolphin", "dolphin") or "dolphin" in info["match"]:
        info["icon"] = "org.kde.dolphin"
    pinned.append(info)
    save_pinned(pinned)
    return True

def unpin(app_id):
    pinned = load_pinned()
    norm_id = app_id.replace(".desktop", "").lower()
    new_pinned = []
    removed = False
    for item in pinned:
        matches = [m.lower() for m in item.get("match", [])]
        if item.get("id", "").lower() == norm_id or norm_id in matches:
            removed = True
            continue
        new_pinned.append(item)
    if removed:
        save_pinned(new_pinned)
    return removed

def toggle(app_id):
    if is_pinned(app_id):
        unpin(app_id)
        return False
    else:
        pin(app_id)
        return True

