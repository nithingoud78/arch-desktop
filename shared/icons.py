#!/usr/bin/env python3
"""
Neon Desktop — Outlined Lucide-Style SVG Icons
Renders high-quality vector icons directly into GdkPixbuf and Gtk.Image.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf

ICONS = {
    "grid": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <circle cx="4" cy="4" r="1.5" fill="currentColor"/>
  <circle cx="12" cy="4" r="1.5" fill="currentColor"/>
  <circle cx="20" cy="4" r="1.5" fill="currentColor"/>
  <circle cx="4" cy="12" r="1.5" fill="currentColor"/>
  <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
  <circle cx="20" cy="12" r="1.5" fill="currentColor"/>
  <circle cx="4" cy="20" r="1.5" fill="currentColor"/>
  <circle cx="12" cy="20" r="1.5" fill="currentColor"/>
  <circle cx="20" cy="20" r="1.5" fill="currentColor"/>
</svg>""",

    "notes": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
  <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
  <line x1="9" y1="12" x2="15" y2="12"/>
  <line x1="9" y1="16" x2="13" y2="16"/>
</svg>""",

    "search": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="7"/>
  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
</svg>""",

    "aperture": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="14.31" y1="8" x2="20.05" y2="17.94"/>
  <line x1="9.69" y1="8" x2="21.17" y2="8"/>
  <line x1="7.38" y1="12" x2="13.12" y2="2.06"/>
  <line x1="9.69" y1="16" x2="3.95" y2="6.06"/>
  <line x1="14.31" y1="16" x2="2.83" y2="16"/>
  <line x1="16.62" y1="12" x2="10.88" y2="21.94"/>
</svg>""",

    "gauge": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="m12 14 4-4"/>
  <path d="M3.34 19a10 10 0 1 1 17.32 0"/>
</svg>""",

    "lightning": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>
</svg>""",

    "leaf": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>
  <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>
</svg>""",

    "moon": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
</svg>""",

    "scale": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>
  <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>
  <path d="M7 21h10"/>
  <path d="M12 3v18"/>
  <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>
</svg>""",

    "rocket": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>
  <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>
  <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>
  <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
</svg>""",

    "music": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9 18V5l12-2v13"/>
  <circle cx="6" cy="18" r="3"/>
  <circle cx="18" cy="16" r="3"/>
</svg>""",

    "youtube": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
</svg>""",

    "settings": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>""",

    "cpu": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <rect width="16" height="16" x="4" y="4" rx="2"/>
  <rect width="6" height="6" x="9" y="9" rx="1"/>
  <path d="M15 2v2"/>
  <path d="M15 20v2"/>
  <path d="M2 15h2"/>
  <path d="M2 9h2"/>
  <path d="M20 15h2"/>
  <path d="M20 9h2"/>
  <path d="M9 2v2"/>
  <path d="M9 20v2"/>
</svg>""",

    "battery": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <rect width="16" height="10" x="2" y="7" rx="2" ry="2"/>
  <line x1="22" x2="22" y1="11" y2="13"/>
</svg>""",

    "battery-charging": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 7h2a2 2 0 0 1 2 2v6c0 1-1 2-2 2h-2"/>
  <path d="M6 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/>
  <line x1="22" x2="22" y1="11" y2="13"/>
  <path d="m11 7-3 5h4l-1 5 4-6h-4l2-4z" fill="currentColor"/>
</svg>""",

    "wifi": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.0" stroke-linecap="round" stroke-linejoin="round" opacity="1">
  <circle cx="12" cy="19.5" r="1.2" fill="currentColor" stroke="none" opacity="1"/>
  <path d="M2 8.82a15 15 0 0 1 20 0" opacity="1"/>
  <path d="M5 12.86a10 10 0 0 1 14 0" opacity="1"/>
  <path d="M8.5 16.43a5 5 0 0 1 7 0" opacity="1"/>
</svg>""",

    "volume-high": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" opacity="1">
  <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" opacity="1"/>
  <path d="M15.54 8.46a5 5 0 0 1 0 7.07" opacity="1"/>
  <path d="M19.07 4.93a10 10 0 0 1 0 14.14" opacity="1"/>
</svg>""",

    "volume-low": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" opacity="1">
  <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" opacity="1"/>
  <path d="M15.54 8.46a5 5 0 0 1 0 7.07" opacity="1"/>
</svg>""",

    "volume-muted": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" opacity="1">
  <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" opacity="1"/>
  <line x1="22" x2="16" y1="9" y2="15" opacity="1"/>
  <line x1="16" x2="22" y1="9" y2="15" opacity="1"/>
</svg>""",

    "bell": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
  <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
</svg>""",

    "notification-panel": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" opacity="1">
  <rect x="3" y="3" width="18" height="18" rx="2.5" opacity="1"/>
  <line x1="15" y1="3" x2="15" y2="21" opacity="1"/>
</svg>""",

    "arch": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 256 256">
  <path d="m127.98 12.07c-10.316 25.309-16.543 41.855-28.031 66.41 7.043 7.4609 15.691 16.156 29.734 25.977-15.098-6.207-25.395-12.445-33.094-18.918-14.703 30.68-37.742 74.391-84.492 158.39 36.746-21.219 65.23-34.293 91.773-39.289-1.1406-4.8945-1.7852-10.195-1.7422-15.734l0.042969-1.1719c0.58203-23.551 12.828-41.645 27.336-40.418 14.508 1.2266 25.781 21.316 25.199 44.867-0.10938 4.4219-0.60938 8.6914-1.4805 12.641 26.258 5.1328 54.438 18.18 90.684 39.105-7.1484-13.156-13.527-25.016-19.621-36.316-9.5938-7.4336-19.605-17.117-40.023-27.594 14.035 3.6406 24.082 7.8516 31.914 12.555-61.941-115.32-66.957-130.66-88.199-180.5z" fill="currentColor" fill-rule="evenodd"/>
</svg>""",

    "prev": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
  <polygon points="19 20 9 12 19 4 19 20"/>
  <line x1="5" y1="19" x2="5" y2="5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
</svg>""",

    "next": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
  <polygon points="5 4 15 12 5 20 5 4"/>
  <line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
</svg>""",

    "play": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
  <polygon points="6 3 20 12 6 21 6 3"/>
</svg>""",

    "pause": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
  <rect x="6" y="4" width="4" height="16" rx="1"/>
  <rect x="14" y="4" width="4" height="16" rx="1"/>
</svg>"""
}

_GICON_CACHE = {}

def get_render_scale():
    """Return HiDPI rasterization scale matching the Wayland display (minimum 2x for crisp edges)."""
    try:
        disp = Gdk.Display.get_default()
        if disp is not None:
            mon = disp.get_primary_monitor() or (disp.get_monitor(0) if disp.get_n_monitors() > 0 else None)
            if mon is not None:
                return max(2, int(mon.get_scale_factor()))
    except Exception:
        pass
    return 2

def get_pixbuf(name, size=16, color="#ffffff", scale=1):
    svg_template = ICONS.get(name)
    if not svg_template:
        return None
    s = svg_template.replace("currentColor", color)
    px = max(1, int(round(size * scale)))
    loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
    loader.set_size(px, px)
    loader.write(s.encode("utf-8"))
    loader.close()
    return loader.get_pixbuf()

def get_gicon(name, color="#ffffff"):
    key = (name, color)
    cached = _GICON_CACHE.get(key)
    if cached is not None:
        return cached
    svg_template = ICONS.get(name)
    if not svg_template:
        return None
    svg_bytes = svg_template.replace("currentColor", color).encode("utf-8")
    gicon = Gio.BytesIcon.new(GLib.Bytes.new(svg_bytes))
    _GICON_CACHE[key] = gicon
    return gicon

def _build_battery_svg(pct, is_charging=False, is_plugged=False):
    pct = max(0, min(100, int(pct)))
    if is_plugged:
        color = '#ef4444' if pct < 10 else ('#f59e0b' if pct < 30 else '#38bdf8')
    else:
        color = '#ef4444' if pct < 10 else ('#f59e0b' if pct < 30 else '#ffffff')

    fill_w = max(1.5, min(13.0, 13.0 * (pct / 100.0)))
    bolt = ""
    if is_charging or is_plugged:
        bolt = f'''<polygon points="10.8,3.8 6.5,11.6 10.2,11.6 8.8,18.2 14.5,10.0 10.8,10.0" fill="#ffffff" stroke="#090a14" stroke-width="0.9" stroke-linejoin="round" opacity="1"/>'''

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
      <rect x="1.5" y="6" width="17.5" height="12" rx="2.6" ry="2.6" fill="none" stroke="#ffffff" stroke-width="1.65" opacity="1"/>
      <rect x="20" y="9.5" width="2" height="5" rx="1" ry="1" fill="#ffffff" opacity="1"/>
      <rect x="3.8" y="8.2" width="{fill_w:.1f}" height="7.6" rx="1.2" ry="1.2" fill="{color}" opacity="1"/>
      {bolt}
    </svg>"""
    return svg, color

def get_battery_pixbuf(pct, is_charging=False, is_plugged=False, width=22, height=14, scale=1):
    """
    Renders dynamic proportional horizontal battery SVG fill and state.
    """
    svg, color = _build_battery_svg(pct, is_charging=is_charging, is_plugged=is_plugged)
    loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
    loader.set_size(max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    loader.write(svg.encode("utf-8"))
    loader.close()
    return loader.get_pixbuf(), color

def get_battery_gicon(pct, is_charging=False, is_plugged=False):
    svg, color = _build_battery_svg(pct, is_charging=is_charging, is_plugged=is_plugged)
    gicon = Gio.BytesIcon.new(GLib.Bytes.new(svg.encode("utf-8")))
    return gicon, color

def set_battery_icon(img_widget, pct, is_charging=False, is_plugged=False, size=22):
    gicon, color = get_battery_gicon(pct, is_charging=is_charging, is_plugged=is_plugged)
    img_widget.set_from_gicon(gicon, Gtk.IconSize.BUTTON)
    img_widget.set_pixel_size(size)
    return color

def set_image_icon(img_widget, name, size=16, color="#ffffff"):
    gicon = get_gicon(name, color=color)
    if gicon is not None:
        img_widget.set_from_gicon(gicon, Gtk.IconSize.BUTTON)
        img_widget.set_pixel_size(size)
        return True
    return False

def get_image(name, size=16, color="#ffffff"):
    gicon = get_gicon(name, color=color)
    if gicon is not None:
        img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.BUTTON)
        img.set_pixel_size(size)
        return img
    img = Gtk.Image()
    img.set_from_icon_name("application-x-executable", Gtk.IconSize.SMALL_TOOLBAR)
    img.set_pixel_size(size)
    return img

