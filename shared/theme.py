#!/usr/bin/env python3
"""
Neon Desktop — Shared Theme Engine
Dynamic palette extraction from wallpapers, color system, and CSS generation.
"""

import os
import re
import json
import colorsys
import threading
import subprocess
from pathlib import Path
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, GLib

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
PALETTE_FILE = os.path.join(CONFIG_DIR, "palette.json")
THEME_CSS_FILE = os.path.join(CONFIG_DIR, "theme.css")
SLIDER_COLORS_FILE = os.path.join(CONFIG_DIR, "topbar_slider_colors")
WAYBAR_CSS_FILE = os.path.expanduser("~/.config/waybar/macos.css")
WAYBAR_CHEVRON_SVG = os.path.expanduser("~/.config/waybar/chevron.svg")
DUNST_RC_FILE = os.path.expanduser("~/.config/dunst/dunstrc")
NWGDRAWER_CSS_FILE = os.path.expanduser("~/.config/nwg-drawer/drawer.css")
HYPR_THEME_FILE = os.path.expanduser("~/.config/hypr/theme.conf")
KITTY_CONF_FILE = os.path.expanduser("~/.config/kitty/kitty.conf")
DRAWER_THEME_FILE = os.path.join(CONFIG_DIR, "drawer_theme.json")
DRAWER_CSS_FILE = os.path.join(CONFIG_DIR, "drawer.css")
DRUN_THEME_FILE = os.path.join(CONFIG_DIR, "drun_theme.json")
DRUN_CSS_FILE = os.path.join(CONFIG_DIR, "drun.css")
SETTINGS_CSS_FILE = os.path.join(CONFIG_DIR, "settings.css")
DEFAULT_WALLPAPER = os.path.expanduser("~/Pictures/Wallpapers/Misty Mountain Peaks.png")

def to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

def to_rgba(rgb, a):
    return "rgba({}, {}, {}, {:.2f})".format(int(rgb[0]), int(rgb[1]), int(rgb[2]), a)

def clamp(val, low=0, high=255):
    return max(low, min(high, int(val)))

_PALETTE_CACHE = {}

def extract_palette(image_path=None):
    """Extract a rich harmonious palette from an image file using GdkPixbuf."""
    if not image_path or not os.path.isfile(image_path):
        image_path = DEFAULT_WALLPAPER
        if not os.path.isfile(image_path):
            return get_default_palette()

    try:
        mtime = os.path.getmtime(image_path)
    except Exception:
        mtime = 0
    cache_key = (image_path, mtime)
    if cache_key in _PALETTE_CACHE:
        return dict(_PALETTE_CACHE[cache_key])

    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(image_path, 120, 80, False)
        pixels = pb.get_pixels()
        n_ch = pb.get_n_channels()
        stride = pb.get_rowstride()
        w = pb.get_width()
        h = pb.get_height()

        samples = []
        for y in range(0, h, 2):
            row_offset = y * stride
            for x in range(0, w, 2):
                idx = row_offset + x * n_ch
                r, g, b = pixels[idx], pixels[idx+1], pixels[idx+2]
                samples.append((r, g, b))

        # Quantize colors into 16-step buckets
        buckets = {}
        for r, g, b in samples:
            qr, qg, qb = (r // 16) * 16, (g // 16) * 16, (b // 16) * 16
            k = (qr, qg, qb)
            buckets[k] = buckets.get(k, 0) + 1

        sorted_colors = sorted(buckets.items(), key=lambda x: x[1], reverse=True)

        vivid = []
        dark = []
        light = []

        for (r, g, b), count in sorted_colors:
            h_val, l_val, s_val = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
            if s_val > 0.22 and 0.25 < l_val < 0.78:
                vivid.append(((r, g, b), h_val, l_val, s_val, count))
            if l_val < 0.22:
                dark.append(((r, g, b), h_val, l_val, s_val, count))
            if l_val > 0.75:
                light.append(((r, g, b), h_val, l_val, s_val, count))

        # Score vivid colors by vibrancy (saturation * balanced lightness)
        vivid.sort(key=lambda x: x[3] * (1.0 - abs(x[2] - 0.5) * 1.5) * (x[4] ** 0.3), reverse=True)

        # Accents
        primary = vivid[0][0] if vivid else (168, 85, 247)
        secondary = vivid[min(len(vivid)-1, 2)][0] if len(vivid) > 2 else (236, 72, 153)
        tertiary = vivid[min(len(vivid)-1, 5)][0] if len(vivid) > 5 else (99, 102, 241)

        # Ensure warm/magenta/purple harmony if wallpaper is Alpenglow
        base_dark = dark[0][0] if dark else (16, 20, 36)
        # Add slight tint of the dark tone to background
        bg_r = clamp(base_dark[0] * 0.7 + 8)
        bg_g = clamp(base_dark[1] * 0.7 + 8)
        bg_b = clamp(base_dark[2] * 0.7 + 16)

        surface_r = clamp(bg_r * 1.4 + 14)
        surface_g = clamp(bg_g * 1.4 + 14)
        surface_b = clamp(bg_b * 1.4 + 24)

        card_r = clamp(bg_r * 1.8 + 20)
        card_g = clamp(bg_g * 1.8 + 20)
        card_b = clamp(bg_b * 1.8 + 35)

        palette = {
            "wallpaper": image_path,
            "base_bg": to_rgba((bg_r, bg_g, bg_b), 0.88),
            "base_bg_solid": to_hex((bg_r, bg_g, bg_b)),
            "secondary_bg": to_rgba((surface_r, surface_g, surface_b), 0.75),
            "surface": to_rgba((card_r, card_g, card_b), 0.60),
            "card_bg": to_rgba((card_r, card_g, card_b), 0.45),
            "card_border": to_rgba((255, 255, 255), 0.08),
            "card_border_hover": to_rgba((255, 255, 255), 0.16),
            "accent_primary": to_hex(primary),
            "accent_primary_rgba": to_rgba(primary, 0.25),
            "accent_secondary": to_hex(secondary),
            "accent_secondary_rgba": to_rgba(secondary, 0.25),
            "accent_tertiary": to_hex(tertiary),
            "highlight": "#38bdf8",
            "text_primary": "#ffffff",
            "text_secondary": "#a0a0b8",
            "text_muted": "#6b7280",
            "border": to_rgba(primary, 0.45),
            "glow": to_rgba(secondary, 0.30),
            "gradient_perimeter": f"linear-gradient(90deg, #ff7e40, {to_hex(secondary)}, {to_hex(primary)}, {to_hex(tertiary)})",
            "gradient_button": f"linear-gradient(135deg, {to_hex(primary)}, {to_hex(secondary)})",
            "gradient_header": f"linear-gradient(90deg, {to_hex(primary)}, {to_hex(secondary)})"
        }
        _PALETTE_CACHE[cache_key] = dict(palette)
        return palette
    except Exception as e:
        print(f"Error extracting palette from {image_path}: {e}")
        return get_default_palette()

def get_default_palette():
    return {
        "wallpaper": DEFAULT_WALLPAPER,
        "base_bg": "rgba(16, 12, 28, 0.88)",
        "base_bg_solid": "#100c1c",
        "secondary_bg": "rgba(28, 22, 44, 0.75)",
        "surface": "rgba(42, 34, 64, 0.60)",
        "card_bg": "rgba(42, 34, 64, 0.45)",
        "card_border": "rgba(255, 255, 255, 0.08)",
        "card_border_hover": "rgba(255, 255, 255, 0.16)",
        "accent_primary": "#a855f7",
        "accent_primary_rgba": "rgba(168, 85, 247, 0.25)",
        "accent_secondary": "#ec4899",
        "accent_secondary_rgba": "rgba(236, 72, 153, 0.25)",
        "accent_tertiary": "#6366f1",
        "highlight": "#38bdf8",
        "text_primary": "#ffffff",
        "text_secondary": "#a0a0b8",
        "text_muted": "#6b7280",
        "border": "rgba(168, 85, 247, 0.45)",
        "glow": "rgba(236, 72, 153, 0.30)",
        "gradient_perimeter": "linear-gradient(90deg, #ff7e40, #ec4899, #a855f7, #6366f1)",
        "gradient_button": "linear-gradient(135deg, #a855f7, #ec4899)",
        "gradient_header": "linear-gradient(90deg, #a855f7, #ec4899)"
    }

def save_palette(palette):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PALETTE_FILE, "w") as f:
        json.dump(palette, f, indent=2)

def load_palette():
    if os.path.isfile(PALETTE_FILE):
        try:
            with open(PALETTE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return get_default_palette()

def generate_css(palette):
    """Generate shared CSS variables and styles."""
    p = palette
    css = f"""
/* Generated Neon Desktop Theme CSS */
@define-color base_bg {p['base_bg']};
@define-color base_bg_solid {p['base_bg_solid']};
@define-color secondary_bg {p['secondary_bg']};
@define-color surface {p['surface']};
@define-color card_bg {p['card_bg']};
@define-color card_border {p['card_border']};
@define-color card_border_hover {p['card_border_hover']};
@define-color accent_primary {p['accent_primary']};
@define-color accent_secondary {p['accent_secondary']};
@define-color accent_tertiary {p['accent_tertiary']};
@define-color highlight {p['highlight']};
@define-color text_primary {p['text_primary']};
@define-color text_secondary {p['text_secondary']};
@define-color text_muted {p['text_muted']};
@define-color border {p['border']};
@define-color glow {p['glow']};

.neon-gradient-perimeter {{
    background: {p['gradient_perimeter']};
}}

.neon-gradient-btn {{
    background: {p['gradient_button']};
}}

.neon-card {{
    background: {p['card_bg']};
    border: 1px solid {p['card_border']};
    border-radius: 12px;
}}
.neon-card:hover {{
    border-color: {p['card_border_hover']};
}}
"""
    with open(THEME_CSS_FILE, "w") as f:
        f.write(css)
    return css

def update_theme(image_path=None):
    """Full update pipeline: extract, save, generate CSS and sync all desktop components."""
    pal = extract_palette(image_path)
    save_palette(pal)
    generate_css(pal)
    try:
        sync_topbar_theme_files(image_path, fallback_palette=pal)
    except Exception as e:
        print(f"[theme] sync_topbar_theme_files error: {e}")
    return pal

def _clamp255(val):
    return max(0, min(255, int(round(val))))

def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(_clamp255(rgb[0]), _clamp255(rgb[1]), _clamp255(rgb[2]))

def _hex_to_rgb(hex_str, default=(168, 85, 247)):
    s = str(hex_str or "").lstrip("#")
    if len(s) >= 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            pass
    return default

def hex_to_rgba(hex_str, alpha=1.0):
    r, g, b = _hex_to_rgb(hex_str)
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"

def _mix_rgb(base_rgb, accent_hex, weight):
    ar, ag, ab = _hex_to_rgb(accent_hex)
    w = max(0.0, min(1.0, float(weight)))
    return (
        _clamp255(base_rgb[0] * (1.0 - w) + ar * w),
        _clamp255(base_rgb[1] * (1.0 - w) + ag * w),
        _clamp255(base_rgb[2] * (1.0 - w) + ab * w),
    )

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
    """Interpolate two RGB stops cleanly across adjacent or complementary hues."""
    h1, l1, s1 = colorsys.rgb_to_hls(*(x / 255.0 for x in c1))
    h2, l2, s2 = colorsys.rgb_to_hls(*(x / 255.0 for x in c2))
    dh_signed = (h2 - h1 + 0.5) % 1.0 - 0.5
    if abs(dh_signed) <= 0.25:
        h = (h1 + dh_signed * t) % 1.0
        s = max(0.58, min(0.88, s1 * (1.0 - t) + s2 * t))
        return _hls_to_rgb255(h, l1 * (1.0 - t) + l2 * t, s)
    rm = c1[0] * (1.0 - t) + c2[0] * t
    gm = c1[1] * (1.0 - t) + c2[1] * t
    bm = c1[2] * (1.0 - t) + c2[2] * t
    hm, _, sm = colorsys.rgb_to_hls(rm / 255.0, gm / 255.0, bm / 255.0)
    lm = max(0.50, min(0.64, l1 * (1.0 - t) + l2 * t))
    ns = max(0.48, min(0.82, max(sm, min(s1, s2) * 0.68)))
    rr, gg, bb = colorsys.hls_to_rgb(hm, lm, ns)
    return (_clamp255(rr * 255), _clamp255(gg * 255), _clamp255(bb * 255))

def lighten_hex(hex_str, l_target=0.74):
    r, g, b = _hex_to_rgb(hex_str)
    h, l, sat = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    nr, ng, nb = colorsys.hls_to_rgb(h, max(l, l_target), min(0.95, sat))
    return _rgb_to_hex((nr * 255, ng * 255, nb * 255))

def _tone_hex(hex_str, target_l, min_s=0.58, max_s=0.90):
    r, g, b = _hex_to_rgb(hex_str)
    h, _, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    nl = max(0.20, min(0.92, target_l))
    ns = max(min_s, min(max_s, s))
    nr, ng, nb = colorsys.hls_to_rgb(h, nl, ns)
    return _rgb_to_hex((nr * 255, ng * 255, nb * 255))

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
    """Detect active wallpaper from hyprpaper IPC, swww, hyprpaper.conf, or fallback."""
    env = _find_hypr_env()
    try:
        out = subprocess.check_output(
            ["hyprctl", "hyprpaper", "listactive"],
            text=True, timeout=1.0, stderr=subprocess.DEVNULL, env=env
        )
        for line in out.splitlines():
            if ":" in line:
                wp = os.path.expanduser(line.split(":", 1)[1].strip())
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

_THEME_EXTRACTION_CACHE = {}

def extract_wallpaper_theme(wallpaper_path, fallback_palette=None, palette_style=None, accent_color=None):
    """Extract harmonious dark-glass base and 5 vivid neon stops matching neon-dock."""
    wp = os.path.expanduser(str(wallpaper_path)) if wallpaper_path else ""
    try:
        mtime = os.path.getmtime(wp) if wp and os.path.isfile(wp) else 0
    except Exception:
        mtime = 0
    cache_key = (wp, mtime, palette_style, accent_color)
    if cache_key in _THEME_EXTRACTION_CACHE:
        return dict(_THEME_EXTRACTION_CACHE[cache_key])

    fp = fallback_palette or {}
    default_stops = ["#ff8a00", "#ec4899", "#d946ef", "#9333ea", "#7c3aed"]
    result = {
        "wallpaper": wallpaper_path or fp.get("wallpaper", ""),
        "base_rgb": (13, 12, 20),
        "stops": list(default_stops),
    }

    wp = os.path.expanduser(str(wallpaper_path)) if wallpaper_path else ""
    wp_lower = os.path.basename(wp).lower() if wp else ""
    if "alpenglow" in wp_lower or "sunset" in wp_lower or "misty mountain" in wp_lower:
        result["base_rgb"] = (22, 12, 34)
        result["stops"] = ["#ff3399", "#f054ba", "#d946ef", "#a838ea", "#7c3aed"]
    elif wp and os.path.isfile(wp):
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
                        s0, s2, s4 = c1_rgb, c0_rgb, wing_shift
                        s1 = _lerp_hue_rgb(s0, s2, 0.62)
                        s3 = _lerp_hue_rgb(s2, s4, 0.50)
                    else:
                        s0, s2, s4 = wing_shift, c0_rgb, c1_rgb
                        s1 = _lerp_hue_rgb(s0, s2, 0.50)
                        s3 = _lerp_hue_rgb(s2, s4, 0.38)
                    stops_rgb = [s0, s1, s2, s3, s4]
                else:
                    wings = sorted([chosen[1], chosen[2]], key=lambda c: c[2])
                    s0, s2, s4 = wings[0][3], c0_rgb, wings[1][3]
                    stops_rgb = [s0, _lerp_hue_rgb(s0, s2, 0.58), s2, _lerp_hue_rgb(s2, s4, 0.42), s4]
                result["stops"] = [_rgb_to_hex(c) for c in stops_rgb]
        except Exception:
            pass

    # Apply palette style transformations
    p_style = palette_style
    if not p_style:
        try:
            from shared import config
            p_style = config.load_settings().get("palette_style", "Vivid")
        except Exception:
            p_style = "Vivid"

    if p_style == "Vivid":
        new_stops = []
        for s in result["stops"]:
            r, g, b = _hex_to_rgb(s)
            h, l, sat = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            sat = min(1.0, max(0.85, sat * 1.35))
            l = min(0.68, max(0.50, l))
            nr, ng, nb = colorsys.hls_to_rgb(h, l, sat)
            new_stops.append(_rgb_to_hex((int(nr * 255), int(ng * 255), int(nb * 255))))
        result["stops"] = new_stops
    elif p_style == "Tonal":
        new_stops = []
        h0, l0, sat0 = colorsys.rgb_to_hls(*[v / 255.0 for v in _hex_to_rgb(result["stops"][0])])
        for i, frac in enumerate([-0.06, -0.03, 0.0, 0.03, 0.06]):
            nh = (h0 + frac) % 1.0
            nl = min(0.65, max(0.45, l0 + (i - 2) * 0.04))
            nsat = min(0.70, max(0.45, sat0 * 0.80))
            nr, ng, nb = colorsys.hls_to_rgb(nh, nl, nsat)
            new_stops.append(_rgb_to_hex((int(nr * 255), int(ng * 255), int(nb * 255))))
        result["stops"] = new_stops
    elif p_style == "Expressive":
        new_stops = []
        h0, l0, sat0 = colorsys.rgb_to_hls(*[v / 255.0 for v in _hex_to_rgb(result["stops"][0])])
        for i, step in enumerate([0.0, 0.12, 0.28, 0.45, 0.60]):
            nh = (h0 + step) % 1.0
            nl = 0.58
            nsat = 0.90
            nr, ng, nb = colorsys.hls_to_rgb(nh, nl, nsat)
            new_stops.append(_rgb_to_hex((int(nr * 255), int(ng * 255), int(nb * 255))))
        result["stops"] = new_stops
    elif p_style == "Neutral":
        new_stops = []
        for s in result["stops"]:
            r, g, b = _hex_to_rgb(s)
            h, l, sat = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            sat = sat * 0.28
            l = min(0.65, max(0.48, l))
            nr, ng, nb = colorsys.hls_to_rgb(h, l, sat)
            new_stops.append(_rgb_to_hex((int(nr * 255), int(ng * 255), int(nb * 255))))
        result["stops"] = new_stops
    elif p_style == "Monochrome":
        result["stops"] = ["#94a3b8", "#cbd5e1", "#e2e8f0", "#94a3b8", "#64748b"]

    # Weave custom accent color if chosen
    acc = accent_color
    if not acc:
        try:
            from shared import config
            acc = config.load_settings().get("accent_color", "auto")
        except Exception:
            acc = "auto"
    if acc and acc not in ("auto", "Auto") and str(acc).startswith("#") and len(result["stops"]) >= 2:
        result["stops"][0] = acc
        r, g, b = _hex_to_rgb(acc)
        h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        nr, ng, nb = colorsys.hls_to_rgb((h + 0.08) % 1.0, l, s)
        result["stops"][1] = _rgb_to_hex((int(nr * 255), int(ng * 255), int(nb * 255)))

    _THEME_EXTRACTION_CACHE[cache_key] = dict(result)
    return result

def derive_topbar_colors(wp_theme, theme_mode=None):
    """Derive harmonious dark glass & vivid contrast-safe accent tokens for Waybar and Control Center."""
    try:
        from shared import config
        t_mode = theme_mode if theme_mode is not None else config.load_settings().get("theme_mode", "Dark")
    except Exception:
        t_mode = theme_mode or "Dark"
    if t_mode not in ("Light", "Dark"):
        t_mode = "Dark"
    is_light = (t_mode == "Light")

    br, bg, bb = wp_theme.get("base_rgb", (13, 12, 20))
    stops = wp_theme.get("stops") or ["#ff8a00", "#ec4899", "#d946ef", "#9333ea", "#7c3aed"]
    s0, s1, s2, s3, s4 = (stops + [stops[-1]] * 5)[:5]

    if is_light:
        bar_l_rgb = (248, 250, 255)
        bar_c_rgb = (248, 250, 255)
        bar_r_rgb = (248, 250, 255)
        ws_rgb = (235, 240, 250)
        popup_rgb = (255, 255, 255)
        cc_rgb = (252, 254, 255)
        drawer_rgb = (248, 250, 255)
    else:
        bar_l_rgb = _mix_rgb((br, bg, bb), s0, 0.16)
        bar_c_rgb = _mix_rgb((br, bg, bb), s2, 0.16)
        bar_r_rgb = _mix_rgb((br, bg, bb), s4, 0.16)
        ws_rgb = _mix_rgb((_clamp255(br + 10), _clamp255(bg + 8), _clamp255(bb + 16)), s2, 0.22)
        cc_rgb = _mix_rgb((br, bg, bb), s2, 0.16)
        popup_rgb = _mix_rgb((br, bg, bb), s2, 0.20)
        drawer_rgb = _mix_rgb((br, bg, bb), s2, 0.15)

    accent_deep = _tone_hex(s1, 0.47, 0.58, 0.88)
    accent_mid = _tone_hex(s2, 0.53, 0.60, 0.90)
    accent_bright = _tone_hex(s3 if s3 != s2 else s2, 0.61, 0.62, 0.92)
    accent_hover = _tone_hex(s2, 0.67, 0.62, 0.92)
    accent_text = lighten_hex(s2, 0.78)
    accent_muted = lighten_hex(s2, 0.70)
    text_soft = "#475569" if is_light else lighten_hex(s2, 0.95)
    soft_rgb = (15, 23, 42) if is_light else _hex_to_rgb(text_soft, (245, 248, 255))

    return {
        "s0": s0, "s1": s1, "s2": s2, "s3": s3, "s4": s4,
        "base_rgb": (br, bg, bb),
        "bar_bg_l": to_rgba(bar_l_rgb, 0.82 if is_light else 0.76),
        "bar_bg_c": to_rgba(bar_c_rgb, 0.82 if is_light else 0.76),
        "bar_bg_r": to_rgba(bar_r_rgb, 0.82 if is_light else 0.76),
        "bar_border": "rgba(0, 0, 0, 0.10)" if is_light else hex_to_rgba(accent_text, 0.24),
        "ws_bg": "rgba(0, 0, 0, 0.05)" if is_light else to_rgba(ws_rgb, 0.66),
        "ws_border": "rgba(0, 0, 0, 0.10)" if is_light else hex_to_rgba(accent_text, 0.26),
        "ws_inactive": "rgba(15, 23, 42, 0.70)" if is_light else to_rgba(soft_rgb, 0.76),
        "popup_bg": "rgba(255, 255, 255, 0.96)" if is_light else to_rgba(popup_rgb, 0.95),
        "popup_border": "rgba(0, 0, 0, 0.10)" if is_light else hex_to_rgba(accent_text, 0.30),
        "cc_bg": "rgba(252, 254, 255, 0.96)" if is_light else to_rgba(cc_rgb, 0.92),
        "cc_power_bg": "rgba(245, 247, 252, 0.95)" if is_light else to_rgba(popup_rgb, 0.92),
        "cc_pwd_bg": "rgba(255, 255, 255, 0.96)" if is_light else to_rgba(popup_rgb, 0.95),
        "cc_border": "rgba(0, 0, 0, 0.10)" if is_light else hex_to_rgba(accent_text, 0.26),
        "cc_pwd_border": hex_to_rgba(accent_mid, 0.45) if is_light else hex_to_rgba(accent_text, 0.42),
        "cc_glow": hex_to_rgba(s2, 0.12 if is_light else 0.18),
        "drawer_bg": "rgba(248, 250, 255, 0.94)" if is_light else to_rgba(drawer_rgb, 0.85),
        "dunst_bg": f"{_rgb_to_hex(popup_rgb)}E6",
        "dunst_low_frame": _rgb_to_hex(ws_rgb),
        "accent_deep": accent_deep,
        "accent_mid": accent_mid,
        "accent_bright": accent_bright,
        "accent_hover": accent_hover,
        "accent_text": accent_text,
        "accent_muted": accent_muted,
        "accent_text_60": hex_to_rgba(accent_text, 0.60),
        "accent_text_50": hex_to_rgba(accent_text, 0.50),
        "accent_text_40": hex_to_rgba(accent_text, 0.40),
        "accent_text_25": hex_to_rgba(accent_text, 0.25),
        "accent_mid_25": hex_to_rgba(accent_mid, 0.25),
        "accent_mid_35": hex_to_rgba(accent_mid, 0.35),
        "accent_mid_40": hex_to_rgba(accent_mid, 0.40),
        "accent_mid_50": hex_to_rgba(accent_mid, 0.50),
        "accent_mid_70": hex_to_rgba(accent_mid, 0.70),
        "accent_mid_85": hex_to_rgba(accent_mid, 0.85),
        "accent_bright_60": hex_to_rgba(accent_bright, 0.60),
        "accent_wing_40": hex_to_rgba(s4, 0.40),
        "text_primary": "#0f172a" if is_light else "#FDFBFE",
        "text_soft": text_soft,
    }

def build_waybar_css(c):
    """Generate Waybar stylesheet keeping exact layout/geometry while adapting colors."""
    return f"""/* ==============================================================================
# Adaptive Wallpaper Theme — Waybar Top Panel Styling
# ============================================================================== */

* {{
    border: none;
    border-radius: 0;
    font-family: "Adwaita Sans", "Symbols Nerd Font", sans-serif;
    font-size: 13px;
    min-height: 0;
}}

window#waybar {{
    background: transparent;
    border: none;
    box-shadow: none;
    color: {c['text_primary']};
}}

window#waybar > revealer > box,
window#waybar > box {{
    background: transparent;
    border: none;
    box-shadow: none;
}}

/* Left side floating elements */
#custom-arch {{
    background-color: {c['ws_bg']};
    border: 1px solid {c['ws_border']};
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 700;
    padding: 0 12px;
    margin: 6px 4px 6px 8px;
    border-radius: 10px;
    transition: background-color 150ms ease-out, border-color 150ms ease-out;
}}

#custom-arch:hover {{
    background-color: {c['accent_mid_40']};
    border-color: {c['popup_border']};
}}

#custom-apps {{
    background-color: {c['ws_bg']};
    border: 1px solid {c['ws_border']};
    padding: 0 13px;
    margin: 6px 4px;
    border-radius: 10px;
    font-weight: 500;
    font-size: 13px;
    color: {c['text_soft']};
    transition: background-color 150ms ease-out, border-color 150ms ease-out;
}}

#custom-apps:hover {{
    background-color: {c['accent_mid_40']};
    border-color: {c['popup_border']};
}}

/* Center Workspaces Capsule */
#workspaces {{
    background: {c['ws_bg']};
    border: 1px solid {c['ws_border']};
    border-radius: 20px;
    padding: 2px 6px;
    margin: 6px 0;
}}

#workspaces button {{
    padding: 2px 10px;
    margin: 0 2px;
    border-radius: 14px;
    color: {c['ws_inactive']};
    font-weight: 600;
    font-size: 13px;
    min-width: 22px;
    transition: color 180ms ease;
    background: transparent;
    border: none;
    box-shadow: none;
}}

#workspaces button.active {{
    background: transparent;
    color: #FFFFFF;
    font-weight: 700;
    box-shadow: none;
}}

#workspaces button:hover {{
    background: transparent;
    background-color: transparent;
    border: none;
    box-shadow: none;
}}

#workspaces button.active:hover {{
    background: transparent;
    background-color: transparent;
    border: none;
    box-shadow: none;
}}

/* Tooltip & GTK Dropdown Menus */
tooltip {{
    background: {c['popup_bg']};
    color: {c['text_primary']};
    border: 1px solid {c['popup_border']};
    border-radius: 10px;
    padding: 6px 12px;
    font-size: 12px;
}}

menu,
.popup menu {{
    background: {c['popup_bg']};
    color: {c['text_primary']};
    border: 1px solid {c['popup_border']};
    border-radius: 12px;
    padding: 4px;
}}

menuitem,
menu menuitem {{
    color: {c['text_soft']};
    border-radius: 8px;
    padding: 5px 10px;
}}

menuitem:hover,
menu menuitem:hover {{
    background-color: {c['accent_mid_35']};
    color: #FFFFFF;
}}
"""

def build_chevron_svg(c):
    accent = c.get("accent_text", "#a4c1ea")
    fill_col = c.get("accent_bright", accent)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">\n'
        f'  <rect x="1.5" y="3" width="21" height="7.5" rx="3.75" fill="{fill_col}" fill-opacity="0.32" stroke="#ffffff" stroke-width="1.5"/>\n'
        '  <circle cx="18.75" cy="6.75" r="2.25" fill="#ffffff"/>\n'
        '  <rect x="1.5" y="13.5" width="21" height="7.5" rx="3.75" stroke="#ffffff" stroke-width="1.5"/>\n'
        f'  <circle cx="5.25" cy="17.25" r="2.25" fill="{accent}"/>\n'
        '</svg>\n'
    )

def build_slider_colors_text(c):
    r1, g1, b1 = _hex_to_rgb(c["accent_deep"], (139, 92, 246))
    r2, g2, b2 = _hex_to_rgb(c["accent_bright"], (192, 132, 252))
    sr, sg, sb = _hex_to_rgb(c["accent_text"], (210, 180, 255))
    return f"{r1} {g1} {b1} {r2} {g2} {b2} {sr} {sg} {sb}\n"

def build_drawer_css(c):
    return f"""/* ==============================================================================
# Adaptive Wallpaper Theme — nwg-drawer (Launchpad) Styling
# ============================================================================== */

window {{
    background-color: {c['drawer_bg']};
    color: {c['text_primary']};
    font-family: "Adwaita Sans", sans-serif;
}}

/* Centered spotlight-style search entry */
entry {{
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid {c['popup_border']};
    border-radius: 18px;
    color: {c['text_primary']};
    padding: 8px 16px;
    margin: 20px 80px;
    font-size: 14px;
}}

entry:focus {{
    border-color: {c['accent_mid']};
    background-color: rgba(255, 255, 255, 0.14);
}}

/* Application items */
button, image {{
    background: none;
    border: none;
}}

button {{
    border-radius: 14px;
    padding: 10px;
    transition: all 180ms cubic-bezier(0.2, 0.9, 0.3, 1);
}}

button:hover {{
    background-color: rgba(255, 255, 255, 0.14);
}}

/* Category buttons */
#category-button {{
    margin: 0 8px;
    padding: 4px 12px;
    border-radius: 10px;
    font-weight: 500;
}}

#category-button:hover {{
    background-color: rgba(255, 255, 255, 0.12);
    color: {c['accent_bright']};
}}

#pinned-box {{
    padding-bottom: 8px;
    border-bottom: 1px solid {c['bar_border']};
}}

#files-box {{
    padding: 8px;
    border: 1px solid {c['bar_border']};
    border-radius: 14px;
}}

#math-label {{
    font-weight: 600;
    font-size: 16px;
    color: {c['accent_bright']};
}}
"""

def _update_dunstrc_text(text, c):
    """Update only [urgency_low] and [urgency_normal] colors while preserving all other settings."""
    out_lines = []
    section = None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            out_lines.append(line)
            continue
        if section in ("urgency_low", "urgency_normal") and "=" in line:
            key = line.split("=", 1)[0].strip()
            indent = line[: len(line) - len(line.lstrip())]
            nl = "\n" if line.endswith("\n") else ""
            if key == "background":
                out_lines.append(f'{indent}background = "{c["dunst_bg"]}"{nl}')
                continue
            if key == "frame_color":
                col = c["dunst_low_frame"] if section == "urgency_low" else c["accent_text"]
                out_lines.append(f'{indent}frame_color = "{col}"{nl}')
                continue
            if key == "highlight":
                out_lines.append(f'{indent}highlight = "{c["accent_text"]}"{nl}')
                continue
        out_lines.append(line)
    return "".join(out_lines)

def _write_if_changed(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == content:
                return False
    except Exception:
        pass
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)
    return True

def update_kitty_cursor(cursor_hex):
    """Update cursor color in kitty.conf."""
    if not os.path.isfile(KITTY_CONF_FILE):
        return False
    try:
        with open(KITTY_CONF_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        new_content = re.sub(
            r"^(\s*cursor\s+)#?[0-9a-fA-F]+",
            f"\\g<1>{cursor_hex}",
            content,
            flags=re.MULTILINE
        )
        return _write_if_changed(KITTY_CONF_FILE, new_content)
    except Exception:
        return False

def update_hypr_border(stops, reload=False):
    """Update Hyprland active window border colors with wallpaper theme stops."""
    valid_stops = [str(s) for s in (stops or []) if str(s).startswith("#")]
    if len(valid_stops) < 2:
        valid_stops = ["#a855f7", "#ec4899"]
    s1 = valid_stops[1].lstrip("#")
    s2 = valid_stops[0].lstrip("#")
    border_val = f"rgba({s1}ee) rgba({s2}ee) 45deg"
    try:
        from shared import system
        system.update_hypr_config(active_border=border_val, reload=reload)
        return True
    except Exception:
        pass
    content = (
        "# Dynamic wallpaper-adaptive theme for Hyprland\n"
        "# Automatically updated by Neon Desktop theme engine\n"
        "general {\n"
        f"    col.active_border = {border_val}\n"
        "    col.inactive_border = rgba(382046aa)\n"
        "}\n"
    )
    changed = _write_if_changed(HYPR_THEME_FILE, content)
    try:
        env = _find_hypr_env()
        cmd = ["hyprctl", "-i", "0", "reload", "config-only"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    except Exception:
        pass
    return changed

def build_neon_drawer_css(dt, c, theme_mode=None, transparency=None, blur_strength=None):
    """Generate CSS for neon-drawer matching Neon Glass App Launcher at Sunset."""
    try:
        from shared import config
        cfg = config.load_settings()
        t_mode = theme_mode if theme_mode is not None else cfg.get("theme_mode", "Dark")
    except Exception:
        cfg = {}
        t_mode = theme_mode or "Dark"
    if t_mode not in ("Light", "Dark"):
        t_mode = "Dark"
    is_light = (t_mode == "Light")

    tb = transparency if transparency is not None else cfg.get("transparency", cfg.get("transparency_blur", 70))
    try:
        t_val = float(tb)
    except Exception:
        t_val = 70.0

    inv_t = max(0.0, min(1.0, (100.0 - t_val) / 100.0))
    if inv_t <= 0.30:
        drawer_alpha = round(0.04 + (inv_t / 0.30) * 0.10, 2)
        drawer_alpha_light = round(0.40 + (inv_t / 0.30) * 0.52, 2)
    else:
        drawer_alpha = round(0.14 + ((inv_t - 0.30) / 0.70) * 0.72, 2)
        drawer_alpha_light = round(0.92 + ((inv_t - 0.30) / 0.70) * 0.06, 2)

    base_r, base_g, base_b = dt.get("base_rgb", (18, 12, 30))
    raw_stops = dt.get("stops", ["#f43f85", "#ec4899", "#d946ef", "#a855f7", "#818cf8"])
    stops = [_tone_hex(s, target_l=0.62, min_s=0.72) for s in raw_stops]
    if len(stops) < 5:
        stops = ["#f5475a", "#9f55e7", "#556ee7", "#5557e7", "#6955e7"]
    s0 = stops[0]
    s1 = stops[1] if len(stops) > 1 else s0
    s2 = stops[2] if len(stops) > 2 else s1
    s3 = stops[3] if len(stops) > 3 else s2
    s4 = stops[4] if len(stops) > 4 else s3

    if is_light:
        card_inner_bg = f"background-color: rgba(248, 250, 255, {drawer_alpha_light});"
        card_inner_gradient = """linear-gradient(135deg, 
        rgba(255, 255, 255, 0.70) 0%, 
        rgba(240, 244, 252, 0.50) 35%, 
        rgba(230, 236, 250, 0.60) 100%
    );"""
        border_top = "border-top: 1.5px solid rgba(255, 255, 255, 0.90);"
        box_shadow = f"""inset 0 0 20px {hex_to_rgba(s0, 0.08)},
        inset 0 1px 1.5px rgba(255, 255, 255, 0.80),
        0 16px 40px rgba(0, 0, 0, 0.12);"""
        back_btn_bg = "rgba(0, 0, 0, 0.05)"
        back_btn_border = "rgba(0, 0, 0, 0.10)"
        back_btn_color = "#0f172a"
        title_color = "#0f172a"
        subtitle_color = "#475569"
        tool_btn_bg = "rgba(0, 0, 0, 0.05)"
        tool_btn_border = "rgba(0, 0, 0, 0.08)"
        tool_btn_color = "#334155"
        cat_pill_color = "#334155"
        cat_pill_hover_bg = "rgba(0, 0, 0, 0.06)"
        cat_pill_hover_color = "#0f172a"
        search_bg = "rgba(255, 255, 255, 0.85)"
        search_border = "rgba(0, 0, 0, 0.12)"
        search_color = "#0f172a"
        search_ph_color = "rgba(15, 23, 42, 0.45)"
        squircle_bg = "rgba(0, 0, 0, 0.04)"
        squircle_border = "rgba(0, 0, 0, 0.08)"
        app_tile_lbl_color = "#0f172a"
        row_bg = "rgba(255, 255, 255, 0.55)"
        row_border = "rgba(0, 0, 0, 0.06)"
        row_hover_bg = "rgba(255, 255, 255, 0.90)"
        app_title_color = "#0f172a"
        app_desc_color = "#64748b"
        badge_bg = "rgba(0, 0, 0, 0.06)"
        badge_border = "rgba(0, 0, 0, 0.08)"
        badge_color = "#475569"
    else:
        card_inner_bg = f"background-color: rgba({base_r}, {base_g}, {base_b}, {drawer_alpha});"
        card_inner_gradient = """linear-gradient(135deg, 
        rgba(255, 255, 255, 0.10) 0%, 
        rgba(255, 255, 255, 0.02) 25%, 
        rgba(0, 0, 0, 0.06) 100%
    );"""
        border_top = "border-top: 1.5px solid rgba(255, 255, 255, 0.40);"
        box_shadow = f"""inset 0 0 20px {hex_to_rgba(s0, 0.20)},
        inset 0 1px 1.5px rgba(255, 255, 255, 0.35);"""
        back_btn_bg = "rgba(255, 255, 255, 0.05)"
        back_btn_border = "rgba(255, 255, 255, 0.10)"
        back_btn_color = "#FFFFFF"
        title_color = "#FFFFFF"
        subtitle_color = "rgba(255, 255, 255, 0.55)"
        tool_btn_bg = "rgba(255, 255, 255, 0.06)"
        tool_btn_border = "rgba(255, 255, 255, 0.10)"
        tool_btn_color = "rgba(255, 255, 255, 0.75)"
        cat_pill_color = "rgba(255, 255, 255, 0.72)"
        cat_pill_hover_bg = "rgba(255, 255, 255, 0.08)"
        cat_pill_hover_color = "#FFFFFF"
        search_bg = "rgba(255, 255, 255, 0.07)"
        search_border = "rgba(255, 255, 255, 0.12)"
        search_color = "#FFFFFF"
        search_ph_color = "rgba(255, 255, 255, 0.45)"
        squircle_bg = "rgba(255, 255, 255, 0.07)"
        squircle_border = "rgba(255, 255, 255, 0.10)"
        app_tile_lbl_color = "#FFFFFF"
        row_bg = "rgba(255, 255, 255, 0.05)"
        row_border = "rgba(255, 255, 255, 0.08)"
        row_hover_bg = "rgba(255, 255, 255, 0.12)"
        app_title_color = "#FFFFFF"
        app_desc_color = "rgba(255, 255, 255, 0.62)"
        badge_bg = "rgba(255, 255, 255, 0.08)"
        badge_border = "rgba(255, 255, 255, 0.08)"
        badge_color = "rgba(255, 255, 255, 0.70)"

    return f"""/* ==============================================================================
# Neon Desktop — Adaptive Glass App Drawer (Sunset Neon Glass Theme)
# ============================================================================== */

* {{
    font-family: "Adwaita Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    outline: none;
}}

#drawer-window,
#drawer-backdrop {{
    background-color: transparent;
    background: transparent;
}}

#launcher-card-border {{
    background: transparent;
    background-color: transparent;
    border-radius: 28px;
    padding: 0;
    box-shadow: none;
}}

#launcher-card-inner {{
    {card_inner_bg}
    background-image: {card_inner_gradient}
    border-radius: 28px;
    padding: 24px 28px;
    border: 1px solid {hex_to_rgba(s1, 0.45)};
    {border_top}
    border-left: 1.5px solid {hex_to_rgba(s0, 0.60)};
    border-right: 1px solid {hex_to_rgba(s2, 0.35)};
    border-bottom: 1px solid {hex_to_rgba(s3, 0.30)};
    box-shadow: {box_shadow}
}}

/* Header Controls */
button,
button.tool-btn,
button.category-pill,
button#back-btn {{
    background-image: none;
    box-shadow: none;
    text-shadow: none;
    border: none;
}}

#back-btn {{
    background-color: {back_btn_bg};
    border: 1px solid {back_btn_border};
    border-radius: 10px;
    padding: 7px 10px;
    color: {back_btn_color};
    transition: all 180ms cubic-bezier(0.4, 0, 0.2, 1);
}}
#back-btn:hover {{
    background-color: {back_btn_bg};
    border-color: rgba(255, 255, 255, 0.24);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35), 0 0 10px rgba(255, 255, 255, 0.12);
}}

#header-title {{
    font-size: 19px;
    font-weight: 700;
    color: {title_color};
}}

#header-subtitle {{
    font-size: 12px;
    color: {subtitle_color};
}}

.tool-btn {{
    background-color: {tool_btn_bg};
    border: 1px solid {tool_btn_border};
    border-radius: 10px;
    padding: 7px 9px;
    color: {tool_btn_color};
    transition: all 180ms ease;
}}
.tool-btn:hover {{
    background-color: {tool_btn_bg};
    border-color: {tool_btn_border};
    color: {tool_btn_color};
    box-shadow: none;
}}
.tool-btn.active {{
    background: linear-gradient(135deg, {s0}, {s1});
    border: none;
    outline: none;
    color: #FFFFFF;
    box-shadow: 0 4px 16px {hex_to_rgba(s0, 0.45)};
}}
.tool-btn.active:hover,
.tool-btn.active:focus {{
    background: linear-gradient(135deg, {s0}, {s1});
    border: none;
    outline: none;
    color: #FFFFFF;
}}

/* Sidebar Category Pills */
.category-pill {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 12px;
    padding: 8px 12px;
    color: {cat_pill_color};
    font-size: 13.5px;
    font-weight: 500;
    transition: all 160ms ease;
}}
.category-pill:hover {{
    background-color: {cat_pill_hover_bg};
    color: {cat_pill_hover_color};
}}
.category-pill.active,
.category-pill.active:hover,
.category-pill.active:focus {{
    background: linear-gradient(135deg, {s0}, {s1});
    border: none;
    outline: none;
    color: #FFFFFF;
    font-weight: 600;
    box-shadow: 0 4px 18px {hex_to_rgba(s0, 0.45)};
}}

.category-badge {{
    background-color: rgba(255, 255, 255, 0.10);
    border-radius: 10px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
    color: {cat_pill_color};
}}
.category-pill.active .category-badge {{
    background-color: rgba(255, 255, 255, 0.28);
    color: #FFFFFF;
    font-weight: 700;
}}

/* Search Entry Box */
#search-bar-box {{
    background-color: {search_bg};
    border: 1px solid {search_border};
    border-radius: 14px;
    padding: 0 12px;
    min-height: 36px;
    transition: all 180ms ease;
}}
#search-bar-box:focus-within {{
    border-color: {s1};
    box-shadow: 0 0 14px {hex_to_rgba(s1, 0.35)};
}}

#search-entry {{
    background: transparent;
    border: none;
    box-shadow: none;
    color: {search_color};
    font-size: 13px;
    padding: 4px 6px;
    min-height: 24px;
}}
#search-entry placeholder {{
    color: {search_ph_color};
}}

/* App Tile (Grid View) */
.app-tile-box {{
    padding: 3px 3px;
    border-radius: 16px;
    transition: all 180ms cubic-bezier(0.2, 0.9, 0.3, 1);
}}

.app-icon-squircle {{
    background-color: {squircle_bg};
    border: 1px solid {squircle_border};
    border-radius: 16px;
    padding: 7px;
    transition: all 180ms ease;
}}

.app-tile-box:hover .app-icon-squircle {{
    background-color: rgba(255, 255, 255, 0.15);
    border-color: rgba(255, 255, 255, 0.30);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35), 0 0 12px {hex_to_rgba(s1, 0.28)};
}}

.app-tile-label {{
    color: {app_tile_lbl_color};
    font-size: 11px;
    font-weight: 500;
    margin-top: 3px;
}}

/* Container & Scrolled Window */
#launcher-scrolled,
#launcher-scrolled viewport,
scrolledwindow,
scrolledwindow viewport,
viewport,
list,
listbox,
row {{
    background-color: transparent;
    background: transparent;
    border: none;
    box-shadow: none;
    outline: none;
}}

#app-list-box {{
    background-color: transparent;
    background: transparent;
}}

.app-list-row {{
    background-color: {row_bg};
    border: 1px solid {row_border};
    border-radius: 14px;
    padding: 9px 14px;
    transition: all 160ms cubic-bezier(0.4, 0, 0.2, 1);
}}
.app-list-row:hover {{
    background-color: {row_hover_bg};
    border-color: rgba(255, 255, 255, 0.22);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.30), 0 0 10px {hex_to_rgba(s1, 0.20)};
}}

.app-list-title {{
    color: {app_title_color};
    font-size: 13px;
    font-weight: 600;
}}

.app-list-desc {{
    color: {app_desc_color};
    font-size: 11.5px;
}}

/* Uniform fixed-size Category Badge for List View */
.app-list-badge {{
    background-color: {badge_bg};
    border: 1px solid {badge_border};
    border-radius: 9px;
    font-size: 11px;
    font-weight: 600;
    color: {badge_color};
    min-width: 76px;
    min-height: 26px;
    padding: 0 4px;
}}

/* Overshoot / Undershoot Scroll Boundary Indicators - Removed */
#launcher-scrolled overshoot.top,
#launcher-scrolled overshoot.bottom,
overshoot.top,
overshoot.bottom,
overshoot,
#launcher-scrolled undershoot.top,
#launcher-scrolled undershoot.bottom,
undershoot.top,
undershoot.bottom,
undershoot {{
    background: none;
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
}}

/* Scrollbar completely invisible while keeping full scrolling */
scrollbar,
scrollbar.vertical,
scrollbar.horizontal,
#launcher-scrolled scrollbar,
#launcher-scrolled scrollbar.vertical,
#launcher-scrolled scrollbar.horizontal,
scrollbar trough,
scrollbar.vertical trough,
#launcher-scrolled scrollbar trough,
#launcher-scrolled scrollbar.vertical trough,
scrollbar slider,
scrollbar.vertical slider,
#launcher-scrolled scrollbar slider,
#launcher-scrolled scrollbar.vertical slider {{
    opacity: 0;
    min-width: 0;
    min-height: 0;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
    background-color: transparent;
    background-image: none;
    -gtk-icon-shadow: none;
    box-shadow: none;
}}

/* Context Menu */
#drawer-context-menu {{
    background-color: rgba({base_r}, {base_g}, {base_b}, 0.96);
    border: 1px solid {hex_to_rgba(s1, 0.50)};
    border-radius: 14px;
    padding: 6px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.65), 0 0 18px {hex_to_rgba(s1, 0.25)};
}}

#drawer-context-menu menuitem {{
    color: #FFFFFF;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
}}

#drawer-context-menu menuitem:hover {{
    background-color: {hex_to_rgba(s1, 0.35)};
    color: #FFFFFF;
}}

/* Rename Modal Dialog */
.dialog-shroud {{
    background-color: rgba(0, 0, 0, 0.42);
    border-radius: 24px;
}}

#rename-dialog {{
    background-color: rgba({base_r}, {base_g}, {base_b}, 0.94);
    border: 1.5px solid {hex_to_rgba(s1, 0.60)};
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.70), 0 0 35px {hex_to_rgba(s1, 0.35)};
}}

#rename-dialog label {{
    color: #FFFFFF;
}}

#rename-dialog .header-subtitle {{
    color: rgba(255, 255, 255, 0.78);
    font-size: 12.5px;
}}

#rename-entry {{
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 12px;
    padding: 8px 14px;
    color: #FFFFFF;
    font-size: 13.5px;
}}

#rename-entry:focus {{
    border-color: {s1};
    box-shadow: 0 0 12px {hex_to_rgba(s1, 0.35)};
}}

.dialog-btn-save {{
    background: linear-gradient(135deg, {s0}, {s1});
    color: #FFFFFF;
    border-radius: 10px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
    border: none;
}}

.dialog-btn-cancel {{
    background-color: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.80);
    border-radius: 10px;
    padding: 7px 16px;
    font-weight: 500;
    font-size: 13px;
    border: 1px solid rgba(255, 255, 255, 0.12);
}}
.dialog-btn-cancel:hover {{
    background-color: rgba(255, 255, 255, 0.14);
}}
"""

_BANNER_CACHE = {}

def _render_feathered_banner_disk(valid_src, base_rgb, out_path, cache_key):
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file(valid_src)
        pb_rgba = pb.add_alpha(False, 0, 0, 0)
        w = pb_rgba.get_width()
        h = pb_rgba.get_height()
        rs = pb_rgba.get_rowstride()
        n_ch = pb_rgba.get_n_channels()
        px = bytearray(pb_rgba.get_pixels())

        br, bg, bb = base_rgb

        for y in range(h):
            y_norm = y / (h - 1)
            if y_norm <= 0.38:
                v_alpha = 1.0
                tint_factor = 0.0
            elif y_norm >= 0.98:
                v_alpha = 0.0
                tint_factor = 1.0
            else:
                t = (y_norm - 0.38) / (0.98 - 0.38)
                ease = 3 * t**2 - 2 * t**3
                v_alpha = 1.0 - ease
                tint_factor = ease

            row_start = y * rs
            for x in range(w):
                x_norm = x / (w - 1)
                if x_norm < 0.38:
                    dark_factor = 0.30 + 0.70 * (x_norm / 0.38)
                else:
                    dark_factor = 1.0

                idx = row_start + x * n_ch
                r = px[idx] * dark_factor
                g = px[idx + 1] * dark_factor
                b = px[idx + 2] * dark_factor

                r = int(r * (1.0 - tint_factor) + br * tint_factor)
                g = int(g * (1.0 - tint_factor) + bg * tint_factor)
                b = int(b * (1.0 - tint_factor) + bb * tint_factor)
                a = int(255 * v_alpha)

                px[idx] = r
                px[idx + 1] = g
                px[idx + 2] = b
                px[idx + 3] = a

        gbytes = GLib.Bytes.new(bytes(px))
        feathered_pb = GdkPixbuf.Pixbuf.new_from_bytes(gbytes, GdkPixbuf.Colorspace.RGB, True, 8, w, h, rs)
        feathered_pb.savev(out_path, "png", [], [])

        arch_assets = os.path.expanduser("~/Projects/arch-desktop/assets")
        if os.path.isdir(arch_assets):
            feathered_pb.savev(os.path.join(arch_assets, "zoro-sunset-feathered.png"), "png", [], [])
        _BANNER_CACHE["key"] = cache_key
        return out_path
    except Exception as e:
        print(f"[theme] generate_feathered_banner error: {e}")
        return valid_src

def generate_feathered_banner(src_path=None, base_rgb=(18, 12, 28), sync=False):
    """
    Generates a smoothly feathered version of the Zoro sunset banner.
    Feathers alpha down to 0 at the bottom and blends RGB with base_rgb
    so it attaches and smoothly merges into the 80% frosted glass card.
    Uses cached asset immediately without freezing theme pipelines.
    """
    candidates = [
        src_path,
        "/home/nithin/Downloads/Zoro Beneath a Crimson Sunset.png",
        os.path.expanduser("~/.config/neon-desktop/assets/zoro-sunset.png"),
        os.path.expanduser("~/Projects/arch-desktop/assets/zoro-sunset.png"),
    ]
    valid_src = None
    for c in candidates:
        if c and os.path.isfile(c):
            valid_src = c
            break

    if not valid_src:
        return ""

    out_dir = os.path.expanduser("~/.config/neon-desktop/assets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "zoro-sunset-feathered.png")

    cache_key = (valid_src, tuple(base_rgb))
    if _BANNER_CACHE.get("key") == cache_key and os.path.isfile(out_path):
        return out_path

    if os.path.isfile(out_path) and not sync:
        if _BANNER_CACHE.get("key") != cache_key and not _BANNER_CACHE.get("updating"):
            _BANNER_CACHE["updating"] = True
            def _bg():
                try:
                    _render_feathered_banner_disk(valid_src, base_rgb, out_path, cache_key)
                finally:
                    _BANNER_CACHE["updating"] = False
            threading.Thread(target=_bg, daemon=True).start()
        return out_path

    return _render_feathered_banner_disk(valid_src, base_rgb, out_path, cache_key)

def build_neon_drun_css(dt, c, transparency=None, blur_strength=None):
    """Generate CSS for neon-drun matching 'Neon Launcher with Zoro Sunset Banner'."""
    try:
        from shared import config
        cfg = config.load_settings()
    except Exception:
        cfg = {}

    tb = transparency if transparency is not None else cfg.get("transparency", cfg.get("transparency_blur", 70))
    try:
        t_val = float(tb)
    except Exception:
        t_val = 70.0

    inv_t = max(0.0, min(1.0, (100.0 - t_val) / 100.0))
    if inv_t <= 0.30:
        card_alpha = round(0.05 + (inv_t / 0.30) * 0.15, 2)
    else:
        card_alpha = round(0.20 + ((inv_t - 0.30) / 0.70) * 0.68, 2)

    base_r, base_g, base_b = dt.get("base_rgb", (18, 12, 30))
    raw_stops = dt.get("stops", ["#f43f85", "#ec4899", "#d946ef", "#a855f7", "#818cf8"])
    stops = [_tone_hex(s, target_l=0.62, min_s=0.72) for s in raw_stops]
    if len(stops) < 5:
        stops = ["#f5475a", "#9f55e7", "#556ee7", "#5557e7", "#6955e7"]
    s0 = stops[0]
    s1 = stops[1] if len(stops) > 1 else s0
    s2 = stops[2] if len(stops) > 2 else s1
    s3 = stops[3] if len(stops) > 3 else s2
    s4 = stops[4] if len(stops) > 4 else s3

    feathered_banner = generate_feathered_banner(base_rgb=(base_r, base_g, base_b))
    if not feathered_banner:
        feathered_banner = os.path.expanduser("~/.config/neon-desktop/assets/zoro-sunset.png")

    return f"""/* ==============================================================================
# Neon Desktop — Adaptive Glass Drun Launcher (Zoro Sunset Banner)
# ============================================================================== */

* {{
    font-family: "Adwaita Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    outline: none;
}}

button,
button:hover,
button:focus,
button:active {{
    background-image: none;
    background-color: transparent;
    border: none;
    box-shadow: none;
    text-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
    color: #ffffff;
}}

image,
image:hover,
button image,
button:hover image,
.drun-pinned-card image,
.drun-mode-btn image,
.drun-list-row image {{
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    border: none;
    box-shadow: none;
    outline: none;
}}

#drun-window,
#drun-backdrop {{
    background-color: transparent;
    background: transparent;
}}

#drun-card-border {{
    background: transparent;
    background-color: transparent;
    border-radius: 24px;
    padding: 0;
    box-shadow: none;
}}

#drun-card-inner {{
    background-color: rgba({base_r}, {base_g}, {base_b}, {card_alpha});
    background-image: 
        linear-gradient(135deg, 
            rgba(255, 255, 255, 0.08) 0%, 
            rgba(255, 255, 255, 0.02) 25%, 
            rgba(0, 0, 0, 0.06) 100%
        ),
        url('{feathered_banner}');
    background-repeat: no-repeat, no-repeat;
    background-position: center center, top center;
    background-size: 100% 100%, 720px 240px;
    border-radius: 24px;
    padding: 0;
    border: 1.5px solid {hex_to_rgba(s1, 0.50)};
    box-shadow: inset 0 1px 1px 0 rgba(255, 255, 255, 0.20),
                inset 0 0 16px 0 {hex_to_rgba(s1, 0.08)};
}}

#drun-header-banner {{
    background: transparent;
    background-color: transparent;
    padding: 0;
    margin: 18px 24px 0px 24px;
    min-height: 36px;
}}

#drun-title {{
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}}

#drun-subtitle {{
    color: rgba(255, 255, 255, 0.65);
    font-size: 11.5px;
    font-weight: 400;
}}

.drun-mode-btn {{
    min-width: 34px;
    min-height: 34px;
    border-radius: 10px;
    background-color: rgba(18, 12, 28, 0.55);
    border: none;
    color: #ffffff;
    padding: 0;
    transition: all 150ms ease;
    box-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

.drun-mode-btn:hover {{
    background-color: rgba(255, 255, 255, 0.14);
    border: none;
    box-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

.drun-mode-btn.active {{
    background-color: {hex_to_rgba(s1, 0.75)};
    border: none;
    box-shadow: 0 0 8px {hex_to_rgba(s1, 0.25)};
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

#drun-search-container {{
    background-color: rgba(255, 255, 255, 0.06);
    background-image: linear-gradient(135deg, 
        rgba(255, 255, 255, 0.08) 0%, 
        rgba(255, 255, 255, 0.02) 100%
    );
    border: 1px solid {hex_to_rgba(s1, 0.40)};
    border-radius: 12px;
    padding: 2px 14px;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.15);
    margin: 104px 24px 12px 24px;
    min-height: 36px;
}}

#drun-search-entry {{
    background: transparent;
    background-color: transparent;
    border: none;
    box-shadow: none;
    color: #ffffff;
    font-size: 13.5px;
    caret-color: {s1};
}}

#drun-search-entry:focus {{
    background: transparent;
    border: none;
    box-shadow: none;
}}

#drun-search-badge {{
    background-color: rgba(10, 8, 16, 0.55);
    border: none;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.75);
}}

.drun-section-header {{
    padding: 4px 26px 4px 26px;
}}

.drun-section-title {{
    font-size: 13.5px;
    font-weight: 700;
    color: #ffffff;
}}

.drun-section-action {{
    font-size: 11.5px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.65);
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 2px 6px;
    border-radius: 6px;
}}

.drun-section-action:hover {{
    color: {s1};
    background-color: rgba(255, 255, 255, 0.05);
}}

.drun-pinned-box {{
    padding: 2px 24px 8px 24px;
}}

.drun-pinned-card {{
    min-width: 54px;
    min-height: 54px;
    background-color: rgba(255, 255, 255, 0.06);
    border: none;
    border-radius: 14px;
    padding: 0;
    transition: all 180ms ease;
    box-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

.drun-pinned-card:hover,
.drun-pinned-card:focus,
.drun-pinned-card:active {{
    background-color: rgba(255, 255, 255, 0.12);
    border: none;
    box-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

.drun-recent-box {{
    padding: 2px 24px 10px 24px;
}}

.drun-list-row {{
    border-radius: 12px;
    padding: 6px 14px;
    background-color: rgba(255, 255, 255, 0.03);
    border: none;
    min-height: 46px;
    transition: all 150ms ease;
    margin-bottom: 5px;
    box-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

.drun-list-row.active,
.drun-list-row:hover,
.drun-list-row:focus {{
    background-color: rgba(255, 255, 255, 0.08);
    border: none;
    box-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
}}

.drun-list-title {{
    font-size: 13px;
    font-weight: 600;
    color: #ffffff;
}}

.drun-list-subtitle {{
    font-size: 11px;
    color: rgba(255, 255, 255, 0.65);
}}

.drun-shortcut-badge {{
    background-color: rgba(10, 8, 16, 0.55);
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 10.5px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.75);
}}

.drun-results-box {{
    padding: 8px 24px;
}}

.drun-results-scrolled {{
    background: transparent;
    background-color: transparent;
}}

.drun-results-scrolled viewport {{
    background: transparent;
    background-color: transparent;
}}

/* Clean transparent scrollbars */
scrollbar,
scrollbar trough,
scrollbar slider {{
    opacity: 0;
    min-width: 0;
    min-height: 0;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
    background-color: transparent;
}}

scrolledwindow overshoot,
scrolledwindow undershoot {{
    background: none;
    background-color: transparent;
}}
"""

def build_neon_settings_css(dt, c, theme_mode=None, transparency_blur=None, rounded_corners=None, animations=None, gradient_accents=None, transparency=None, blur_strength=None):
    """Generate CSS for neon-settings matching 'Neon Glass Settings with Media Dock'."""
    try:
        from shared import config
        cfg = config.load_settings()
    except Exception:
        cfg = {}

    t_mode = theme_mode if theme_mode is not None else cfg.get("theme_mode", "Dark")
    if t_mode not in ("Light", "Dark"):
        t_mode = "Dark"
    effective_mode = t_mode

    if transparency is not None:
        tb = transparency
    elif transparency_blur is not None:
        tb = transparency_blur
    else:
        tb = cfg.get("transparency", cfg.get("transparency_blur", 70))

    rc = rounded_corners if rounded_corners is not None else cfg.get("rounded_corners", 16)
    anim = animations if animations is not None else cfg.get("animations", True)
    grad = gradient_accents if gradient_accents is not None else cfg.get("gradient_accents", True)
    translucent = cfg.get("translucent_panels", True)

    if not translucent:
        glass_opacity = 0.98
    else:
        glass_opacity = max(0.30, min(0.98, round(0.40 + (tb / 100.0) * 0.52, 2)))
    r_win = max(4, int(rc))
    r_card = max(4, int(rc) - 2)

    base_r, base_g, base_b = dt.get("base_rgb", (18, 12, 30))
    raw_stops = dt.get("stops", ["#f43f85", "#ec4899", "#d946ef", "#a855f7", "#818cf8"])
    stops = [_tone_hex(s, target_l=0.62, min_s=0.72) for s in raw_stops]
    if len(stops) < 5:
        stops = ["#f5475a", "#9f55e7", "#556ee7", "#5557e7", "#6955e7"]
    s0 = stops[0]
    s1 = stops[1] if len(stops) > 1 else s0
    s2 = stops[2] if len(stops) > 2 else s1
    s3 = stops[3] if len(stops) > 3 else s2
    s4 = stops[4] if len(stops) > 4 else s3

    accent_grad = f"linear-gradient(135deg, {s0}, {s1})" if grad else f"{s0}"

    if effective_mode == "Light":
        light_glass_alpha = max(0.25, min(0.85, round(0.35 + (tb / 100.0) * 0.38, 2)))
        bg_card_inner = f"rgba(244, 246, 252, {light_glass_alpha})"
        inner_gradient = (
            "linear-gradient(135deg, "
            "rgba(255, 255, 255, 0.50) 0%, "
            "rgba(255, 255, 255, 0.22) 35%, "
            "rgba(228, 234, 248, 0.30) 100%)"
        )
        text_primary = "#0f172a"
        text_secondary = "#475569"
        card_bg = "rgba(255, 255, 255, 0.25)"
        card_border = "rgba(255, 255, 255, 0.60)"
        sidebar_bg = "rgba(255, 255, 255, 0.18)"
        search_bg = "rgba(255, 255, 255, 0.35)"
        search_border = "rgba(0, 0, 0, 0.08)"
        sec_btn_bg = "rgba(255, 255, 255, 0.28)"
        sec_btn_border = "rgba(0, 0, 0, 0.08)"
        menu_bg = "rgba(255, 255, 255, 0.94)"
        menu_border = "rgba(0, 0, 0, 0.10)"
        menu_item_col = "#0f172a"
        mockup_bg = "rgba(240, 243, 250, 0.60)"
        nav_hover_bg = "rgba(0, 0, 0, 0.05)"
        window_border_top = "rgba(255, 255, 255, 0.90)"
        window_border_side = hex_to_rgba(s1, 0.35)
        window_box_shadow = "0 24px 64px rgba(0, 0, 0, 0.15), inset 0 1px 1px rgba(255, 255, 255, 0.80)"
        trough_bg = "rgba(0, 0, 0, 0.10)"
    else:
        bg_card_inner = f"rgba({base_r}, {base_g}, {base_b}, {glass_opacity})"
        inner_gradient = (
            "linear-gradient(135deg, "
            "rgba(255, 255, 255, 0.08) 0%, "
            "rgba(255, 255, 255, 0.02) 25%, "
            "rgba(0, 0, 0, 0.15) 100%)"
        )
        text_primary = "#ffffff"
        text_secondary = "rgba(255, 255, 255, 0.50)"
        card_bg = "rgba(255, 255, 255, 0.04)" if translucent else f"rgba({base_r + 15}, {base_g + 15}, {base_b + 20}, 0.96)"
        card_border = "rgba(255, 255, 255, 0.07)" if translucent else "rgba(255, 255, 255, 0.14)"
        sidebar_bg = "rgba(0, 0, 0, 0.15)" if translucent else f"rgba({base_r // 2}, {base_g // 2}, {base_b // 2}, 0.98)"
        search_bg = "rgba(255, 255, 255, 0.06)"
        search_border = "rgba(255, 255, 255, 0.10)"
        sec_btn_bg = "rgba(255, 255, 255, 0.07)"
        sec_btn_border = "rgba(255, 255, 255, 0.12)"
        menu_bg = "rgba(22, 16, 32, 0.96)"
        menu_border = "rgba(255, 255, 255, 0.15)"
        menu_item_col = "rgba(255, 255, 255, 0.85)"
        mockup_bg = f"rgba(18, 12, 30, 0.85)" if translucent else f"rgba({base_r}, {base_g}, {base_b}, 0.98)"
        nav_hover_bg = "rgba(255, 255, 255, 0.08)"
        window_border_top = "rgba(255, 255, 255, 0.35)"
        window_border_side = hex_to_rgba(s1, 0.40)
        window_box_shadow = f"0 24px 64px rgba(0, 0, 0, 0.75), inset 0 1px 1px rgba(255, 255, 255, 0.25), inset 0 0 20px {hex_to_rgba(s1, 0.12)}"
        trough_bg = "rgba(255, 255, 255, 0.10)"

    anim_override = "" if anim else "* { transition-duration: 0s; }"

    return f"""/* ==============================================================================
# Neon Desktop — Adaptive Glass Settings Application
# ============================================================================== */

* {{
    font-family: "Adwaita Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    outline: none;
}}

{anim_override}

button,
button:hover,
button:focus,
button:active {{
    background-image: none;
    background-color: transparent;
    border: none;
    box-shadow: none;
    text-shadow: none;
    -gtk-icon-shadow: none;
    -gtk-icon-effect: none;
    outline: none;
    color: {text_primary};
}}

#settings-window,
#settings-backdrop {{
    background-color: transparent;
    background: transparent;
}}

#settings-card-border {{
    background: transparent;
    background-color: transparent;
    border-radius: {r_win}px;
    padding: 0;
    box-shadow: none;
}}

#settings-card-inner {{
    background-color: {bg_card_inner};
    background-image: {inner_gradient};
    border-radius: {r_win}px;
    border: 1px solid {window_border_side};
    border-top: 1.5px solid {window_border_top};
    border-left: 1.5px solid {hex_to_rgba(s0, 0.45)};
    border-right: 1px solid {hex_to_rgba(s2, 0.30)};
    border-bottom: 1px solid {hex_to_rgba(s3, 0.25)};
    box-shadow: {window_box_shadow};
}}

/* Header Bar */
#settings-header {{
    padding: 14px 20px 10px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}}

.traffic-dot,
button.traffic-dot {{
    min-width: 12px;
    min-height: 12px;
    border-radius: 6px;
    padding: 0;
    margin: 0 4px;
    border: none;
    box-shadow: none;
}}
.traffic-dot.close {{ background-color: #ff5f56; }}
.traffic-dot.close:hover {{ background-color: #ff3b30; }}
.traffic-dot.min {{ background-color: #ffbd2e; }}
.traffic-dot.min:hover {{ background-color: #ff9500; }}
.traffic-dot.max {{ background-color: #27c93f; }}
.traffic-dot.max:hover {{ background-color: #34c759; }}

#settings-header-title {{
    font-size: 15px;
    font-weight: 700;
    color: {text_primary};
    margin-left: 12px;
}}

/* Sidebar */
#settings-sidebar {{
    background-color: {sidebar_bg};
    border-right: 1px solid rgba(255, 255, 255, 0.07);
    padding: 14px 10px;
    min-width: 160px;
}}

#settings-search-box {{
    background-color: {search_bg};
    border: 1px solid {search_border};
    border-radius: 12px;
    padding: 2px 10px;
    margin: 0 4px 12px 4px;
    min-height: 34px;
    transition: all 150ms ease;
}}
#settings-search-box:focus-within {{
    border-color: {s1};
    box-shadow: 0 0 10px {hex_to_rgba(s1, 0.30)};
}}

#settings-search-entry {{
    background: transparent;
    border: none;
    color: {text_primary};
    font-size: 12.5px;
}}

.sidebar-section-header {{
    font-size: 10px;
    font-weight: 700;
    color: {text_secondary};
    letter-spacing: 0.8px;
    margin: 12px 10px 4px 10px;
}}

.nav-item {{
    border-radius: 10px;
    padding: 7px 12px;
    margin: 2px 4px;
    color: {text_primary};
    opacity: 0.85;
    font-size: 13px;
    font-weight: 500;
    transition: all 160ms cubic-bezier(0.4, 0, 0.2, 1);
}}
.nav-item:hover {{
    background-color: {nav_hover_bg};
    opacity: 1.0;
}}
.nav-item.active,
button.nav-item.active,
button.nav-item.active:hover,
button.nav-item.active:focus {{
    background-color: {s0};
    background-image: {accent_grad};
    color: #ffffff;
    opacity: 1.0;
    font-weight: 600;
    box-shadow: 0 4px 14px {hex_to_rgba(s0, 0.40)};
}}

/* Main Content Area */
#settings-content-scroll {{
    padding: 16px 20px;
    background: transparent;
}}

.page-title {{
    font-size: 26px;
    font-weight: 700;
    color: {text_primary};
}}

.page-subtitle {{
    font-size: 12.5px;
    color: {text_secondary};
    margin-bottom: 20px;
}}

.section-title {{
    font-size: 14.5px;
    font-weight: 600;
    color: {text_primary};
    margin-bottom: 4px;
}}

.section-desc {{
    font-size: 11.5px;
    color: {text_secondary};
    margin-bottom: 12px;
}}

/* Setting Cards & Rows */
.setting-card {{
    background-color: {card_bg};
    border: 1px solid {card_border};
    border-radius: {r_card}px;
    padding: 14px 18px;
    margin-bottom: 14px;
}}

.setting-row {{
    padding: 8px 0;
}}

.setting-row-title {{
    font-size: 13.5px;
    font-weight: 500;
    color: {text_primary};
}}

.setting-row-desc {{
    font-size: 11.5px;
    color: {text_secondary};
}}

/* Segmented Control */
.segmented-box {{
    background-color: {sec_btn_bg};
    border: 1px solid {sec_btn_border};
    border-radius: 12px;
    padding: 3px;
}}

.segmented-btn {{
    border-radius: 8px;
    padding: 4px 10px;
    color: {text_secondary};
    font-size: 11.5px;
    font-weight: 500;
    transition: all 150ms ease;
}}
.segmented-btn:hover {{
    color: {text_primary};
    background-color: rgba(255, 255, 255, 0.06);
}}
.segmented-btn.active,
button.segmented-btn.active,
button.segmented-btn.active:hover,
button.segmented-btn.active:focus {{
    background-color: {s0};
    background-image: {accent_grad};
    color: #ffffff;
    font-weight: 500;
    box-shadow: 0 2px 10px {hex_to_rgba(s0, 0.35)};
}}

/* Dock Elements & Ordering List */
.dock-elements-list {{
    background-color: transparent;
    border: none;
}}
.dock-element-row {{
    background-color: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 8px 12px;
    margin-bottom: 6px;
    transition: all 150ms ease;
}}
.dock-element-row:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.14);
}}
.dock-element-title {{
    font-size: 13px;
    font-weight: 500;
    color: {text_primary};
}}
.dock-element-grip {{
    color: {text_secondary};
    opacity: 0.65;
    padding: 4px 6px;
    transition: opacity 150ms ease;
}}
.dock-element-grip:hover {{
    opacity: 1.0;
    color: {text_primary};
}}

/* Modern Themed CheckButton */
checkbutton {{
    color: {text_primary};
}}
checkbutton check {{
    border-radius: 6px;
    border: 1.5px solid rgba(255, 255, 255, 0.28);
    background-color: rgba(255, 255, 255, 0.06);
    min-width: 18px;
    min-height: 18px;
    transition: all 140ms ease;
}}
checkbutton:hover check {{
    border-color: {s0};
    background-color: rgba(255, 255, 255, 0.12);
}}
checkbutton:checked check {{
    background-color: {s0};
    background-image: {accent_grad};
    border-color: {s0};
    color: #ffffff;
}}

/* Sliders */
scale {{
    padding: 6px 0;
}}
scale trough {{
    background-color: {trough_bg};
    border-radius: 6px;
    min-height: 6px;
    border: none;
}}
scale highlight {{
    background: {accent_grad};
    border-radius: 6px;
    min-height: 6px;
    border: none;
}}
scale slider {{
    background: #ffffff;
    border-radius: 50%;
    min-width: 16px;
    min-height: 16px;
    margin: -5px;
    border: none;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.40);
}}

.slider-val-lbl {{
    color: {text_primary};
    font-size: 12px;
    font-weight: 500;
}}

/* Switch / Toggle */
switch {{
    border-radius: 14px;
    border: 1px solid {card_border};
    background-color: {trough_bg};
    min-width: 44px;
    min-height: 24px;
    transition: all 180ms ease;
}}
switch:checked {{
    background: {accent_grad};
    border-color: {s0};
    box-shadow: 0 0 10px {hex_to_rgba(s0, 0.35)};
}}
switch slider {{
    background-color: #ffffff;
    border-radius: 50%;
    min-width: 20px;
    min-height: 20px;
    margin: 2px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.30);
}}

/* Wallpaper Carousel & Thumbnails (Jitter-free, Smooth Fluid Motion) */
.wp-carousel-box {{
    padding: 0;
}}
.wp-thumb,
button.wp-thumb {{
    border-radius: 10px;
    border: 2px solid rgba(255, 255, 255, 0.08);
    padding: 0;
    margin: 0;
    background-color: rgba(255, 255, 255, 0.0);
    box-shadow: none;
    transition: border-color 260ms cubic-bezier(0.16, 1, 0.3, 1), background-color 260ms cubic-bezier(0.16, 1, 0.3, 1);
}}
.wp-thumb:hover,
button.wp-thumb:hover {{
    border-color: rgba(255, 255, 255, 0.50);
    background-color: rgba(255, 255, 255, 0.08);
    box-shadow: none;
}}
.wp-thumb.active,
button.wp-thumb.active {{
    border-color: {s1};
    background-color: {hex_to_rgba(s1, 0.18)};
    box-shadow: none;
}}

/* Carousel Arrow Buttons */
.carousel-arrow-btn,
button.carousel-arrow-btn {{
    min-width: 26px;
    min-height: 48px;
    border-radius: 8px;
    background-color: {sec_btn_bg};
    border: 1px solid {sec_btn_border};
    color: {text_primary};
    font-size: 14px;
    font-weight: 700;
    padding: 0;
    margin: 0;
    transition: background-color 220ms cubic-bezier(0.16, 1, 0.3, 1), border-color 220ms cubic-bezier(0.16, 1, 0.3, 1);
}}
.carousel-arrow-btn:hover,
button.carousel-arrow-btn:hover {{
    background-color: rgba(255, 255, 255, 0.22);
    border-color: rgba(255, 255, 255, 0.40);
    color: {text_primary};
}}

/* ComboBox Dropdown Styling (Theme Adaptive) */
combobox {{
    background: transparent;
    background-color: transparent;
    border: none;
    box-shadow: none;
    padding: 0;
}}
combobox button.combo {{
    background-color: {sec_btn_bg};
    border: 1px solid {sec_btn_border};
    border-radius: 10px;
    padding: 4px 12px;
    color: {text_primary};
    font-size: 12.5px;
    font-weight: 500;
    box-shadow: none;
    transition: background-color 150ms ease, border-color 150ms ease;
}}
combobox button.combo:hover {{
    background-color: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.30);
}}
combobox cellview {{
    color: {text_primary};
    background: transparent;
}}
combobox arrow {{
    color: {text_secondary};
    min-width: 14px;
    min-height: 14px;
}}
menu,
.popup menu,
menu.context-menu {{
    background-color: {menu_bg};
    border: 1px solid {menu_border};
    border-radius: 12px;
    padding: 6px;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.65);
}}
menu menuitem {{
    background: transparent;
    color: {menu_item_col};
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12.5px;
}}
menu menuitem:hover {{
    background-color: {s0};
    background-image: {accent_grad};
    color: #ffffff;
    font-weight: 600;
}}

/* Right Panel (Live Preview & Quick Settings) */
#settings-right-panel {{
    background: transparent;
    background-color: transparent;
    border: none;
    padding: 0;
}}

.preview-desktop-screen {{
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    background-color: #000000;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.45);
}}

.preview-window-mockup {{
    background-color: {mockup_bg};
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 8px;
    padding: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.50);
}}

.preview-dock-capsule {{
    background-color: rgba(18, 12, 30, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 6px;
    padding: 2px 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.40);
}}

/* Action Button */
.action-btn,
button.action-btn,
button.action-btn:hover,
button.action-btn:focus {{
    background-color: {s0};
    background-image: {accent_grad};
    color: #ffffff;
    border-radius: 10px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
    box-shadow: 0 3px 12px {hex_to_rgba(s0, 0.35)};
    transition: all 150ms ease;
}}
.action-btn:hover {{
    box-shadow: 0 5px 18px {hex_to_rgba(s0, 0.55)};
}}

.secondary-btn {{
    background-color: {sec_btn_bg};
    border: 1px solid {sec_btn_border};
    color: {text_primary};
    border-radius: 10px;
    padding: 7px 16px;
    font-size: 12.5px;
    transition: all 150ms ease;
}}
.secondary-btn:hover {{
    background-color: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.25);
}}

/* Auto Accent Button & Accent Color Circles (Zero Hover Shaking / Reflow) */
.color-auto-btn,
button.color-auto-btn,
button.color-auto-btn:focus,
button.color-auto-btn:active {{
    min-height: 24px;
    min-width: 52px;
    padding: 0 10px;
    margin: 0 4px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    color: {text_primary};
    background-color: {sec_btn_bg};
    border: 2px solid transparent;
    box-shadow: none;
    transition: border-color 150ms ease, background-color 150ms ease;
}}
.color-auto-btn:hover,
button.color-auto-btn:hover {{
    background-color: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.50);
    box-shadow: none;
}}
.color-auto-btn.active,
button.color-auto-btn.active,
button.color-auto-btn.active:hover {{
    background: {accent_grad};
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.50);
    box-shadow: none;
}}

.color-circle,
button.color-circle,
button.color-circle:hover,
button.color-circle:focus,
button.color-circle:active {{
    min-width: 24px;
    min-height: 24px;
    border-radius: 12px;
    padding: 0;
    margin: 0 4px;
    border: 2px solid transparent;
    box-shadow: none;
    transition: border-color 150ms ease;
}}
.color-circle:hover,
button.color-circle:hover {{
    border-color: rgba(255, 255, 255, 0.50);
    box-shadow: none;
}}
.color-circle.active,
button.color-circle.active,
button.color-circle.active:hover {{
    border-color: rgba(255, 255, 255, 0.50);
    box-shadow: none;
}}

.color-circle.col-a855f7, button.color-circle.col-a855f7 {{ background-color: #a855f7; }}
.color-circle.col-3b82f6, button.color-circle.col-3b82f6 {{ background-color: #3b82f6; }}
.color-circle.col-06b6d4, button.color-circle.col-06b6d4 {{ background-color: #06b6d4; }}
.color-circle.col-10b981, button.color-circle.col-10b981 {{ background-color: #10b981; }}
.color-circle.col-ec4899, button.color-circle.col-ec4899 {{ background-color: #ec4899; }}

/* Invisible Scrollbar */
scrollbar,
scrollbar trough,
scrollbar slider {{
    opacity: 0;
    min-width: 0;
    min-height: 0;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
    background-color: transparent;
}}

/* Remove edge overshoot & undershoot indicators */
scrolledwindow overshoot,
scrolledwindow overshoot.left,
scrolledwindow overshoot.right,
scrolledwindow overshoot.top,
scrolledwindow overshoot.bottom,
scrolledwindow undershoot,
scrolledwindow undershoot.left,
scrolledwindow undershoot.right,
scrolledwindow undershoot.top,
scrolledwindow undershoot.bottom,
overshoot,
overshoot.left,
overshoot.right,
overshoot.top,
overshoot.bottom,
undershoot,
undershoot.left,
undershoot.right,
undershoot.top,
undershoot.bottom {{
    background: none;
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    -gtk-icon-shadow: none;
}}
"""

def sync_topbar_theme_files(wallpaper_path=None, reload_services=False, fallback_palette=None, palette_style=None, accent_color=None):
    """Extract wallpaper theme and update Waybar, workspace slider, chevron, drawer, hyprland borders, kitty cursor, and dunst."""
    pal = fallback_palette if fallback_palette is not None else load_palette()
    wp = wallpaper_path or detect_active_wallpaper(pal.get("wallpaper"))
    dt = extract_wallpaper_theme(wp, pal, palette_style=palette_style, accent_color=accent_color)
    
    try:
        from shared import config
        cfg = config.load_settings()
        active_t_mode = cfg.get("theme_mode", "Dark")
        active_trans = cfg.get("transparency", cfg.get("transparency_blur", 70))
        active_blur = cfg.get("blur_strength", cfg.get("transparency_blur", 70))
        if active_t_mode not in ("Light", "Dark"):
            active_t_mode = "Dark"
    except Exception:
        active_t_mode = "Dark"
        active_trans = 70
        active_blur = 70

    colors = derive_topbar_colors(dt, theme_mode=active_t_mode)

    slider_changed = _write_if_changed(SLIDER_COLORS_FILE, build_slider_colors_text(colors))
    waybar_changed = _write_if_changed(WAYBAR_CSS_FILE, build_waybar_css(colors))
    _write_if_changed(WAYBAR_CHEVRON_SVG, build_chevron_svg(colors))
    _write_if_changed(NWGDRAWER_CSS_FILE, build_drawer_css(colors))
    _write_if_changed(DRAWER_CSS_FILE, build_neon_drawer_css(dt, colors, theme_mode=active_t_mode, transparency=active_trans, blur_strength=active_blur))
    _write_if_changed(DRUN_CSS_FILE, build_neon_drun_css(dt, colors, transparency=active_trans, blur_strength=active_blur))
    _write_if_changed(SETTINGS_CSS_FILE, build_neon_settings_css(dt, colors, theme_mode=active_t_mode, transparency=active_trans, blur_strength=active_blur))

    # Update drawer and drun theme json
    drawer_theme_data = {
        "wallpaper": wp,
        "base_rgb": dt.get("base_rgb", (18, 12, 30)),
        "stops": dt.get("stops", []),
        "accent_primary": colors.get("accent_mid", "#a855f7"),
        "accent_secondary": colors.get("accent_bright", "#ec4899"),
        "text_primary": colors.get("text_primary", "#ffffff"),
        "text_soft": colors.get("text_soft", "rgba(255, 255, 255, 0.6)"),
    }
    _write_if_changed(DRAWER_THEME_FILE, json.dumps(drawer_theme_data, indent=2))
    _write_if_changed(DRUN_THEME_FILE, json.dumps(drawer_theme_data, indent=2))

    # Update Hyprland window borders
    try:
        from shared import config
        frame_accent = config.load_settings().get("color_frame_to_accent", True)
    except Exception:
        frame_accent = True

    if frame_accent:
        update_hypr_border(dt.get("stops", []), reload=False)
    else:
        try:
            from shared import system
            system.update_hypr_config(active_border="rgba(555555ee) rgba(333333ee) 45deg", reload=False)
        except Exception:
            pass

    # Update Kitty text cursor
    cursor_color = dt.get("stops", ["#A855F7"])[1] if len(dt.get("stops", [])) > 1 else "#A855F7"
    update_kitty_cursor(cursor_color)

    dunst_changed = False
    if os.path.isfile(DUNST_RC_FILE):
        try:
            with open(DUNST_RC_FILE, "r", encoding="utf-8") as f:
                orig_dunst = f.read()
            new_dunst = _update_dunstrc_text(orig_dunst, colors)
            dunst_changed = _write_if_changed(DUNST_RC_FILE, new_dunst)
        except Exception:
            pass

    if reload_services:
        if waybar_changed or slider_changed:
            try:
                subprocess.Popen(
                    ["systemctl", "--user", "reload", "waybar"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass
        if dunst_changed:
            try:
                subprocess.Popen(
                    ["dunstctl", "reload"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    return dt, colors

if __name__ == "__main__":
    p = update_theme()
    print("Theme updated successfully with wallpaper:", p.get("wallpaper"))
    print("Primary accent:", p.get("accent_primary"))
    print("Secondary accent:", p.get("accent_secondary"))

