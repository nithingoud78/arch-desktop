# Arch Desktop (Hyprland + Neon Dock + Control Center)

A clean, self-contained Arch Linux + Hyprland desktop configuration built around an auto-hiding GTK3 Layer-Shell bottom dock (`neon-dock`), a slide-over frosted-glass Control Center (`control-center`), dynamic wallpaper-derived theming, and a topbar-free workspace layout (Waybar completely removed).

---

## Repository Structure

```text
arch-desktop/
├── config/
│   ├── arch-desktop/settings.json   # Dock size profile setting ("small", etc.)
│   ├── dunst/dunstrc                # Notification daemon appearance & urgency rules
│   ├── hypr/
│   │   ├── hyprland.conf            # Authoritative Hyprland settings & keybindings
│   │   ├── hyprland.lua             # Hyprland 0.57 Lua bridge translating hyprland.conf
│   │   └── hyprpaper.conf           # Wallpaper configuration (IPC enabled)
│   ├── kitty/kitty.conf             # Kitty terminal styling & colors
│   └── nwg-drawer/drawer.css        # Full-screen application drawer styling
├── control-center/
│   └── control-center               # GTK3 + Layer-Shell Control Center daemon & CLI
├── dock/
│   └── neon-dock.py                 # Main bottom dock application (GTK3 + Layer-Shell)
├── Pictures/
│   └── Wallpapers/                  # Wallpaper collection used with hyprpaper
├── scripts/
│   ├── brightness-control           # Logical brightness mapper (prevents black screen at min)
│   ├── hyprland-conf-reload         # Verifies config with Hyprland before live reload
│   ├── hyprshut                     # Graceful session shutdown / exit helper
│   ├── master-theme-launch          # User service restart launcher
│   ├── notify-send                  # Lightweight D-Bus desktop notification wrapper
│   ├── screenshot-area              # Region screenshot (slurp + grim + wl-copy)
│   ├── screenshot-full              # Fullscreen screenshot (grim + wl-copy)
│   ├── toggle-desktop               # Non-destructive Show Desktop toggle via workspace IPC
│   └── toggle-screen-recording      # Screen recorder toggle (wf-recorder)
├── shared/
│   ├── config.py                    # Shared Neon Desktop settings & notes loader/saver
│   ├── icons.py                     # HiDPI vector SVG icon renderer (dock, tray, chevron, Arch logo)
│   ├── system.py                    # Hyprland, PipeWire, NetworkManager, Bluetooth, & stats helpers
│   └── theme.py                     # Wallpaper color extraction & glass/accent token generator
├── systemd/user/
│   ├── control-center.service       # Runs control-center --daemon
│   ├── hyprland-conf-sync.path      # Watches hyprland.conf for changes
│   ├── hyprland-conf-sync.service   # Triggers safe verification & reload
│   └── neon-dock.service            # Runs neon-dock
├── .gitignore
├── install.sh                       # Deploys scripts, configs, and systemd user services
└── README.md
```

---

## Features

### 1. Neon Bottom Dock (`dock/neon-dock.py`)
An edge-triggered, auto-hiding bottom dock anchored via `gtk-layer-shell` with translucent glass styling dynamically tinted from the active wallpaper:

- **App Launcher & Running Apps (`ApplicationsModule`)**:
  - **9-dot Grid Button**: Opens the full-screen `nwg-drawer` Applications menu (`nwg-drawer -wm uwsm -term kitty -fm dolphin`).
  - **Pinned & Dynamic Apps**: Fixed-width cells with running indicators for pinned apps (Dolphin, Brave, Kitty, Antigravity, VLC) plus dynamically tracked open windows.
- **Navigation Actions**:
  - **Search (`SearchModule`)**: Opens Wofi launcher (`wofi --show drun`).
  - **Snap (`SnapModule`)**: Captures a selected area screenshot (`slurp` + `grim`) saved to `~/Pictures/Screenshots/`.
  - **Notes (`NotesModule`)**: Opens/shows CopyQ clipboard manager (`copyq show`).
- **Compact Workspace Switcher (`WorkspaceSwitcherModule`)**:
  - Embedded directly in the bottom dock with compact vertical capsule geometry (`26px` container / `22px` inner capsule) styled from the active wallpaper palette (`theme.derive_topbar_colors`).
  - Reacts live to Hyprland IPC (`.socket2.sock`) for workspace switching and occupied/active indicators.
- **Media Player (`PlayerModule`)**: Live MPRIS playback controls and artwork/standby state via `playerctl`.
- **Settings (`SettingsModule`)**: Opens the Control Center directly to the Desktop Settings page.
- **System Monitor (`SystemMonitorModule`)**: Compact rounded progress bars displaying live **CPU**, **RAM**, and **GPU** usage.
- **Date & Clock (`DateModule`)**: Live time and date readout.
- **Uniform System Tray (`SystemTrayModule`)**:
  - Equally spaced icons inside a fixed `160px` container: **Wi-Fi**, **Audio Volume**, **Battery / Charging**, **Control Center Toggle**, and **Notification Panel** (`dunstctl history-pop`).
  - **Control Center Toggle (`#cc-toggle-btn`)**: Crisp HiDPI SVG chevron (`shared/icons.py` / `shared/theme.py`), zero hover background box, smoothly rotates `180deg` when the Control Center opens and rotates back on close (including Escape or outside clicks).
- **Show Desktop Corner Button (`#arch-desktop-btn`)**:
  - Minimal white HiDPI Arch Linux vector icon at the far right corner (no rounded border box or hover background).
  - Runs `toggle-desktop`, which switches temporarily to an empty named workspace (`name:desktop`) via Hyprland Lua IPC without killing, minimizing, or swapping window positions, and restores the previous workspace on the next click.

### 2. Interactive Control Center (`control-center/control-center`)
A background-cached GTK3 Layer-Shell daemon (`control-center --daemon`) with smooth frame-clock animations (`SmoothStack`) and non-blocking hardware queries (`StateWatcher`):

- **Main View**: Quick cards and toggles for Wi-Fi, Bluetooth, Hotspot, Airplane Mode, brightness & volume sliders, and media controls.
- **Dedicated Subpages**: Interactive Wi-Fi scanner with stdin password prompt, Bluetooth device/pairing view, Hotspot SSID/password configuration, and Desktop Settings (display info & segmented Small / Medium / Large dock sizing).
- **Dismissal UX**: Clicking outside the Control Center (excluding the dock's `#cc-toggle-btn` rect at `/run/user/$UID/cc-toggle.rect`) or pressing `Escape` dismisses the panel cleanly and syncs the dock chevron rotation.

### 3. Dynamic Wallpaper Theming (`shared/theme.py` & `shared/icons.py`)
- Automatically inspects the active wallpaper (`hyprpaper.conf` / palette cache) and derives dark glass backgrounds, borders, and contrast-safe accent gradients for both the dock and Control Center.
- Programmatic SVG icons rasterized at display scale for sharp rendering across all tray and dock elements.

### 4. Hyprland Configuration & Helper Scripts
- **Unified Hyprland Config**: `hyprland.conf` serves as the single source of truth, loaded via `hyprland.lua` on Hyprland `0.57+` with automatic validation before reload (`hyprland-conf-sync.path` -> `hyprland-conf-reload`).
- **Waybar-Free Setup**: Top bar (`waybar.service`) is disabled and masked; all workspace, tray, clock, and Control Center controls live cleanly in the bottom dock.
- **Capture & Hardware Utilities**:
  - `brightness-control`: Safe logical `[0%, 100%]` mapping over `[2, 254]` raw backlight values (`nvidia_wmi_ec_backlight` / `brightnessctl`) so brightness `0%` never blacks out the panel.
  - `screenshot-area` / `screenshot-full` / `toggle-screen-recording`: Screenshots copied to Wayland clipboard and saved to `~/Pictures/Screenshots/`, and MP4 recordings managed safely in `~/Videos/Nithin/ScreenRecordings/`.

---

## Keybindings (`config/hypr/hyprland.conf`)

| Shortcut | Action |
| :--- | :--- |
| `Super + Return` | Open Kitty terminal |
| `Super + Q` | Close active window |
| `Super + E` | Open Dolphin file manager |
| `Super + V` | Toggle floating window |
| `Super + R` | Open `nwg-drawer` app menu |
| `Super + B` | Launch Brave browser |
| `Super + C` | Toggle Control Center |
| `Super + [1..0]` | Switch to workspace `1..10` |
| `Super + Shift + [1..0]` | Move active window to workspace `1..10` |
| `Super + [ / ]` | Fullscreen / Pseudo-tile |
| `Super + S` / `Super + Shift + S` | Toggle / move to `magic` scratchpad |
| `Print` | Screenshot area (`screenshot-area`) |
| `Super + Print` | Screenshot full screen (`screenshot-full`) |
| `Super + Shift + Print` | Toggle screen recording (`toggle-screen-recording`) |
| `XF86Audio*` / `XF86MonBrightness*` | PipeWire volume, `playerctl` media, and safe brightness control |

---

## Dependencies (Arch Linux)

Core packages and tools used by the desktop suite and scripts:

- **Compositor & Core**: `hyprland`, `hyprpaper`, `uwsm`, `dunst`, `kitty`, `dolphin`, `copyq`, `polkit-kde-agent`
- **GTK / Layer Shell / Python**: `python`, `python-gobject`, `gtk3`, `gtk-layer-shell`, `python-cairo`, `python-pillow` (optional/theme sampling fallback if used)
- **Launchers & Utilities**: `nwg-drawer`, `wofi`, `grim`, `slurp`, `wl-clipboard`, `wf-recorder`, `playerctl`, `brightnessctl`, `networkmanager`, `bluez`, `wireplumber`

---

## Installation & Restore

1. Clone or copy this repository and run the installer:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
2. Reload Hyprland or start the user services:
   ```bash
   systemctl --user start control-center.service neon-dock.service hyprpaper.service
   ```
3. *(Optional)* Set your wallpaper path in `~/.config/hypr/hyprpaper.conf`.

---

## Saving to Git

To initialize a local repository and push to a remote:

```bash
git init -b main
git add .
git commit -m "Initial clean Arch Hyprland desktop setup"
git remote add origin <your-git-remote-url>
git push -u origin main
```

