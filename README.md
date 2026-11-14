# Arch Desktop (Hyprland + Taskbar Main + Settings + Control Center)

A clean, self-contained, high-performance Arch Linux + Hyprland desktop environment built around an auto-hiding GTK3 Layer-Shell bottom dock (`taskbar-main` / `neon-dock`), an all-in-one native Desktop Settings application (`settings-real` / `settings`), a slide-over frosted-glass Control Center (`control-center`), adaptive App Launchers (`drun-real` / `launcher-real`), dynamic wallpaper-derived theming (Light and Dark mode), and a topbar-free layout (Waybar completely replaced).

---

## Repository Structure

```text
arch-desktop/
├── assets/
│   ├── zoro-sunset.png              # High-resolution Zoro sunset top banner artwork for Drun
│   └── zoro-sunset-feathered.png    # Gradient feathered banner artwork
├── config/
│   ├── arch-desktop/settings.json   # Dock size profile setting
│   ├── dunst/dunstrc                # Notification daemon appearance & urgency rules
│   ├── hypr/
│   │   ├── hyprland.conf            # Authoritative Hyprland settings & keybindings
│   │   ├── hyprland.lua             # Hyprland 0.57 Lua bridge translating hyprland.conf
│   │   ├── hyprpaper.conf           # Wallpaper configuration (IPC enabled)
│   │   └── theme.conf               # Dynamic wallpaper-adaptive Hyprland border theme
│   ├── kitty/
│   │   ├── kitty.conf               # Kitty terminal styling & dynamic cursor color
│   │   └── kitty.desktop            # Desktop launcher using official macOS terminal icon
│   ├── nwg-drawer/drawer.css        # Legacy drawer fallback styling
│   └── settings.desktop             # Desktop launcher for native Settings application
├── control-center/
│   └── control-center               # GTK3 + Layer-Shell Control Center daemon & CLI
├── dock/
│   ├── neon-dock.py                 # Main bottom dock application (canonical GTK3 + Layer-Shell)
│   └── taskbar-main.py              # Direct alias to neon-dock.py
├── drawer/
│   ├── neon-drawer.py               # Sunset Neon Glass App Launcher (GTK3 + Layer-Shell)
│   └── launcher-real.py             # Direct alias to neon-drawer.py
├── drun/
│   ├── neon-drun.py                 # Adaptive glass search & app launcher with banner artwork
│   └── drun-real.py                 # Direct alias to neon-drun.py
├── icons/                           # Custom high-res desktop icons (Kitty, Antigravity, Dolphin)
│   ├── antigravity-ide.png
│   ├── kitty.png
│   ├── kitty.svg
│   └── org.kde.dolphin.svg
├── Pictures/
│   └── Wallpapers/                  # Curated wallpaper collection used with hyprpaper
├── scripts/
│   ├── brightness-control           # Logical brightness mapper (prevents black screen at min)
│   ├── drun-real                    # CLI alias for drun launcher
│   ├── hyprland-conf-reload         # Verifies config with Hyprland before live reload
│   ├── hyprshut                     # Graceful session shutdown / exit helper
│   ├── launcher-real                # CLI alias for app drawer
│   ├── master-theme-launch          # User service restart launcher
│   ├── neon-dock-pin                # Pinned applications CLI (list, pin, unpin, toggle)
│   ├── neon-drawer                  # App drawer CLI wrapper
│   ├── neon-drun                    # Drun launcher CLI wrapper
│   ├── notify-send                  # Lightweight D-Bus desktop notification wrapper
│   ├── screenshot-area              # Region screenshot (slurp + grim + wl-copy)
│   ├── screenshot-full              # Fullscreen screenshot (grim + wl-copy)
│   ├── settings-real                # CLI alias for Settings application
│   ├── taskbar-main                 # CLI alias for Taskbar Main (neon-dock)
│   ├── toggle-desktop               # Non-destructive Show Desktop toggle via workspace IPC
│   └── toggle-screen-recording      # Screen recorder toggle (wf-recorder)
├── settings/
│   ├── settings.py                  # Full native desktop control center application
│   └── settings-real.py             # Direct alias to settings.py
├── shared/
│   ├── config.py                    # Shared settings loader/saver & default schemas
│   ├── dock_pin.py                  # Pinned apps management library (~/.config/neon-desktop/pinned.json)
│   ├── icons.py                     # HiDPI vector SVG icon renderer (dock, tray, categories, Arch logo)
│   ├── system.py                    # Hyprland, PipeWire, NetworkManager, Bluetooth, & stats helpers
│   └── theme.py                     # Wallpaper color extraction & system-wide theme sync engine
├── systemd/user/
│   ├── control-center.service       # Runs control-center --daemon
│   ├── hyprland-conf-sync.path      # Watches hyprland.conf for changes
│   ├── hyprland-conf-sync.service   # Triggers safe verification & reload
│   └── neon-dock.service            # Runs neon-dock (taskbar-main)
├── .gitignore
├── install.sh                       # Deploys scripts, configs, and systemd user services
└── README.md
```

---

## Core Components & Features

### 1. Taskbar Main (`dock/neon-dock.py` / `taskbar-main`)
A high-performance, auto-hiding GTK3 Layer-Shell bottom dock dynamically themed from the active wallpaper with support for both Dark and Light modes:
- **Capsule & Floating Modes**:
  - Live animated transition between floating capsule mode (`16px` border radius with screen margin) and full edge-to-edge dock (`0px` border radius).
  - Jitter-free dynamic icon sizing & spacing slider (`20px` to `36px`) constrained cleanly to screen boundaries.
- **Dock Elements & Ordering**:
  - Fully reorderable via drag-and-drop or checkboxes in Settings, with immediate live IPC update:
    1. **Pinned and Running Apps** (`apps`): Pinned apps (Dolphin, Brave, Kitty, Antigravity, etc.) with active window tracking, running dots, and context menus.
    2. **Search Launcher** (`search`): Triggers the Zoro Sunset App Launcher (`drun-real` / `neon-drun`).
    3. **Snap** (`snap`): Quick region screenshot tool (`slurp` + `grim`).
    4. **Notes** (`notes`): Quick clipboard notes & manager (`copyq`).
    5. **Workspace Switcher** (`modes`): Segmented capsule showing active and occupied Hyprland workspaces.
    6. **Media Player** (`player`): Live MPRIS playback controls, track title, and artist.
    7. **Settings Launcher** (`settings`): One-click launcher for the native Settings app.
    8. **System Monitor** (`sysmon`): Live progress bars for CPU, RAM, and GPU utilization.
    9. **Date & Time** (`date`): Live formatted clock and date readout.
    10. **System Tray & Stats** (`systray`): Wi-Fi, audio volume, battery status, notification center, and desktop toggle.
  - **Reset to Default**: One-click restore button in Settings to instantly reinstate this exact factory layout.
- **Live Wallpaper Palette & Light/Dark Theme**:
  - Automatically derives multi-stop neon gradient borders and glass background colors from the active wallpaper.
  - Supports both Dark Mode (dark glass capsule with glowing neon accents) and Light Mode (crisp frosted light glass with slate text and accents).

### 2. Native Settings Application (`settings/settings.py` / `settings-real`)
A comprehensive, standalone GTK3 desktop control center built specifically for Arch Linux and Hyprland:
- **17 Dedicated Categories**:
  - **Personalization**: Wallpaper carousel & browser, Dock & Taskbar controls, App Launcher & Search (Drun) custom artwork, Themes & Colors (Light/Dark toggle, Blur strength, Transparency).
  - **Display**: Resolution, refresh rate, scaling, and monitor layout.
  - **Sound**: Output/input device selection, volume levels, and test audio.
  - **Power & Battery**: Performance profiles, sleep/suspend timeouts, and power button actions.
  - **Network & Bluetooth**: Wireless scanning, connection management, and device pairing.
  - **Applications, Desktop & Windows, Workspaces, Keyboard & Mouse, Shell & Interface, Notifications, Privacy & Security, Accessibility, Performance, System Information, Advanced**.
- **Buttery Smooth Frame-Clock Scrolling**:
  - Custom `SmoothScroller` synchronized to monitor refresh rate (60Hz, 144Hz, 165Hz+) via GTK tick callbacks.
  - Mathematical exponential decay and velocity accumulation eliminate discrete mouse wheel jumps.
  - Non-hijacking wallpaper carousel preserves vertical scrolling momentum when cursor traverses over thumbnails.

### 3. Adaptive Glass App Launcher (`drun/neon-drun.py` / `drun-real`)
- Centered frosted glass search card with backdrop blur.
- High-resolution top banner artwork (`assets/zoro-sunset.png`) with feathered gradient transition.
- Live blur strength (0%–100%) and transparency adjustments synced with Settings.
- Quick keyboard launch (`Super + Space` or `Super + R`), fuzzy application search, and pinned taskbar indicators.

### 4. Sunset Applications Drawer (`drawer/neon-drawer.py` / `launcher-real`)
- 9 categorized application lists with live application counts and Lucide vector icons.
- Grid View (2x2 squircle tiles) and List View (detailed capsule rows).
- In-menu app renaming with persistent overrides stored in `~/.config/neon-desktop/app_names.json`.
- Right-click taskbar pinning and unpinning.

### 5. Interactive Control Center (`control-center/control-center`)
- Slide-over right-side panel with smooth frame-clock animations (`SmoothStack`).
- Quick toggles for Wi-Fi, Bluetooth, Airplane Mode, Brightness, Volume, and MPRIS media playback.
- Synchronized bottom dock chevron indicator that rotates 180° when open.

### 6. System-Wide Dynamic Theming (`shared/theme.py`)
- Extracts 5 vibrant neon gradient stops (`s0`–`s4`) and background RGB from any wallpaper via hyprpaper IPC.
- Dynamically updates Hyprland window borders (`~/.config/hypr/theme.conf`), Kitty cursor color, Dunst notification frames, and bottom dock styling.

---

## CLI Aliases & Executables

All commands are installed to `~/.local/bin/` and available in `$PATH`:

| Command | Target | Description |
| :--- | :--- | :--- |
| `taskbar-main` | `neon-dock` | Launch or control the bottom dock |
| `settings-real` | `settings` | Launch the native Settings application |
| `drun-real` | `neon-drun` | Launch the Zoro Sunset glass search launcher |
| `launcher-real` | `neon-drawer` | Launch the full applications drawer |
| `control-center` | `control-center` | Toggle or query the slide-over Control Center |
| `neon-dock-pin` | `neon-dock-pin` | CLI to list, pin, unpin, or toggle dock pinned apps |
| `brightness-control` | `brightness-control` | Safe brightness increment/decrement mapper |
| `screenshot-area` | `screenshot-area` | Region screenshot with slurp & grim |
| `screenshot-full` | `screenshot-full` | Fullscreen screenshot with grim |
| `toggle-desktop` | `toggle-desktop` | Switch to clean workspace without closing windows |

---

## Keybindings (`config/hypr/hyprland.conf`)

| Shortcut | Action |
| :--- | :--- |
| `Super + Return` | Open Kitty terminal |
| `Super + Q` | Close active window |
| `Super + E` | Open Dolphin file manager |
| `Super + V` | Toggle floating window |
| `Super + R` | Open `launcher-real` (Applications Drawer) |
| `Super + Space` | Open `drun-real` (Glass Search Launcher) |
| `Super + B` | Launch Brave browser |
| `Super + C` | Toggle Control Center |
| `Super + [1..0]` | Switch to workspace `1..10` |
| `Super + Shift + [1..0]` | Move active window to workspace `1..10` |
| `Super + [ / ]` | Fullscreen / Pseudo-tile |
| `Print` | Region screenshot (`screenshot-area`) |
| `Super + Print` | Fullscreen screenshot (`screenshot-full`) |
| `Super + Shift + Print` | Toggle screen recording (`toggle-screen-recording`) |
| `XF86Audio*` / `XF86MonBrightness*` | Volume, media controls, and safe brightness |

---

## Installation & Deployment

1. Make the installer executable and deploy:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

2. Start or verify the user services:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart neon-dock.service control-center.service hyprpaper.service
   ```

3. Ensure user services are enabled across reboots:
   ```bash
   systemctl --user enable neon-dock.service control-center.service hyprpaper.service
   ```

---

## Ready for Git Push

This repository has been cleaned, structured, and verified:
- Redundant backup files (`.bak*`, `bak_*`), bytecode caches (`__pycache__`), and temporary files have been removed.
- All latest production files for the taskbar, settings app, launchers, and shared libraries are in place as canonical originals with matching convenience aliases.
- Verified syntax, executable permissions, and systemd service startup.
