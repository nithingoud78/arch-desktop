#!/usr/bin/env python3
"""
Neon Desktop — Shared Theme Engine
Dynamic palette extraction from wallpapers, color system, and CSS generation.
"""

import os
import re
import json
import colorsys
import subprocess
from pathlib import Path
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
PALETTE_FILE = os.path.join(CONFIG_DIR, "palette.json")
THEME_CSS_FILE = os.path.join(CONFIG_DIR, "theme.css")
SLIDER_COLORS_FILE = os.path.join(CONFIG_DIR, "topbar_slider_colors")
WAYBAR_CSS_FILE = os.path.expanduser("~/.config/waybar/macos.css")
WAYBAR_CHEVRON_SVG = os.path.expanduser("~/.config/waybar/chevron.svg")
DUNST_RC_FILE = os.path.expanduser("~/.config/dunst/dunstrc")
NWGDRAWER_CSS_FILE = os.path.expanduser("~/.config/nwg-drawer/drawer.css")
DEFAULT_WALLPAPER = "/home/nithin/Pictures/Wallpapers/Alpenglow Over Misty Mountain Peaks.png"

def to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

def to_rgba(rgb, a):
    return "rgba({}, {}, {}, {:.2f})".format(int(rgb[0]), int(rgb[1]), int(rgb[2]), a)

def clamp(val, low=0, high=255):
    return max(low, min(high, int(val)))

def extract_palette(image_path=None):
    """Extract a rich harmonious palette from an image file using GdkPixbuf."""
    if not image_path or not os.path.isfile(image_path):
        image_path = DEFAULT_WALLPAPER
        if not os.path.isfile(image_path):
            return get_default_palette()

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
    """Full update pipeline: extract, save, generate CSS."""
    pal = extract_palette(image_path)
    save_palette(pal)
    generate_css(pal)
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

def extract_wallpaper_theme(wallpaper_path, fallback_palette=None):
    """Extract harmonious dark-glass base and 5 vivid neon stops matching neon-dock."""
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
    return result

def derive_topbar_colors(wp_theme):
    """Derive harmonious dark glass & vivid contrast-safe accent tokens for Waybar and Control Center."""
    br, bg, bb = wp_theme.get("base_rgb", (13, 12, 20))
    stops = wp_theme.get("stops") or ["#ff8a00", "#ec4899", "#d946ef", "#9333ea", "#7c3aed"]
    s0, s1, s2, s3, s4 = (stops + [stops[-1]] * 5)[:5]

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
    text_soft = lighten_hex(s2, 0.95)
    soft_rgb = _hex_to_rgb(text_soft, (245, 248, 255))

    return {
        "s0": s0, "s1": s1, "s2": s2, "s3": s3, "s4": s4,
        "base_rgb": (br, bg, bb),
        "bar_bg_l": to_rgba(bar_l_rgb, 0.76),
        "bar_bg_c": to_rgba(bar_c_rgb, 0.76),
        "bar_bg_r": to_rgba(bar_r_rgb, 0.76),
        "bar_border": hex_to_rgba(accent_text, 0.24),
        "ws_bg": to_rgba(ws_rgb, 0.66),
        "ws_border": hex_to_rgba(accent_text, 0.26),
        "ws_inactive": to_rgba(soft_rgb, 0.76),
        "popup_bg": to_rgba(popup_rgb, 0.95),
        "popup_border": hex_to_rgba(accent_text, 0.30),
        "cc_bg": to_rgba(cc_rgb, 0.92),
        "cc_power_bg": to_rgba(popup_rgb, 0.92),
        "cc_pwd_bg": to_rgba(popup_rgb, 0.95),
        "cc_border": hex_to_rgba(accent_text, 0.26),
        "cc_pwd_border": hex_to_rgba(accent_text, 0.42),
        "cc_glow": hex_to_rgba(s2, 0.18),
        "drawer_bg": to_rgba(drawer_rgb, 0.85),
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
        "text_primary": "#FDFBFE",
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

def sync_topbar_theme_files(wallpaper_path=None, reload_services=True, fallback_palette=None):
    """Extract wallpaper theme and update Waybar CSS, workspace slider colors, chevron SVG, drawer CSS, and dunst."""
    pal = fallback_palette if fallback_palette is not None else load_palette()
    wp = wallpaper_path or detect_active_wallpaper(pal.get("wallpaper"))
    dt = extract_wallpaper_theme(wp, pal)
    colors = derive_topbar_colors(dt)

    slider_changed = _write_if_changed(SLIDER_COLORS_FILE, build_slider_colors_text(colors))
    waybar_changed = _write_if_changed(WAYBAR_CSS_FILE, build_waybar_css(colors))
    _write_if_changed(WAYBAR_CHEVRON_SVG, build_chevron_svg(colors))
    _write_if_changed(NWGDRAWER_CSS_FILE, build_drawer_css(colors))

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

