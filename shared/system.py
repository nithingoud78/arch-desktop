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

def hypr_set_keyword(opt_name, value):
    return run_cmd(f"hyprctl keyword {opt_name} {value}")

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

def get_system_info():
    kernel = run_cmd("uname -r")
    cpu_model = run_cmd("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip()
    gpu_model = run_cmd("lspci | grep -iE 'vga|3d' | head -1 | cut -d: -f3").strip()
    mem_total = run_cmd("grep -m1 'MemTotal' /proc/meminfo | awk '{print int($2/1024/1024 + 0.5) \" GB\"}'")
    uptime = run_cmd("uptime -p")
    return {
        "os": "Arch Linux",
        "kernel": kernel,
        "hyprland": run_cmd("hyprctl version | head -1"),
        "cpu": cpu_model,
        "gpu": gpu_model,
        "ram": mem_total,
        "uptime": uptime
    }

