#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_BIN="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config"
NEON_DIR="$HOME/Projects/neon-desktop"
SYSTEMD_USER_DIR="$CONFIG_DIR/systemd/user"

mkdir -p \
    "$LOCAL_BIN" \
    "$NEON_DIR/dock" \
    "$NEON_DIR/shared" \
    "$CONFIG_DIR/hypr" \
    "$CONFIG_DIR/arch-desktop" \
    "$CONFIG_DIR/dunst" \
    "$CONFIG_DIR/kitty" \
    "$CONFIG_DIR/nwg-drawer" \
    "$SYSTEMD_USER_DIR"

# 1. Install Neon Dock runtime modules and launcher
install -m 644 "$REPO_DIR/shared/"*.py "$NEON_DIR/shared/"
install -m 644 "$REPO_DIR/dock/neon-dock.py" "$NEON_DIR/dock/neon-dock.py"
install -m 755 "$REPO_DIR/dock/neon-dock.py" "$LOCAL_BIN/neon-dock"

# 2. Install Control Center & desktop utility scripts
install -m 755 "$REPO_DIR/control-center/control-center" "$LOCAL_BIN/control-center"
install -m 755 "$REPO_DIR/scripts/"* "$LOCAL_BIN/"

# 3. Install configuration files
install -m 644 "$REPO_DIR/config/hypr/"* "$CONFIG_DIR/hypr/"
install -m 644 "$REPO_DIR/config/arch-desktop/settings.json" "$CONFIG_DIR/arch-desktop/settings.json"
install -m 644 "$REPO_DIR/config/dunst/dunstrc" "$CONFIG_DIR/dunst/dunstrc"
install -m 644 "$REPO_DIR/config/kitty/kitty.conf" "$CONFIG_DIR/kitty/kitty.conf"
install -m 644 "$REPO_DIR/config/nwg-drawer/drawer.css" "$CONFIG_DIR/nwg-drawer/drawer.css"

# Relocate hardcoded /home/nithin paths cleanly when deploying under a different user
if [[ "$HOME" != "/home/nithin" ]]; then
    for target in \
        "$CONFIG_DIR/hypr/hyprland.conf" \
        "$CONFIG_DIR/hypr/hyprland.lua" \
        "$CONFIG_DIR/hypr/hyprpaper.conf" \
        "$NEON_DIR/shared/config.py" \
        "$NEON_DIR/dock/neon-dock.py" \
        "$LOCAL_BIN/neon-dock"; do
        sed -i "s|/home/nithin|$HOME|g" "$target"
    done
fi

# 4. Install wallpapers (if included)
if [[ -d "$REPO_DIR/Pictures/Wallpapers" ]]; then
    mkdir -p "$HOME/Pictures/Wallpapers"
    install -m 644 "$REPO_DIR/Pictures/Wallpapers/"* "$HOME/Pictures/Wallpapers/"
fi

# 5. Install & enable systemd user units (Waybar remains masked)
install -m 644 "$REPO_DIR/systemd/user/"* "$SYSTEMD_USER_DIR/"

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user disable --now waybar.service 2>/dev/null || true
    systemctl --user mask waybar.service 2>/dev/null || true
    systemctl --user enable --now hyprland-conf-sync.path
    systemctl --user enable control-center.service neon-dock.service hyprpaper.service
fi

echo "Arch Desktop installed cleanly."
echo "Note: Update ~/.config/hypr/hyprpaper.conf with your preferred wallpaper path if needed."

