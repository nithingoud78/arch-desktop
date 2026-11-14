#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_BIN="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config"
CONFIG_NEON_DIR="$CONFIG_DIR/neon-desktop"
SYSTEMD_USER_DIR="$CONFIG_DIR/systemd/user"

mkdir -p \
    "$LOCAL_BIN" \
    "$CONFIG_NEON_DIR/shared" \
    "$CONFIG_NEON_DIR/assets" \
    "$CONFIG_DIR/hypr" \
    "$CONFIG_DIR/arch-desktop" \
    "$CONFIG_DIR/dunst" \
    "$CONFIG_DIR/kitty" \
    "$CONFIG_DIR/nwg-drawer" \
    "$SYSTEMD_USER_DIR"

# 1. Install Shared libraries & runtime assets
install -m 644 "$REPO_DIR/shared/"*.py "$CONFIG_NEON_DIR/shared/"
if [[ -d "$REPO_DIR/assets" ]]; then
    install -m 644 "$REPO_DIR/assets/"* "$CONFIG_NEON_DIR/assets/"
fi

# 2. Install Bottom Dock (taskbar-main), App Drawer (launcher-real), Drun (drun-real), and Settings (settings-real)
install -m 755 "$REPO_DIR/dock/neon-dock.py" "$LOCAL_BIN/neon-dock"
ln -sf "$LOCAL_BIN/neon-dock" "$LOCAL_BIN/taskbar-main"

install -m 755 "$REPO_DIR/drawer/neon-drawer.py" "$LOCAL_BIN/neon-drawer"
ln -sf "$LOCAL_BIN/neon-drawer" "$LOCAL_BIN/launcher-real"

install -m 755 "$REPO_DIR/drun/neon-drun.py" "$LOCAL_BIN/neon-drun"
ln -sf "$LOCAL_BIN/neon-drun" "$LOCAL_BIN/drun"
ln -sf "$LOCAL_BIN/neon-drun" "$LOCAL_BIN/drun-real"

install -m 755 "$REPO_DIR/settings/settings.py" "$LOCAL_BIN/settings"
ln -sf "$LOCAL_BIN/settings" "$LOCAL_BIN/settings-real"

# 3. Install Control Center & desktop utility scripts
install -m 755 "$REPO_DIR/control-center/control-center" "$LOCAL_BIN/control-center"
install -m 755 "$REPO_DIR/scripts/"* "$LOCAL_BIN/"

# 4. Install configuration files
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
        "$CONFIG_NEON_DIR/shared/config.py" \
        "$LOCAL_BIN/neon-dock"; do
        if [[ -f "$target" ]]; then
            sed -i "s|/home/nithin|$HOME|g" "$target"
        fi
    done
fi

# 5. Install icons & desktop entries
if [[ -d "$REPO_DIR/icons" ]]; then
    mkdir -p "$HOME/.local/share/icons"
    install -m 644 "$REPO_DIR/icons/"* "$HOME/.local/share/icons/"
    if command -v python3 >/dev/null 2>&1 && [[ -f "$HOME/.local/share/icons/kitty.png" ]]; then
        python3 -c "
import gi; gi.require_version('GdkPixbuf', '2.0'); from gi.repository import GdkPixbuf; import os
src = os.path.expanduser('~/.local/share/icons/kitty.png')
if os.path.isfile(src):
    pb = GdkPixbuf.Pixbuf.new_from_file(src)
    for s in [16, 24, 32, 48, 64, 128, 256, 512]:
        d = os.path.expanduser(f'~/.local/share/icons/hicolor/{s}x{s}/apps')
        os.makedirs(d, exist_ok=True)
        pb.scale_simple(s, s, GdkPixbuf.InterpType.HYPER).savev(os.path.join(d, 'kitty.png'), 'png', [], [])
" 2>/dev/null || true
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
fi

mkdir -p "$HOME/.local/share/applications"
if [[ -f "$REPO_DIR/config/kitty/kitty.desktop" ]]; then
    install -m 644 "$REPO_DIR/config/kitty/kitty.desktop" "$HOME/.local/share/applications/kitty.desktop"
    if [[ "$HOME" != "/home/nithin" ]]; then
        sed -i "s|/home/nithin|$HOME|g" "$HOME/.local/share/applications/kitty.desktop"
    fi
fi

if [[ -f "$REPO_DIR/config/settings.desktop" ]]; then
    install -m 644 "$REPO_DIR/config/settings.desktop" "$HOME/.local/share/applications/settings.desktop"
    if [[ "$HOME" != "/home/nithin" ]]; then
        sed -i "s|/home/nithin|$HOME|g" "$HOME/.local/share/applications/settings.desktop"
    fi
fi
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# 6. Install wallpapers (if included)
if [[ -d "$REPO_DIR/Pictures/Wallpapers" ]]; then
    mkdir -p "$HOME/Pictures/Wallpapers"
    install -m 644 "$REPO_DIR/Pictures/Wallpapers/"* "$HOME/Pictures/Wallpapers/"
fi

# 7. Install & enable systemd user units (Waybar remains masked)
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

