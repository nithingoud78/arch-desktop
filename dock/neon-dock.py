#!/usr/bin/env python3
"""
Neon Desktop — Bottom Dock (Phase 1.1 Final Production Release)
Faithfully addresses all 12 visual matching corrections:
 1. 100% continuous dark glass capsule with zero rectangular purple extension
 2. Seamless multicolour neon lighting (orange -> pink -> magenta -> violet -> purple)
 3. Modes section as a single shared rounded segmented container with vertical icon/name
    (Eco: leaf, Quiet: half-moon, Balanced: scale, Performance: lightning, Turbo: rocket)
 4. Direct 3x3 grid launcher on glass (no grey background box or border)
 5. Fixed application icon cells and mathematical running-indicator alignment
 6. Centered standby artwork and perfectly circular playback control hover states
 7. Compact rounded progress bars for CPU, RAM, GPU monitor
 8. Crisp, antialiased typography using Adwaita Sans & Adwaita Mono
 9. Outlined notification-panel stacked cards icon (not a bell)
10. Preserved balanced system tray and date alignment
11. Full-width dock layout spanning screen with minimal side margins (~16px)
12. Rock-solid dimensions and zero hover layout compression or jitter
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('Gdk', '3.0')
gi.require_version('Gio', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gtk, GtkLayerShell, Gdk, Gio, GLib, Pango, GdkPixbuf
import subprocess
import threading
import json
import os
import signal
import socket
import sys
import time
import math
import colorsys
from datetime import datetime
from pathlib import Path

# Add shared module path
POSSIBLE_SHARED = [
    os.path.expanduser("~/Projects/arch-desktop"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
    os.path.expanduser("~/.config/neon-desktop"),
    os.path.expanduser("~/Projects/neon-desktop"),
]
for p in POSSIBLE_SHARED:
    if os.path.isdir(os.path.join(p, "shared")) and p not in sys.path:
        sys.path.insert(0, p)
        break
from shared import theme, config, system, icons

# ── Display Metrics ──────────────────────────────────────────────────────
DOCK_HEIGHT = 54
APP_ICON_SIZE = 26

def clip_rounded_pixbuf(src_pb, radius=6):
    if not src_pb:
        return None
    w = src_pb.get_width()
    h = src_pb.get_height()
    if w <= 0 or h <= 0:
        return src_pb

    if not src_pb.get_has_alpha():
        pb = src_pb.add_alpha(False, 0, 0, 0)
    else:
        pb = src_pb.copy()

    pixels = bytearray(pb.get_pixels())
    rs = pb.get_rowstride()
    ch = pb.get_n_channels()
    r = float(radius)

    for y in range(h):
        for x in range(w):
            cx, cy = None, None
            if x < r and y < r:
                cx, cy = r, r
            elif x >= w - r and y < r:
                cx, cy = w - r, r
            elif x < r and y >= h - r:
                cx, cy = r, h - r
            elif x >= w - r and y >= h - r:
                cx, cy = w - r, h - r

            if cx is not None:
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if d > r + 0.5:
                    offset = y * rs + x * ch
                    pixels[offset + 3] = 0
                elif d > r - 0.5:
                    factor = max(0.0, min(1.0, r + 0.5 - d))
                    offset = y * rs + x * ch
                    pixels[offset + 3] = int(pixels[offset + 3] * factor)

    glib_bytes = GLib.Bytes.new(bytes(pixels))
    return GdkPixbuf.Pixbuf.new_from_bytes(
        glib_bytes,
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        w,
        h,
        rs
    )

def hex_to_rgba(hex_str, alpha=1.0):
    hex_str = str(hex_str).lstrip('#')
    if len(hex_str) >= 6:
        try:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha:.2f})"
        except ValueError:
            pass
    return f"rgba(168, 85, 247, {alpha:.2f})"

def _clamp255(val):
    return max(0, min(255, int(round(val))))

def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(_clamp255(rgb[0]), _clamp255(rgb[1]), _clamp255(rgb[2]))

def _hls_to_rgb255(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.46, min(0.64, l)), max(0.56, min(0.90, s)))
    return (_clamp255(r * 255), _clamp255(g * 255), _clamp255(b * 255))

def _polish_stop_rgb(r, g, b):
    """Preserve true wallpaper hue while keeping luminous glow contrast on dark glass."""
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    nl = max(0.50, min(0.64, l * 0.45 + 0.56 * 0.55))
    ns = max(0.62, min(0.90, s * 1.32 + 0.22))
    return _hls_to_rgb255(h, nl, ns)

def _lerp_hue_rgb(c1, c2, t):
    """Interpolate two RGB stops without taking alien long hue detours across opposite hues."""
    h1, l1, s1 = colorsys.rgb_to_hls(*(x / 255.0 for x in c1))
    h2, l2, s2 = colorsys.rgb_to_hls(*(x / 255.0 for x in c2))
    dh_signed = (h2 - h1 + 0.5) % 1.0 - 0.5
    if abs(dh_signed) <= 0.25:
        h = (h1 + dh_signed * t) % 1.0
        s = max(0.58, min(0.88, s1 * (1.0 - t) + s2 * t))
        return _hls_to_rgb255(h, l1 * (1.0 - t) + l2 * t, s)
    # Orthogonal/complementary hues: blend in RGB and keep healthy luminance/chroma
    rm = c1[0] * (1.0 - t) + c2[0] * t
    gm = c1[1] * (1.0 - t) + c2[1] * t
    bm = c1[2] * (1.0 - t) + c2[2] * t
    hm, _, sm = colorsys.rgb_to_hls(rm / 255.0, gm / 255.0, bm / 255.0)
    lm = max(0.50, min(0.64, l1 * (1.0 - t) + l2 * t))
    ns = max(0.48, min(0.82, max(sm, min(s1, s2) * 0.68)))
    rr, gg, bb = colorsys.hls_to_rgb(hm, lm, ns)
    return (_clamp255(rr * 255), _clamp255(gg * 255), _clamp255(bb * 255))

def _lighten_hex(hex_str, l_target=0.74):
    s = str(hex_str).lstrip('#')
    if len(s) >= 6:
        try:
            r, g, b = int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0
            h, l, sat = colorsys.rgb_to_hls(r, g, b)
            nr, ng, nb = colorsys.hls_to_rgb(h, max(l, l_target), min(0.95, sat))
            return _rgb_to_hex((nr * 255, ng * 255, nb * 255))
        except ValueError:
            pass
    return "#e879f9"

def _find_hypr_socket():
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if sig:
        sock = os.path.join(runtime_dir, "hypr", sig, ".socket.sock")
        if os.path.exists(sock):
            return sock
    hypr_dir = os.path.join(runtime_dir, "hypr")
    if os.path.isdir(hypr_dir):
        try:
            candidates = sorted(
                (os.path.getmtime(os.path.join(hypr_dir, d)), d)
                for d in os.listdir(hypr_dir)
                if os.path.isdir(os.path.join(hypr_dir, d))
            )
            for _, d in reversed(candidates):
                sock = os.path.join(hypr_dir, d, ".socket.sock")
                if os.path.exists(sock):
                    return sock
        except Exception:
            pass
    return None

def query_hypr_cursorpos(cached_sock=None):
    """Return global logical (x, y) cursor position from Hyprland IPC socket, or None."""
    sock_path = cached_sock or _find_hypr_socket()
    if not sock_path:
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.08)
        s.connect(sock_path)
        s.sendall(b"cursorpos")
        data = s.recv(64).decode("utf-8", errors="ignore").strip()
        s.close()
        if "," in data:
            px, py = data.split(",", 1)
            return int(float(px.strip())), int(float(py.strip()))
    except Exception:
        pass
    return None

def _spawn_detached(args):
    """Launch an application non-blockingly in its own session."""
    try:
        subprocess.Popen(
            args,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

def _find_hypr_env():
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return None
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    hypr_dir = os.path.join(runtime_dir, "hypr")
    if os.path.isdir(hypr_dir):
        try:
            candidates = sorted(
                (os.path.getmtime(os.path.join(hypr_dir, d)), d)
                for d in os.listdir(hypr_dir)
                if os.path.isdir(os.path.join(hypr_dir, d))
            )
            if candidates:
                env = os.environ.copy()
                env["HYPRLAND_INSTANCE_SIGNATURE"] = candidates[-1][1]
                return env
        except Exception:
            pass
    return None

def detect_active_wallpaper(fallback=None):
    """Detect active wallpaper from hyprpaper IPC, swww, hyprpaper.conf, or palette fallback."""
    env = _find_hypr_env()
    try:
        out = subprocess.check_output(
            ["hyprctl", "hyprpaper", "listactive"],
            text=True, timeout=1.0, stderr=subprocess.DEVNULL, env=env
        )
        for line in out.splitlines():
            if ":" in line:
                wp = line.split(":", 1)[1].strip()
                wp = os.path.expanduser(wp)
                if wp and os.path.isfile(wp):
                    return wp
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["swww", "query"],
            text=True, timeout=1.0, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if "image:" in line:
                wp = os.path.expanduser(line.split("image:", 1)[1].strip())
                if wp and os.path.isfile(wp):
                    return wp
    except Exception:
        pass

    conf_path = os.path.expanduser("~/.config/hypr/hyprpaper.conf")
    if os.path.isfile(conf_path):
        try:
            with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("path") and "=" in s:
                        wp = os.path.expanduser(s.split("=", 1)[1].strip())
                        if wp and os.path.isfile(wp):
                            return wp
        except Exception:
            pass

    if fallback and os.path.isfile(os.path.expanduser(str(fallback))):
        return os.path.expanduser(str(fallback))
    return fallback

def extract_dock_theme(wallpaper_path, fallback_palette=None):
    """Extract harmonious dark-glass base and 5 vivid neon stops faithful to the wallpaper."""
    fp = fallback_palette or {}
    default_stops = ["#ff8a00", "#ec4899", "#d946ef", "#9333ea", "#7c3aed"]
    result = {
        "wallpaper": wallpaper_path or fp.get("wallpaper", ""),
        "base_rgb": (13, 12, 20),
        "stops": list(default_stops),
    }

    wp = os.path.expanduser(str(wallpaper_path)) if wallpaper_path else ""
    if not wp or not os.path.isfile(wp):
        return result

    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(wp, 120, 68, False)
        px = pb.get_pixels()
        rs = pb.get_rowstride()
        nc = pb.get_n_channels()
        w = pb.get_width()
        h = pb.get_height()

        bins = [[] for _ in range(24)]
        relaxed_bins = [[] for _ in range(24)]
        darks = []
        for y in range(h):
            for x in range(w):
                i = y * rs + x * nc
                r, g, b = px[i], px[i + 1], px[i + 2]
                hu, li, sa = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
                if 0.03 <= li <= 0.28:
                    darks.append((r, g, b))
                if sa > 0.05 and 0.06 < li < 0.94:
                    bi = int(hu * 24) % 24
                    wt = (0.35 + 0.65 * sa) * (1.05 - 0.50 * abs(li - 0.52))
                    item = (wt, x / max(1, w - 1), r, g, b)
                    relaxed_bins[bi].append(item)
                    if sa > 0.12 and 0.10 < li < 0.90:
                        bins[bi].append(item)

        min_count = max(12, int(w * h * 0.002))
        if sum(len(b) for b in bins) < min_count * 2:
            bins = relaxed_bins

        clusters = []
        for items in bins:
            if len(items) >= min_count:
                tot_w = sum(t[0] for t in items)
                if tot_w <= 0:
                    continue
                ar = sum(t[0] * t[2] for t in items) / tot_w
                ag = sum(t[0] * t[3] for t in items) / tot_w
                ab = sum(t[0] * t[4] for t in items) / tot_w
                ax = sum(t[0] * t[1] for t in items) / tot_w
                ahu, _, _ = colorsys.rgb_to_hls(ar / 255.0, ag / 255.0, ab / 255.0)
                clusters.append((tot_w, ahu, ax, _polish_stop_rgb(ar, ag, ab)))
        clusters.sort(reverse=True)

        chosen = []
        for tot_w, hu, ax, rgb in clusters:
            if all(min(abs(hu - c[1]), 1.0 - abs(hu - c[1])) > 0.11 for c in chosen):
                chosen.append((tot_w, hu, ax, rgb))
            if len(chosen) >= 3:
                break

        if len(chosen) == 3 and chosen[2][0] < chosen[0][0] * 0.22:
            chosen = chosen[:2]

        if darks:
            adr = sum(c[0] for c in darks) / len(darks)
            adg = sum(c[1] for c in darks) / len(darks)
            adb = sum(c[2] for c in darks) / len(darks)
            scale = min(0.32, 22.0 / max(adr, adg, adb, 1.0))
            result["base_rgb"] = (
                _clamp255(adr * scale + 5),
                _clamp255(adg * scale + 5),
                _clamp255(adb * scale + 6),
            )
        elif chosen:
            c0 = chosen[0][3]
            result["base_rgb"] = (
                _clamp255(c0[0] * 0.08 + 6),
                _clamp255(c0[1] * 0.08 + 6),
                _clamp255(c0[2] * 0.08 + 8),
            )

        if chosen:
            c0_rgb = chosen[0][3]
            h0, l0, sat0 = colorsys.rgb_to_hls(*(v / 255.0 for v in c0_rgb))
            if len(chosen) == 1:
                stops_rgb = [_hls_to_rgb255(h0 + d / 360.0, l0, sat0) for d in (-24, -12, 0, 12, 24)]
            elif len(chosen) == 2:
                c1_rgb = chosen[1][3]
                wing_shift = _hls_to_rgb255(h0 + (18 / 360.0), l0, sat0)
                if chosen[1][2] < chosen[0][2]:
                    # Secondary accent is on left side of wallpaper, primary dominates center/right
                    s0, s2, s4 = c1_rgb, c0_rgb, wing_shift
                    s1 = _lerp_hue_rgb(s0, s2, 0.62)
                    s3 = _lerp_hue_rgb(s2, s4, 0.50)
                else:
                    # Primary dominates left/center, secondary accent illuminates right wing
                    s0, s2, s4 = wing_shift, c0_rgb, c1_rgb
                    s1 = _lerp_hue_rgb(s0, s2, 0.50)
                    s3 = _lerp_hue_rgb(s2, s4, 0.38)
                stops_rgb = [s0, s1, s2, s3, s4]
            else:
                # 3 strong colors: primary dominant at center (s2), other two ordered by wallpaper left->right
                wings = sorted([chosen[1], chosen[2]], key=lambda c: c[2])
                s0, s2, s4 = wings[0][3], c0_rgb, wings[1][3]
                stops_rgb = [s0, _lerp_hue_rgb(s0, s2, 0.58), s2, _lerp_hue_rgb(s2, s4, 0.42), s4]
            result["stops"] = [_rgb_to_hex(c) for c in stops_rgb]
    except Exception:
        pass
    return result

# ── Dynamic CSS ──────────────────────────────────────────────────────────
def build_dock_css(palette, dock_theme=None, transparency=90, glow_strength=100, floating=True, radius=None, theme_mode="Dark"):
    dt = dock_theme or extract_dock_theme(palette.get('wallpaper'), palette)
    if theme_mode not in ("Light", "Dark"):
        theme_mode = "Dark"
    is_light = (theme_mode == "Light")
    ws_c = theme.derive_topbar_colors(dt, theme_mode=theme_mode)
    br, bg, bb = dt.get('base_rgb', (13, 10, 26))
    s0, s1, s2, s3, s4 = dt.get('stops', ["#ff8a00", "#ec4899", "#d946ef", "#9333ea", "#7c3aed"])
    s2_light = _lighten_hex(s2, 0.74)

    translucent = True
    try:
        from shared import config
        translucent = config.load_settings().get("translucent_panels", True)
    except Exception:
        pass

    try:
        t_val = float(transparency)
    except Exception:
        t_val = 90.0

    # Reversed as requested: 0% strength = solid (0% transparency), 100% strength = clear (full transparency)
    if translucent:
        inv_t = (100.0 - t_val) / 100.0
        inner_alpha = max(0.12, min(0.98, inv_t * 0.86 + 0.12))
    else:
        inner_alpha = 0.98

    try:
        g_val = float(glow_strength)
    except Exception:
        g_val = 100.0
    glow_scale = max(0.0, min(1.0, g_val / 100.0))

    if radius is not None:
        rad_val = max(0.0, min(16.0, float(radius)))
    else:
        rad_val = 16.0 if floating else 0.0

    ratio = rad_val / 16.0
    border_rad_css = f"border-radius: {rad_val:.1f}px;"
    inner_rad = max(0.0, rad_val - 1.8) if rad_val > 1.8 else 0.0
    inner_rad_css = f"border-radius: {inner_rad:.1f}px;"

    pad_side = 1.8 * ratio
    pad_bot = 1.8 * ratio
    pad_top = 1.8 if (ratio > 0.05 or glow_scale > 0.01) else 0.0
    border_padding_css = f"padding: {pad_top:.1f}px {pad_side:.1f}px {pad_bot:.1f}px {pad_side:.1f}px;"

    if glow_scale > 0.01:
        border_bg_css = f"""background: linear-gradient(90deg, 
        {hex_to_rgba(s0, glow_scale)} 0%, 
        {hex_to_rgba(s1, glow_scale)} 25%, 
        {hex_to_rgba(s2, glow_scale)} 50%, 
        {hex_to_rgba(s3, glow_scale)} 75%, 
        {hex_to_rgba(s4, glow_scale)} 100%
    );"""
    else:
        border_bg_css = "background: transparent;"

    if glow_scale > 0.01 and ratio > 0.05:
        g_alpha = glow_scale * ratio
        radial_glows = f"""
        radial-gradient(ellipse at 1.2% 50%, {hex_to_rgba(s0, 0.82 * g_alpha)} 0%, {hex_to_rgba(s0, 0.40 * g_alpha)} 4.5%, transparent 10.0%),
        radial-gradient(ellipse at 98.8% 50%, {hex_to_rgba(s4, 0.78 * g_alpha)} 0%, {hex_to_rgba(s4, 0.38 * g_alpha)} 4.5%, transparent 10.0%),"""
    else:
        radial_glows = ""

    alpha_scale = inner_alpha / 0.82

    if is_light:
        dock_inner_bg_color = f"rgba(246, 248, 252, {inner_alpha})"
        dock_inner_gradient = f"""linear-gradient(180deg,
            rgba(255, 255, 255, {min(1.0, 0.75 * alpha_scale)}) 0%,
            rgba(244, 247, 254, {min(1.0, 0.40 * alpha_scale)}) 50%,
            rgba(232, 238, 250, {min(1.0, 0.65 * alpha_scale)}) 100%
        ),{radial_glows}
        linear-gradient(90deg,
            {hex_to_rgba(s0, 0.70 * glow_scale)} 0%,
            {hex_to_rgba(s1, 0.65 * glow_scale)} 25%,
            {hex_to_rgba(s2, 0.60 * glow_scale)} 50%,
            {hex_to_rgba(s3, 0.65 * glow_scale)} 75%,
            {hex_to_rgba(s4, 0.70 * glow_scale)} 100%
        );"""
        if glow_scale > 0.01:
            inner_shadow_css = f"""box-shadow: 
        inset 0 1.5px 3px rgba(255, 255, 255, {0.90 * glow_scale * ratio:.2f}), 
        inset 0 -1.5px 3px rgba(0, 0, 0, {0.08 * glow_scale * ratio:.2f});"""
        else:
            inner_shadow_css = "box-shadow: none;"
        launcher_bg_css = "linear-gradient(180deg, rgba(255, 255, 255, 0.90) 0%, rgba(240, 244, 252, 0.75) 44%, rgba(225, 234, 248, 0.85) 100%);"
        launcher_border_css = "1px solid rgba(0, 0, 0, 0.12);"
        launcher_shadow_css = "inset 0 1px 0 rgba(255, 255, 255, 0.95), inset 0 -1px 1px rgba(0, 0, 0, 0.06);"
        launcher_hover_bg_css = "linear-gradient(180deg, rgba(255, 255, 255, 1.0) 0%, rgba(245, 248, 255, 0.85) 44%, rgba(230, 238, 252, 0.90) 100%);"
        launcher_hover_border_css = "1px solid rgba(0, 0, 0, 0.18);"
        sep_color = "rgba(0, 0, 0, 0.10)"
        lbl_nav_color = "#334155"
        lbl_heading_color = "#0f172a"
        ws_bg_css = "rgba(0, 0, 0, 0.05)"
        ws_border_css = "1px solid rgba(0, 0, 0, 0.10)"
        ws_inactive_color = "#64748b"
        player_bg_css = "rgba(0, 0, 0, 0.04)"
        player_border_css = "1px solid rgba(0, 0, 0, 0.08)"
        player_ctrl_color = "#475569"
        player_ctrl_hover_bg = "rgba(0, 0, 0, 0.08)"
        player_ctrl_hover_color = "#0f172a"
        stat_name_color = "#475569"
        stat_val_color = "#0f172a"
        trough_bg = "rgba(0, 0, 0, 0.08)"
        date_tile_css = f"""
    background: {hex_to_rgba(s3, 0.14)};
    background-image: linear-gradient(180deg, {hex_to_rgba(s2, 0.20)} 0%, {hex_to_rgba(s3, 0.10)} 100%);
    border: 1px solid {hex_to_rgba(s2, 0.40)};
    border-radius: 8px;
    padding: 2px 5px;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.80);
    color: {s3};"""
        lbl_date_color = "#475569"
        lbl_time_color = "#0f172a"
        lbl_tray_color = "#334155"
        notes_inner_bg = "rgba(248, 250, 255, 0.95)"
        notes_text_bg = "rgba(0, 0, 0, 0.03)"
        notes_text_border = "rgba(0, 0, 0, 0.08)"
        notes_text_color = "#0f172a"
    else:
        dock_inner_bg_color = f"rgba({br}, {bg}, {bb}, {inner_alpha})"
        dock_inner_gradient = f"""linear-gradient(180deg,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.04 * alpha_scale)}) 0%,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.36 * alpha_scale)}) 14%,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.62 * alpha_scale)}) 32%,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.70 * alpha_scale)}) 50%,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.62 * alpha_scale)}) 68%,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.32 * alpha_scale)}) 86%,
            rgba({br}, {bg}, {bb}, {min(1.0, 0.04 * alpha_scale)}) 100%
        ),{radial_glows}
        linear-gradient(90deg,
            {hex_to_rgba(s0, 0.84 * glow_scale)} 0%,
            {hex_to_rgba(s1, 0.74 * glow_scale)} 25%,
            {hex_to_rgba(s2, 0.70 * glow_scale)} 50%,
            {hex_to_rgba(s3, 0.74 * glow_scale)} 75%,
            {hex_to_rgba(s4, 0.82 * glow_scale)} 100%
        );"""
        if glow_scale > 0.01:
            if ratio > 0.05:
                inner_shadow_css = f"""box-shadow: 
        inset 0 1.5px 4px rgba(255, 255, 255, {0.24 * glow_scale * ratio:.2f}), 
        inset 0 -2px 5px {hex_to_rgba(s2, 0.28 * glow_scale * ratio)};"""
            else:
                inner_shadow_css = f"""box-shadow: 
        inset 0 1.5px 2px rgba(255, 255, 255, {0.18 * glow_scale:.2f}), 
        inset 0 2px 4px {hex_to_rgba(s2, 0.25 * glow_scale)};"""
        else:
            inner_shadow_css = "box-shadow: none;"
        launcher_bg_css = "linear-gradient(180deg, rgba(255, 255, 255, 0.09) 0%, rgba(10, 9, 22, 0.18) 44%, rgba(4, 4, 12, 0.32) 100%);"
        launcher_border_css = "1px solid rgba(255, 255, 255, 0.22);"
        launcher_shadow_css = "inset 0 1px 0 rgba(255, 255, 255, 0.24), inset 0 -1px 1px rgba(0, 0, 0, 0.22);"
        launcher_hover_bg_css = "linear-gradient(180deg, rgba(255, 255, 255, 0.14) 0%, rgba(12, 10, 26, 0.24) 44%, rgba(6, 5, 16, 0.36) 100%);"
        launcher_hover_border_css = "1px solid rgba(255, 255, 255, 0.34);"
        sep_color = "rgba(255, 255, 255, 0.12)"
        lbl_nav_color = "#F5EBFB"
        lbl_heading_color = "#FDFBFE"
        ws_bg_css = ws_c['ws_bg']
        ws_border_css = f"1px solid {ws_c['ws_border']}"
        ws_inactive_color = ws_c['ws_inactive']
        player_bg_css = "rgba(255, 255, 255, 0.04)"
        player_border_css = "1px solid rgba(255, 255, 255, 0.09)"
        player_ctrl_color = "#cbd5e1"
        player_ctrl_hover_bg = "rgba(255, 255, 255, 0.10)"
        player_ctrl_hover_color = "#ffffff"
        stat_name_color = "#F5EBFB"
        stat_val_color = "#FDFBFE"
        trough_bg = "rgba(255, 255, 255, 0.08)"
        date_tile_css = f"""
    background: {hex_to_rgba(s3, 0.28)};
    background-image: linear-gradient(180deg, {hex_to_rgba(s2, 0.34)} 0%, {hex_to_rgba(s3, 0.18)} 100%);
    border: 1px solid {hex_to_rgba(s2_light, 0.58)};
    border-radius: 8px;
    padding: 2px 5px;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
    color: #FDFBFE;"""
        lbl_date_color = "#F5EBFB"
        lbl_time_color = "#FDFBFE"
        lbl_tray_color = "#F5EBFB"
        notes_inner_bg = "rgba(15, 12, 28, 0.95)"
        notes_text_bg = "rgba(255, 255, 255, 0.04)"
        notes_text_border = "rgba(255, 255, 255, 0.08)"
        notes_text_color = "#ffffff"

    return f"""
* {{
    font-family: "Adwaita Sans", "Symbols Nerd Font", "Font Awesome 7 Free", "Font Awesome 7 Free Solid", sans-serif;
    outline: none;
}}

/* ── Reset GTK default button styles ─────────────────────────────────── */
button,
button:hover,
button:active,
button:focus,
button:checked,
button:backdrop,
#dock-inner label,
#dock-inner label:hover,
#dock-inner label:backdrop,
#dock-inner image,
#dock-inner image:hover,
#dock-inner image:backdrop,
#dock-inner button image,
#dock-inner button:hover image,
#dock-inner button:backdrop image,
.dock-btn,
.dock-nav-btn,
.dock-app-btn,
.ws-segment-btn,
.player-ctrl-btn,
#play-pause-btn {{
    border: none;
    outline: none;
    box-shadow: none;
    text-shadow: none;
    background: transparent;
    background-image: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    opacity: 1.0;
    padding: 0;
    margin: 0;
}}

/* ── 1. Root & Outer Window: 100% Genuine Transparency ───────────────── */
window,
window.background,
.background,
#dock-window,
#dock-outer-box {{
    background: transparent;
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
}}

#dock-outer-box {{
    padding: 0;
}}

/* ── 1 & 2. Continuous Multicolour Capsule & Strictly Internal Glow ─── */
/* INVARIANT: The dock exterior must always remain genuinely transparent.
   Only the rounded capsule may render a visible surface. Never leak glow outside the dock border. */
#dock-border {{
    {border_bg_css}
    {border_rad_css}
    {border_padding_css}
    box-shadow: none;
}}

/* ── 1. Inner Translucent Glass (Internal glow behind all elements) */
#dock-inner {{
    background-color: {dock_inner_bg_color};
    background-image: {dock_inner_gradient}
    {inner_rad_css}
    padding: 0 14px;
    {inner_shadow_css}
    transition: background-color 220ms ease, box-shadow 220ms ease;
}}

/* ── 4. Launcher Grid Button: 3x3 Dots Inside Compact Glass Box ─── */
#dock-inner button#launcher-btn,
#launcher-btn,
button#launcher-btn {{
    background: transparent;
    background-color: transparent;
    background-image: {launcher_bg_css}
    border: {launcher_border_css}
    outline: none;
    box-shadow: {launcher_shadow_css}
    padding: 0;
    margin: 0;
    min-width: 30px;
    min-height: 30px;
    border-radius: 10px;
    opacity: 1.0;
    transition: background-image 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}}
#dock-inner button#launcher-btn image,
#launcher-btn image,
#launcher-btn .app-icon {{
    opacity: 1.0;
}}
#dock-inner button#launcher-btn:hover,
#launcher-btn:hover,
button#launcher-btn:hover {{
    background: transparent;
    background-color: transparent;
    background-image: {launcher_hover_bg_css}
    border: {launcher_hover_border_css}
    box-shadow: {launcher_shadow_css}
}}
#dock-inner button#launcher-btn:focus,
#dock-inner button#launcher-btn:active,
#launcher-btn:focus,
#launcher-btn:active,
button#launcher-btn:focus,
button#launcher-btn:active {{
    background: transparent;
    background-color: transparent;
    background-image: {launcher_bg_css}
    border: {launcher_border_css}
    outline: none;
    box-shadow: {launcher_shadow_css}
}}

/* ── 5. Pinned Apps & Dynamic Running Apps ────────────────────────────── */
.dock-app-btn,
.dock-app-btn:hover,
.dock-app-btn:focus,
.dock-app-btn:active,
button.dock-app-btn,
button.dock-app-btn:hover,
button.dock-app-btn:focus,
button.dock-app-btn:active {{
    background: transparent;
    background-color: transparent;
    background-image: none;
    border: none;
    outline: none;
    box-shadow: none;
    padding: 0;
    margin: 0;
    min-width: 20px;
    min-height: 48px;
    border-radius: 0;
    opacity: 1.0;
}}

.app-icon {{
    opacity: 1.0;
    -gtk-icon-shadow: none;
    transition: -gtk-icon-shadow 150ms ease;
}}

#launcher-btn:hover .app-icon,
#launcher-btn:hover image,
.dock-app-btn:hover .app-icon,
.dock-app-btn:hover image {{
    -gtk-icon-shadow: 0 0 6px {hex_to_rgba(s2, 0.85)}, 0 0 12px {hex_to_rgba(s1, 0.45)};
}}

.app-dot {{
    border-radius: 50%;
    min-width: 3px;
    min-height: 3px;
    background: transparent;
    transition: background 150ms ease, opacity 150ms ease;
}}
.app-dot.running {{
    background: {s1};
    box-shadow: 0 0 4px {s1};
    opacity: 1;
}}
.app-dot.not-running {{
    opacity: 0;
}}

/* ── Separators ────────────────────────────────────────────────────────── */
.dock-sep {{
    background: {sep_color};
    min-width: 1px;
    margin: 8px 0;
}}

layout.liquid-nav-slot,
.liquid-nav-slot {{
    background: transparent;
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
}}

/* ── Navigation Buttons (Notes, Search, Snap) ────────────────────────── */
.dock-nav-btn,
.dock-nav-btn:hover,
.dock-nav-btn:focus,
.dock-nav-btn:active,
.dock-nav-btn:checked,
.dock-nav-btn:backdrop,
button.dock-nav-btn,
button.dock-nav-btn:hover,
button.dock-nav-btn:focus,
button.dock-nav-btn:active {{
    border: none;
    outline: none;
    box-shadow: none;
    background: transparent;
    background-color: transparent;
    background-image: none;
    padding: 0;
    margin: 0;
    min-width: 46px;
    min-height: 48px;
}}

.dock-nav-btn,
.dock-nav-btn:hover,
.dock-nav-btn:focus,
.dock-nav-btn:active,
.dock-nav-btn:checked,
.dock-nav-btn:backdrop {{
    opacity: 1.0;
}}

.lbl-nav,
.dock-nav-btn:hover .lbl-nav,
.dock-nav-btn:backdrop .lbl-nav {{
    color: {lbl_nav_color};
    font-size: 8.5px;
    font-weight: 600;
    opacity: 1.0;
    transition: color 180ms ease;
}}

.lbl-heading {{
    color: {lbl_heading_color};
    font-size: 11.5px;
    font-weight: 600;
    transition: color 180ms ease;
}}

/* ── 3. Workspace Switcher: Topbar-Matched Capsule & Sliding Pill ─────── */
#ws-segmented-box {{
    background: {ws_bg_css};
    background-image: none;
    border: {ws_border_css};
    border-radius: 14px;
    box-shadow: none;
    min-width: 200px;
    min-height: 26px;
    transition: background-color 180ms ease, border-color 180ms ease;
}}

#ws-segmented-overlay,
#ws-buttons-box,
.ws-spacer {{
    background: transparent;
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
}}

#ws-segmented-box #ws-active-indicator,
#ws-segmented-box .ws-sliding-capsule,
#ws-active-indicator,
.ws-sliding-capsule {{
    background: linear-gradient(135deg, {hex_to_rgba(ws_c['accent_deep'], 0.88)} 0%, {hex_to_rgba(ws_c['accent_bright'], 0.82)} 100%);
    background-color: {hex_to_rgba(ws_c['accent_mid'], 0.85)};
    border: 1px solid {hex_to_rgba(ws_c['accent_text'], 0.35)};
    outline: none;
    border-radius: 11px;
    box-shadow: 0 0 4px 0px {hex_to_rgba(ws_c['accent_mid'], 0.35)};
    min-width: 24px;
    min-height: 20px;
    opacity: 1.0;
}}

#ws-segmented-box button.ws-segment-btn,
#ws-segmented-box button.ws-segment-btn:hover,
#ws-segmented-box button.ws-segment-btn:focus,
#ws-segmented-box button.ws-segment-btn:active,
#ws-segmented-box button.ws-segment-btn:checked,
#ws-segmented-box button.ws-segment-btn:backdrop,
button.ws-segment-btn,
button.ws-segment-btn:hover,
button.ws-segment-btn:focus,
button.ws-segment-btn:active,
button.ws-segment-btn:checked,
button.ws-segment-btn:backdrop {{
    border: none;
    outline: none;
    box-shadow: none;
    background: transparent;
    background-color: transparent;
    background-image: none;
    -gtk-icon-shadow: none;
    padding: 0;
    margin: 0;
    min-width: 0px;
    min-height: 26px;
}}

.ws-segment-btn .lbl-ws-btn,
.ws-segment-btn:hover .lbl-ws-btn,
.ws-segment-btn:backdrop .lbl-ws-btn,
.lbl-ws-btn {{
    color: {ws_inactive_color};
    font-size: 12px;
    font-weight: 600;
    opacity: 1.0;
    transition: color 180ms ease;
}}
.ws-segment-btn.active-ws .lbl-ws-btn,
.ws-segment-btn.active-ws:hover .lbl-ws-btn {{
    color: #FFFFFF;
    font-weight: 700;
    opacity: 1.0;
}}

/* ── 6. Media Player Card ────────────────────────────────────────────── */
#player-card {{
    background: {player_bg_css};
    border: {player_border_css};
    border-radius: 11px;
    padding: 3px 8px;
    transition: background-color 180ms ease, border-color 180ms ease;
}}
#player-art-box {{
    background: transparent;
    background-color: transparent;
    border: none;
    outline: none;
    box-shadow: none;
    min-width: 28px;
    min-height: 28px;
}}
.player-ctrl-btn {{
    min-width: 20px;
    min-height: 20px;
    border-radius: 10px;
    padding: 0;
    margin: 0;
    color: {player_ctrl_color};
    transition: background 120ms ease, color 120ms ease;
}}
.player-ctrl-btn:hover {{
    background: {player_ctrl_hover_bg};
    color: {player_ctrl_hover_color};
}}
#play-pause-btn {{
    background: linear-gradient(135deg, {s2}, {s1});
    min-width: 22px;
    min-height: 22px;
    border-radius: 11px;
    padding: 0;
    margin: 0;
    box-shadow: 0 0 6px {hex_to_rgba(s2, 0.38)};
    transition: box-shadow 120ms ease;
}}
#play-pause-btn:hover {{
    box-shadow: 0 0 9px {hex_to_rgba(s2, 0.55)};
}}

/* ── Settings Launcher ────────────────────────────────────────────────── */
#dock-inner button#settings-btn,
#dock-inner button#settings-btn:hover,
#dock-inner button#settings-btn:focus,
#dock-inner button#settings-btn:active,
#dock-inner button#settings-btn:backdrop,
#settings-btn,
#settings-btn:hover,
#settings-btn:focus,
#settings-btn:active,
#settings-btn:backdrop {{
    background: transparent;
    background-color: transparent;
    background-image: none;
    border: none;
    outline: none;
    box-shadow: none;
    border-radius: 8px;
    padding: 4px 6px;
}}

/* ── 7. System Monitor: Compact Rounded Progress Bars ─────────────────── */
.sys-progress {{
    min-height: 4px;
    min-width: 52px;
    border-radius: 3px;
    border: none;
    background: transparent;
}}
.sys-progress trough {{
    background: {trough_bg};
    border-radius: 3px;
    min-height: 4px;
    border: none;
}}
.sys-progress progress {{
    background: linear-gradient(90deg, {s1}, {s2}, {s3});
    border-radius: 3px;
    min-height: 4px;
    border: none;
}}
.stat-name {{
    color: {stat_name_color};
    font-size: 9px;
    font-weight: 600;
    min-width: 24px;
    opacity: 1.0;
    transition: color 180ms ease;
}}
.stat-val {{
    color: {stat_val_color};
    font-size: 9.5px;
    font-weight: 500;
    min-width: 28px;
    font-family: "Adwaita Sans", "Symbols Nerd Font", "Font Awesome 7 Free", "Font Awesome 7 Free Solid", sans-serif;
    opacity: 1.0;
    transition: color 180ms ease;
}}

/* ── 8. Date Tile & Typography ───────────────────────────────────────── */
#dock-inner label#date-tile,
#dock-inner #date-tile,
#date-tile {{
    {date_tile_css}
    transition: background-color 180ms ease, border-color 180ms ease, color 180ms ease;
    font-size: 12.5px;
    font-weight: 600;
    font-family: "Adwaita Sans", "Symbols Nerd Font", "Font Awesome 7 Free", "Font Awesome 7 Free Solid", sans-serif;
    min-width: 22px;
    min-height: 22px;
}}
.lbl-date-str {{
    color: {lbl_date_color};
    font-size: 9.5px;
    font-weight: 500;
    opacity: 1.0;
    transition: color 180ms ease;
}}
.lbl-time-str {{
    color: {lbl_time_color};
    font-size: 12px;
    font-weight: 600;
    transition: color 180ms ease;
}}

/* ── 9 & 10. System Tray ─────────────────────────────────────────────── */
.tray-item,
.tray-item:hover,
.tray-item:focus,
.tray-item:active,
.tray-item:backdrop {{
    padding: 2px 2px;
    border-radius: 6px;
    background: transparent;
    opacity: 1.0;
}}
#notif-btn,
#notif-btn:hover,
#notif-btn:focus,
#notif-btn:active,
#notif-btn:backdrop,
#cc-toggle-btn,
#cc-toggle-btn:hover,
#cc-toggle-btn:focus,
#cc-toggle-btn:active,
#cc-toggle-btn:backdrop,
#dock-inner button#cc-toggle-btn,
#dock-inner button#cc-toggle-btn:hover {{
    padding: 2px 2px;
    border-radius: 6px;
    background: transparent;
    background-color: transparent;
    background-image: none;
    opacity: 1.0;
}}
#cc-toggle-img {{
    -gtk-icon-transform: rotate(0deg);
    transition: -gtk-icon-transform 220ms cubic-bezier(0.2, 0.9, 0.3, 1);
}}
#cc-toggle-img.open {{
    -gtk-icon-transform: rotate(180deg);
}}
.tray-item image,
.tray-item:hover image,
.tray-item:focus image,
.tray-item:active image,
.tray-item:backdrop image,
#notif-btn image,
#notif-btn:hover image,
#notif-btn:focus image,
#notif-btn:active image,
#notif-btn:backdrop image,
#dock-inner button#notif-btn image,
#cc-toggle-btn image,
#cc-toggle-btn:hover image,
#cc-toggle-btn:focus image,
#cc-toggle-btn:active image,
#cc-toggle-btn:backdrop image,
#dock-inner button#cc-toggle-btn image,
#arch-desktop-btn image,
#arch-desktop-btn:hover image,
#arch-desktop-btn:focus image,
#arch-desktop-btn:active image,
#arch-desktop-btn:backdrop image,
#dock-inner button#arch-desktop-btn image {{
    opacity: 1.0;
}}
#arch-desktop-btn,
#arch-desktop-btn:hover,
#arch-desktop-btn:focus,
#arch-desktop-btn:active,
#arch-desktop-btn:backdrop,
#dock-inner button#arch-desktop-btn,
#dock-inner button#arch-desktop-btn:hover,
#dock-inner button#arch-desktop-btn:focus,
#dock-inner button#arch-desktop-btn:active,
#dock-inner button#arch-desktop-btn:backdrop {{
    padding: 2px 2px;
    border-radius: 6px;
    border: none;
    background: transparent;
    background-color: transparent;
    background-image: none;
    box-shadow: none;
    opacity: 1.0;
}}
.lbl-tray {{
    color: {lbl_tray_color};
    font-size: 11px;
    font-weight: 500;
    font-family: "Adwaita Sans", "Symbols Nerd Font", "Font Awesome 7 Free", "Font Awesome 7 Free Solid", sans-serif;
    transition: color 180ms ease;
}}

/* ── Notes popup ─────────────────────────────────────────────────────── */
#notes-window {{
    background: transparent;
}}
#notes-border {{
    background: linear-gradient(90deg, {s0}, {s1}, {s2}, {s3}, {s4});
    border-radius: 16px;
    padding: 1.5px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.60);
}}
#notes-inner {{
    background: {notes_inner_bg};
    border-radius: 15px;
    padding: 12px;
}}
.notes-text {{
    background: {notes_text_bg};
    border: {notes_text_border};
    border-radius: 10px;
    color: {notes_text_color};
    padding: 8px;
    font-size: 12px;
}}
"""

def make_sep():
    s = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
    s.get_style_context().add_class("dock-sep")
    return s

def make_sep_box(hexpand=False, margin=8):
    b = Gtk.Box()
    b.set_hexpand(hexpand)
    b.set_margin_start(margin)
    b.set_margin_end(margin)
    s = make_sep()
    s.set_halign(Gtk.Align.CENTER)
    b.pack_start(s, True, False, 0)
    return b


class FixedWidthBox(Gtk.Box):
    """Gtk.Box whose minimum and natural width stays locked to fixed_width."""

    def __init__(self, fixed_width, **kwargs):
        super().__init__(**kwargs)
        self._fixed_w = int(fixed_width)

    def do_get_preferred_width(self):
        return self._fixed_w, self._fixed_w


class FixedWidthButton(Gtk.Button):
    """Gtk.Button whose minimum and natural width stays locked to fixed_width."""

    def __init__(self, fixed_width, **kwargs):
        super().__init__(**kwargs)
        self._fixed_w = int(fixed_width)

    def do_get_preferred_width(self):
        return self._fixed_w, self._fixed_w


class LiquidNavRevealer:
    """VSync-synchronized liquid width + opacity collapse/expand container."""

    DURATION_US = 240000

    def __init__(
        self,
        child,
        target_width=63,
        height=48,
        duration_us=DURATION_US,
        start_revealed=True,
        flex_min_width=None,
        on_shown=None,
        on_hidden=None,
        on_progress=None,
    ):
        self._target_w = max(1, int(target_width))
        self._height = int(height)
        self._duration_us = int(duration_us)
        self._flex_min_w = flex_min_width
        self._on_shown = on_shown
        self._on_hidden = on_hidden
        self._on_progress = on_progress

        self._revealed = bool(start_revealed)
        self._cur_frac = 1.0 if self._revealed else 0.0
        self._start_frac = self._cur_frac
        self._target_frac = self._cur_frac
        self._anim_running = False
        self._anim_start_us = 0
        self._anim_dur_us = self._duration_us
        self._tick_id = None

        self.child = child
        if flex_min_width is None:
            self.child.set_size_request(self._target_w, self._height)
        self.child.set_opacity(1.0 if self._revealed else 0.0)

        self.widget = Gtk.Layout()
        self.widget.get_style_context().add_class("liquid-nav-slot")
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_halign(Gtk.Align.FILL if flex_min_width is not None else Gtk.Align.CENTER)
        self.widget.set_hexpand(bool(flex_min_width is not None and self._revealed))
        self.widget.set_vexpand(False)
        self.widget.set_size(self._target_w, self._height)
        init_w = (flex_min_width if flex_min_width is not None else self._target_w) if self._revealed else 1
        self.widget.set_size_request(init_w, self._height)
        self.widget.put(self.child, 0, 0)
        self.widget.connect("size-allocate", self._on_size_allocate)
        if not self._revealed:
            self.widget.set_no_show_all(True)
            self.widget.set_visible(False)

    def _child_natural_width(self):
        _, c_nat = self.child.get_preferred_width()
        return max(1, c_nat)

    def _on_size_allocate(self, widget, alloc):
        if self._flex_min_w is not None and not self._anim_running and self._revealed:
            cw = self._child_natural_width()
            self.widget.move(self.child, int(round((alloc.width - cw) * 0.5)), 0)

    def is_revealed(self):
        return self._revealed

    def update_sizes(self, target_w, flex_min_w=None):
        self._target_w = max(1, int(target_w))
        if flex_min_w is not None:
            self._flex_min_w = int(flex_min_w)
        self.widget.set_size(self._target_w, self._height)
        if self._revealed and not self._anim_running:
            w = self._flex_min_w if self._flex_min_w is not None else self._target_w
            self.widget.set_size_request(w, self._height)

    def set_callbacks(self, on_shown=None, on_hidden=None, on_progress=None):
        self._on_shown = on_shown
        self._on_hidden = on_hidden
        if on_progress is not None:
            self._on_progress = on_progress

    def begin_collapse(self):
        alloc_w = self.widget.get_allocation().width
        if alloc_w > 1:
            self._target_w = alloc_w
        self.widget.set_hexpand(False)
        self.widget.set_halign(Gtk.Align.CENTER)
        self.widget.set_size_request(max(1, int(round(self._target_w * self._cur_frac))), self._height)
        self.set_reveal(False)

    def _apply_frame(self, frac):
        self._cur_frac = max(0.0, min(1.0, frac))
        cur_w = max(1, int(round(self._target_w * self._cur_frac)))
        cw = self._child_natural_width()
        slide_x = int(round((cur_w - cw) * 0.5))

        # Smoothstep opacity fade ahead of width collapse to avoid visual clipping
        a = max(0.0, min(1.0, (self._cur_frac - 0.16) / 0.84))
        alpha = a * a * (3.0 - 2.0 * a)

        self.child.set_opacity(alpha)
        self.widget.set_size_request(cur_w, self._height)
        self.widget.move(self.child, slide_x, 0)

    def set_reveal(self, reveal, animated=True):
        reveal = bool(reveal)
        if not animated:
            if self._tick_id is not None:
                self.widget.remove_tick_callback(self._tick_id)
                self._tick_id = None
            self._anim_running = False
            self._revealed = reveal
            self._cur_frac = 1.0 if reveal else 0.0
            self._start_frac = self._cur_frac
            self._target_frac = self._cur_frac
            self._apply_frame(self._cur_frac)
            if reveal:
                if self._flex_min_w is not None:
                    self.widget.set_halign(Gtk.Align.FILL)
                    self.widget.set_hexpand(True)
                    self.widget.set_size_request(self._flex_min_w, self._height)
                self.widget.set_no_show_all(False)
                self.widget.set_visible(True)
                if self._on_shown:
                    self._on_shown(self)
            else:
                self.widget.set_no_show_all(True)
                self.widget.set_visible(False)
                if self._on_hidden:
                    self._on_hidden(self)
            return

        if reveal == self._revealed and (
            (not self._anim_running and self._cur_frac == (1.0 if reveal else 0.0))
            or self._anim_running
        ):
            return

        self._revealed = reveal
        if self._tick_id is not None:
            self.widget.remove_tick_callback(self._tick_id)
            self._tick_id = None

        if self._flex_min_w is not None:
            self.widget.set_hexpand(False)
            self.widget.set_halign(Gtk.Align.CENTER)

        self._start_frac = self._cur_frac
        self._target_frac = 1.0 if reveal else 0.0
        dist = abs(self._target_frac - self._start_frac)
        if dist < 0.005:
            self._anim_running = False
            self._apply_frame(self._target_frac)
            if reveal:
                if self._flex_min_w is not None:
                    self.widget.set_halign(Gtk.Align.FILL)
                    self.widget.set_hexpand(True)
                    self.widget.set_size_request(self._flex_min_w, self._height)
                self.widget.set_no_show_all(False)
                self.widget.set_visible(True)
                if self._on_shown:
                    self._on_shown(self)
            else:
                self.widget.set_no_show_all(True)
                self.widget.set_visible(False)
                if self._on_hidden:
                    self._on_hidden(self)
            return

        if reveal and not self.widget.get_visible():
            self._apply_frame(self._cur_frac)
            self.widget.set_no_show_all(False)
            self.widget.set_visible(True)
            self.widget.show_all()

        self._anim_dur_us = max(120000, int(round(self._duration_us * dist)))
        self._anim_start_us = 0
        self._anim_running = True
        self._tick_id = self.widget.add_tick_callback(self._on_tick)

    def _on_tick(self, widget, frame_clock):
        now_us = frame_clock.get_frame_time()
        if self._anim_start_us == 0:
            self._anim_start_us = now_us

        elapsed = max(0, now_us - self._anim_start_us)
        p = min(1.0, elapsed / self._anim_dur_us) if self._anim_dur_us > 0 else 1.0

        # Quintic smootherstep (zero velocity and acceleration at start and end)
        e = p * p * p * (p * (p * 6.0 - 15.0) + 10.0)
        frac = self._start_frac + (self._target_frac - self._start_frac) * e
        self._apply_frame(frac)
        if hasattr(self, "_on_progress") and self._on_progress:
            try:
                self._on_progress(self, frac)
            except Exception:
                pass

        if p >= 1.0:
            self._apply_frame(self._target_frac)
            self._anim_running = False
            self._tick_id = None
            if self._target_frac <= 0.0:
                self.widget.set_no_show_all(True)
                self.widget.set_visible(False)
                if self._on_hidden:
                    self._on_hidden(self)
            else:
                if self._flex_min_w is not None:
                    self.widget.set_halign(Gtk.Align.FILL)
                    self.widget.set_hexpand(True)
                    self.widget.set_size_request(self._flex_min_w, self._height)
                if self._on_shown:
                    self._on_shown(self)
            if hasattr(self, "_on_progress") and self._on_progress:
                try:
                    self._on_progress(self, self._target_frac)
                except Exception:
                    pass
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════
#  FLOATING NOTES POPUP
# ══════════════════════════════════════════════════════════════════════════
class NotesPopup:
    def __init__(self):
        self.window = Gtk.Window()
        self.window.set_title("Neon Notes")
        self.window.set_name("notes-window")

        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.window.set_visual(visual)

        self.window.set_app_paintable(True)
        self.window.set_decorated(False)

        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_namespace(self.window, "neon-notes")
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.BOTTOM, 74)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.LEFT, 160)

        border = Gtk.Box()
        border.set_name("notes-border")

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_name("notes-inner")
        inner.set_size_request(340, 260)

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr.pack_start(icons.get_image("notes", 16, "#f1f5f9"), False, False, 0)
        lbl = Gtk.Label(label="Quick Notes")
        lbl.get_style_context().add_class("lbl-heading")
        hdr.pack_start(lbl, False, False, 0)

        close_btn = Gtk.Button(label="✕")
        close_btn.get_style_context().add_class("dock-btn")
        close_btn.connect("clicked", lambda *_: self.hide())
        hdr.pack_end(close_btn, False, False, 0)
        inner.pack_start(hdr, False, False, 0)

        # Scrolled Text View
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textview.get_style_context().add_class("notes-text")
        self.textbuffer = self.textview.get_buffer()
        self.textbuffer.set_text(config.load_notes())
        self.textbuffer.connect("changed", self._on_text_change)
        sw.add(self.textview)
        inner.pack_start(sw, True, True, 0)

        border.add(inner)
        self.window.add(border)
        self.visible = False

    def _on_text_change(self, buf):
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, True)
        config.save_notes(text)

    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def show(self):
        self.window.show_all()
        self.visible = True

    def hide(self):
        self.window.hide()
        self.visible = False


# ── Applications & Icon Helpers ──────────────────────────────────────────
_ICON_CACHE = {}

def resolve_desktop_icon(app_class):
    if not app_class:
        return "application-x-executable"
    if app_class in _ICON_CACHE:
        return _ICON_CACHE[app_class]

    cls_lower = app_class.lower()
    search_dirs = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/local/share/applications",
        "/usr/share/applications"
    ]

    for d in search_dirs:
        for fname in (f"{app_class}.desktop", f"{cls_lower}.desktop"):
            df = os.path.join(d, fname)
            if os.path.exists(df):
                try:
                    with open(df, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if line.startswith("Icon="):
                                icon = line.split("=", 1)[1].strip()
                                _ICON_CACHE[app_class] = icon
                                return icon
                except Exception:
                    pass

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".desktop"):
                    df = os.path.join(root, f)
                    try:
                        with open(df, "r", encoding="utf-8", errors="ignore") as fp:
                            content = fp.read()
                            if f"StartupWMClass={app_class}" in content or f"StartupWMClass={cls_lower}" in content:
                                for line in content.splitlines():
                                    if line.startswith("Icon="):
                                        icon = line.split("=", 1)[1].strip()
                                        _ICON_CACHE[app_class] = icon
                                        return icon
                    except Exception:
                        pass

    _ICON_CACHE[app_class] = app_class
    return app_class

_APP_GICON_CACHE = {}

def _pixbuf_to_bytes_gicon(pb):
    if not pb:
        return None
    try:
        ok, data = pb.save_to_bufferv("png", [], [])
        if ok and data:
            return Gio.BytesIcon.new(GLib.Bytes.new(data))
    except Exception:
        pass
    return None

def _highres_path_to_gicon(path, target_px, rounded_radius=0):
    if not path or not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in (".svg", ".svgz") and rounded_radius <= 0:
        return Gio.FileIcon.new(Gio.File.new_for_path(path))
    try:
        if ext in (".svg", ".svgz"):
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, target_px, target_px, rounded_radius <= 0)
        else:
            src = GdkPixbuf.Pixbuf.new_from_file(path)
            sw, sh = src.get_width(), src.get_height()
            if rounded_radius > 0:
                tw, th = target_px, target_px
            elif sw >= sh:
                tw = target_px
                th = max(1, int(round(target_px * sh / max(1, sw))))
            else:
                th = target_px
                tw = max(1, int(round(target_px * sw / max(1, sh))))
            if sw == tw and sh == th:
                pb = src
            else:
                pb = src.scale_simple(tw, th, GdkPixbuf.InterpType.HYPER)
        if rounded_radius > 0 and pb is not None:
            pb = clip_rounded_pixbuf(pb, rounded_radius)
        return _pixbuf_to_bytes_gicon(pb)
    except Exception:
        return None

def get_app_gicon(icon_name, size=APP_ICON_SIZE):
    if not icon_name:
        return None
    scale = icons.get_render_scale()
    target_px = max(1, int(round(size * scale)))
    cache_key = (icon_name, target_px)
    if cache_key in _APP_GICON_CACHE:
        return _APP_GICON_CACHE[cache_key]

    gicon = None
    if icon_name.startswith("/") and os.path.isfile(icon_name):
        gicon = _highres_path_to_gicon(icon_name, target_px)
    if gicon is None:
        theme_mgr = Gtk.IconTheme.get_default()
        for name in [icon_name, icon_name.lower(), "application-x-executable"]:
            try:
                info = theme_mgr.lookup_icon_for_scale(name, 256, 1, 0) or theme_mgr.lookup_icon(name, 256, 0)
                if info is not None:
                    fname = info.get_filename()
                    if fname and os.path.isfile(fname):
                        gicon = _highres_path_to_gicon(fname, target_px)
                        if gicon is not None:
                            break
            except Exception:
                continue
        if gicon is None:
            for name in [icon_name, icon_name.lower(), "application-x-executable"]:
                if theme_mgr.has_icon(name):
                    gicon = Gio.ThemedIcon.new(name)
                    break

    _APP_GICON_CACHE[cache_key] = gicon
    return gicon

def get_app_pixbuf(icon_name, size=APP_ICON_SIZE):
    scale = icons.get_render_scale()
    if not icon_name:
        return None
    if icon_name.startswith("/") and os.path.isfile(icon_name):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_name, size * scale, size * scale, True)
        except Exception:
            pass
    theme_mgr = Gtk.IconTheme.get_default()
    for name in [icon_name, icon_name.lower(), "application-x-executable"]:
        try:
            return theme_mgr.load_icon_for_scale(name, size, scale, Gtk.IconLookupFlags.FORCE_SIZE)
        except Exception:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 1: Applications (Launcher, Pinned Apps, Dynamic Running Apps)
# ══════════════════════════════════════════════════════════════════════════
class ApplicationsModule:
    PINNED_APPS = [
        {"id": "org.kde.dolphin", "name": "Files", "icon": "org.kde.dolphin", "match": ["dolphin", "org.kde.dolphin"]},
        {"id": "brave-browser", "name": "Brave", "icon": "brave-desktop", "match": ["brave-browser", "brave"]},
        {"id": "kitty", "name": "Terminal", "icon": "/home/nithin/.local/share/icons/kitty.png", "match": ["kitty"]},
        {"id": "antigravity-ide", "name": "Antigravity", "icon": "/home/nithin/.local/share/icons/antigravity-ide.png", "match": ["antigravity-ide", "antigravity"]},
        {"id": "vlc", "name": "VLC", "icon": "vlc", "match": ["vlc"]}
    ]

    IGNORED_CLASSES = {
        "neon-dock", "wofi", "waybar", "hyprlock", "hyprpaper",
        "xdg-desktop-portal-gtk", "polkit-kde-authentication-agent-1"
    }

    def __init__(self, on_capacity_changed=None, icon_size=APP_ICON_SIZE):
        self.on_capacity_changed = on_capacity_changed
        self.icon_size = max(20, min(36, int(icon_size)))
        self.current_effective_size = self.icon_size
        self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.widget.set_hexpand(True)
        self.widget.set_valign(Gtk.Align.CENTER)

        # 4. 3x3 grid launcher icon centered inside compact dark glass box
        grid_cell = Gtk.Box()
        grid_cell.set_size_request(34, 48)
        grid_cell.set_valign(Gtk.Align.CENTER)
        grid_cell.set_halign(Gtk.Align.CENTER)
        grid_cell.set_margin_end(2)

        btn_grid = Gtk.Button()
        btn_grid.set_name("launcher-btn")
        btn_grid.set_size_request(30, 30)
        btn_grid.set_valign(Gtk.Align.CENTER)
        btn_grid.set_halign(Gtk.Align.CENTER)
        self.grid_icon = icons.get_image("grid", 16, "#ffffff")
        self.grid_icon.set_halign(Gtk.Align.CENTER)
        self.grid_icon.set_valign(Gtk.Align.CENTER)
        self.grid_icon.get_style_context().add_class("app-icon")
        btn_grid.add(self.grid_icon)
        btn_grid.set_tooltip_text("Applications")
        btn_grid.connect(
            "clicked",
            lambda *_: _spawn_detached(["neon-drawer"]),
        )
        grid_cell.pack_start(btn_grid, False, False, 0)
        self.widget.pack_start(grid_cell, False, False, 0)

        # Separator keeping launcher icon distinct from pinned/running apps
        self.widget.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)

        # Pinned and dynamic app icons container (smoothly distributed across available width)
        self.apps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.apps_box.set_homogeneous(False)
        self.apps_box.set_hexpand(True)
        self.apps_box.set_valign(Gtk.Align.CENTER)
        self.widget.pack_start(self.apps_box, True, True, 0)

        self._app_items = []
        self._dynamic_items = {}
        self._pinned_mtime = self._get_pinned_mtime()
        self._load_apps()

    def update_theme_mode(self, mode):
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "grid_icon") and self.grid_icon:
            icons.set_image_icon(self.grid_icon, "grid", 16, col)

    def get_total_apps_count(self):
        active_dyn = sum(1 for info in self._dynamic_items.values() if not info.get("closing"))
        return len(self._app_items) + active_dyn

    def calculate_required_width(self, size, n_apps):
        if n_apps <= 0:
            return 0
        sz = max(20, min(36, int(size)))
        cell_w = max(24, sz)
        spacing = max(0, int((sz - 20) * 0.4))
        return n_apps * cell_w + max(0, n_apps - 1) * spacing

    def calculate_fitting_icon_size(self, req_size, n_apps, avail_w):
        req_size = max(20, min(36, int(req_size)))
        if n_apps <= 0:
            return req_size, 0
        best_size = 20
        for s in range(req_size, 19, -1):
            if self.calculate_required_width(s, n_apps) <= avail_w:
                best_size = s
                break
        best_spacing = max(0, int((best_size - 20) * 0.4))
        return best_size, best_spacing

    def apply_effective_sizing(self, eff_size, eff_spacing):
        if (
            getattr(self, "current_effective_size", None) == eff_size
            and self.apps_box.get_spacing() == eff_spacing
        ):
            return
        self.current_effective_size = eff_size
        self.apps_box.set_spacing(eff_spacing)
        cell_w = max(24, eff_size)

        for item in self._app_items:
            cell = item.get("cell")
            btn = item.get("btn")
            if cell:
                cell.set_size_request(cell_w, 48)
            if btn:
                btn.set_size_request(cell_w, 48)
                img = btn.get_child()
                if isinstance(img, Gtk.Image):
                    img.set_pixel_size(eff_size)

        for info in self._dynamic_items.values():
            cell = info.get("cell")
            btn = info.get("btn")
            slot = info.get("slot")
            if cell:
                cell.set_size_request(cell_w, 48)
            if btn:
                btn.set_size_request(cell_w, 48)
                img = btn.get_child()
                if isinstance(img, Gtk.Image):
                    img.set_pixel_size(eff_size)
            if slot and hasattr(slot, "update_sizes"):
                slot.update_sizes(target_w=cell_w, flex_min_w=cell_w)

    def set_icon_size(self, size):
        self.icon_size = max(20, min(36, int(size)))
        if self.on_capacity_changed:
            self.on_capacity_changed()

    def _create_app_cell(self, name, icon_name, app_id, is_dynamic=False):
        sz = getattr(self, "current_effective_size", getattr(self, "icon_size", APP_ICON_SIZE))
        cell_w = max(24, sz)
        cell = Gtk.Overlay()
        cell.set_size_request(cell_w, 48)
        cell.set_valign(Gtk.Align.CENTER)
        cell.set_halign(Gtk.Align.CENTER)

        btn = Gtk.Button()
        btn.get_style_context().add_class("dock-app-btn")
        btn.set_size_request(cell_w, 48)
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_halign(Gtk.Align.CENTER)

        gicon = get_app_gicon(icon_name, sz)
        if gicon:
            img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.BUTTON)
            img.set_pixel_size(sz)
        else:
            img = icons.get_image("grid", sz, "#ffffff")

        img.set_halign(Gtk.Align.CENTER)
        img.set_valign(Gtk.Align.CENTER)
        img.get_style_context().add_class("app-icon")
        btn.add(img)
        btn.set_tooltip_text(name)
        if is_dynamic:
            btn.connect("clicked", self._focus_or_launch_dynamic, app_id)
        else:
            btn.connect("clicked", self._launch_app, app_id)
        cell.add(btn)

        dot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dot_box.set_valign(Gtk.Align.END)
        dot_box.set_halign(Gtk.Align.CENTER)
        dot_box.set_margin_bottom(3)

        dot = Gtk.Box()
        dot.get_style_context().add_class("app-dot")
        dot.get_style_context().add_class("running" if is_dynamic else "not-running")
        dot.set_size_request(3, 3)
        dot.set_halign(Gtk.Align.CENTER)
        dot.set_valign(Gtk.Align.CENTER)
        dot_box.pack_start(dot, False, False, 0)

        cell.add_overlay(dot_box)
        cell.set_overlay_pass_through(dot_box, True)
        cell.show_all()
        return cell, btn, dot

    def _focus_or_launch_dynamic(self, btn, app_class):
        system.run_cmd(f"hyprctl dispatch focuswindow class:'(?i){app_class}' 2>/dev/null || gtk-launch '{app_class}' 2>/dev/null")

    PINNED_FILE = os.path.expanduser("~/.config/neon-desktop/pinned.json")

    def _get_pinned_list(self):
        if os.path.isfile(self.PINNED_FILE):
            try:
                with open(self.PINNED_FILE, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass
        return self.PINNED_APPS

    def _get_pinned_mtime(self):
        try:
            return os.path.getmtime(self.PINNED_FILE) if os.path.isfile(self.PINNED_FILE) else 0
        except Exception:
            return 0

    def reload_pinned(self):
        for item in self._app_items:
            cell = item.get("cell")
            if cell and cell.get_parent() is self.apps_box:
                self.apps_box.remove(cell)
            if cell:
                cell.destroy()
        self._app_items.clear()
        self._pinned_mtime = self._get_pinned_mtime()
        pinned_list = self._get_pinned_list()
        for idx, item in enumerate(pinned_list):
            app_id = item.get("id", "")
            icon_name = item.get("icon", "")
            name = item.get("name", app_id)
            match = item.get("match", [app_id.lower()])
            cell, btn, dot = self._create_app_cell(name, icon_name, app_id, is_dynamic=False)
            self._app_items.append({"id": app_id, "name": name, "match": match, "cell": cell, "btn": btn, "dot": dot})
            self.apps_box.pack_start(cell, True, True, 0)
            self.apps_box.reorder_child(cell, idx)
        self.apps_box.show_all()
        if self.on_capacity_changed:
            self.on_capacity_changed()

    def check_pinned_update(self):
        cur_mtime = self._get_pinned_mtime()
        if cur_mtime != self._pinned_mtime:
            self.reload_pinned()

    def _load_apps(self):
        for item in self._get_pinned_list():
            app_id = item.get("id", "")
            icon_name = item.get("icon", "")
            name = item.get("name", app_id)
            match = item.get("match", [app_id.lower()])
            cell, btn, dot = self._create_app_cell(name, icon_name, app_id, is_dynamic=False)
            self._app_items.append({"id": app_id, "name": name, "match": match, "cell": cell, "btn": btn, "dot": dot})
            self.apps_box.pack_start(cell, True, True, 0)

    def _launch_app(self, btn, app_id):
        system.run_cmd(f"gtk-launch {app_id} 2>/dev/null || hyprctl dispatch exec '{app_id}'")

    def _finish_remove_dynamic(self, u_cls):
        info = self._dynamic_items.pop(u_cls, None)
        if info and info.get("slot"):
            slot_widget = info["slot"].widget
            if slot_widget.get_parent() is self.apps_box:
                self.apps_box.remove(slot_widget)
            slot_widget.destroy()

    def _on_dynamic_shown(self, slot):
        if slot.widget.get_parent() is self.apps_box:
            self.apps_box.set_child_packing(slot.widget, True, True, 0, Gtk.PackType.START)

    def update_running(self, running_classes):
        matched_classes = set()
        for item in self._app_items:
            matches = item.get("match", [item["id"].lower()])
            is_running = False
            for r_cls in running_classes:
                r_lower = r_cls.lower()
                if any(m in r_lower or r_lower in m for m in matches):
                    is_running = True
                    matched_classes.add(r_cls)
            ctx = item["dot"].get_style_context()
            if is_running:
                ctx.remove_class("not-running")
                ctx.add_class("running")
            else:
                ctx.remove_class("running")
                ctx.add_class("not-running")

        unpinned = set()
        for r_cls in running_classes:
            if not r_cls or r_cls.lower() in self.IGNORED_CLASSES or r_cls in matched_classes:
                continue
            already_pinned = False
            for item in self._app_items:
                if any(m in r_cls.lower() or r_cls.lower() in m for m in item.get("match", [])):
                    already_pinned = True
                    break
            if not already_pinned:
                unpinned.add(r_cls)

        changed = False
        active_count = sum(1 for info in self._dynamic_items.values() if not info.get("closing"))
        for u_cls in sorted(unpinned):
            existing = self._dynamic_items.get(u_cls)
            if existing is not None:
                if existing.get("closing"):
                    existing["closing"] = False
                    slot = existing["slot"]
                    slot.set_callbacks(on_shown=self._on_dynamic_shown, on_hidden=None)
                    if slot.widget.get_parent() is self.apps_box:
                        self.apps_box.set_child_packing(slot.widget, False, False, 0, Gtk.PackType.START)
                    slot.set_reveal(True)
                    active_count += 1
                    changed = True
                continue

            if active_count >= 8:
                break

            active_count += 1
            avail_w = self.apps_box.get_allocation().width
            if avail_w < 100:
                avail_w = 300
            total_visible = len(self._app_items) + active_count
            target_slot_w = max(28, int(round(avail_w / max(1, total_visible))))

            icon_target = resolve_desktop_icon(u_cls)
            display_name = u_cls.capitalize()
            cell, btn, dot = self._create_app_cell(display_name, icon_target, u_cls, is_dynamic=True)
            pin_w = max(24, self._app_items[0]["cell"].get_preferred_width()[1]) if self._app_items else 26
            slot = LiquidNavRevealer(
                cell,
                target_width=target_slot_w,
                height=48,
                duration_us=340000,
                start_revealed=False,
                flex_min_width=pin_w,
                on_shown=self._on_dynamic_shown,
            )
            self.apps_box.pack_start(slot.widget, False, False, 0)
            self._dynamic_items[u_cls] = {
                "slot": slot,
                "cell": cell,
                "btn": btn,
                "dot": dot,
                "closing": False,
            }
            slot.set_reveal(True)
            changed = True

        for k, info in list(self._dynamic_items.items()):
            if k not in unpinned and not info.get("closing"):
                info["closing"] = True
                slot = info["slot"]
                if slot.widget.get_parent() is self.apps_box:
                    self.apps_box.set_child_packing(slot.widget, False, False, 0, Gtk.PackType.START)
                slot.set_callbacks(
                    on_shown=None,
                    on_hidden=lambda s, key=k: self._finish_remove_dynamic(key),
                )
                slot.begin_collapse()
                changed = True

        if changed and self.on_capacity_changed:
            active_dyn = sum(1 for info in self._dynamic_items.values() if not info.get("closing"))
            total_apps = len(self._app_items) + active_dyn
            self.on_capacity_changed(total_apps)


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 2: Notes (Vertical stack, icon above, name below, fixed cell)
# ══════════════════════════════════════════════════════════════════════════
class NotesModule:
    def __init__(self, notes_popup):
        self.popup = notes_popup
        self.widget = Gtk.Button()
        self.widget.get_style_context().add_class("dock-nav-btn")
        self.widget.set_size_request(46, 48)
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_halign(Gtk.Align.CENTER)
        self.widget.set_hexpand(False)
        self.widget.set_vexpand(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_size_request(46, -1)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_hexpand(False)
        vbox.set_vexpand(False)

        self.icon = icons.get_image("notes", 13, "#ffffff")
        self.icon.set_halign(Gtk.Align.CENTER)
        self.icon.set_valign(Gtk.Align.CENTER)
        vbox.pack_start(self.icon, False, False, 0)

        lbl = Gtk.Label(label="Notes")
        lbl.get_style_context().add_class("lbl-nav")
        lbl.set_size_request(46, -1)
        lbl.set_xalign(0.5)
        lbl.set_yalign(0.5)
        vbox.pack_start(lbl, False, False, 0)

        self.widget.add(vbox)
        self.widget.connect(
            "clicked",
            lambda *_: _spawn_detached(["sh", "-c", "pgrep -x copyq >/dev/null || (copyq & sleep 0.3); copyq show"]),
        )

    def update_theme_mode(self, mode):
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "icon") and self.icon:
            icons.set_image_icon(self.icon, "notes", 13, col)


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 3: Search (Vertical stack, icon above, name below, fixed cell)
# ══════════════════════════════════════════════════════════════════════════
class SearchModule:
    def __init__(self):
        self.widget = Gtk.Button()
        self.widget.get_style_context().add_class("dock-nav-btn")
        self.widget.set_size_request(46, 48)
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_halign(Gtk.Align.CENTER)
        self.widget.set_hexpand(False)
        self.widget.set_vexpand(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_size_request(46, -1)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_hexpand(False)
        vbox.set_vexpand(False)

        self.icon = icons.get_image("search", 13, "#ffffff")
        self.icon.set_halign(Gtk.Align.CENTER)
        self.icon.set_valign(Gtk.Align.CENTER)
        vbox.pack_start(self.icon, False, False, 0)

        lbl = Gtk.Label(label="Search")
        lbl.get_style_context().add_class("lbl-nav")
        lbl.set_size_request(46, -1)
        lbl.set_xalign(0.5)
        lbl.set_yalign(0.5)
        vbox.pack_start(lbl, False, False, 0)

        self.widget.add(vbox)
        self.widget.connect("clicked", lambda *_: _spawn_detached(["neon-drun"]))

    def update_theme_mode(self, mode):
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "icon") and self.icon:
            icons.set_image_icon(self.icon, "search", 13, col)


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 4: Snap (Aperture icon, name below, fixed cell, interactive screenshot)
# ══════════════════════════════════════════════════════════════════════════
class SnapModule:
    def __init__(self):
        self.widget = Gtk.Button()
        self.widget.get_style_context().add_class("dock-nav-btn")
        self.widget.set_size_request(46, 48)
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_halign(Gtk.Align.CENTER)
        self.widget.set_hexpand(False)
        self.widget.set_vexpand(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_size_request(46, -1)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_hexpand(False)
        vbox.set_vexpand(False)

        self.icon = icons.get_image("aperture", 13, "#ffffff")
        self.icon.set_halign(Gtk.Align.CENTER)
        self.icon.set_valign(Gtk.Align.CENTER)
        vbox.pack_start(self.icon, False, False, 0)

        lbl = Gtk.Label(label="Snap")
        lbl.get_style_context().add_class("lbl-nav")
        lbl.set_size_request(46, -1)
        lbl.set_xalign(0.5)
        lbl.set_yalign(0.5)
        vbox.pack_start(lbl, False, False, 0)

        self.widget.add(vbox)
        self.widget.connect("clicked", self._take_screenshot)

    def update_theme_mode(self, mode):
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "icon") and self.icon:
            icons.set_image_icon(self.icon, "aperture", 13, col)

    def _take_screenshot(self, *args):
        cmd = """
        mkdir -p ~/Pictures/Screenshots
        grim -g "$(slurp)" ~/Pictures/Screenshots/Snap_$(date +%Y%m%d_%H%M%S).png 2>/dev/null &
        """
        system.run_cmd(cmd)


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 5: Workspace Switcher (Topbar-Matched Hyprland Workspaces)
# ══════════════════════════════════════════════════════════════════════════
class WorkspaceSwitcherModule:
    PERSISTENT_IDS = [1, 2, 3, 4]
    TOTAL_WIDTH = 200
    CONTAINER_HEIGHT = 26
    SPACER_X = 6
    CAPSULE_HEIGHT = 22
    CAPSULE_Y = 2

    def __init__(self):
        self.widget = FixedWidthBox(self.TOTAL_WIDTH, orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.widget.set_name("ws-segmented-box")
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_halign(Gtk.Align.CENTER)
        self.widget.set_hexpand(False)
        self.widget.set_vexpand(False)
        self.widget.set_size_request(self.TOTAL_WIDTH, self.CONTAINER_HEIGHT)

        self.segmented_container = Gtk.Overlay()
        self.segmented_container.set_name("ws-segmented-overlay")
        self.segmented_container.set_valign(Gtk.Align.CENTER)
        self.segmented_container.set_halign(Gtk.Align.CENTER)
        self.segmented_container.set_size_request(self.TOTAL_WIDTH, self.CONTAINER_HEIGHT)
        self.segmented_container.set_hexpand(False)

        self.slider_fixed = Gtk.Fixed()
        self.slider_fixed.set_size_request(self.TOTAL_WIDTH, self.CONTAINER_HEIGHT)
        self.slider_fixed.set_hexpand(False)
        self.slider_fixed.set_halign(Gtk.Align.CENTER)

        self.slider_capsule = Gtk.Box()
        self.slider_capsule.set_name("ws-active-indicator")
        self.slider_capsule.get_style_context().add_class("ws-sliding-capsule")

        self.ws_ids = list(self.PERSISTENT_IDS)
        self.active_ws = 1
        self.active_idx = 0
        self.buttons = []
        self.btn_width = 47
        self.capsule_width = 43

        self.current_x = float(self.SPACER_X + 2)
        self.target_x = self.current_x
        self.start_x = self.current_x
        self._tick_id = None
        self._anim_running = False
        self.anim_start_time_us = 0
        self.anim_duration_us = 220000

        self.slider_fixed.put(self.slider_capsule, int(round(self.current_x)), self.CAPSULE_Y)
        self.segmented_container.add(self.slider_fixed)

        self.buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.buttons_box.set_name("ws-buttons-box")
        self.buttons_box.set_size_request(self.TOTAL_WIDTH, self.CONTAINER_HEIGHT)
        self.buttons_box.set_hexpand(False)
        self.buttons_box.set_halign(Gtk.Align.CENTER)

        self.sp_left = Gtk.Box()
        self.sp_left.get_style_context().add_class("ws-spacer")
        self.buttons_box.pack_start(self.sp_left, False, False, 0)

        self.slots_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.slots_box.set_halign(Gtk.Align.CENTER)
        self.slots_box.set_valign(Gtk.Align.CENTER)
        self.buttons_box.pack_start(self.slots_box, False, False, 0)

        self.sp_right = Gtk.Box()
        self.sp_right.get_style_context().add_class("ws-spacer")
        self.buttons_box.pack_start(self.sp_right, False, False, 0)

        self.segmented_container.add_overlay(self.buttons_box)

        ev_box = Gtk.EventBox()
        ev_box.set_visible_window(False)
        ev_box.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        ev_box.connect("scroll-event", self._on_scroll)
        ev_box.add(self.segmented_container)

        self.widget.pack_start(ev_box, False, False, 0)

        self._rebuild_buttons(self.ws_ids)
        self._refresh_workspaces(animate=False)
        self._start_hypr_listener()
        GLib.timeout_add(2500, lambda: self._refresh_workspaces(animate=True) or True)

    def _query_hypr_json(self, cmd):
        sock = _find_hypr_socket()
        if sock:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.35)
                s.connect(sock)
                s.sendall(cmd.encode("utf-8"))
                chunks = []
                while True:
                    d = s.recv(4096)
                    if not d:
                        break
                    chunks.append(d)
                s.close()
                return json.loads(b"".join(chunks).decode("utf-8", errors="ignore"))
            except Exception:
                pass
        return None

    def _switch_workspace(self, ws_id):
        lua = f"hl.dispatch(hl.dsp.focus({{ workspace = {int(ws_id)} }}))"
        def _send():
            sock = _find_hypr_socket()
            if sock:
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(0.4)
                    s.connect(sock)
                    s.sendall(f"eval {lua}".encode("utf-8"))
                    s.recv(256)
                    s.close()
                    return
                except Exception:
                    pass
            _spawn_detached(["hyprctl", "eval", lua])
        threading.Thread(target=_send, daemon=True).start()

    def _rebuild_buttons(self, ws_ids):
        for child in self.slots_box.get_children():
            self.slots_box.remove(child)
        self.buttons = []
        self.ws_ids = list(ws_ids)

        n = max(1, len(self.ws_ids))
        avail = self.TOTAL_WIDTH - (self.SPACER_X * 2)
        self.btn_width = max(24, avail // n)
        used = self.btn_width * n
        left_pad = (self.TOTAL_WIDTH - used) // 2
        right_pad = self.TOTAL_WIDTH - used - left_pad
        self.sp_left.set_size_request(max(0, left_pad), self.CONTAINER_HEIGHT)
        self.sp_right.set_size_request(max(0, right_pad), self.CONTAINER_HEIGHT)
        self._left_pad = max(0, left_pad)

        self.capsule_width = max(20, self.btn_width - 4)
        self.slider_capsule.set_size_request(self.capsule_width, self.CAPSULE_HEIGHT)

        for wid in self.ws_ids:
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_focus_on_click(False)
            btn.get_style_context().add_class("ws-segment-btn")
            btn.set_size_request(self.btn_width, self.CONTAINER_HEIGHT)
            btn.set_hexpand(False)

            lbl = Gtk.Label(label=str(wid))
            lbl.get_style_context().add_class("lbl-ws-btn")
            lbl.set_halign(Gtk.Align.CENTER)
            lbl.set_valign(Gtk.Align.CENTER)
            btn.add(lbl)
            btn.connect("clicked", self._on_ws_click, wid)
            btn._ws_id = wid
            self.buttons.append(btn)
            self.slots_box.pack_start(btn, False, False, 0)

        self.slots_box.show_all()

    def _target_x_for_idx(self, idx):
        center = self._left_pad + (idx * self.btn_width) + (self.btn_width / 2.0)
        return center - (self.capsule_width / 2.0)

    def _on_ws_click(self, btn, ws_id):
        if ws_id != self.active_ws:
            self._apply_state(self.ws_ids, ws_id, animate=True)
        self._switch_workspace(ws_id)

    def _on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP or (
            event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y < 0
        ):
            idx = max(0, self.active_idx - 1)
        elif event.direction == Gdk.ScrollDirection.DOWN or (
            event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y > 0
        ):
            idx = min(len(self.ws_ids) - 1, self.active_idx + 1)
        else:
            return False
        if 0 <= idx < len(self.ws_ids):
            wid = self.ws_ids[idx]
            if wid != self.active_ws:
                self._apply_state(self.ws_ids, wid, animate=True)
                self._switch_workspace(wid)
        return True

    def _refresh_workspaces(self, animate=True):
        def _fetch():
            aw = self._query_hypr_json("j/activeworkspace")
            ws_list = self._query_hypr_json("j/workspaces")
            if aw is None and ws_list is None:
                return
            try:
                active_id = int(aw.get("id") or 0) if isinstance(aw, dict) else 1
            except Exception:
                active_id = 0
            ids = set(self.PERSISTENT_IDS)
            if active_id > 0:
                ids.add(active_id)
            if isinstance(ws_list, list):
                for w in ws_list:
                    try:
                        wid = int(w.get("id") or 0) if isinstance(w, dict) else 0
                    except Exception:
                        wid = 0
                    if wid > 0:
                        ids.add(wid)
            sorted_ids = sorted(ids)
            GLib.idle_add(self._apply_state, sorted_ids, active_id, animate)
        threading.Thread(target=_fetch, daemon=True).start()
        return False

    def _apply_state(self, ws_ids, active_id, animate=True):
        if ws_ids != self.ws_ids:
            self._rebuild_buttons(ws_ids)

        self.active_ws = active_id
        has_active = active_id in self.ws_ids
        self.slider_capsule.set_visible(has_active)
        new_idx = self.ws_ids.index(active_id) if has_active else self.active_idx
        self.active_idx = new_idx

        for btn in self.buttons:
            ctx = btn.get_style_context()
            if has_active and btn._ws_id == active_id:
                if not ctx.has_class("active-ws"):
                    ctx.add_class("active-ws")
            else:
                if ctx.has_class("active-ws"):
                    ctx.remove_class("active-ws")

        if not has_active:
            return False

        target_x = self._target_x_for_idx(new_idx)
        if not animate:
            if self._tick_id is not None:
                self.slider_fixed.remove_tick_callback(self._tick_id)
                self._tick_id = None
            self._anim_running = False
            self.current_x = target_x
            self.target_x = target_x
            self.slider_fixed.move(self.slider_capsule, int(round(target_x)), self.CAPSULE_Y)
        else:
            self._slide_to_x(target_x)
        return False

    def _slide_to_x(self, target_x):
        if abs(target_x - self.current_x) < 0.25 and not self._anim_running:
            return
        if self._tick_id is not None:
            self.slider_fixed.remove_tick_callback(self._tick_id)
            self._tick_id = None

        self.start_x = self.current_x
        self.target_x = float(target_x)
        self.anim_start_time_us = 0
        dist = abs(self.target_x - self.start_x)
        duration_sec = 0.17 + 0.06 * min(1.0, dist / 145.0)
        self.anim_duration_us = int(duration_sec * 1_000_000)

        self._anim_running = True
        self._tick_id = self.slider_fixed.add_tick_callback(self._on_tick)

    def _on_tick(self, widget, frame_clock):
        frame_time = frame_clock.get_frame_time()
        if self.anim_start_time_us == 0:
            self.anim_start_time_us = frame_time
        elapsed_us = max(0, frame_time - self.anim_start_time_us)
        progress = min(1.0, elapsed_us / self.anim_duration_us) if self.anim_duration_us > 0 else 1.0
        ease = 1.0 - pow(1.0 - progress, 3.2)
        self.current_x = self.start_x + (self.target_x - self.start_x) * ease
        self.slider_fixed.move(self.slider_capsule, int(round(self.current_x)), self.CAPSULE_Y)
        if progress >= 1.0:
            self.current_x = self.target_x
            self.slider_fixed.move(self.slider_capsule, int(round(self.current_x)), self.CAPSULE_Y)
            self._anim_running = False
            self._tick_id = None
            return False
        return True

    def _start_hypr_listener(self):
        def _listen():
            while True:
                sock1 = _find_hypr_socket()
                sock2 = sock1.replace(".socket.sock", ".socket2.sock") if sock1 else None
                if not sock2 or not os.path.exists(sock2):
                    time.sleep(2.0)
                    continue
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(sock2)
                    s.settimeout(5.0)
                    while True:
                        try:
                            data = s.recv(1024)
                            if not data:
                                break
                            text = data.decode("utf-8", errors="ignore")
                            for line in text.splitlines():
                                if line.startswith((
                                    "workspace>>", "workspacev2>>",
                                    "focusedmon>>", "focusedmonv2>>",
                                    "createworkspace>>", "createworkspacev2>>",
                                    "destroyworkspace>>", "destroyworkspacev2>>",
                                )):
                                    self._refresh_workspaces(animate=True)
                                    break
                        except socket.timeout:
                            continue
                except Exception:
                    time.sleep(1.0)
        threading.Thread(target=_listen, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 6: Media Player (Live Multi-Player MPRIS Tracking)
# ══════════════════════════════════════════════════════════════════════════
class PlayerModule:
    def __init__(self):
        self.widget = FixedWidthBox(228, orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.widget.set_name("player-card")
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_size_request(228, 36)

        # Centered Standby/Artwork Box with rounded corners
        self.art_box = FixedWidthBox(28)
        self.art_box.set_name("player-art-box")
        self.art_box.set_size_request(28, 28)
        self.art_box.set_valign(Gtk.Align.CENTER)
        self.art_box.set_halign(Gtk.Align.CENTER)

        self.art_img = Gtk.Image()
        self.art_img.set_halign(Gtk.Align.CENTER)
        self.art_img.set_valign(Gtk.Align.CENTER)
        self.art_box.pack_start(self.art_img, True, True, 0)
        self.widget.pack_start(self.art_box, False, False, 0)

        # Track title & artist
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        info.set_valign(Gtk.Align.CENTER)
        info.set_size_request(98, -1)

        self.title_lbl = Gtk.Label(label="Standby")
        self.title_lbl.get_style_context().add_class("lbl-heading")
        self.title_lbl.set_xalign(0)
        self.title_lbl.set_single_line_mode(True)
        self.title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_lbl.set_width_chars(1)
        self.title_lbl.set_max_width_chars(14)
        info.pack_start(self.title_lbl, False, False, 0)

        self.artist_lbl = Gtk.Label(label="Play me")
        self.artist_lbl.get_style_context().add_class("lbl-date-str")
        self.artist_lbl.set_xalign(0)
        self.artist_lbl.set_single_line_mode(True)
        self.artist_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_lbl.set_width_chars(1)
        self.artist_lbl.set_max_width_chars(14)
        info.pack_start(self.artist_lbl, False, False, 0)
        self.widget.pack_start(info, True, True, 2)

        # Circular playback controls
        ctrls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        ctrls.set_valign(Gtk.Align.CENTER)

        btn_prev = Gtk.Button()
        btn_prev.get_style_context().add_class("player-ctrl-btn")
        btn_prev.set_size_request(20, 20)
        self.prev_img = icons.get_image("prev", 11, "#ffffff")
        btn_prev.add(self.prev_img)
        btn_prev.connect("clicked", self._on_prev)
        ctrls.pack_start(btn_prev, False, False, 0)

        self.btn_play = Gtk.Button()
        self.btn_play.set_name("play-pause-btn")
        self.btn_play.set_size_request(22, 22)
        self.play_img = icons.get_image("play", 11, "#ffffff")
        self.btn_play.add(self.play_img)
        self.btn_play.connect("clicked", self._on_play_pause)
        ctrls.pack_start(self.btn_play, False, False, 0)

        btn_next = Gtk.Button()
        btn_next.get_style_context().add_class("player-ctrl-btn")
        btn_next.set_size_request(20, 20)
        self.next_img = icons.get_image("next", 11, "#ffffff")
        btn_next.add(self.next_img)
        btn_next.connect("clicked", self._on_next)
        ctrls.pack_start(btn_next, False, False, 0)

        self.widget.pack_start(ctrls, False, False, 0)

        self._active_player = None
        self._reset_art()

        self._update()
        GLib.timeout_add(1500, self._update)

    def update_theme_mode(self, mode):
        self.theme_mode = mode
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "prev_img") and self.prev_img:
            icons.set_image_icon(self.prev_img, "prev", 11, col)
        if hasattr(self, "next_img") and self.next_img:
            icons.set_image_icon(self.next_img, "next", 11, col)

    def _on_prev(self, *args):
        p_arg = f"-p {self._active_player}" if self._active_player else ""
        system.run_cmd(f"playerctl {p_arg} previous 2>/dev/null")

    def _on_play_pause(self, *args):
        p_arg = f"-p {self._active_player}" if self._active_player else ""
        system.run_cmd(f"playerctl {p_arg} play-pause 2>/dev/null")

    def _on_next(self, *args):
        p_arg = f"-p {self._active_player}" if self._active_player else ""
        system.run_cmd(f"playerctl {p_arg} next 2>/dev/null")

    def _update(self):
        def _fetch():
            data = system.get_mpris_info()
            GLib.idle_add(self._apply, data)
        threading.Thread(target=_fetch, daemon=True).start()
        return True

    def _apply(self, data):
        if not data:
            self._active_player = None
            self.title_lbl.set_text("Standby")
            self.artist_lbl.set_text("Play me")
            icons.set_image_icon(self.play_img, "play", 11, "#ffffff")
            self._reset_art()
            return

        self._active_player = data.get("player")
        st = data.get("status", "Stopped")
        title = data.get("title", "") or "Music"
        artist = data.get("artist", "") or "Playing"
        url = (data.get("url", "") or "").lower()
        art_url = data.get("art", "")
        player = (data.get("player", "") or "").lower()

        self.title_lbl.set_text(title)
        self.artist_lbl.set_text(artist)

        icon_key = "pause" if st == "Playing" else "play"
        icons.set_image_icon(self.play_img, icon_key, 11, "#ffffff")

        # 1. Album artwork: If active MPRIS session provides artwork, display that artwork
        scale = icons.get_render_scale()
        clean_path = art_url.replace("file://", "")
        if clean_path and os.path.isfile(clean_path):
            art_gicon = _highres_path_to_gicon(clean_path, 28 * scale, rounded_radius=6 * scale)
            if art_gicon:
                self.art_img.set_from_gicon(art_gicon, Gtk.IconSize.BUTTON)
                self.art_img.set_pixel_size(28)
                return

        # 2. YouTube media: If album artwork is unavailable and media is identified as YouTube
        is_youtube = ("youtube" in url or "youtube" in title.lower() or "youtube" in artist.lower())
        if is_youtube:
            if icons.set_image_icon(self.art_img, "youtube", 18, "#ff0033"):
                return

        # 3. Browser media: Display actual browser/application icon
        if "brave" in player:
            g_app = get_app_gicon("brave-desktop", 20)
            if g_app:
                self.art_img.set_from_gicon(g_app, Gtk.IconSize.BUTTON)
                self.art_img.set_pixel_size(20)
                return
        elif "chrome" in player or "chromium" in player:
            g_app = get_app_gicon("google-chrome", 20)
            if g_app:
                self.art_img.set_from_gicon(g_app, Gtk.IconSize.BUTTON)
                self.art_img.set_pixel_size(20)
                return
        elif "firefox" in player:
            g_app = get_app_gicon("firefox", 20)
            if g_app:
                self.art_img.set_from_gicon(g_app, Gtk.IconSize.BUTTON)
                self.art_img.set_pixel_size(20)
                return

        # 4. Other players: Use corresponding player application icon
        base_player = player.split(".")[0]
        theme_mgr = Gtk.IconTheme.get_default()
        if theme_mgr.has_icon(base_player):
            g_app = get_app_gicon(base_player, 20)
            if g_app:
                self.art_img.set_from_gicon(g_app, Gtk.IconSize.BUTTON)
                self.art_img.set_pixel_size(20)
                return

        # 5. Standby / fallback: Music note icon
        self._reset_art()

    def _reset_art(self):
        icons.set_image_icon(self.art_img, "music", 14, "#ffffff")


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 7: Settings Launcher
# ══════════════════════════════════════════════════════════════════════════
class SettingsModule:
    def __init__(self):
        self.widget = FixedWidthButton(82)
        self.widget.set_name("settings-btn")
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_size_request(82, 32)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        settings_png = os.path.expanduser("~/.local/share/icons/settings.png")
        if os.path.isfile(settings_png):
            try:
                gicon = Gio.FileIcon.new(Gio.File.new_for_path(settings_png))
                s_img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.BUTTON)
                s_img.set_pixel_size(18)
            except Exception:
                s_img = icons.get_image("settings", 16, "#ffffff")
        else:
            s_img = icons.get_image("settings", 16, "#ffffff")
        self.s_img = s_img
        box.pack_start(s_img, False, False, 0)

        lbl = Gtk.Label(label="Settings")
        lbl.get_style_context().add_class("lbl-heading")
        box.pack_start(lbl, False, False, 0)

        self.widget.add(box)
        self.widget.connect("clicked", lambda *_: subprocess.Popen(["/home/nithin/.local/bin/settings"], start_new_session=True))

    def update_theme_mode(self, mode):
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "s_img") and self.s_img and not os.path.isfile(os.path.expanduser("~/.local/share/icons/settings.png")):
            icons.set_image_icon(self.s_img, "settings", 16, col)


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 8: System Monitor (Req 7: Compact Rounded Progress Bars)
# ══════════════════════════════════════════════════════════════════════════
class MiniProgressBar(Gtk.ProgressBar):
    def do_get_preferred_width(self):
        return 58, 58

class SystemMonitorModule:
    def __init__(self):
        self.widget = FixedWidthBox(137, orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_size_request(137, 38)

        self.chip_icon = icons.get_image("cpu", 16, "#c084fc")
        self.widget.pack_start(self.chip_icon, False, False, 0)

        # Stack of 3 rounded progress rows
        rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)

        self.cpu_row, self.cpu_bar, self.cpu_lbl = self._make_row("CPU")
        self.ram_row, self.ram_bar, self.ram_lbl = self._make_row("RAM")
        self.gpu_row, self.gpu_bar, self.gpu_lbl = self._make_row("GPU")

        rows_box.pack_start(self.cpu_row, False, False, 0)
        rows_box.pack_start(self.ram_row, False, False, 0)
        rows_box.pack_start(self.gpu_row, False, False, 0)

        self.widget.pack_start(rows_box, False, False, 0)

        self._update()
        GLib.timeout_add(3000, self._update)

    def apply_theme(self, accent_hex):
        icons.set_image_icon(self.chip_icon, "cpu", 16, accent_hex)

    def _make_row(self, name):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        nlbl = Gtk.Label(label=name)
        nlbl.get_style_context().add_class("stat-name")
        nlbl.set_xalign(0)
        row.pack_start(nlbl, False, False, 0)

        bar = MiniProgressBar()
        bar.get_style_context().add_class("sys-progress")
        bar.set_size_request(52, 4)
        bar.set_fraction(0.0)
        bar.set_valign(Gtk.Align.CENTER)
        row.pack_start(bar, False, False, 0)

        vlbl = Gtk.Label(label="0%")
        vlbl.get_style_context().add_class("stat-val")
        vlbl.set_size_request(28, -1)
        vlbl.set_xalign(1)
        row.pack_start(vlbl, False, False, 0)

        return row, bar, vlbl

    def _update(self):
        def _fetch():
            c = system.get_cpu_usage()
            r = system.get_ram_usage()
            g = system.get_gpu_usage()
            GLib.idle_add(self._apply, c, r, g)
        threading.Thread(target=_fetch, daemon=True).start()
        return True

    def _apply(self, c, r, g):
        self.cpu_bar.set_fraction(c / 100.0)
        self.cpu_lbl.set_text(f"{c}%")
        self.ram_bar.set_fraction(r / 100.0)
        self.ram_lbl.set_text(f"{r}%")
        self.gpu_bar.set_fraction(g / 100.0)
        self.gpu_lbl.set_text(f"{g}%")


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 9: Date Tile & Live Clock (Req 8 & 10: Clear hierarchy)
# ══════════════════════════════════════════════════════════════════════════
class DateModule:
    def __init__(self):
        self.widget = FixedWidthBox(109, orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        self.widget.set_halign(Gtk.Align.CENTER)
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_size_request(109, 28)

        # Balanced rounded date tile
        self.cal_lbl = Gtk.Label(label="28")
        self.cal_lbl.set_name("date-tile")
        self.cal_lbl.set_size_request(28, 28)
        self.cal_lbl.set_valign(Gtk.Align.CENTER)
        self.cal_lbl.set_xalign(0.5)
        self.cal_lbl.set_yalign(0.5)
        self.widget.pack_start(self.cal_lbl, False, False, 0)

        # Date & Time stack
        dt_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        dt_box.set_valign(Gtk.Align.CENTER)
        dt_box.set_halign(Gtk.Align.CENTER)

        self.date_lbl = Gtk.Label(label="Tue, Oct 28")
        self.date_lbl.get_style_context().add_class("lbl-date-str")
        self.date_lbl.set_size_request(68, -1)
        self.date_lbl.set_xalign(0.5)
        self.date_lbl.set_halign(Gtk.Align.CENTER)
        dt_box.pack_start(self.date_lbl, False, False, 0)

        self.clock_lbl = Gtk.Label(label="10:24 PM")
        self.clock_lbl.get_style_context().add_class("lbl-time-str")
        self.clock_lbl.set_size_request(68, -1)
        self.clock_lbl.set_xalign(0.5)
        self.clock_lbl.set_halign(Gtk.Align.CENTER)
        dt_box.pack_start(self.clock_lbl, False, False, 0)

        self.widget.pack_start(dt_box, False, False, 0)

        self._update_time()
        GLib.timeout_add(1000, self._update_time)

    def _update_time(self):
        now = datetime.now()
        self.cal_lbl.set_text(now.strftime("%d"))
        self.date_lbl.set_text(now.strftime("%a, %b %d"))
        self.clock_lbl.set_text(now.strftime("%-I:%M %p"))
        return True


# ══════════════════════════════════════════════════════════════════════════
#  GROUP 10: System Tray (Req 5: Notification-Panel, Req 6: Live Battery)
# ══════════════════════════════════════════════════════════════════════════
class SystemTrayModule:
    CC_SVG_PATH = os.path.expanduser("~/.config/waybar/chevron.svg")
    CC_STATE_FILE = f"/run/user/{os.getuid()}/control-center.state"
    CC_PID_FILE = f"/tmp/control-center-{os.getuid()}.pid"

    def __init__(self):
        self.theme_mode = "Dark"
        self.widget = FixedWidthBox(160, orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.widget.set_valign(Gtk.Align.CENTER)
        self.widget.set_size_request(160, 28)

        self.tray_items_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        self.tray_items_box.set_valign(Gtk.Align.CENTER)
        self.tray_items_box.set_halign(Gtk.Align.CENTER)
        self.widget.pack_start(self.tray_items_box, True, False, 0)

        # Wi-Fi
        self.wifi_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.wifi_box.get_style_context().add_class("tray-item")
        self.wifi_img = icons.get_image("wifi", 16, "#ffffff")
        self.wifi_box.pack_start(self.wifi_img, False, False, 0)
        self.tray_items_box.pack_start(self.wifi_box, False, False, 0)

        # Audio Volume
        self.vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.vol_box.get_style_context().add_class("tray-item")
        self.vol_img = icons.get_image("volume-high", 16, "#ffffff")
        self.vol_box.pack_start(self.vol_img, False, False, 0)
        self.tray_items_box.pack_start(self.vol_box, False, False, 0)

        # Horizontal Battery with proportional fill and live charging state as one compact unit
        self.bat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.bat_box.get_style_context().add_class("tray-item")
        self.bat_box.set_valign(Gtk.Align.CENTER)
        self.bat_img = Gtk.Image()
        self.bat_img.set_valign(Gtk.Align.CENTER)
        self.bat_lbl = Gtk.Label(label="--%")
        self.bat_lbl.get_style_context().add_class("lbl-tray")
        self.bat_lbl.set_valign(Gtk.Align.CENTER)
        self.bat_lbl.set_xalign(0.0)
        self.bat_box.pack_start(self.bat_img, False, False, 0)
        self.bat_box.pack_start(self.bat_lbl, False, False, 0)
        self.tray_items_box.pack_start(self.bat_box, False, False, 0)

        # Control Center Toggle button (between charging and notification panel)
        self.cc_btn = Gtk.Button()
        self.cc_btn.set_name("cc-toggle-btn")
        self.cc_btn.get_style_context().add_class("tray-item")
        self.cc_btn.set_size_request(20, 24)
        self.cc_btn.set_valign(Gtk.Align.CENTER)
        self.cc_btn.set_halign(Gtk.Align.CENTER)
        self.cc_btn.set_tooltip_text("Control Center")
        self.cc_icon = Gtk.Image()
        self.cc_icon.set_name("cc-toggle-img")
        self.cc_icon.set_valign(Gtk.Align.CENTER)
        self.cc_icon.set_halign(Gtk.Align.CENTER)
        self.refresh_toggle_icon()
        self.cc_btn.add(self.cc_icon)
        self.cc_btn.connect(
            "clicked",
            lambda *_: _spawn_detached([os.path.expanduser("~/.local/bin/control-center"), "toggle"]),
        )
        self.tray_items_box.pack_start(self.cc_btn, False, False, 0)

        # Clean outlined notification-panel button (NOT a bell!)
        notif_btn = Gtk.Button()
        notif_btn.set_name("notif-btn")
        notif_btn.get_style_context().add_class("tray-item")
        notif_btn.set_size_request(20, 24)
        notif_btn.set_valign(Gtk.Align.CENTER)
        notif_btn.set_halign(Gtk.Align.CENTER)
        self.notif_icon = icons.get_image("notification-panel", 16, "#ffffff")
        notif_btn.add(self.notif_icon)
        notif_btn.connect("clicked", lambda *_: system.run_cmd("dunstctl history-pop 2>/dev/null || true"))
        self.tray_items_box.pack_start(notif_btn, False, False, 0)

        self._cc_state_monitor = None
        self._start_cc_monitor()
        self._sync_cc_state()

        self._update_system()
        GLib.timeout_add(2500, self._update_system)

    def _is_cc_open(self):
        try:
            if not os.path.isfile(self.CC_PID_FILE):
                return False
            with open(self.CC_PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            with open(self.CC_STATE_FILE, "r") as f:
                return f.read().strip().lower() == "open"
        except Exception:
            return False

    def _sync_cc_state(self):
        ctx = self.cc_icon.get_style_context()
        if self._is_cc_open():
            if not ctx.has_class("open"):
                ctx.add_class("open")
        else:
            if ctx.has_class("open"):
                ctx.remove_class("open")
        return False

    def _start_cc_monitor(self):
        try:
            gfile = Gio.File.new_for_path(self.CC_STATE_FILE)
            self._cc_state_monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._cc_state_monitor.connect("changed", lambda *_: GLib.idle_add(self._sync_cc_state))
        except Exception:
            self._cc_state_monitor = None

    def refresh_toggle_icon(self):
        try:
            svg_bytes = None
            if os.path.isfile(self.CC_SVG_PATH):
                with open(self.CC_SVG_PATH, "rb") as f:
                    svg_bytes = f.read()
            else:
                svg_bytes = theme.build_chevron_svg(theme.load_palette()).encode("utf-8")
            gicon = Gio.BytesIcon.new(GLib.Bytes.new(svg_bytes))
            self.cc_icon.set_from_gicon(gicon, Gtk.IconSize.BUTTON)
            self.cc_icon.set_pixel_size(16)
            return
        except Exception:
            pass
        icons.set_image_icon(self.cc_icon, "sliders", 16, "#ffffff")

    def _update_system(self):
        def _fetch():
            bat_info = system.get_battery_info()
            vol = system.get_audio_volume()
            mute = system.get_audio_mute()
            wifi = system.get_wifi_status()
            GLib.idle_add(self._apply_sys, bat_info, vol, mute, wifi)
        threading.Thread(target=_fetch, daemon=True).start()
        return True

    def update_theme_mode(self, mode):
        self.theme_mode = mode
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "notif_icon") and self.notif_icon:
            icons.set_image_icon(self.notif_icon, "notification-panel", 16, col)
        if hasattr(self, "vol_img") and self.vol_img:
            icons.set_image_icon(self.vol_img, "volume-high", 16, col)
        if hasattr(self, "wifi_img") and self.wifi_img:
            icons.set_image_icon(self.wifi_img, "wifi", 16, col)

    def _apply_sys(self, bat_info, vol, mute, wifi):
        pct = bat_info.get("capacity", 100)
        is_charging = bat_info.get("is_charging", False)
        is_plugged = bat_info.get("is_plugged", False)

        self.bat_lbl.set_text(f"{pct}%")

        icons.set_battery_icon(self.bat_img, pct, is_charging=is_charging, is_plugged=is_plugged, size=19)

        base_col = "#1e293b" if getattr(self, "theme_mode", "Dark") == "Light" else "#ffffff"
        if mute or vol == 0:
            icons.set_image_icon(self.vol_img, "volume-muted", 16, base_col)
        elif vol > 50:
            icons.set_image_icon(self.vol_img, "volume-high", 16, base_col)
        else:
            icons.set_image_icon(self.vol_img, "volume-low", 16, base_col)

        w_color = "#38bdf8" if wifi.get("connected") else base_col
        icons.set_image_icon(self.wifi_img, "wifi", 16, w_color)
        self._sync_cc_state()


# ══════════════════════════════════════════════════════════════════════════
#  MAIN DOCK CONTROLLER (Req 1 & 11: Continuous Capsule, Zero Extension)
# ══════════════════════════════════════════════════════════════════════════
class NeonDockApp(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Neon Bottom Dock")
        self.set_name("dock-window")

        # 1. RGBA visual BEFORE LayerShell init
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.set_app_paintable(True)
        self.set_decorated(False)

        # Crisp slight-hinted HiDPI text rendering (clean non-bold outlines)
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings is not None:
            gtk_settings.set_property("gtk-xft-antialias", 1)
            gtk_settings.set_property("gtk-xft-hinting", 1)
            gtk_settings.set_property("gtk-xft-hintstyle", "hintslight")
            gtk_settings.set_property("gtk-xft-rgba", "none")

        # Layer Shell: Full width with 16px side margins; bottom rests at 5px via border_box margin
        full_cfg = config.load_settings()
        dock_cfg = full_cfg.get("dock", {})
        self.theme_mode = dock_cfg.get("theme_mode", full_cfg.get("theme_mode", "Dark"))
        if self.theme_mode not in ("Light", "Dark"):
            self.theme_mode = "Dark"
        self.dock_transparency = dock_cfg.get("transparency", 90)
        self.dock_neon_glow = dock_cfg.get("neon_glow_strength", 100)
        self.autohide = dock_cfg.get("autohide", True)
        self.floating = dock_cfg.get("floating", True)
        self.current_radius = 16.0 if self.floating else 0.0
        self._float_anim_id = None
        self.icon_size = dock_cfg.get("icon_size", 26)
        default_secs = ["apps", "search", "snap", "notes", "modes", "player", "settings", "sysmon", "date", "systray"]
        self.enabled_sections = list(dock_cfg.get("enabled_sections", default_secs))
        if "date" not in self.enabled_sections:
            self.enabled_sections.append("date")
        self.section_order = list(dock_cfg.get("section_order", default_secs))
        if "date" not in self.section_order:
            self.section_order.append("date")

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_namespace(self, "neon-dock")
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, 0)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, 16 if self.floating else 0)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, 16 if self.floating else 0)
        GtkLayerShell.set_exclusive_zone(self, 0)

        self._start_ipc_server()

        # Autohide state
        self._hypr_sock = _find_hypr_socket()
        self._dock_target_open = False
        self._hide_delay_id = None
        self._hover_poll_id = None
        self._pointer_inside = False
        self.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("enter-notify-event", self._on_dock_enter)
        self.connect("leave-notify-event", self._on_dock_leave)

        # Dynamic palette, active wallpaper detection & CSS
        self.palette = theme.load_palette()
        self._active_wallpaper = detect_active_wallpaper(self.palette.get("wallpaper"))
        self._wp_mtime = self._safe_mtime(self._active_wallpaper)
        self._pal_mtime = self._safe_mtime(theme.PALETTE_FILE)
        self.dock_theme = extract_dock_theme(self._active_wallpaper, self.palette)
        self.css_provider = Gtk.CssProvider()
        self._apply_css()

        # Notes popup
        self.notes_popup = NotesPopup()

        # Build UI
        self._build_ui()
        if hasattr(self, "sysmon_mod"):
            self.sysmon_mod.apply_theme(self.dock_theme["stops"][2])
        self.update_dock_capacity(animated=False)

        # Edge trigger strip along entire bottom edge
        self._edge_trigger = self._build_edge_trigger()

        # Timers
        self._check_running_apps()
        GLib.timeout_add(1000, self._check_running_apps)
        GLib.timeout_add(1500, self._check_theme_update)
        GLib.timeout_add(100, self._poll_edge_trigger)

        self.connect("destroy", Gtk.main_quit)
        self._edge_trigger.show_all()
        self.show_all()
        self.update_dock_capacity(animated=False)
        if not getattr(self, "autohide", True):
            self._show_dock()
        elif self._is_cursor_at_bottom_edge():
            self._show_dock()
        else:
            self._hide_dock()
            self.hide()

    def _poll_edge_trigger(self):
        if not getattr(self, "autohide", True):
            if not self._dock_target_open:
                self._show_dock()
            return True
        if not self._dock_target_open:
            if self._is_cursor_at_bottom_edge():
                self._show_dock()
        return True

    def _build_edge_trigger(self):
        trig = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        trig.set_name("neon-dock-edge")
        screen = trig.get_screen()
        vis = screen.get_rgba_visual()
        if vis:
            trig.set_visual(vis)
        trig.set_app_paintable(True)
        trig.set_decorated(False)
        GtkLayerShell.init_for_window(trig)
        GtkLayerShell.set_layer(trig, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_namespace(trig, "neon-dock-edge")
        GtkLayerShell.set_anchor(trig, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(trig, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(trig, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(trig, GtkLayerShell.Edge.BOTTOM, 0)
        GtkLayerShell.set_margin(trig, GtkLayerShell.Edge.LEFT, 0)
        GtkLayerShell.set_margin(trig, GtkLayerShell.Edge.RIGHT, 0)
        GtkLayerShell.set_exclusive_zone(trig, 0)
        GtkLayerShell.set_keyboard_mode(trig, GtkLayerShell.KeyboardMode.NONE)

        ev_box = Gtk.EventBox()
        ev_box.set_name("neon-dock-edge-box")
        ev_box.set_size_request(-1, 2)
        ev_box.set_hexpand(True)
        ev_box.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        ev_box.connect("enter-notify-event", self._on_edge_enter)
        ev_box.connect("motion-notify-event", self._on_edge_enter)
        edge_css = Gtk.CssProvider()
        edge_css.load_from_data(b"#neon-dock-edge, #neon-dock-edge-box { background-color: rgba(0, 0, 0, 0.004); padding: 0; margin: 0; border: none; min-height: 2px; }")
        ev_box.get_style_context().add_provider(edge_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        trig.get_style_context().add_provider(edge_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        trig.add(ev_box)
        trig.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        trig.connect("enter-notify-event", self._on_edge_enter)
        trig.connect("motion-notify-event", self._on_edge_enter)
        return trig

    def _get_monitor_geometry(self):
        try:
            disp = Gdk.Display.get_default()
            if disp:
                mon = disp.get_primary_monitor() or disp.get_monitor(0)
                if mon:
                    return mon.get_geometry()
        except Exception:
            pass
        return None

    def _get_screen_height(self):
        geom = self._get_monitor_geometry()
        if geom:
            return max(200, int(geom.height))
        return 1000

    def _is_cursor_at_bottom_edge(self):
        pos = query_hypr_cursorpos(self._hypr_sock)
        if pos is None:
            self._hypr_sock = _find_hypr_socket()
            pos = query_hypr_cursorpos(self._hypr_sock)
        if pos is None:
            return False
        cx, cy = pos
        geom = self._get_monitor_geometry()
        if geom:
            if not (geom.x <= cx <= (geom.x + geom.width)):
                return False
            return cy >= (geom.y + geom.height - 2)
        sh = self._get_screen_height()
        return cy >= (sh - 2)

    def _is_cursor_in_dock_zone(self):
        if getattr(self.notes_popup, "visible", False):
            return True
        pos = query_hypr_cursorpos(self._hypr_sock)
        if pos is None:
            self._hypr_sock = _find_hypr_socket()
            pos = query_hypr_cursorpos(self._hypr_sock)
        if pos is None:
            return self._pointer_inside
        cx, cy = pos
        geom = self._get_monitor_geometry()
        sh = int(geom.height) if geom else self._get_screen_height()
        alloc = self.get_allocation()
        win_h = alloc.height if alloc and alloc.height > 10 else (DOCK_HEIGHT + 14)
        if geom:
            if not (geom.x <= cx <= (geom.x + geom.width)):
                return False
        return cy >= (sh - (win_h + 8))

    def _cancel_hide_delay(self):
        if self._hide_delay_id is not None:
            GLib.source_remove(self._hide_delay_id)
            self._hide_delay_id = None

    def _ensure_hover_poll(self):
        if self._hover_poll_id is None:
            self._hover_poll_id = GLib.timeout_add(85, self._poll_cursor_keep_open)

    def _stop_hover_poll(self):
        if self._hover_poll_id is not None:
            GLib.source_remove(self._hover_poll_id)
            self._hover_poll_id = None

    def _on_edge_enter(self, widget, event):
        if not self._dock_target_open:
            self._show_dock()
        return False

    def _on_dock_enter(self, widget, event):
        self._pointer_inside = True
        self._cancel_hide_delay()
        if not self._dock_target_open:
            if not getattr(self, "autohide", True) or self._is_cursor_at_bottom_edge():
                self._show_dock()
        return False

    def _on_dock_leave(self, widget, event):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._pointer_inside = False
        if not getattr(self, "autohide", True):
            return False
        self._schedule_hide_check()
        return False

    def _poll_cursor_keep_open(self):
        if not getattr(self, "autohide", True):
            return True
        if not self._dock_target_open and not self._dock_revealer.get_child_revealed():
            self._hover_poll_id = None
            return False
        if self._dock_target_open:
            if self._is_cursor_in_dock_zone():
                self._cancel_hide_delay()
            else:
                self._schedule_hide_check()
        return True

    def _schedule_hide_check(self):
        if not getattr(self, "autohide", True):
            return
        if self._hide_delay_id is not None or not self._dock_target_open:
            return
        def _after_grace():
            self._hide_delay_id = None
            if not getattr(self, "autohide", True):
                return False
            if not self._is_cursor_in_dock_zone():
                self._hide_dock()
            return False
        self._hide_delay_id = GLib.timeout_add(320, _after_grace)

    def _update_cc_toggle_rect(self, visible):
        rect_path = f"/run/user/{os.getuid()}/cc-toggle.rect"
        try:
            if not visible or not hasattr(self, "tray_mod"):
                with open(rect_path, "w") as f:
                    f.write("")
                return False
            btn = self.tray_mod.cc_btn
            pos = btn.translate_coordinates(self, 0, 0)
            if not pos:
                return False
            bx, by = pos
            alloc = btn.get_allocation()
            win_h = max(1, self.get_allocated_height())
            sh = self._get_screen_height()
            x1 = 16 + int(bx)
            y1 = sh - win_h + int(by)
            x2 = x1 + max(1, int(alloc.width))
            y2 = y1 + max(1, int(alloc.height))
            with open(rect_path, "w") as f:
                f.write(f"{x1},{y1},{x2},{y2}")
        except Exception:
            pass
        return False

    def _show_dock(self):
        self._cancel_hide_delay()
        self._ensure_hover_poll()
        self._dock_target_open = True
        if hasattr(self, "_edge_trigger") and self._edge_trigger:
            self._edge_trigger.hide()
        if not self.get_visible():
            self.show()
        self._dock_revealer.set_reveal_child(True)
        GLib.idle_add(self._update_cc_toggle_rect, True)

    def _hide_dock(self):
        self._cancel_hide_delay()
        self._dock_target_open = False
        self._update_cc_toggle_rect(False)
        self._dock_revealer.set_reveal_child(False)

    def _on_dock_revealed_changed(self, revealer, pspec):
        if not revealer.get_reveal_child() and not revealer.get_child_revealed():
            self._stop_hover_poll()
            self._update_cc_toggle_rect(False)
            self.hide()
            if hasattr(self, "_edge_trigger") and self._edge_trigger:
                self._edge_trigger.show_all()
        elif revealer.get_reveal_child() and revealer.get_child_revealed():
            self._update_cc_toggle_rect(True)

    @staticmethod
    def _safe_mtime(path):
        try:
            return os.path.getmtime(path) if path and os.path.isfile(path) else 0.0
        except Exception:
            return 0.0

    def _start_ipc_server(self):
        sock_path = f"/run/user/{os.getuid()}/neon-dock.sock"
        try:
            if os.path.exists(sock_path):
                os.unlink(sock_path)
        except Exception:
            pass

        try:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(sock_path)
            server.listen(5)
        except Exception:
            return

        def _listen():
            while True:
                try:
                    conn, _ = server.accept()
                    with conn:
                        data = b""
                        while b"\n" not in data:
                            chunk = conn.recv(1024)
                            if not chunk:
                                break
                            data += chunk
                        if data:
                            msg = json.loads(data.decode().strip())
                            GLib.idle_add(self._handle_ipc_message, msg)
                except Exception:
                    time.sleep(0.05)

        threading.Thread(target=_listen, daemon=True).start()

    def _handle_ipc_message(self, msg):
        cmd = msg.get("cmd")
        if cmd == "set_theme_mode":
            self.set_theme_mode(msg.get("val", "Dark"))
        elif cmd == "set_transparency":
            self.dock_transparency = int(msg.get("val", 90))
            self._apply_css()
        elif cmd == "set_glow":
            self.dock_neon_glow = int(msg.get("val", 100))
            self._apply_css()
        elif cmd == "set_autohide":
            self.set_autohide(msg.get("val", True))
        elif cmd == "set_floating":
            self.set_floating(msg.get("val", True))
        elif cmd == "set_icon_size":
            self.set_icon_size(msg.get("val", 26))
        elif cmd == "set_sections":
            self.update_sections(msg.get("enabled"), msg.get("order"))
        return False

    def set_theme_mode(self, mode):
        if mode not in ("Light", "Dark"):
            mode = "Dark"
        self.theme_mode = mode
        self._apply_css()
        self._update_icon_colors()
        self.queue_draw()

    def _update_icon_colors(self):
        mode = getattr(self, "theme_mode", "Dark")
        col = "#1e293b" if mode == "Light" else "#ffffff"
        if hasattr(self, "apps_mod"):
            self.apps_mod.update_theme_mode(mode)
        if hasattr(self, "notes_mod"):
            self.notes_mod.update_theme_mode(mode)
        if hasattr(self, "search_mod"):
            self.search_mod.update_theme_mode(mode)
        if hasattr(self, "snap_mod"):
            self.snap_mod.update_theme_mode(mode)
        if hasattr(self, "player_mod"):
            self.player_mod.update_theme_mode(mode)
        if hasattr(self, "settings_mod"):
            self.settings_mod.update_theme_mode(mode)
        if hasattr(self, "tray_mod"):
            self.tray_mod.update_theme_mode(mode)
        if hasattr(self, "arch_btn"):
            child = self.arch_btn.get_child()
            if child:
                icons.set_image_icon(child, "arch", 17, col)

    def set_autohide(self, enabled):
        self.autohide = bool(enabled)
        if not self.autohide:
            self._cancel_hide_delay()
            self._show_dock()
        else:
            if not self._is_cursor_in_dock_zone():
                self._schedule_hide_check()

    def set_floating(self, enabled):
        self.floating = bool(enabled)
        self.update_dock_capacity()
        target_side = 16 if self.floating else 0
        target_bot = 5 if self.floating else 0
        target_radius = 16.0 if self.floating else 0.0

        cur_side = GtkLayerShell.get_margin(self, GtkLayerShell.Edge.LEFT)
        cur_bot = getattr(self, "border_box", None)
        cur_b_val = cur_bot.get_margin_bottom() if cur_bot else (5 if not self.floating else 0)
        cur_radius = getattr(self, "current_radius", 16.0 if not self.floating else 0.0)

        if hasattr(self, "_float_anim_id") and self._float_anim_id:
            GLib.source_remove(self._float_anim_id)
            self._float_anim_id = None

        steps = 14
        step_idx = [0]
        def _step():
            step_idx[0] += 1
            progress = min(1.0, step_idx[0] / steps)
            ease = 1.0 - (1.0 - progress) ** 3
            s = int(round(cur_side + (target_side - cur_side) * ease))
            b = int(round(cur_b_val + (target_bot - cur_b_val) * ease))
            r = cur_radius + (target_radius - cur_radius) * ease
            self.current_radius = r

            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, s)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, s)
            if hasattr(self, "border_box"):
                self.border_box.set_margin_bottom(b)
            self._apply_css(radius=r)
            self.queue_resize()

            if progress >= 1.0:
                self.current_radius = target_radius
                self._apply_css(radius=target_radius)
                self._float_anim_id = None
                return False
            return True

        self._float_anim_id = GLib.timeout_add(16, _step)

    def set_icon_size(self, size):
        self.icon_size = max(20, min(36, int(size)))
        if hasattr(self, "apps_mod"):
            self.apps_mod.icon_size = self.icon_size
        self.update_dock_capacity()

    def update_sections(self, enabled_list=None, order_list=None):
        if enabled_list is not None:
            self.enabled_sections = list(enabled_list)
        if order_list is not None:
            self.section_order = list(order_list)

        enabled = set(self.enabled_sections)
        for sid, box in getattr(self, "section_containers", {}).items():
            is_vis = sid in enabled or (sid == "workspaces" and "modes" in enabled) or (sid == "modes" and "workspaces" in enabled)
            box.set_visible(is_vis)

        if hasattr(self, "search_mod") and hasattr(self, "snap_revealer") and hasattr(self, "notes_revealer"):
            nav_vis = ("search" in enabled) or ("snap" in enabled) or ("notes" in enabled)
            box_nav = getattr(self, "section_boxes", {}).get("search")
            if box_nav:
                box_nav.set_visible(nav_vis)

        if hasattr(self, "inner_box"):
            pos = 0
            seen = set()
            for sid in self.section_order:
                actual_sid = "workspaces" if sid == "modes" else sid
                if actual_sid in getattr(self, "section_boxes", {}):
                    box = self.section_boxes[actual_sid]
                    if box not in seen:
                        self.inner_box.reorder_child(box, pos)
                        pos += 1
                        seen.add(box)
            if hasattr(self, "arch_btn"):
                self.inner_box.reorder_child(self.arch_btn, -1)

    def _apply_css(self, radius=None):
        rad = radius if radius is not None else getattr(self, "current_radius", None)
        css_data = build_dock_css(
            self.palette,
            self.dock_theme,
            transparency=getattr(self, "dock_transparency", 90),
            glow_strength=getattr(self, "dock_neon_glow", 100),
            floating=getattr(self, "floating", True),
            radius=rad,
            theme_mode=getattr(self, "theme_mode", "Dark")
        )
        self.css_provider.load_from_data(css_data.encode())
        if not getattr(self, "_css_provider_added", False):
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
            self._css_provider_added = True
        self.queue_draw()

    def _check_theme_update(self):
        def _poll():
            cur_pal = theme.load_palette()
            pal_wp = cur_pal.get("wallpaper")
            pal_mtime = self._safe_mtime(theme.PALETTE_FILE)
            active_wp = detect_active_wallpaper(pal_wp)
            # If palette.json was explicitly updated more recently than hyprpaper, prefer it only when hyprpaper returned None
            if not active_wp:
                active_wp = pal_wp
            wp_mtime = self._safe_mtime(active_wp)

            changed = (
                active_wp != self._active_wallpaper
                or wp_mtime != self._wp_mtime
                or pal_mtime != self._pal_mtime
                or cur_pal.get("accent_primary") != self.palette.get("accent_primary")
            )
            if changed:
                new_dock_theme = extract_dock_theme(active_wp, cur_pal)
                GLib.idle_add(self._apply_theme_state, cur_pal, active_wp, wp_mtime, pal_mtime, new_dock_theme)

        threading.Thread(target=_poll, daemon=True).start()
        return True

    def _apply_theme_state(self, cur_pal, active_wp, wp_mtime, pal_mtime, new_dock_theme):
        self.palette = cur_pal
        self._active_wallpaper = active_wp
        self._wp_mtime = wp_mtime
        self._pal_mtime = pal_mtime
        self.dock_theme = new_dock_theme
        self._apply_css()
        if hasattr(self, "sysmon_mod"):
            self.sysmon_mod.apply_theme(self.dock_theme["stops"][2])
        if hasattr(self, "tray_mod"):
            self.tray_mod.refresh_toggle_icon()
        return False

    def _cancel_nav_stagger(self):
        stagger_id = getattr(self, "_nav_stagger_id", None)
        if stagger_id is not None:
            GLib.source_remove(stagger_id)
            self._nav_stagger_id = None

    def _get_screen_width(self):
        try:
            screen = self.get_screen()
            display = screen.get_display() if screen else Gdk.Display.get_default()
            if display:
                monitor = display.get_primary_monitor() or display.get_monitor(0)
                if monitor:
                    return monitor.get_geometry().width
            if screen:
                return screen.get_width()
        except Exception:
            pass
        return 1600

    def _on_nav_revealer_progress(self, revealer, frac):
        if not hasattr(self, "apps_mod") or not hasattr(self, "inner_box"):
            return
        n_apps = self.apps_mod.get_total_apps_count()
        req_size = getattr(self, "icon_size", 26)
        screen_w = self._get_screen_width()
        margin = 16 if getattr(self, "floating", True) else 0
        max_dock_w = screen_w - (margin * 2)
        dock_frame_padding = 30
        apps_chrome = 66

        box_apps = getattr(self, "box_apps", None) or self.section_boxes.get("apps")
        current_other = 0
        for child in self.inner_box.get_children():
            if child is not box_apps and child.get_visible():
                current_other += child.get_preferred_width()[0]

        avail_now = max(10, max_dock_w - dock_frame_padding - current_other - apps_chrome)
        eff_size, eff_spacing = self.apps_mod.calculate_fitting_icon_size(req_size, n_apps, avail_now)
        self.apps_mod.apply_effective_sizing(eff_size, eff_spacing)

    def update_dock_capacity(self, total_apps=None, animated=True):
        if not hasattr(self, "apps_mod") or not hasattr(self, "inner_box"):
            return

        n_apps = total_apps if total_apps is not None else self.apps_mod.get_total_apps_count()
        req_size = getattr(self, "icon_size", 26)

        screen_w = self._get_screen_width()
        margin = 16 if getattr(self, "floating", True) else 0
        max_dock_w = screen_w - (margin * 2)

        dock_frame_padding = 30
        apps_chrome = 66

        box_apps = getattr(self, "box_apps", None) or self.section_boxes.get("apps")
        box_nav = getattr(self, "section_boxes", {}).get("search")

        # Stable base width of all other non-collapsible modules
        base_other = 0
        for child in self.inner_box.get_children():
            if child is not box_apps and child is not box_nav and child.get_visible():
                base_other += child.get_preferred_width()[0]
        if hasattr(self, "search_mod") and self.search_mod.widget.get_visible():
            base_other += self.search_mod.widget.get_preferred_width()[0] + 17

        # Available space under each target state
        avail_both = max(10, max_dock_w - dock_frame_padding - (base_other + 126) - apps_chrome)
        avail_snap = max(10, max_dock_w - dock_frame_padding - (base_other + 63) - apps_chrome)
        avail_none = max(10, max_dock_w - dock_frame_padding - base_other - apps_chrome)

        req_w = self.apps_mod.calculate_required_width(req_size, n_apps)

        self._cancel_nav_stagger()
        if req_w <= avail_both:
            was_both_hidden = (not self.snap_revealer.is_revealed() and not self.notes_revealer.is_revealed())
            self.snap_revealer.set_reveal(True, animated=animated)
            if was_both_hidden and animated:
                def _show_notes():
                    self._nav_stagger_id = None
                    self.notes_revealer.set_reveal(True, animated=True)
                    return False
                self._nav_stagger_id = GLib.timeout_add(100, _show_notes)
            else:
                self.notes_revealer.set_reveal(True, animated=animated)
        elif req_w <= avail_snap:
            self.notes_revealer.set_reveal(False, animated=animated)
            self.snap_revealer.set_reveal(True, animated=animated)
        else:
            self.notes_revealer.set_reveal(False, animated=animated)
            if self.snap_revealer.is_revealed() and animated:
                def _hide_snap():
                    self._nav_stagger_id = None
                    self.snap_revealer.set_reveal(False, animated=True)
                    return False
                self._nav_stagger_id = GLib.timeout_add(100, _hide_snap)
            else:
                self.snap_revealer.set_reveal(False, animated=animated)

        # Apply safe effective sizing based on what ACTUALLY fits right now
        current_other = 0
        for child in self.inner_box.get_children():
            if child is not box_apps and child.get_visible():
                current_other += child.get_preferred_width()[0]

        avail_now = max(10, max_dock_w - dock_frame_padding - current_other - apps_chrome)
        eff_size, eff_spacing = self.apps_mod.calculate_fitting_icon_size(req_size, n_apps, avail_now)
        self.apps_mod.apply_effective_sizing(eff_size, eff_spacing)

    def _on_apps_capacity_changed(self, total_apps=None):
        self.update_dock_capacity(total_apps)

    def _build_ui(self):
        # Outer transparent wrapper
        self.outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.outer_box.set_name("dock-outer-box")

        border_box = Gtk.Box()
        border_box.set_name("dock-border")
        border_box.set_hexpand(True)
        self.border_box = border_box

        inner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        inner_box.set_name("dock-inner")
        inner_box.set_size_request(-1, DOCK_HEIGHT - 6)
        inner_box.set_hexpand(True)
        self.inner_box = inner_box

        # ── EXACT ORDER OF 9 GROUPS MATCHING SPECIFICATION ──────────────
        # 1. Applications launcher, pinned apps, and dynamic running apps
        box_apps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_apps.set_valign(Gtk.Align.CENTER)
        box_apps.set_hexpand(True)
        self.box_apps = box_apps
        self.apps_mod = ApplicationsModule(on_capacity_changed=self._on_apps_capacity_changed, icon_size=self.icon_size)
        box_apps.pack_start(self.apps_mod.widget, True, True, 0)
        box_apps.pack_start(make_sep_box(hexpand=False, margin=8), False, False, 0)
        inner_box.pack_start(box_apps, True, True, 0)

        # 2. Navigation Group: Search -> Snap -> Notes (with progressive visibility & separators)
        self.search_mod = SearchModule()
        self.snap_mod = SnapModule()
        self.notes_mod = NotesModule(self.notes_popup)

        snap_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        snap_box.set_valign(Gtk.Align.CENTER)
        snap_box.pack_start(make_sep_box(hexpand=False, margin=8), False, False, 0)
        snap_box.pack_start(self.snap_mod.widget, False, False, 0)
        self.snap_revealer = LiquidNavRevealer(
            snap_box,
            target_width=63,
            height=48,
            duration_us=240000,
            on_progress=self._on_nav_revealer_progress,
        )

        notes_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        notes_box.set_valign(Gtk.Align.CENTER)
        notes_box.pack_start(make_sep_box(hexpand=False, margin=8), False, False, 0)
        notes_box.pack_start(self.notes_mod.widget, False, False, 0)
        self.notes_revealer = LiquidNavRevealer(
            notes_box,
            target_width=63,
            height=48,
            duration_us=240000,
            on_progress=self._on_nav_revealer_progress,
        )

        box_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_nav.set_valign(Gtk.Align.CENTER)
        box_nav.set_halign(Gtk.Align.CENTER)
        box_nav.set_hexpand(False)
        box_nav.pack_start(self.search_mod.widget, False, False, 0)
        box_nav.pack_start(self.snap_revealer.widget, False, False, 0)
        box_nav.pack_start(self.notes_revealer.widget, False, False, 0)
        box_nav.pack_start(make_sep_box(hexpand=False, margin=8), False, False, 0)
        inner_box.pack_start(box_nav, False, False, 0)

        # 3. Workspace Switcher (Topbar-Matched Segmented Container)
        box_ws = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_ws.set_valign(Gtk.Align.CENTER)
        self.ws_mod = WorkspaceSwitcherModule()
        box_ws.pack_start(self.ws_mod.widget, False, False, 0)
        box_ws.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)
        inner_box.pack_start(box_ws, False, False, 0)

        # 4. Media player
        box_player = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_player.set_valign(Gtk.Align.CENTER)
        self.player_mod = PlayerModule()
        box_player.pack_start(self.player_mod.widget, False, False, 0)
        box_player.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)
        inner_box.pack_start(box_player, False, False, 0)

        # 5. Settings launcher
        box_settings = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_settings.set_valign(Gtk.Align.CENTER)
        self.settings_mod = SettingsModule()
        box_settings.pack_start(self.settings_mod.widget, False, False, 0)
        box_settings.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)
        inner_box.pack_start(box_settings, False, False, 0)

        # 6. System Monitor
        box_sysmon = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_sysmon.set_valign(Gtk.Align.CENTER)
        self.sysmon_mod = SystemMonitorModule()
        box_sysmon.pack_start(self.sysmon_mod.widget, False, False, 0)
        box_sysmon.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)
        inner_box.pack_start(box_sysmon, False, False, 0)

        # 7. Date tile and live clock
        box_date = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_date.set_valign(Gtk.Align.CENTER)
        self.date_mod = DateModule()
        box_date.pack_start(self.date_mod.widget, False, False, 0)
        box_date.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)
        inner_box.pack_start(box_date, False, False, 0)

        # 8. System Tray
        box_tray = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box_tray.set_valign(Gtk.Align.CENTER)
        self.tray_mod = SystemTrayModule()
        box_tray.pack_start(self.tray_mod.widget, False, False, 0)
        box_tray.pack_start(make_sep_box(hexpand=False, margin=6), False, False, 0)
        inner_box.pack_start(box_tray, False, False, 0)

        # 9. Show Desktop Arch Button (Far Right Corner)
        arch_btn = FixedWidthButton(24)
        arch_btn.set_name("arch-desktop-btn")
        arch_btn.set_size_request(24, 24)
        arch_btn.set_valign(Gtk.Align.CENTER)
        arch_btn.set_halign(Gtk.Align.CENTER)
        arch_btn.set_focus_on_click(False)
        arch_btn.set_tooltip_text("Show Desktop")
        arch_icon = icons.get_image("arch", 17, "#ffffff")
        arch_icon.set_halign(Gtk.Align.CENTER)
        arch_icon.set_valign(Gtk.Align.CENTER)
        arch_btn.add(arch_icon)
        arch_btn.connect(
            "clicked",
            lambda *_: _spawn_detached([os.path.expanduser("~/.local/bin/toggle-desktop")]),
        )
        inner_box.pack_start(arch_btn, False, False, 0)
        self.arch_btn = arch_btn

        self.section_containers = {
            "apps": box_apps,
            "search": self.search_mod.widget,
            "snap": self.snap_revealer.widget,
            "notes": self.notes_revealer.widget,
            "workspaces": box_ws,
            "modes": box_ws,
            "player": box_player,
            "settings": box_settings,
            "sysmon": box_sysmon,
            "date": box_date,
            "systray": box_tray,
        }
        self.section_boxes = {
            "apps": box_apps,
            "search": box_nav,
            "snap": box_nav,
            "notes": box_nav,
            "workspaces": box_ws,
            "modes": box_ws,
            "player": box_player,
            "settings": box_settings,
            "sysmon": box_sysmon,
            "date": box_date,
            "systray": box_tray,
        }

        # 1. inner_box expands 100% inside border_box with ZERO exposed border gradient
        border_box.pack_start(inner_box, True, True, 0)
        border_box.set_margin_bottom(5 if self.floating else 0)
        self._dock_revealer = Gtk.Revealer()
        self._dock_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self._dock_revealer.set_transition_duration(220)
        self._dock_revealer.set_reveal_child(False)
        self._dock_revealer.set_valign(Gtk.Align.END)
        self._dock_revealer.connect("notify::child-revealed", self._on_dock_revealed_changed)
        self._dock_revealer.add(border_box)
        self.outer_box.set_size_request(-1, DOCK_HEIGHT + 5)
        self.outer_box.pack_start(self._dock_revealer, True, True, 0)
        self.add(self.outer_box)
        self.outer_box.show_all()
        self.update_sections(self.enabled_sections, self.section_order)
        self._update_icon_colors()

    def _check_running_apps(self):
        if hasattr(self, "apps_mod"):
            self.apps_mod.check_pinned_update()
        def _fetch():
            out = system.run_cmd("hyprctl clients -j 2>/dev/null")
            try:
                clients = json.loads(out)
                classes = {c.get("class") or c.get("initialClass") or "" for c in clients}
                classes = {cls for cls in classes if cls}
                GLib.idle_add(self.apps_mod.update_running, classes)
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()
        return True

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    app = NeonDockApp()
    Gtk.main()

if __name__ == "__main__":
    main()
