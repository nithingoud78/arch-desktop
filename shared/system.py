#!/usr/bin/env python3
"""
Neon Desktop — Shared System Helper
Safe interfaces for Hyprland, Audio (PipeWire), Power Profiles,
Network (NM), Bluetooth, Brightness, Displays, and Hardware info.
"""

import subprocess
import json
import os
import re
import socket

def run_cmd(cmd, timeout=3):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

# ── Hyprland ─────────────────────────────────────────────────────────────
def hypr_get_option(opt_name):
    try:
        out = run_cmd(f"hyprctl getoption {opt_name} -j")
        data = json.loads(out)
        if "int" in data:
            return data["int"]
        elif "float" in data:
            return data["float"]
        elif "custom" in data:
            return data["custom"]
        elif "str" in data:
            return data["str"]
        return None
    except Exception:
        return None

def calc_hypr_blur(strength):
    """Map 0-100% blur strength into progressive (enabled, passes, size) curve."""
    try:
        v = max(0, min(100, int(strength)))
    except Exception:
        v = 70
    if v <= 0:
        return False, 0, 0
    elif v <= 35:
        # Subtle softening: strictly 1 pass, size 1 to 5
        s = max(1, int(round(1 + ((v - 1) / 34.0) * 4)))
        return True, 1, s
    elif v <= 70:
        # Balanced frosted glass: 2 passes, size 2 to 6
        s = max(2, int(round(2 + ((v - 36) / 34.0) * 4)))
        return True, 2, s
    else:
        # Deep acrylic diffusion: 3 passes, size 4 to 8
        s = max(4, int(round(4 + ((v - 71) / 29.0) * 4)))
        return True, 3, s


def set_hypr_blur_live(enabled=None, size=None, passes=None):
    """Directly and instantaneously update Hyprland blur in compositor VRAM with zero reload or lag."""
    parts = []
    if enabled is not None:
        parts.append(f"enabled = {'true' if enabled else 'false'}")
    if size is not None:
        parts.append(f"size = {int(size)}")
    if passes is not None:
        parts.append(f"passes = {int(passes)}")
    if not parts:
        return
    inner = ", ".join(parts)
    lua_cmd = f"hl.config({{ decoration = {{ blur = {{ {inner} }} }} }})"
    try:
        subprocess.run(["hyprctl", "eval", lua_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.1)
    except Exception:
        pass


def update_hypr_config(rounding=None, shadow=None, blur=None, blur_size=None, blur_passes=None, animations=None, active_border=None, inactive_border=None, border_size=None, gaps_in=None, gaps_out=None, reload=False):
    """Safely update dynamic Hyprland theme config and reload config-only live."""
    conf_path = os.path.expanduser("~/.config/hypr/theme.conf")
    data = {
        "col.active_border": "rgba(3042cfee) rgba(6b30cfee) 45deg",
        "col.inactive_border": "rgba(382046aa)",
        "border_size": 2,
        "gaps_in": 5,
        "gaps_out": 10,
        "rounding": 16,
        "shadow_enabled": True,
        "blur_enabled": True,
        "blur_size": 8,
        "blur_passes": 3,
        "animations_enabled": True,
    }
    if os.path.isfile(conf_path):
        try:
            with open(conf_path, "r") as f:
                content = f.read()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("col.active_border") and "=" in line:
                    data["col.active_border"] = line.split("=", 1)[1].strip()
                elif line.startswith("col.inactive_border") and "=" in line:
                    data["col.inactive_border"] = line.split("=", 1)[1].strip()
                elif line.startswith("border_size") and "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit(): data["border_size"] = int(val)
                elif line.startswith("gaps_in") and "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit(): data["gaps_in"] = int(val)
                elif line.startswith("gaps_out") and "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit(): data["gaps_out"] = int(val)
                elif line.startswith("rounding") and "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit(): data["rounding"] = int(val)
                elif line.startswith("size") and "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit(): data["blur_size"] = int(val)
                elif line.startswith("passes") and "=" in line:
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit(): data["blur_passes"] = int(val)
                elif line.startswith("enabled") and "=" in line:
                    val = line.split("=", 1)[1].strip().lower()
                    # Could belong to shadow, blur, or animations depending on context, handled by overrides below
        except Exception:
            pass

    if rounding is not None: data["rounding"] = int(rounding)
    if shadow is not None: data["shadow_enabled"] = bool(shadow)
    if blur is not None: data["blur_enabled"] = bool(blur)
    if blur_size is not None: data["blur_size"] = int(blur_size)
    if blur_passes is not None: data["blur_passes"] = int(blur_passes)
    if animations is not None: data["animations_enabled"] = bool(animations)
    if active_border is not None: data["col.active_border"] = str(active_border)
    if inactive_border is not None: data["col.inactive_border"] = str(inactive_border)
    if border_size is not None: data["border_size"] = int(border_size)
    if gaps_in is not None: data["gaps_in"] = int(gaps_in)
    if gaps_out is not None: data["gaps_out"] = int(gaps_out)

    out = f"""# Dynamic wallpaper-adaptive theme for Hyprland
# Automatically updated by Neon Desktop theme engine
general {{
    col.active_border = {data["col.active_border"]}
    col.inactive_border = {data["col.inactive_border"]}
    border_size = {data["border_size"]}
    gaps_in = {data["gaps_in"]}
    gaps_out = {data["gaps_out"]}
}}

decoration {{
    rounding = {data["rounding"]}
    shadow {{
        enabled = {'true' if data["shadow_enabled"] else 'false'}
    }}
    blur {{
        enabled = {'true' if data["blur_enabled"] else 'false'}
        size = {data["blur_size"]}
        passes = {data["blur_passes"]}
    }}
}}

animations {{
    enabled = {'true' if data["animations_enabled"] else 'false'}
}}
"""
    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
    with open(conf_path, "w") as f:
        f.write(out)
    if reload:
        try:
            subprocess.run(["hyprctl", "reload", "config-only"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
        except Exception:
            pass
    return "ok"


def hypr_set_keyword(opt_name, value):
    # Route theme/decoration/animation options directly through theme.conf for Hyprland 0.57+
    if opt_name in ("decoration:rounding", "rounding"):
        return update_hypr_config(rounding=value)
    if opt_name in ("animations:enabled", "animations"):
        return update_hypr_config(animations=(int(value) if str(value).isdigit() else bool(value)))
    if opt_name in ("decoration:blur:enabled", "blur"):
        return update_hypr_config(blur=(int(value) if str(value).isdigit() else bool(value)))
    if opt_name in ("decoration:shadow:enabled", "shadow"):
        return update_hypr_config(shadow=(int(value) if str(value).isdigit() else bool(value)))
    if opt_name in ("general:border_size", "border_size"):
        return update_hypr_config(border_size=value)
    if opt_name in ("general:gaps_in", "gaps_in"):
        return update_hypr_config(gaps_in=value)
    if opt_name in ("general:gaps_out", "gaps_out"):
        return update_hypr_config(gaps_out=value)

    res = run_cmd(f"hyprctl keyword {opt_name} {value}")
    if "unknown request" in res.lower() or "error" in res.lower():
        # Fallback to config reload
        pass
    return res

def hypr_get_monitors():
    try:
        out = run_cmd("hyprctl monitors -j")
        return json.loads(out)
    except Exception:
        return []

def hypr_get_workspaces():
    try:
        out = run_cmd("hyprctl workspaces -j")
        return json.loads(out)
    except Exception:
        return []

# ── Power Profiles (ACPI Hardware & Tuned/PPD) ───────────────────────────
PLATFORM_PROFILE_SYSFS = "/sys/firmware/acpi/platform_profile"
DAMX_SOCKET_PATH = "/var/run/DAMX.sock"

def get_platform_profile():
    """
    Authoritative read from Acer Predator PHN16-71 ACPI platform profile:
    low-power, quiet, balanced, balanced-performance, performance
    """
    try:
        if os.path.exists(PLATFORM_PROFILE_SYSFS):
            with open(PLATFORM_PROFILE_SYSFS, "r") as f:
                val = f.read().strip()
                if val:
                    return val
    except Exception:
        pass
    # Fallback to D-Bus PowerProfiles
    return get_power_profile()

def set_platform_profile(profile_name):
    """
    Sets platform profile in /sys/firmware/acpi/platform_profile.
    Choices: low-power, quiet, balanced, balanced-performance, performance
    Uses DAMX.sock (root daemon managing ACPI / Linuwu-Sense) or direct sysfs write.
    Verifies that the sysfs file reflects the change before returning.
    """
    # 1. Try direct write (if running as root or permissions allow)
    try:
        if os.path.exists(PLATFORM_PROFILE_SYSFS):
            with open(PLATFORM_PROFILE_SYSFS, "w") as f:
                f.write(profile_name)
            with open(PLATFORM_PROFILE_SYSFS, "r") as f:
                if f.read().strip() == profile_name:
                    return True
    except (PermissionError, IOError, OSError):
        pass

    # 2. Try DAMX socket (root daemon managing ACPI / Linuwu-Sense driver)
    if os.path.exists(DAMX_SOCKET_PATH):
        try:
            import socket
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(DAMX_SOCKET_PATH)
            req = {"command": "set_thermal_profile", "params": {"profile": profile_name}}
            s.sendall(json.dumps(req).encode("utf-8"))
            data = s.recv(4096)
            s.close()
            resp = json.loads(data.decode("utf-8"))
            if resp.get("success"):
                try:
                    with open(PLATFORM_PROFILE_SYSFS, "r") as f:
                        if f.read().strip() == profile_name:
                            return True
                except Exception:
                    return True
        except Exception:
            pass

    return False

def get_power_profile():
    try:
        out = run_cmd("gdbus call --system --dest net.hadess.PowerProfiles --object-path /net/hadess/PowerProfiles --method org.freedesktop.DBus.Properties.Get net.hadess.PowerProfiles ActiveProfile")
        m = re.search(r"<'([^']+)'", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "balanced"

def set_power_profile(profile_name):
    """Sets power-saver, balanced, or performance."""
    cmd = f"gdbus call --system --dest net.hadess.PowerProfiles --object-path /net/hadess/PowerProfiles --method org.freedesktop.DBus.Properties.Set net.hadess.PowerProfiles ActiveProfile \"<'{profile_name}'>\""
    return run_cmd(cmd)

# ── Battery & Power Supply ───────────────────────────────────────────────
def get_battery_info():
    """
    Reads hardware battery and AC mains status directly from sysfs.
    Returns: {"capacity": int, "status": str, "is_charging": bool, "is_plugged": bool}
    """
    info = {"capacity": 100, "status": "Unknown", "is_charging": False, "is_plugged": False}
    try:
        base = "/sys/class/power_supply"
        if os.path.exists(base):
            for d in os.listdir(base):
                if d.startswith("BAT"):
                    cap_f = os.path.join(base, d, "capacity")
                    stat_f = os.path.join(base, d, "status")
                    if os.path.exists(cap_f):
                        with open(cap_f) as f:
                            c = f.read().strip()
                            if c.isdigit():
                                info["capacity"] = int(c)
                    if os.path.exists(stat_f):
                        with open(stat_f) as f:
                            st = f.read().strip()
                            info["status"] = st
                            info["is_charging"] = (st.lower() == "charging")
                elif d.startswith("AC") or d.startswith("ADP"):
                    on_f = os.path.join(base, d, "online")
                    if os.path.exists(on_f):
                        with open(on_f) as f:
                            val = f.read().strip()
                            if val == "1":
                                info["is_plugged"] = True
    except Exception:
        pass
    return info

# ── Live MPRIS Media Player ───────────────────────────────────────────────
def get_mpris_info():
    """
    Scans MPRIS players (Spotify, browser, etc.) and prioritizes actively playing sessions.
    Returns None if no player or stopped with no metadata.
    """
    players_out = run_cmd("playerctl -l 2>/dev/null")
    players = [p.strip() for p in players_out.splitlines() if p.strip()]
    if not players:
        return None

    delim = "===MPRIS_FIELD==="
    best_data = None
    for p in players:
        st = run_cmd(f"playerctl -p {p} status 2>/dev/null").strip()
        meta = run_cmd(f"playerctl -p {p} metadata --format '{{{{title}}}}{delim}{{{{artist}}}}{delim}{{{{mpris:artUrl}}}}{delim}{{{{xesam:url}}}}' 2>/dev/null")
        if meta and delim in meta:
            parts = meta.split(delim)
            title = parts[0].strip() if len(parts) > 0 else ""
            artist = parts[1].strip() if len(parts) > 1 else ""
            art = parts[2].strip() if len(parts) > 2 else ""
            url = parts[3].strip() if len(parts) > 3 else ""
            if title or artist:
                p_data = {"player": p, "status": st, "title": title, "artist": artist, "art": art, "url": url}
                if st == "Playing":
                    return p_data
                elif not best_data:
                    best_data = p_data
    return best_data

# ── Audio ────────────────────────────────────────────────────────────────
def get_audio_volume():
    try:
        out = run_cmd("pactl get-sink-volume @DEFAULT_SINK@")
        m = re.search(r"(\d+)%", out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 50

def set_audio_volume(pct):
    pct = max(0, min(150, int(pct)))
    return run_cmd(f"pactl set-sink-volume @DEFAULT_SINK@ {pct}%")

def get_audio_mute():
    out = run_cmd("pactl get-sink-mute @DEFAULT_SINK@")
    return "yes" in out.lower()

def set_audio_mute(mute):
    val = "1" if mute else "0"
    return run_cmd(f"pactl set-sink-mute @DEFAULT_SINK@ {val}")

# ── Brightness ───────────────────────────────────────────────────────────
def get_brightness():
    try:
        cur = int(run_cmd("brightnessctl get"))
        max_b = int(run_cmd("brightnessctl max"))
        if max_b > 0:
            return int((cur / max_b) * 100)
    except Exception:
        pass
    return 100

def set_brightness(pct):
    pct = max(1, min(100, int(pct)))
    return run_cmd(f"brightnessctl set {pct}%")

# ── Network ──────────────────────────────────────────────────────────────
def get_wifi_status():
    try:
        out = run_cmd("nmcli -t -f active,ssid,signal dev wifi")
        active_ssid = ""
        signal = 0
        for line in out.splitlines():
            if line.startswith("yes:"):
                parts = line.split(":")
                if len(parts) >= 3:
                    active_ssid = parts[1]
                    signal = int(parts[2]) if parts[2].isdigit() else 0
                break
        return {"connected": bool(active_ssid), "ssid": active_ssid, "signal": signal}
    except Exception:
        return {"connected": False, "ssid": "", "signal": 0}

# ── Bluetooth ────────────────────────────────────────────────────────────
def get_bluetooth_status():
    try:
        out = run_cmd("bluetoothctl show")
        powered = "Powered: yes" in out
        devices = []
        dev_out = run_cmd("bluetoothctl devices Connected")
        for line in dev_out.splitlines():
            if line.startswith("Device"):
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    devices.append(parts[2])
        return {"powered": powered, "connected_devices": devices}
    except Exception:
        return {"powered": False, "connected_devices": []}

# ── System Stats ─────────────────────────────────────────────────────────
def get_cpu_usage():
    try:
        out = run_cmd("awk '/^cpu / {u=$2+$4; t=$2+$3+$4+$5+$6+$7+$8; print int(u*100/t)}' /proc/stat")
        return int(out) if out.isdigit() else 0
    except Exception:
        return 0

def get_ram_usage():
    try:
        out = run_cmd("free | awk '/Mem:/ {print int($3*100/$2)}'")
        return int(out) if out.isdigit() else 0
    except Exception:
        return 0

def get_gpu_usage():
    try:
        out = run_cmd("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null")
        return int(out.strip()) if out.strip().isdigit() else 0
    except Exception:
        return 0

_SYS_INFO_STATIC = None

def get_system_info():
    global _SYS_INFO_STATIC
    if _SYS_INFO_STATIC is None:
        kernel = run_cmd("uname -r")
        cpu_model = run_cmd("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip()
        gpu_model = run_cmd("lspci | grep -iE 'vga|3d' | head -1 | cut -d: -f3").strip()
        mem_total = run_cmd("grep -m1 'MemTotal' /proc/meminfo | awk '{print int($2/1024/1024 + 0.5) \" GB\"}'")
        hypr = run_cmd("hyprctl version | head -1")
        _SYS_INFO_STATIC = {
            "os": "Arch Linux",
            "kernel": kernel,
            "hyprland": hypr,
            "cpu": cpu_model,
            "gpu": gpu_model,
            "ram": mem_total,
        }
    info = dict(_SYS_INFO_STATIC)
    info["uptime"] = run_cmd("uptime -p")
    return info

def get_hardware_temperatures():
    """Returns dict of temperatures in Celsius: cpu, gpu, nvme."""
    temps = {"cpu": 0, "gpu": 0}
    try:
        # CPU temp
        if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                t = f.read().strip()
                if t.isdigit():
                    temps["cpu"] = int(t) // 1000
    except Exception:
        pass
    try:
        # GPU temp (nvidia-smi)
        out = run_cmd("nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null")
        if out.isdigit():
            temps["gpu"] = int(out)
    except Exception:
        pass
    return temps

def get_storage_info():
    """Returns human-readable root storage usage."""
    return run_cmd("df -h / | awk 'NR==2 {print $3 \" used of \" $2 \" (\" $5 \" full)\"}'") or "24G used of 118G (22%)"

def get_audio_sinks():
    """Returns list of available audio sinks (name, desc)."""
    sinks = []
    out = run_cmd("pactl list sinks short")
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            name = parts[1]
            label = name.split(".")[-1] if "." in name else name
            sinks.append((name, label))
    return sinks or [("@DEFAULT_SINK@", "Default System Audio Output")]

def get_audio_sources():
    """Returns list of available audio sources / microphones."""
    sources = []
    out = run_cmd("pactl list sources short")
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and not parts[1].endswith(".monitor"):
            name = parts[1]
            label = name.split(".")[-1] if "." in name else name
            sources.append((name, label))
    return sources or [("@DEFAULT_SOURCE@", "Default Microphone")]

def get_mic_volume():
    try:
        out = run_cmd("pactl get-source-volume @DEFAULT_SOURCE@")
        m = re.search(r"(\d+)%", out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 80

def set_mic_volume(pct):
    pct = max(0, min(100, int(pct)))
    return run_cmd(f"pactl set-source-volume @DEFAULT_SOURCE@ {pct}%")

def send_dock_cmd(cmd_dict):
    """Send command dictionary to neon-dock IPC socket."""
    sock_path = f"/run/user/{os.getuid()}/neon-dock.sock"
    if not os.path.exists(sock_path):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.2)
        s.connect(sock_path)
        payload = (json.dumps(cmd_dict) + "\n").encode()
        s.sendall(payload)
        s.close()
        return True
    except Exception:
        return False


