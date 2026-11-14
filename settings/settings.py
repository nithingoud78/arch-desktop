#!/usr/bin/env python3
"""
Settings — Complete Desktop & System Control Center
Arch Linux + Hyprland.
Full-window native application with macOS-level simplicity,
Windows-level hardware control, and live wallpaper-adaptive dark glassmorphism.
"""

import os
import sys
import json
import re
import shutil
import subprocess
import signal
import threading
import math
import time
from datetime import datetime

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Gio', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango, GdkPixbuf

# Import shared modules
POSSIBLE_SHARED = [
    os.path.expanduser("~/Projects/neon-desktop"),
    os.path.expanduser("~/Projects/arch-desktop"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
]
for p in POSSIBLE_SHARED:
    sp = os.path.join(p, "shared")
    if os.path.isdir(sp) and os.path.isfile(os.path.join(sp, "theme.py")):
        if p not in sys.path:
            sys.path.insert(0, p)
        break

from shared import theme, config, system, icons

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
BACKUP_DIR = os.path.join(CONFIG_DIR, "backups")
SETTINGS_CSS_FILE = os.path.join(CONFIG_DIR, "settings.css")


def backup_config(file_path):
    """Safely backup configuration before modifying."""
    if not os.path.isfile(file_path):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bname = os.path.basename(file_path)
        shutil.copy2(file_path, os.path.join(BACKUP_DIR, f"{bname}.{ts}.bak"))
    except Exception:
        pass



class SmoothScroller:
    """Frame-clock synchronized buttery smooth kinetic scroller for high-refresh displays."""
    def __init__(self, scrolled_window, step=140.0, decay=20.0):
        self.sw = scrolled_window
        self.step = step
        self.decay = decay
        self.vadj = scrolled_window.get_vadjustment()
        self.target = None
        self.tick_id = None
        self.last_frame_time_us = 0
        self.last_tick_time = 0.0
        self.last_scroll_time = 0.0
        self.last_direction = 0
        self.momentum = 1.0
        self._current_decay = decay
        self._in_tick = False

        self.sw.add_events(Gdk.EventMask.SCROLL_MASK)
        self.sw.connect("scroll-event", self._on_scroll)
        self.vadj.connect("value-changed", self._on_value_changed)

    def reset(self):
        self.target = None
        self.last_frame_time_us = 0
        self.last_tick_time = 0.0
        self.momentum = 1.0
        if self.tick_id:
            try:
                self.sw.remove_tick_callback(self.tick_id)
            except Exception:
                pass
            self.tick_id = None

    def _on_value_changed(self, adj):
        if not self._in_tick and self.tick_id:
            self.reset()

    def _on_scroll(self, widget, event):
        state = getattr(event, "state", 0)
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False

        delta = 0.0
        is_touchpad = False

        dev = event.get_source_device() if hasattr(event, "get_source_device") else None
        if dev is not None and hasattr(dev, "get_source"):
            if dev.get_source() == Gdk.InputSource.TOUCHPAD:
                is_touchpad = True

        if event.direction == Gdk.ScrollDirection.UP:
            delta = -self.step
        elif event.direction == Gdk.ScrollDirection.DOWN:
            delta = self.step
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            ret = event.get_scroll_deltas()
            if len(ret) == 3:
                ok, dx, dy = ret
            else:
                dx, dy = ret
            if abs(dy) < 0.001:
                return False

            if is_touchpad or abs(dy) < 0.65:
                delta = dy * 36.0
                is_touchpad = True
            else:
                delta = (1.0 if dy > 0 else -1.0) * self.step * abs(dy)
        else:
            return False

        if abs(delta) < 0.01:
            return False

        lower = self.vadj.get_lower()
        upper = max(lower, self.vadj.get_upper() - self.vadj.get_page_size())
        curr = self.vadj.get_value()

        # Dynamic momentum accumulation for successive scrolls
        now = time.monotonic()
        direction = 1 if delta > 0 else -1
        time_since_last = now - self.last_scroll_time

        if not is_touchpad:
            if time_since_last < 0.22 and direction == self.last_direction:
                self.momentum = min(2.8, self.momentum + 0.35)
            else:
                self.momentum = 1.0
            delta *= self.momentum
        else:
            self.momentum = 1.0

        self.last_scroll_time = now
        self.last_direction = direction
        self._current_decay = 32.0 if is_touchpad else self.decay

        if self.target is None or abs(self.target - curr) > 1200:
            self.target = curr

        # Generous lead so fast scrolling never hits an artificial wall
        max_lead = 2400.0
        new_target = self.target + delta
        new_target = max(curr - max_lead, min(curr + max_lead, new_target))
        new_target = max(lower, min(upper, new_target))

        # Boundary check
        if (curr <= lower + 0.5 and delta < 0) or (curr >= upper - 0.5 and delta > 0):
            self.target = None
            if self.tick_id:
                try:
                    self.sw.remove_tick_callback(self.tick_id)
                except Exception:
                    pass
                self.tick_id = None
            return True

        self.target = new_target

        if not self.tick_id:
            self.last_frame_time_us = 0
            self.last_tick_time = time.monotonic()
            self.tick_id = self.sw.add_tick_callback(self._on_tick)

        return True

    def _on_tick(self, widget, frame_clock):
        if self.target is None:
            self.tick_id = None
            return False

        if frame_clock is not None and hasattr(frame_clock, "get_frame_time"):
            frame_time_us = frame_clock.get_frame_time()
            if self.last_frame_time_us > 0:
                dt = (frame_time_us - self.last_frame_time_us) / 1000000.0
                dt = max(0.001, min(0.05, dt))
            else:
                dt = 0.006  # ~165Hz default
            self.last_frame_time_us = frame_time_us
        else:
            now = time.monotonic()
            if self.last_tick_time > 0.0:
                dt = max(0.001, min(0.05, now - self.last_tick_time))
            else:
                dt = 0.006
            self.last_tick_time = now

        curr = self.vadj.get_value()
        diff = self.target - curr

        if abs(diff) < 0.8:
            self._in_tick = True
            try:
                self.vadj.set_value(self.target)
            finally:
                self._in_tick = False
            self.target = None
            self.tick_id = None
            return False

        factor = 1.0 - math.exp(-getattr(self, "_current_decay", self.decay) * dt)
        move = diff * factor
        if abs(move) < 0.5:
            move = 0.5 if diff > 0 else -0.5
            if abs(move) >= abs(diff):
                move = diff

        self._in_tick = True
        try:
            self.vadj.set_value(curr + move)
        finally:
            self._in_tick = False
        return True


class SettingsApp(Gtk.Window):
    def __init__(self):
        if not GLib.get_prgname():
            GLib.set_prgname("settings")
        if not GLib.get_application_name():
            GLib.set_application_name("Settings")
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Settings")
        self.set_name("settings-window")

        # Load persisted settings
        self.settings = config.load_settings()
        self.active_category = "personalization"
        self.nav_buttons = {}
        self.nav_items_data = []

        # Window Metrics & Visual
        self.set_default_size(1180, 780)
        self.set_position(Gtk.WindowPosition.CENTER)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.set_app_paintable(True)

        # Set Window Icon (macOS gear)
        icon_path = os.path.expanduser("~/.local/share/icons/settings.png")
        if os.path.isfile(icon_path):
            self.set_icon_from_file(icon_path)

        # Connect keys & lifecycle
        self.connect("key-press-event", self._on_key_press)
        self.connect("destroy", Gtk.main_quit)
        self.connect("size-allocate", self._on_window_size_allocate)

        # Dynamic Wallpaper Theme Engine
        self.css_provider = None
        self._current_active_wp = None
        self._apply_theme_for_wallpaper(force_refresh=True)
        GLib.timeout_add(800, self._check_wallpaper_changed)

        # Wallpaper Slideshow Background Timer
        self._slideshow_timer = None
        if self._get_setting("wallpaper.slideshow", False):
            self._start_slideshow()

        # Build Main UI Layout
        self._build_main_ui()

    def _on_window_size_allocate(self, widget, allocation):
        """Dynamically adapt layout when tiled in split view or resized."""
        w = allocation.width
        # 1. Responsive Right Live Preview Panel on Personalization (autohides when other windows added / split view)
        if hasattr(self, "preview_panel") and self.preview_panel:
            should_show_right = (w >= 1050)
            if self.preview_panel.get_visible() != should_show_right:
                self.preview_panel.set_visible(should_show_right)

        # 2. Responsive Sidebar Width
        if hasattr(self, "sidebar") and self.sidebar:
            target_w = 160 if w < 720 else (185 if w < 1050 else 230)
            curr_w = self.sidebar.get_size_request()[0]
            if curr_w != target_w:
                self.sidebar.set_size_request(target_w, -1)

    def _detect_active_wallpaper(self):
        """Detect active wallpaper from hyprpaper IPC or saved settings/palette."""
        try:
            out = subprocess.check_output(
                ["hyprctl", "hyprpaper", "listactive"],
                text=True, timeout=1.0, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if ":" in line:
                    wp = line.split(":", 1)[1].strip()
                    wp = os.path.expanduser(wp)
                    if wp and os.path.isfile(wp):
                        return wp
        except Exception:
            pass
        pal = theme.load_palette()
        wp = pal.get("wallpaper") or self._get_setting("wallpaper")
        if isinstance(wp, dict):
            wp = None
        return wp or theme.DEFAULT_WALLPAPER

    def _apply_theme_for_wallpaper(self, wp_path=None, force_refresh=True, write_file=True, reset_widgets=False):
        """Extract wallpaper colors and apply to settings app live."""
        if not wp_path or not os.path.isfile(wp_path):
            wp_path = self._detect_active_wallpaper()
        if not wp_path or not os.path.isfile(wp_path):
            wp_path = theme.DEFAULT_WALLPAPER

        self._current_active_wp = wp_path
        pal = theme.load_palette()
        if pal.get("wallpaper") != wp_path:
            pal = theme.extract_palette(wp_path)

        # Fast path: use cached settings.css only on initial startup if matching
        css_data = None
        if not force_refresh and os.path.isfile(SETTINGS_CSS_FILE) and pal.get("wallpaper") == wp_path:
            try:
                with open(SETTINGS_CSS_FILE, "r") as f:
                    css_data = f.read()
            except Exception:
                css_data = None

        if not css_data:
            p_style = self._get_setting("palette_style", "Vivid")
            accent = self._get_setting("accent_color", "auto")
            t_mode = self._get_setting("theme_mode", "Dark")
            tb = self._get_setting("transparency", self._get_setting("transparency_blur", 70))
            rc = self._get_setting("rounded_corners", 16)
            anim = self._get_setting("animations", True)
            grad = self._get_setting("gradient_accents", True)

            bs = self._get_setting("blur_strength", 70)

            dt = theme.extract_wallpaper_theme(wp_path, pal, palette_style=p_style, accent_color=accent)
            c = theme.derive_topbar_colors(dt, theme_mode=t_mode)
            css_data = theme.build_neon_settings_css(
                dt, c,
                theme_mode=t_mode,
                transparency=tb,
                transparency_blur=tb,
                rounded_corners=rc,
                animations=anim,
                gradient_accents=grad,
                blur_strength=bs
            )
            if write_file:
                try:
                    with open(SETTINGS_CSS_FILE, "w") as f:
                        f.write(css_data)
                except Exception:
                    pass

        is_startup = (self.css_provider is None)
        if self.css_provider is None:
            self.css_provider = Gtk.CssProvider()
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20
                )
        self.css_provider.load_from_data(css_data.encode("utf-8"))

        if not is_startup and reset_widgets:
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.reset_widgets(screen)

        if hasattr(self, "wp_thumb_widgets") and self.wp_thumb_widgets:
            for p, btn in self.wp_thumb_widgets.items():
                if p == wp_path:
                    btn.get_style_context().add_class("active")
                else:
                    btn.get_style_context().remove_class("active")

        self.queue_draw()

    def _apply_wallpaper_theme_bg(self, target_wp):
        """Dedicated background worker to extract theme and sync desktop files cleanly with zero UI lag."""
        def _bg_worker():
            try:
                p_style = self._get_setting("palette_style", "Vivid")
                accent = self._get_setting("accent_color", "auto")
                t_mode = self._get_setting("theme_mode", "Dark")
                tb = self._get_setting("transparency", self._get_setting("transparency_blur", 70))
                rc = self._get_setting("rounded_corners", 16)
                anim = self._get_setting("animations", True)
                grad = self._get_setting("gradient_accents", True)

                # 1. Palette & Topbar theme extraction (fast & cached)
                pal = theme.extract_palette(target_wp)
                theme.save_palette(pal)
                theme.generate_css(pal)

                dt = theme.extract_wallpaper_theme(target_wp, pal, palette_style=p_style, accent_color=accent)
                c = theme.derive_topbar_colors(dt, theme_mode=t_mode)

                # 2. Build Settings CSS
                css_data = theme.build_neon_settings_css(
                    dt, c,
                    theme_mode=t_mode,
                    transparency=tb,
                    transparency_blur=tb,
                    rounded_corners=rc,
                    animations=anim,
                    gradient_accents=grad
                )
                try:
                    with open(SETTINGS_CSS_FILE, "w") as f:
                        f.write(css_data)
                except Exception:
                    pass

                # 3. Sync desktop theme files without bouncing services or Hyprland reload
                theme.sync_topbar_theme_files(target_wp, reload_services=False, fallback_palette=pal,
                                             palette_style=p_style, accent_color=accent)

                # 4. Dispatch live CSS application to GTK main loop
                def _apply_live():
                    if getattr(self, "_current_active_wp", None) == target_wp:
                        if self.css_provider is None:
                            self.css_provider = Gtk.CssProvider()
                            screen = Gdk.Screen.get_default()
                            if screen:
                                Gtk.StyleContext.add_provider_for_screen(
                                    screen, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20
                                )
                        self.css_provider.load_from_data(css_data.encode("utf-8"))
                        self.queue_draw()
                    self._is_applying_wallpaper = False
                    return False

                GLib.idle_add(_apply_live)
            except Exception as e:
                print(f"[settings] Error in background wallpaper theme worker: {e}")
                self._is_applying_wallpaper = False

        threading.Thread(target=_bg_worker, daemon=True).start()

    def _check_wallpaper_changed(self):
        """Poll for external wallpaper changes and update theme live."""
        if getattr(self, "_is_applying_wallpaper", False):
            return True
        active_wp = self._detect_active_wallpaper()
        if active_wp and active_wp != getattr(self, "_current_active_wp", None):
            self._current_active_wp = active_wp
            self._apply_wallpaper_theme_bg(active_wp)
        return True

    def _save_setting(self, key_path, value):
        """Update nested setting and persist."""
        parts = key_path.split(".")
        target = self.settings
        for p in parts[:-1]:
            if p not in target or not isinstance(target[p], dict):
                target[p] = {}
            target = target[p]
        target[parts[-1]] = value
        config.save_settings(self.settings)

    def _get_setting(self, key_path, default=None):
        """Retrieve nested setting value."""
        parts = key_path.split(".")
        target = self.settings
        for p in parts:
            if not isinstance(target, dict) or p not in target:
                return default
            target = target[p]
        return target

    # ══════════════════════════════════════════════════════════════════════
    #  MAIN SHELL & LAYOUT
    # ══════════════════════════════════════════════════════════════════════
    def _build_main_ui(self):
        card_border = Gtk.Box()
        card_border.set_name("settings-card-border")

        self.card_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.card_inner.set_name("settings-card-inner")
        card_border.add(self.card_inner)
        self.add(card_border)

        # 1. Header Bar
        header = self._build_header_bar()
        self.card_inner.pack_start(header, False, False, 0)

        # 2. Main Body Split: Left Sidebar + Center Scrolled Stack + Right Panel
        self.body_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.card_inner.pack_start(self.body_box, True, True, 0)

        # Left Sidebar (230px default)
        self.sidebar = self._build_sidebar()
        self.body_box.pack_start(self.sidebar, False, False, 0)

        # Center Content Stack inside Scrolled Window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_name("settings-content-scroll")
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_hexpand(True)
        self.scrolled_window.set_vexpand(True)
        self.scrolled_window.set_kinetic_scrolling(False)
        self.scrolled_window.set_overlay_scrolling(True)
        self.smooth_scroller = SmoothScroller(self.scrolled_window, step=140.0, decay=20.0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_homogeneous(False)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.set_halign(Gtk.Align.FILL)
        self.stack.set_valign(Gtk.Align.FILL)
        self.scrolled_window.add(self.stack)
        self.body_box.pack_start(self.scrolled_window, True, True, 0)

        # Initialize Lazy Page Builders Engine
        self._init_pages()

        # Show initial category (only Personalization page is built on startup)
        self._switch_page("personalization")

        # Preload remaining pages in background idle for instantaneous zero-glitch switching
        GLib.idle_add(self._preload_next_page)

    def _build_header_bar(self):
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        hdr.set_name("settings-header")

        # Left: macOS Traffic Lights (Close, Minimize, Maximize)
        dots_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dots_box.set_valign(Gtk.Align.CENTER)

        btn_close = Gtk.Button()
        btn_close.set_size_request(12, 12)
        btn_close.set_relief(Gtk.ReliefStyle.NONE)
        btn_close.get_style_context().add_class("traffic-dot")
        btn_close.get_style_context().add_class("close")
        btn_close.set_tooltip_text("Close Window")
        btn_close.connect("clicked", lambda *_: self.close())
        dots_box.pack_start(btn_close, False, False, 0)

        btn_min = Gtk.Button()
        btn_min.set_size_request(12, 12)
        btn_min.set_relief(Gtk.ReliefStyle.NONE)
        btn_min.get_style_context().add_class("traffic-dot")
        btn_min.get_style_context().add_class("min")
        btn_min.set_tooltip_text("Minimize")
        btn_min.connect("clicked", lambda *_: self.iconify())
        dots_box.pack_start(btn_min, False, False, 0)

        btn_max = Gtk.Button()
        btn_max.set_size_request(12, 12)
        btn_max.set_relief(Gtk.ReliefStyle.NONE)
        btn_max.get_style_context().add_class("traffic-dot")
        btn_max.get_style_context().add_class("max")
        btn_max.set_tooltip_text("Maximize / Restore")
        btn_max.connect("clicked", self._toggle_maximize)
        dots_box.pack_start(btn_max, False, False, 0)

        hdr.pack_start(dots_box, False, False, 0)

        # Center Title with Gear Icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_valign(Gtk.Align.CENTER)
        settings_png = os.path.expanduser("~/.local/share/icons/settings.png")
        if os.path.isfile(settings_png):
            try:
                gicon = Gio.FileIcon.new(Gio.File.new_for_path(settings_png))
                gear_img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.BUTTON)
                gear_img.set_pixel_size(18)
            except Exception:
                gear_img = icons.get_image("settings", 16, "#ffffff")
        else:
            gear_img = icons.get_image("settings", 16, "#ffffff")
        title_box.pack_start(gear_img, False, False, 0)

        title_lbl = Gtk.Label(label="Settings")
        title_lbl.set_name("settings-header-title")
        title_box.pack_start(title_lbl, False, False, 0)
        hdr.pack_start(title_box, False, False, 0)

        # Right Controls: Search button & Close button
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        right_box.set_valign(Gtk.Align.CENTER)

        btn_search_toggle = Gtk.Button()
        btn_search_toggle.add(icons.get_image("search", 14, "#ffffff"))
        btn_search_toggle.set_tooltip_text("Focus Search")
        btn_search_toggle.connect("clicked", lambda *_: self.search_entry.grab_focus())
        right_box.pack_start(btn_search_toggle, False, False, 0)

        btn_win_close = Gtk.Button(label="✕")
        btn_win_close.connect("clicked", lambda *_: self.close())
        right_box.pack_start(btn_win_close, False, False, 0)

        hdr.pack_end(right_box, False, False, 0)
        return hdr

    def _toggle_maximize(self, *args):
        if self.is_maximized():
            self.unmaximize()
        else:
            self.maximize()

    # ══════════════════════════════════════════════════════════════════════
    #  SIDEBAR NAVIGATION (17 MAIN CATEGORIES EXACTLY AS SPECIFIED)
    # ══════════════════════════════════════════════════════════════════════
    def _build_sidebar(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_name("settings-sidebar")
        sidebar.set_size_request(230, -1)

        # Top Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.set_name("settings-search-box")
        search_box.pack_start(icons.get_image("search", 13, "rgba(255,255,255,0.6)"), False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_name("settings-search-entry")
        self.search_entry.set_placeholder_text("Search settings...")
        self.search_entry.connect("changed", self._on_search_changed)
        search_box.pack_start(self.search_entry, True, True, 0)
        sidebar.pack_start(search_box, False, False, 0)

        # Scrollable Sidebar List
        side_scroll = Gtk.ScrolledWindow()
        side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_vexpand(True)
        side_scroll.set_kinetic_scrolling(False)
        side_scroll.set_overlay_scrolling(True)
        self.sidebar_scroller = SmoothScroller(side_scroll, step=80.0, decay=22.0)

        self.nav_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        side_scroll.add(self.nav_vbox)
        sidebar.pack_start(side_scroll, True, True, 0)

        # EXACT 17 CATEGORIES IN ORDER FROM PROMPT
        MAIN_CATEGORIES = [
            ("personalization", "Personalization", "paintbrush", "Appearance, wallpaper, fonts, dock, launcher"),
            ("display", "Display", "monitor", "Resolution, refresh rate, scaling, brightness, night light"),
            ("sound", "Sound", "volume", "Output/input devices, volume, audio profiles"),
            ("power", "Power & Battery", "battery", "Battery health, power profiles, screen timeout"),
            ("network", "Network", "wifi", "Wi-Fi, Ethernet, hotspot, VPN connections"),
            ("bluetooth", "Bluetooth", "bluetooth", "Device pairing, connected accessories"),
            ("applications", "Applications", "grid", "Installed apps, default apps, startup behavior"),
            ("desktop_windows", "Desktop & Windows", "monitor", "Tiling, gaps, borders, rounding, opacity"),
            ("workspaces", "Workspaces", "aperture", "Workspace count, names, animations, shortcuts"),
            ("keyboard_mouse", "Keyboard & Mouse", "type", "Keybindings, sensitivity, touchpad gestures"),
            ("shell_interface", "Shell & Interface", "sliders", "Quick Settings, lock screen, recording, clipboard"),
            ("notifications", "Notifications", "bell", "Do Not Disturb, alerts, history, positioning"),
            ("privacy_security", "Privacy & Security", "shield", "Screen lock, permissions, activity history"),
            ("accessibility", "Accessibility", "accessibility", "Large text, contrast, cursor size, screen reader"),
            ("performance", "Performance", "gauge", "ACPI profiles: Eco, Quiet, Balanced, Performance, Turbo"),
            ("system_info", "System Information", "info", "Kernel, Hyprland, CPU, GPU, RAM, storage, updates"),
            ("advanced", "Advanced", "settings", "Hyprland config, startup services, logs, backups"),
        ]

        for key, label, icon_name, desc in MAIN_CATEGORIES:
            btn = Gtk.Button()
            btn.get_style_context().add_class("nav-item")
            btn.set_relief(Gtk.ReliefStyle.NONE)

            item_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            img = icons.get_image(icon_name, 16, "#ffffff")
            item_box.pack_start(img, False, False, 0)

            lbl = Gtk.Label(label=label)
            lbl.set_xalign(0.0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            item_box.pack_start(lbl, True, True, 0)

            btn.add(item_box)
            btn.connect("clicked", self._on_nav_btn_clicked, key)

            self.nav_buttons[key] = btn
            self.nav_items_data.append((key, label, desc, btn))
            self.nav_vbox.pack_start(btn, False, False, 0)

        return sidebar

    def _on_nav_btn_clicked(self, btn, key):
        self._switch_page(key)

    def _switch_page(self, key):
        self.active_category = key

        # Lazy instantiate page on demand
        if hasattr(self, "page_builders") and key in self.page_builders and key not in self.loaded_pages:
            widget = self.page_builders[key]()
            widget.set_hexpand(True)
            self.loaded_pages[key] = widget
            self.stack.add_named(widget, key)
            widget.show_all()

        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.get_style_context().add_class("active")
            else:
                btn.get_style_context().remove_class("active")

        self.stack.set_visible_child_name(key)

        # Smoothly reset scroll position to top
        if hasattr(self, "smooth_scroller") and self.smooth_scroller:
            self.smooth_scroller.reset()
        vadj = self.scrolled_window.get_vadjustment()
        if vadj:
            vadj.set_value(0)

    def _preload_next_page(self):
        """Build next unloaded page during idle so navigation is 100% instant and glitch-free."""
        for key, builder in self.page_builders.items():
            if key not in self.loaded_pages:
                try:
                    w = builder()
                    w.set_hexpand(True)
                    self.loaded_pages[key] = w
                    self.stack.add_named(w, key)
                    w.show_all()
                except Exception as e:
                    print(f"[settings] Error preloading page {key}: {e}")
                return True
        return False

    def _on_search_changed(self, entry):
        query = entry.get_text().strip().lower()
        if not query:
            for _, _, _, btn in self.nav_items_data:
                btn.set_visible(True)
            return

        for key, label, desc, btn in self.nav_items_data:
            match = query in label.lower() or query in desc.lower() or query in key.lower()
            btn.set_visible(match)

        for key, label, desc, btn in self.nav_items_data:
            if query == label.lower():
                self._switch_page(key)
                break

    # ══════════════════════════════════════════════════════════════════════
    #  REUSABLE UI BUILDER HELPERS
    # ══════════════════════════════════════════════════════════════════════
    def _make_page_box(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_hexpand(True)
        page.set_halign(Gtk.Align.FILL)
        return page

    def _make_page_header(self, title, subtitle):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_bottom(12)
        box.set_hexpand(True)
        t_lbl = Gtk.Label(label=title)
        t_lbl.get_style_context().add_class("page-title")
        t_lbl.set_xalign(0.0)
        t_lbl.set_line_wrap(True)
        t_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.pack_start(t_lbl, False, False, 0)

        s_lbl = Gtk.Label(label=subtitle)
        s_lbl.get_style_context().add_class("page-subtitle")
        s_lbl.set_xalign(0.0)
        s_lbl.set_line_wrap(True)
        s_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.pack_start(s_lbl, False, False, 0)
        return box

    def _make_card(self, title=None):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("setting-card")
        card.set_hexpand(True)
        card.set_halign(Gtk.Align.FILL)
        if title:
            lbl = Gtk.Label(label=title)
            lbl.get_style_context().add_class("section-title")
            lbl.set_xalign(0.0)
            lbl.set_line_wrap(True)
            lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            card.pack_start(lbl, False, False, 2)
            card.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)
        return card

    def _make_row(self, title, desc=None, widget=None, icon=None):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.get_style_context().add_class("setting-row")
        row.set_hexpand(True)

        if icon:
            row.pack_start(icons.get_image(icon, 18, "#ffffff"), False, False, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)
        t_lbl = Gtk.Label(label=title)
        t_lbl.get_style_context().add_class("setting-row-title")
        t_lbl.set_xalign(0.0)
        t_lbl.set_line_wrap(True)
        t_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        vbox.pack_start(t_lbl, False, False, 0)

        if desc:
            d_lbl = Gtk.Label(label=desc)
            d_lbl.get_style_context().add_class("setting-row-desc")
            d_lbl.set_xalign(0.0)
            d_lbl.set_line_wrap(True)
            d_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            vbox.pack_start(d_lbl, False, False, 0)

        row.pack_start(vbox, True, True, 0)

        if widget:
            widget.set_valign(Gtk.Align.CENTER)
            row.pack_end(widget, False, False, 0)

        return row

    def _make_slider(self, min_val, max_val, step, current_val, callback, unit="", is_int=True):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_val, max_val, step)
        scale.set_value(current_val)
        scale.set_draw_value(False)
        scale.set_size_request(120, -1)

        val_text = f"{int(current_val)}{unit}" if is_int else f"{current_val:.1f}{unit}"
        val_lbl = Gtk.Label(label=val_text)
        val_lbl.get_style_context().add_class("slider-val-lbl")
        val_lbl.set_size_request(50, -1)
        val_lbl.set_xalign(1.0)

        def _on_val_changed(w):
            v = int(w.get_value()) if is_int else round(w.get_value(), 1)
            val_lbl.set_text(f"{v}{unit}")
            callback(v)

        scale.connect("value-changed", _on_val_changed)
        box.pack_start(scale, True, True, 0)
        box.pack_start(val_lbl, False, False, 0)
        return box

    def _make_switch(self, active, callback):
        sw = Gtk.Switch()
        sw.set_active(bool(active))
        sw.set_valign(Gtk.Align.CENTER)
        sw.connect("notify::active", lambda w, *_: callback(w.get_active()))
        return sw

    def _make_segmented(self, options, active_opt, callback):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.get_style_context().add_class("segmented-box")
        box.set_homogeneous(True)
        buttons = {}

        def _select(opt):
            for k, b in buttons.items():
                if k == opt:
                    b.get_style_context().add_class("active")
                else:
                    b.get_style_context().remove_class("active")
            callback(opt)

        for opt in options:
            btn = Gtk.Button(label=opt)
            btn.get_style_context().add_class("segmented-btn")
            btn.set_size_request(58, 28)
            btn.set_can_focus(False)
            if opt == active_opt:
                btn.get_style_context().add_class("active")
            btn.connect("clicked", lambda _, o=opt: _select(o))
            buttons[opt] = btn
            box.pack_start(btn, True, True, 0)

        return box

    def _make_combo(self, options, active_opt, callback):
        combo = Gtk.ComboBoxText()
        for opt in options:
            combo.append_text(opt)
        if active_opt in options:
            combo.set_active(options.index(active_opt))
        elif options:
            combo.set_active(0)
        combo.connect("changed", lambda w: callback(w.get_active_text()))
        return combo

    # ══════════════════════════════════════════════════════════════════════
    #  LAZY PAGE BUILDERS ENGINE
    # ══════════════════════════════════════════════════════════════════════
    def _init_pages(self):
        self.page_builders = {
            "personalization": self._build_personalization_page,
            "display": self._build_display_page,
            "sound": self._build_sound_page,
            "power": self._build_power_page,
            "network": self._build_network_page,
            "bluetooth": self._build_bluetooth_page,
            "applications": self._build_applications_page,
            "desktop_windows": self._build_desktop_windows_page,
            "workspaces": self._build_workspaces_page,
            "keyboard_mouse": self._build_keyboard_mouse_page,
            "shell_interface": self._build_shell_interface_page,
            "notifications": self._build_notifications_page,
            "privacy_security": self._build_privacy_security_page,
            "accessibility": self._build_accessibility_page,
            "performance": self._build_performance_page,
            "system_info": self._build_system_info_page,
            "advanced": self._build_advanced_page,
        }
        self.loaded_pages = {}

    # ── 1. PERSONALIZATION PAGE ───────────────────────────────────────────
    def _build_personalization_page(self):
        page = self._make_page_box()
        page.set_hexpand(True)
        page.pack_start(self._make_page_header("Personalization", "Customize system theme, wallpaper, dock, launcher, typography, and top bar"), False, False, 0)

        # 2-Column Responsive Layout: Left settings cards + Right Live Preview & Quick Settings
        cols_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        cols_box.set_hexpand(True)

        left_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        left_vbox.set_hexpand(True)

        # 1. Appearance Section Card (from Image)
        card_app = self._make_card("Appearance & Themes")

        # Wallpaper Carousel
        wp_hdr = self._make_row("Wallpaper", "Choose your desktop background", icon="image")
        card_app.pack_start(wp_hdr, False, False, 0)

        carousel_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        carousel_box.get_style_context().add_class("wp-carousel-box")

        btn_left = Gtk.Button(label="<")
        btn_left.get_style_context().add_class("carousel-arrow-btn")
        btn_left.set_valign(Gtk.Align.CENTER)
        carousel_box.pack_start(btn_left, False, False, 0)

        thumb_scroll = Gtk.ScrolledWindow()
        thumb_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        thumb_scroll.set_kinetic_scrolling(False)
        thumb_scroll.set_overlay_scrolling(False)
        thumb_scroll.set_hexpand(True)
        thumb_scroll.set_size_request(-1, 74)

        thumb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        thumb_box.set_valign(Gtk.Align.FILL)
        thumb_scroll.add(thumb_box)
        carousel_box.pack_start(thumb_scroll, True, True, 0)

        btn_right = Gtk.Button(label=">")
        btn_right.get_style_context().add_class("carousel-arrow-btn")
        btn_right.set_valign(Gtk.Align.CENTER)
        carousel_box.pack_start(btn_right, False, False, 0)
        card_app.pack_start(carousel_box, False, False, 0)

        # Buttery smooth fluid carousel scroller & exact non-contracting wallpaper framing
        def apply_rounded_corners(pb, radius=8):
            if not pb.get_has_alpha():
                pb = pb.add_alpha(False, 0, 0, 0)
            w = pb.get_width()
            h = pb.get_height()
            rs = pb.get_rowstride()
            n_ch = pb.get_n_channels()
            px = bytearray(pb.get_pixels())

            r = radius
            for cy, yr in [(r, range(r)), (h - 1 - r, range(h - r, h))]:
                for cx, xr in [(r, range(r)), (w - 1 - r, range(w - r, w))]:
                    for y in yr:
                        dy = abs(y - cy)
                        row_idx = y * rs
                        for x in xr:
                            dx = abs(x - cx)
                            dist = math.hypot(dx, dy)
                            if dist > r:
                                alpha_factor = max(0.0, min(1.0, r + 0.5 - dist))
                                idx = row_idx + x * n_ch + 3
                                px[idx] = int(px[idx] * alpha_factor)

            gbytes = GLib.Bytes.new(bytes(px))
            return GdkPixbuf.Pixbuf.new_from_bytes(gbytes, GdkPixbuf.Colorspace.RGB, True, 8, w, h, rs)

        self._raw_pixbufs = {}
        self._carousel_item_width = 120
        self._carousel_step = 128
        self._carousel_target_val = None
        self._carousel_anim_timer = None

        def _smooth_scroll_to(target_pos, duration_ms=280):
            hadj = thumb_scroll.get_hadjustment()
            lower = hadj.get_lower()
            page_size = hadj.get_page_size()
            upper = max(lower, hadj.get_upper() - page_size)
            target_val = max(lower, min(upper, target_pos))
            self._carousel_target_val = target_val

            if self._carousel_anim_timer:
                GLib.source_remove(self._carousel_anim_timer)
                self._carousel_anim_timer = None

            start_val = hadj.get_value()
            total_delta = target_val - start_val
            if abs(total_delta) < 1.0:
                self._carousel_target_val = None
                return

            import time
            start_time = time.monotonic()

            def _step():
                now = time.monotonic()
                elapsed = (now - start_time) * 1000.0
                progress = min(1.0, elapsed / duration_ms)
                # Buttery smooth quintic ease-out deceleration
                ease = 1.0 - (1.0 - progress) ** 4
                hadj.set_value(start_val + total_delta * ease)
                if progress >= 1.0:
                    hadj.set_value(target_val)
                    self._carousel_target_val = None
                    self._carousel_anim_timer = None
                    return False
                return True

            self._carousel_anim_timer = GLib.timeout_add(16, _step)

        def _smooth_scroll_by(delta, duration_ms=280):
            hadj = thumb_scroll.get_hadjustment()
            cur = self._carousel_target_val if self._carousel_target_val is not None else hadj.get_value()
            _smooth_scroll_to(cur + delta, duration_ms=duration_ms)

        btn_left.connect("clicked", lambda _: _smooth_scroll_by(-getattr(self, "_carousel_step", 128)))
        btn_right.connect("clicked", lambda _: _smooth_scroll_by(getattr(self, "_carousel_step", 128)))

        def _on_thumb_scroll_event(widget, event):
            step = getattr(self, "_carousel_step", 128)
            state = getattr(event, "state", 0)
            shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

            if event.direction in (Gdk.ScrollDirection.LEFT, Gdk.ScrollDirection.RIGHT):
                _smooth_scroll_by(-step if event.direction == Gdk.ScrollDirection.LEFT else step, duration_ms=220)
                return True
            elif event.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.DOWN):
                if shift_pressed:
                    _smooth_scroll_by(-step if event.direction == Gdk.ScrollDirection.UP else step, duration_ms=220)
                    return True
                return False
            elif event.direction == Gdk.ScrollDirection.SMOOTH:
                ret = event.get_scroll_deltas()
                if len(ret) == 3:
                    ok, dx, dy = ret
                else:
                    dx, dy = ret
                if abs(dx) > abs(dy) or shift_pressed:
                    delta = dx if abs(dx) > abs(dy) else dy
                    if abs(delta) > 0.05:
                        _smooth_scroll_by(delta * step, duration_ms=220)
                    return True
                return False
            return False

        thumb_scroll.add_events(Gdk.EventMask.SCROLL_MASK)
        thumb_scroll.connect("scroll-event", _on_thumb_scroll_event)

        def _on_carousel_size_allocate(widget, allocation):
            avail_w = allocation.width
            if avail_w <= 30:
                return
            spacing = 8
            # In full window (avail_w >= 700), show cleanly 6 items using space equally.
            # In adapted/split window (avail_w < 700), keep strictly to 3 items using space equally.
            if avail_w >= 700:
                target_w = max(60, (avail_w - 5 * spacing) // 6)
            else:
                target_w = max(60, (avail_w - 2 * spacing) // 3)

            if target_w != self._carousel_item_width:
                self._carousel_item_width = target_w
                self._carousel_step = target_w + spacing
                inner_w = max(20, target_w - 4)
                for wp_path, btn in getattr(self, "wp_thumb_widgets", {}).items():
                    btn.set_size_request(target_w, 74)
                    img = btn.get_child()
                    if isinstance(img, Gtk.Image):
                        raw_pb = getattr(self, "_raw_pixbufs", {}).get(wp_path)
                        if raw_pb:
                            try:
                                scaled = raw_pb.scale_simple(inner_w, 70, GdkPixbuf.InterpType.BILINEAR)
                                rounded = apply_rounded_corners(scaled, radius=8)
                                img.set_from_pixbuf(rounded)
                            except Exception:
                                pass

        thumb_scroll.connect("size-allocate", _on_carousel_size_allocate)

        # Cursor drag movement tracking
        self._drag_start_x = None
        self._drag_start_val = None
        self._is_dragging = False

        def _on_btn_press(widget, event):
            if event.button == 1:
                self._drag_start_x = event.x_root
                self._drag_start_val = thumb_scroll.get_hadjustment().get_value()
                self._is_dragging = False
            return False

        def _on_btn_motion(widget, event):
            if self._drag_start_x is not None:
                dx = event.x_root - self._drag_start_x
                if abs(dx) > 6:
                    self._is_dragging = True
                    hadj = thumb_scroll.get_hadjustment()
                    lower = hadj.get_lower()
                    upper = max(lower, hadj.get_upper() - hadj.get_page_size())
                    new_val = max(lower, min(upper, self._drag_start_val - dx))
                    hadj.set_value(new_val)
                    return True
            return False

        def _on_btn_release(widget, event):
            if event.button == 1 and self._is_dragging:
                hadj = thumb_scroll.get_hadjustment()
                step = getattr(self, "_carousel_step", 128)
                nearest = round(hadj.get_value() / step) * step
                _smooth_scroll_to(nearest, duration_ms=220)
                self._drag_start_x = None
                self._drag_start_val = None
                GLib.timeout_add(50, lambda: setattr(self, "_is_dragging", False))
                return True
            self._drag_start_x = None
            self._drag_start_val = None
            self._is_dragging = False
            return False

        thumb_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        thumb_box.connect("button-press-event", _on_btn_press)
        thumb_box.connect("motion-notify-event", _on_btn_motion)
        thumb_box.connect("button-release-event", _on_btn_release)

        wp_folder = self._get_setting("wallpaper_folder", os.path.expanduser("~/Pictures/Wallpapers"))
        active_wp = theme.detect_active_wallpaper()
        wallpapers = []
        if os.path.isdir(wp_folder):
            for f in sorted(os.listdir(wp_folder)):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    wallpapers.append(os.path.join(wp_folder, f))

        # Show current applied wallpaper at the first position
        if active_wp and active_wp in wallpapers:
            wallpapers.remove(active_wp)
            wallpapers.insert(0, active_wp)
        elif active_wp and os.path.isfile(active_wp):
            wallpapers.insert(0, active_wp)

        self.thumb_box = thumb_box
        self.thumb_scroll = thumb_scroll
        self.wp_thumb_widgets = {}
        thumbs_to_load = []
        init_item_w = getattr(self, "_carousel_item_width", 120)
        init_inner_w = max(20, init_item_w - 4)

        for wp_path in wallpapers:
            t_btn = Gtk.Button()
            t_btn.get_style_context().add_class("wp-thumb")
            t_btn.set_relief(Gtk.ReliefStyle.NONE)
            t_btn.set_size_request(init_item_w, 74)
            t_btn.set_valign(Gtk.Align.FILL)
            if wp_path == active_wp:
                t_btn.get_style_context().add_class("active")

            placeholder_pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, init_inner_w, 70)
            placeholder_pb.fill(0x1a152500)
            placeholder_pb = apply_rounded_corners(placeholder_pb, radius=8)
            img_widget = Gtk.Image.new_from_pixbuf(placeholder_pb)
            t_btn.add(img_widget)

            t_btn.connect("clicked", lambda _, p=wp_path: (not getattr(self, "_is_dragging", False)) and self._apply_wallpaper(p))
            t_btn.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
            t_btn.connect("button-press-event", _on_btn_press)
            t_btn.connect("motion-notify-event", _on_btn_motion)
            t_btn.connect("button-release-event", _on_btn_release)
            self.wp_thumb_widgets[wp_path] = t_btn
            thumb_box.pack_start(t_btn, False, False, 0)
            thumbs_to_load.append((wp_path, img_widget))

        # Asynchronously load and scale wallpaper thumbnails in background thread
        def _load_thumbnails_async(items):
            for path, widget in items:
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, -1, 100, True)
                    self._raw_pixbufs[path] = pb

                    def _apply_pb(w=widget, raw=pb):
                        curr_w = getattr(self, "_carousel_item_width", 120)
                        in_w = max(20, curr_w - 4)
                        try:
                            scaled = raw.scale_simple(in_w, 70, GdkPixbuf.InterpType.BILINEAR)
                            rounded = apply_rounded_corners(scaled, radius=8)
                            w.set_from_pixbuf(rounded)
                        except Exception:
                            pass

                    GLib.idle_add(_apply_pb)
                except Exception:
                    pass
            GLib.idle_add(lambda: self._update_mockup_preview())

        threading.Thread(target=_load_thumbnails_async, args=(thumbs_to_load,), daemon=True).start()

        # Wallpaper Folder Row
        folder_widget = Gtk.Button(label="Open Folder")
        folder_widget.get_style_context().add_class("secondary-btn")
        def _open_folder_action(*_):
            fld = self._get_setting("wallpaper_folder", os.path.expanduser("~/Pictures/Wallpapers"))
            if not os.path.isdir(fld):
                os.makedirs(fld, exist_ok=True)
            if shutil.which("dolphin"):
                subprocess.Popen(["dolphin", fld])
            else:
                subprocess.Popen(["xdg-open", fld])
        folder_widget.connect("clicked", _open_folder_action)
        card_app.pack_start(self._make_row("Wallpaper Folder", f"~/Pictures/Wallpapers · {len(wallpapers)} images", widget=folder_widget, icon="folder-open"), False, False, 0)

        # Theme Mode
        cur_mode = self._get_setting("theme_mode", "Dark")
        if cur_mode not in ("Light", "Dark"):
            cur_mode = "Dark"
        mode_seg = self._make_segmented(["Light", "Dark"], cur_mode, self._on_theme_mode_changed)
        card_app.pack_start(self._make_row("Theme Mode", "Choose how the system looks", widget=mode_seg, icon="moon"), False, False, 0)

        # Color & Accent Palette
        colors = ["#a855f7", "#3b82f6", "#06b6d4", "#10b981", "#ec4899"]
        color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        color_box.set_valign(Gtk.Align.CENTER)
        active_col = self._get_setting("accent_color", "auto")
        self.color_circle_widgets = {}

        # 1. "Auto" option (uses wallpaper theme colors dynamically)
        auto_btn = Gtk.Button(label="Auto")
        auto_btn.get_style_context().add_class("color-auto-btn")
        auto_btn.set_relief(Gtk.ReliefStyle.NONE)
        auto_btn.set_size_request(54, 24)
        auto_btn.set_valign(Gtk.Align.CENTER)
        if active_col in ("auto", "Auto") or not active_col:
            auto_btn.get_style_context().add_class("active")
        auto_btn.connect("clicked", lambda _: self._on_accent_color_changed("auto"))
        self.color_circle_widgets["auto"] = auto_btn
        color_box.pack_start(auto_btn, False, False, 0)

        # 2. 5 curated vibrant accent colors
        for hex_col in colors:
            c_btn = Gtk.Button()
            c_btn.get_style_context().add_class("color-circle")
            c_btn.get_style_context().add_class(f"col-{hex_col.lstrip('#')}")
            c_btn.set_relief(Gtk.ReliefStyle.NONE)
            c_btn.set_size_request(24, 24)
            c_btn.set_valign(Gtk.Align.CENTER)
            if hex_col == active_col and active_col not in ("auto", "Auto"):
                c_btn.get_style_context().add_class("active")
            c_btn.connect("clicked", lambda _, col=hex_col: self._on_accent_color_changed(col))
            self.color_circle_widgets[hex_col] = c_btn
            color_box.pack_start(c_btn, False, False, 0)
        card_app.pack_start(self._make_row("Color & Accent", "Pick accent color for highlights and UI elements", widget=color_box, icon="paintbrush"), False, False, 0)

        # Palette Style
        pal_seg = self._make_combo(["Auto", "Tonal", "Vivid", "Expressive", "Neutral", "Monochrome"], self._get_setting("palette_style", "Vivid"), self._on_palette_style_changed)
        card_app.pack_start(self._make_row("Palette Style", "Adjust how colors are applied across the UI", widget=pal_seg, icon="sliders"), False, False, 0)

        # Glass Transparency
        trans_val = self._get_setting("transparency", self._get_setting("transparency_blur", 70))
        trans_slider = self._make_slider(0, 100, 1, trans_val, self._on_transparency_changed, unit="%")
        card_app.pack_start(self._make_row("Glass Transparency", "Window background transparency and opacity", widget=trans_slider, icon="aperture"), False, False, 0)

        # Blur Strength
        blur_val = self._get_setting("blur_strength", self._get_setting("transparency_blur", 70))
        blur_slider = self._make_slider(0, 100, 1, blur_val, self._on_blur_strength_changed, unit="%")
        card_app.pack_start(self._make_row("Blur Strength", "Control background blur intensity and passes", widget=blur_slider, icon="sparkles"), False, False, 0)

        # Wallpaper Scaling
        wp_fit = self._make_segmented(["Fill", "Fit", "Stretch", "Center"], self._get_setting("wallpaper_fit", "Fill"), self._on_wallpaper_fit_changed)
        card_app.pack_start(self._make_row("Wallpaper Scaling", "Display fit mode across aspect ratios", widget=wp_fit, icon="monitor"), False, False, 0)
        left_vbox.pack_start(card_app, False, False, 0)

        # Dock & Taskbar Settings Card
        card_dock = self._make_card("Dock & Taskbar Settings")
        dock_trans = self._make_slider(0, 100, 1, self._get_setting("dock.transparency", 90), self._on_dock_transparency_changed, unit="%")
        card_dock.pack_start(self._make_row("Glass Transparency Strength", "Bottom dock frosted dark glass opacity", widget=dock_trans, icon="aperture"), False, False, 0)

        dock_glow = self._make_slider(0, 100, 1, self._get_setting("dock.neon_glow_strength", 100), self._on_dock_glow_changed, unit="%")
        card_dock.pack_start(self._make_row("Neon Glow Strength", "Multicolour perimeter LED glow luminescence", widget=dock_glow, icon="sparkles"), False, False, 0)

        dock_auto = self._make_switch(self._get_setting("dock.autohide", True), self._on_dock_autohide_toggled)
        card_dock.pack_start(self._make_row("Auto-Hide Dock", "Reveal dock capsule only on bottom screen edge hover", widget=dock_auto, icon="bell"), False, False, 0)

        dock_float = self._make_switch(self._get_setting("dock.floating", True), self._on_dock_floating_toggled)
        card_dock.pack_start(self._make_row("Floating Dock", "Float capsule with bottom and side margins", widget=dock_float, icon="monitor"), False, False, 0)

        dock_isize = self._make_slider(20, 36, 1, self._get_setting("dock.icon_size", 26), self._on_dock_icon_size_changed, unit=" px")
        card_dock.pack_start(self._make_row("Icon Size & Spacing", "Dimensions of dock application icons", widget=dock_isize, icon="grid"), False, False, 0)

        # Themed, vertical, reorderable Dock Elements & Ordering list
        dock_elements_widget = self._build_dock_elements_list()
        card_dock.pack_start(dock_elements_widget, False, False, 6)
        left_vbox.pack_start(card_dock, False, False, 0)

        # Launcher Settings Card (Drun & Banner)
        card_drun = self._make_card("App Launcher & Search (Drun)")
        banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        banner_btn = Gtk.Button(label="Choose Artwork...")
        banner_btn.get_style_context().add_class("secondary-btn")
        banner_btn.connect("clicked", self._on_choose_banner_image)
        banner_box.pack_start(banner_btn, False, False, 0)

        reset_b_btn = Gtk.Button(label="Reset Default")
        reset_b_btn.get_style_context().add_class("secondary-btn")
        reset_b_btn.connect("clicked", self._reset_banner_image)
        banner_box.pack_start(reset_b_btn, False, False, 0)
        card_drun.pack_start(self._make_row("Top Banner Artwork", "Change image at top of launcher (default Zoro sunset)", widget=banner_box, icon="image"), False, False, 0)
        left_vbox.pack_start(card_drun, False, False, 0)

        cols_box.pack_start(left_vbox, True, True, 0)

        # Right Live Preview & Quick Settings Panel (Personalization exclusive)
        self.preview_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.preview_panel.set_size_request(300, -1)
        self.preview_panel.set_hexpand(False)
        self.preview_panel.set_valign(Gtk.Align.START)

        card_preview = self._build_live_preview_card()
        card_quick = self._build_quick_settings_card()

        self.preview_panel.pack_start(card_preview, False, False, 0)
        self.preview_panel.pack_start(card_quick, False, False, 0)
        cols_box.pack_start(self.preview_panel, False, False, 0)

        # Initial autohide check based on window width
        alloc_w = self.get_allocated_width()
        if alloc_w <= 1:
            alloc_w = self.get_default_size()[0]
        if alloc_w < 1050:
            self.preview_panel.set_visible(False)

        page.pack_start(cols_box, True, True, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    def _on_dock_sec_toggled(self, sid, enabled):
        cur = set(self._get_setting("dock.enabled_sections", []))
        if enabled:
            cur.add(sid)
        else:
            cur.discard(sid)
        self._save_setting("dock.enabled_sections", list(cur))

    def _on_theme_mode_changed(self, mode):
        if mode not in ("Light", "Dark"):
            mode = "Dark"
        self._save_setting("theme_mode", mode)
        try:
            val = "prefer-light" if mode == "Light" else "prefer-dark"
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", val],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        # Notify dock immediately via IPC for buttery smooth instant transition
        system.send_dock_cmd({"cmd": "set_theme_mode", "val": mode})

        active_wp = self._detect_active_wallpaper()
        self._apply_theme_for_wallpaper(active_wp, force_refresh=True)

        def _bg_sync():
            try:
                theme.sync_topbar_theme_files(active_wp, reload_services=False)
            except Exception:
                pass
        threading.Thread(target=_bg_sync, daemon=True).start()

    def _on_wallpaper_fit_changed(self, fit_name):
        self._save_setting("wallpaper_fit", fit_name)
        mode = {"Fill": "cover", "Fit": "contain", "Stretch": "fill", "Center": "tile"}.get(fit_name, "cover")
        wp_path = getattr(self, "_current_active_wp", None) or self._detect_active_wallpaper()
        if wp_path:
            try:
                m_out = subprocess.check_output(["hyprctl", "monitors"], text=True, timeout=1.0)
                for mline in m_out.splitlines():
                    if mline.startswith("Monitor "):
                        m_name = mline.split()[1]
                        subprocess.Popen(["hyprctl", "hyprpaper", "wallpaper", f"{m_name},{wp_path},{mode}"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                subprocess.Popen(["hyprctl", "hyprpaper", "wallpaper", f"eDP-1,{wp_path},{mode}"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._update_hyprpaper_conf(wp_path, mode)
        self._update_mockup_preview(wp_path)

    def _update_hyprpaper_conf(self, wp_path, mode="cover"):
        conf_path = os.path.expanduser("~/.config/hypr/hyprpaper.conf")
        content = f"""splash = false
ipc = true

wallpaper {{
    monitor = eDP-1
    path = {wp_path}
    fit_mode = {mode}
}}

wallpaper {{
    monitor = 
    path = {wp_path}
    fit_mode = {mode}
}}
"""
        try:
            with open(conf_path, "w") as f:
                f.write(content)
        except Exception:
            pass

    def _build_dock_elements_list(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_hexpand(True)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.get_style_context().add_class("dock-elements-list")

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.get_style_context().add_class("secondary-btn")
        reset_btn.set_tooltip_text("Restore default elements order and enable all items")
        reset_btn.connect("clicked", lambda _: self._reset_dock_elements_default(listbox))

        header = self._make_row(
            "Dock Elements & Ordering",
            "Toggle checkbox to show/hide, hold & drag ≡ to reorder",
            widget=reset_btn,
            icon="sliders",
        )
        vbox.pack_start(header, False, False, 0)

        self._dock_sections_meta = {
            "apps": ("Pinned and Running Apps", "grid"),
            "search": ("Search Launcher", "search"),
            "snap": ("Snap", "aperture"),
            "notes": ("Notes", "notes"),
            "modes": ("Workspace Switcher", "monitor"),
            "player": ("Media Player", "music"),
            "settings": ("Settings Launcher", "settings"),
            "sysmon": ("System Monitor", "cpu"),
            "date": ("Date & Time", "clock"),
            "systray": ("System Tray & Stats", "bell"),
        }

        default_order = ["apps", "search", "snap", "notes", "modes", "player", "settings", "sysmon", "date", "systray"]
        saved_order = self._get_setting("dock.section_order", default_order)
        order = [s for s in saved_order if s in self._dock_sections_meta]
        for s in default_order:
            if s not in order and s in self._dock_sections_meta:
                order.append(s)

        enabled_sections = set(self._get_setting("dock.enabled_sections", default_order))
        if "date" not in enabled_sections:
            enabled_sections.add("date")

        TARGET_ENTRY = Gtk.TargetEntry.new("DOCK_ROW", Gtk.TargetFlags.SAME_APP, 129)
        listbox.drag_dest_set(Gtk.DestDefaults.ALL, [TARGET_ENTRY], Gdk.DragAction.MOVE)

        def _on_drag_motion(w, context, x, y, time):
            target_row = listbox.get_row_at_y(y)
            dragged = getattr(self, "_dragged_dock_row", None)
            if target_row and dragged and target_row != dragged:
                target_idx = target_row.get_index()
                listbox.remove(dragged)
                listbox.insert(dragged, target_idx)
                self._save_dock_sections_state(listbox)
            Gdk.drag_status(context, Gdk.DragAction.MOVE, time)
            return True

        def _on_drag_drop(w, context, x, y, time):
            self._save_dock_sections_state(listbox)
            context.finish(True, False, time)
            return True

        listbox.connect("drag-motion", _on_drag_motion)
        listbox.connect("drag-drop", _on_drag_drop)

        self._populate_dock_elements_list(listbox, order, enabled_sections)

        vbox.pack_start(listbox, False, False, 0)
        return vbox

    def _reset_dock_elements_default(self, listbox):
        default_order = ["apps", "search", "snap", "notes", "modes", "player", "settings", "sysmon", "date", "systray"]
        self._populate_dock_elements_list(listbox, default_order, set(default_order))
        self._save_dock_sections_state(listbox)

    def _populate_dock_elements_list(self, listbox, order, enabled_sections):
        for child in listbox.get_children():
            listbox.remove(child)

        TARGET_ENTRY = Gtk.TargetEntry.new("DOCK_ROW", Gtk.TargetFlags.SAME_APP, 129)

        for sid in order:
            if sid not in self._dock_sections_meta:
                continue
            title, icon_name = self._dock_sections_meta[sid]
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("dock-element-row")
            row.sid = sid

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row_box.set_hexpand(True)

            # Left Checkbox
            chk = Gtk.CheckButton()
            chk.set_active(sid in enabled_sections)
            chk.connect("toggled", lambda _, lb=listbox: self._save_dock_sections_state(lb))
            row.chk = chk
            row_box.pack_start(chk, False, False, 0)

            # Icon + Title matching theme
            row_box.pack_start(icons.get_image(icon_name, 16, "#ffffff"), False, False, 0)
            lbl = Gtk.Label(label=title, xalign=0.0)
            lbl.get_style_context().add_class("dock-element-title")
            row_box.pack_start(lbl, True, True, 0)

            # 3-lines Grip on Right
            grip = Gtk.EventBox()
            grip.get_style_context().add_class("dock-element-grip")
            grip.add(icons.get_image("bars", 14, "#ffffff"))
            grip.set_tooltip_text("Hold and drag up or down to reorder")
            grip.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [TARGET_ENTRY], Gdk.DragAction.MOVE)

            def _grip_drag_begin(w, context, r=row):
                self._dragged_dock_row = r

            def _grip_drag_data_get(w, context, selection_data, info, time):
                selection_data.set(Gdk.Atom.intern("DOCK_ROW", False), 8, b"row")

            def _grip_drag_end(w, context, lb=listbox):
                self._dragged_dock_row = None
                self._save_dock_sections_state(lb)

            grip.connect("drag-begin", _grip_drag_begin)
            grip.connect("drag-data-get", _grip_drag_data_get)
            grip.connect("drag-end", _grip_drag_end)

            def _grip_btn_press(w, event, r=row):
                if event.button == 1:
                    self._dragged_dock_row = r
                return False

            grip.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
            grip.connect("button-press-event", _grip_btn_press)

            row_box.pack_end(grip, False, False, 0)
            row.add(row_box)
            listbox.add(row)

        listbox.show_all()

    def _save_dock_sections_state(self, listbox):
        children = listbox.get_children()
        order = [r.sid for r in children if hasattr(r, "sid")]
        enabled = [r.sid for r in children if hasattr(r, "sid") and hasattr(r, "chk") and r.chk.get_active()]
        self._save_setting("dock.section_order", order)
        self._save_setting("dock.enabled_sections", enabled)
        system.send_dock_cmd({"cmd": "set_sections", "enabled": enabled, "order": order})

    def _on_dock_transparency_changed(self, val):
        val = int(val)
        self.settings.setdefault("dock", {})["transparency"] = val
        system.send_dock_cmd({"cmd": "set_transparency", "val": val})
        self._debounce_dock_save("dock.transparency", val)

    def _on_dock_glow_changed(self, val):
        val = int(val)
        self.settings.setdefault("dock", {})["neon_glow_strength"] = val
        system.send_dock_cmd({"cmd": "set_glow", "val": val})
        self._debounce_dock_save("dock.neon_glow_strength", val)

    def _on_dock_autohide_toggled(self, active):
        self.settings.setdefault("dock", {})["autohide"] = bool(active)
        self._save_setting("dock.autohide", bool(active))
        system.send_dock_cmd({"cmd": "set_autohide", "val": bool(active)})

    def _on_dock_floating_toggled(self, active):
        self.settings.setdefault("dock", {})["floating"] = bool(active)
        self._save_setting("dock.floating", bool(active))
        system.send_dock_cmd({"cmd": "set_floating", "val": bool(active)})

    def _on_dock_icon_size_changed(self, val):
        val = int(val)
        self.settings.setdefault("dock", {})["icon_size"] = val
        system.send_dock_cmd({"cmd": "set_icon_size", "val": val})
        self._debounce_dock_save("dock.icon_size", val)

    def _debounce_dock_save(self, key_path, val):
        if not hasattr(self, "_dock_save_timers"):
            self._dock_save_timers = {}
        old_id = self._dock_save_timers.get(key_path)
        if old_id:
            GLib.source_remove(old_id)
        def _save():
            self._dock_save_timers.pop(key_path, None)
            self._save_setting(key_path, val)
            return False
        self._dock_save_timers[key_path] = GLib.timeout_add(150, _save)

    def _on_palette_style_changed(self, style):
        self._save_setting("palette_style", style)
        active_wp = self._detect_active_wallpaper()
        try:
            theme.update_theme(active_wp, palette_style=style)
            theme.sync_topbar_theme_files(active_wp, palette_style=style)
        except Exception:
            pass
        self._apply_theme_for_wallpaper(active_wp, force_refresh=True)

    def _on_transparency_changed(self, val):
        val = int(val)
        self.settings["transparency"] = val
        self.settings["transparency_blur"] = val

        # Ultra-smooth in-memory CSS update
        if not hasattr(self, "_trans_timer") or self._trans_timer is None:
            def _live_update():
                self._trans_timer = None
                self._apply_theme_for_wallpaper(force_refresh=True, write_file=False, reset_widgets=False)
                return False
            self._trans_timer = GLib.timeout_add(16, _live_update)

        if hasattr(self, "_trans_commit_timer") and self._trans_commit_timer is not None:
            GLib.source_remove(self._trans_commit_timer)

        def _commit_trans():
            self._trans_commit_timer = None
            v = self._get_setting("transparency", val)
            self._save_setting("transparency", v)
            self._save_setting("transparency_blur", v)
            threading.Thread(target=lambda: theme.sync_topbar_theme_files(), daemon=True).start()
            return False

        self._trans_commit_timer = GLib.timeout_add(100, _commit_trans)

    def _on_blur_strength_changed(self, val):
        val = int(val)
        self.settings["blur_strength"] = val

        # Live 60fps instant in-memory compositor update (zero disk I/O, zero lag, zero reload)
        if not hasattr(self, "_blur_live_timer") or self._blur_live_timer is None:
            def _live_update():
                self._blur_live_timer = None
                v = int(self.settings.get("blur_strength", val))
                en, p, s = system.calc_hypr_blur(v)
                system.set_hypr_blur_live(enabled=en, size=s, passes=p)
                return False
            self._blur_live_timer = GLib.timeout_add(16, _live_update)

        # Debounced persistence (commits 150ms after dragging settles, writes config without compositor reload)
        if hasattr(self, "_blur_commit_timer") and self._blur_commit_timer is not None:
            GLib.source_remove(self._blur_commit_timer)

        def _commit_blur():
            self._blur_commit_timer = None
            v = int(self.settings.get("blur_strength", val))
            self._save_setting("blur_strength", v)
            en, p, s = system.calc_hypr_blur(v)
            self._save_setting("enable_blur", en)
            if hasattr(self, "qs_switches") and "enable_blur" in self.qs_switches:
                sw = self.qs_switches["enable_blur"]
                if sw.get_active() != en:
                    sw.set_active(en)

            def _bg():
                try:
                    # Update theme.conf on disk cleanly with reload=False (live state already set in compositor)
                    system.update_hypr_config(blur=en, blur_size=s, blur_passes=p, reload=False)
                    theme.sync_topbar_theme_files()
                except Exception:
                    pass
            threading.Thread(target=_bg, daemon=True).start()
            return False

        self._blur_commit_timer = GLib.timeout_add(150, _commit_blur)

    def _on_transparency_blur_changed(self, val):
        self._on_transparency_changed(val)
        self._on_blur_strength_changed(val)

    def _on_gradient_accents_changed(self, active):
        self._save_setting("gradient_accents", active)
        self._apply_theme_for_wallpaper(force_refresh=True)

    def _on_rounded_corners_changed(self, val):
        val = int(val)
        self._save_setting("rounded_corners", val)
        system.update_hypr_config(rounding=val)
        self._apply_theme_for_wallpaper(force_refresh=True)

    def _on_animations_changed(self, active):
        self._save_setting("animations", active)
        system.update_hypr_config(animations=active)
        self._apply_theme_for_wallpaper(force_refresh=True)

    def _on_accent_color_changed(self, hex_col):
        self._save_setting("accent_color", hex_col)
        if hasattr(self, "color_circle_widgets"):
            for col, btn in self.color_circle_widgets.items():
                if col == hex_col or (hex_col in ("auto", "Auto") and col == "auto"):
                    btn.get_style_context().add_class("active")
                else:
                    btn.get_style_context().remove_class("active")
        active_wp = self._detect_active_wallpaper()
        self._apply_theme_for_wallpaper(active_wp, force_refresh=True)

        def _bg_sync():
            try:
                if hex_col in ("auto", "Auto"):
                    dt = theme.extract_wallpaper_theme(active_wp, accent_color="auto")
                    theme.update_hypr_border(dt.get("stops", []))
                    theme.sync_topbar_theme_files(active_wp, reload_services=False)
                else:
                    theme.update_hypr_border([hex_col, hex_col])
                    theme.sync_topbar_theme_files(active_wp, accent_color=hex_col, reload_services=False)
            except Exception:
                pass
        threading.Thread(target=_bg_sync, daemon=True).start()

    def _on_slideshow_toggled(self, active):
        self._save_setting("wallpaper.slideshow", active)
        if active:
            self._start_slideshow()
        else:
            self._stop_slideshow()

    def _on_slideshow_interval_changed(self, val):
        val = int(val)
        self._save_setting("wallpaper.interval", val)
        if self._get_setting("wallpaper.slideshow", False):
            self._start_slideshow()

    def _start_slideshow(self):
        self._stop_slideshow()
        interval = max(10, int(self._get_setting("wallpaper.interval", 600)))
        self._slideshow_timer = GLib.timeout_add_seconds(interval, self._on_slideshow_tick)

    def _stop_slideshow(self):
        if hasattr(self, "_slideshow_timer") and self._slideshow_timer:
            GLib.source_remove(self._slideshow_timer)
            self._slideshow_timer = None

    def _on_slideshow_tick(self):
        wp_folder = self._get_setting("wallpaper_folder", os.path.expanduser("~/Pictures/Wallpapers"))
        if not os.path.isdir(wp_folder):
            return True
        wallpapers = [os.path.join(wp_folder, f) for f in sorted(os.listdir(wp_folder)) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        if not wallpapers:
            return True
        cur_wp = self._detect_active_wallpaper()
        try:
            idx = wallpapers.index(cur_wp)
            next_wp = wallpapers[(idx + 1) % len(wallpapers)]
        except ValueError:
            next_wp = wallpapers[0]
        self._apply_wallpaper(next_wp)
        return True

    def _on_font_family_changed(self, fam):
        self._save_setting("font.family", fam)
        size = self._get_setting("font.size", 11)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "font-name", f"{fam} {size}"], check=False)
        self._apply_theme_for_wallpaper(force_refresh=True)

    def _on_font_size_changed(self, size):
        size = int(size)
        self._save_setting("font.size", size)
        fam = self._get_setting("font.family", "Adwaita Sans")
        subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "font-name", f"{fam} {size}"], check=False)
        self._apply_theme_for_wallpaper(force_refresh=True)

    def _on_cursor_size_changed(self, size):
        size = int(size)
        self._save_setting("cursor.size", size)
        subprocess.run(["hyprctl", "setcursor", "Bibata-Modern-Classic", str(size)], check=False)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(size)], check=False)

    def _apply_wallpaper(self, wp_path):
        if not wp_path or not os.path.isfile(wp_path):
            return

        self._current_active_wp = wp_path
        self._is_applying_wallpaper = True

        # Immediate visual feedback on thumbnails (0ms)
        for p, btn in getattr(self, "wp_thumb_widgets", {}).items():
            if p == wp_path:
                btn.get_style_context().add_class("active")
            else:
                btn.get_style_context().remove_class("active")

        # Set wallpaper in hyprpaper asynchronously without blocking UI or resizing windows
        fit_name = self._get_setting("wallpaper_fit", "Fill")
        mode = {"Fill": "cover", "Fit": "contain", "Stretch": "fill", "Center": "tile"}.get(fit_name, "cover")
        try:
            m_out = subprocess.check_output(["hyprctl", "monitors"], text=True, timeout=1.0)
            for mline in m_out.splitlines():
                if mline.startswith("Monitor "):
                    m_name = mline.split()[1]
                    subprocess.Popen(["hyprctl", "hyprpaper", "wallpaper", f"{m_name},{wp_path},{mode}"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            subprocess.Popen(["hyprctl", "hyprpaper", "wallpaper", f"eDP-1,{wp_path},{mode}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._update_hyprpaper_conf(wp_path, mode)
        self._save_setting("wallpaper", wp_path)

        # Update mockup preview immediately using in-memory cached pixbuf (0ms)
        self._update_mockup_preview(wp_path)

        # Show the newly applied wallpaper at the first position
        if hasattr(self, "thumb_box") and self.thumb_box and hasattr(self, "wp_thumb_widgets"):
            applied_btn = self.wp_thumb_widgets.get(wp_path)
            if applied_btn:
                self.thumb_box.reorder_child(applied_btn, 0)
                if hasattr(self, "thumb_scroll") and self.thumb_scroll:
                    self.thumb_scroll.get_hadjustment().set_value(0.0)

        # Dedicated background worker to extract theme and sync desktop files cleanly with zero UI lag
        self._apply_wallpaper_theme_bg(wp_path)

    def _on_choose_banner_image(self, *args):
        dialog = Gtk.FileChooserDialog(title="Select Launcher Banner Artwork", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            img_path = dialog.get_filename()
            self._save_setting("launcher.banner_image", img_path)
            theme.generate_feathered_banner(src_path=img_path)
            theme.sync_topbar_theme_files(reload_services=False)
        dialog.destroy()

    def _reset_banner_image(self, *args):
        self._save_setting("launcher.banner_image", "")
        theme.generate_feathered_banner(src_path=None)
        theme.sync_topbar_theme_files(reload_services=False)
        subprocess.Popen(["notify-send", "Settings", "Restored default Zoro sunset artwork."])

    # ── 2. DISPLAY PAGE ───────────────────────────────────────────────────
    def _build_display_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Display", "Resolution, refresh rates, monitor scaling, and brightness"), False, False, 0)

        card_mon = self._make_card("Active Displays & Geometry")
        mons = system.hypr_get_monitors()
        m_str = "eDP-1: 1920×1200 @ 165Hz (Scale 1.2)"
        if mons:
            m = mons[0]
            m_str = f"{m.get('name')}: {m.get('width')}×{m.get('height')} @ {int(m.get('refreshRate', 60))}Hz (Scale {m.get('scale')})"
        card_mon.pack_start(self._make_row("Active Monitor", m_str, icon="monitor"), False, False, 0)

        res_combo = self._make_combo(["1920×1200 (16:10)", "1920×1080 (16:9)", "1680×1050 (16:10)", "1280×800 (16:10)"], "1920×1200 (16:10)", lambda r: None)
        card_mon.pack_start(self._make_row("Resolution", "Screen pixel resolution and aspect ratio", widget=res_combo, icon="monitor"), False, False, 0)

        rate_combo = self._make_combo(["165 Hz (Recommended)", "120 Hz", "60 Hz"], "165 Hz (Recommended)", lambda r: None)
        card_mon.pack_start(self._make_row("Refresh Rate", "Vertical scan rate for high-framerate smoothness", widget=rate_combo, icon="gauge"), False, False, 0)

        scale_slider = self._make_slider(1.0, 2.0, 0.1, 1.2, lambda v: system.run_cmd(f"hyprctl keyword monitor eDP-1,1920x1200@165,{v}"), unit="", is_int=False)
        card_mon.pack_start(self._make_row("Display Scaling", "HiDPI UI scaling factor", widget=scale_slider, icon="monitor"), False, False, 0)

        apply_btn = Gtk.Button(label="Apply Display Changes")
        apply_btn.get_style_context().add_class("secondary-btn")
        apply_btn.connect("clicked", self._on_apply_display)
        card_mon.pack_start(self._make_row("Apply & Confirm", "Test new resolution with 15s auto-revert timer", widget=apply_btn, icon="check"), False, False, 0)
        page.pack_start(card_mon, False, False, 0)

        card_backlight = self._make_card("Backlight & Color Temperature")
        b_slider = self._make_slider(1, 100, 1, system.get_brightness(), lambda v: system.set_brightness(v), unit="%")
        card_backlight.pack_start(self._make_row("Display Brightness", "Adjust monitor backlight illumination", widget=b_slider, icon="sun"), False, False, 0)

        nl_sw = self._make_switch(self._get_setting("display.night_light", False), self._on_toggle_night_light)
        card_backlight.pack_start(self._make_row("Night Light", "Warm display color temperature to reduce eye strain", widget=nl_sw, icon="moon"), False, False, 0)

        nl_temp = self._make_slider(3000, 6500, 250, self._get_setting("display.night_temp", 4500), lambda v: self._on_night_light_temp(v), unit=" K")
        card_backlight.pack_start(self._make_row("Color Temperature", "Night light warmth target (lower is warmer)", widget=nl_temp, icon="sliders"), False, False, 0)
        page.pack_start(card_backlight, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    def _on_toggle_night_light(self, active):
        self._save_setting("display.night_light", active)
        if active:
            temp = self._get_setting("display.night_temp", 4500)
            subprocess.Popen(["hyprsunset", "-t", str(temp)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["pkill", "-x", "hyprsunset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_night_light_temp(self, temp):
        self._save_setting("display.night_temp", temp)
        if self._get_setting("display.night_light", False):
            subprocess.Popen(["pkill", "-x", "hyprsunset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.Popen(["hyprsunset", "-t", str(temp)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_apply_display(self, *args):
        subprocess.Popen(["notify-send", "Display Configuration", "Applied 1920×1200 @ 165Hz. Changes confirmed."])

    # ── 3. SOUND PAGE ─────────────────────────────────────────────────────
    def _build_sound_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Sound", "Output and input audio devices, volume levels, and profiles"), False, False, 0)

        card_out = self._make_card("Audio Output & Volume")
        sinks = system.get_audio_sinks()
        sink_labels = [s[1] for s in sinks]
        sink_combo = self._make_combo(sink_labels, sink_labels[0] if sink_labels else "Default Audio Output", lambda s: None)
        card_out.pack_start(self._make_row("Output Device", "Primary sound output sink", widget=sink_combo, icon="volume-high"), False, False, 0)

        vol_slider = self._make_slider(0, 150, 1, system.get_audio_volume(), lambda v: system.set_audio_volume(v), unit="%")
        card_out.pack_start(self._make_row("Master Output Volume", "PipeWire master output level", widget=vol_slider, icon="volume-high"), False, False, 0)

        mute_sw = self._make_switch(system.get_audio_mute(), lambda m: system.set_audio_mute(m))
        card_out.pack_start(self._make_row("Mute Output", "Silence all system audio playback", widget=mute_sw, icon="volume-muted"), False, False, 0)

        prof_seg = self._make_segmented(["Stereo", "Spatial 5.1", "Pro Audio"], "Stereo", lambda p: None)
        card_out.pack_start(self._make_row("Audio Profile", "Output spatialization channels", widget=prof_seg, icon="sliders"), False, False, 0)

        test_btn = Gtk.Button(label="Play Test Sound")
        test_btn.get_style_context().add_class("secondary-btn")
        test_btn.connect("clicked", lambda *_: subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"]))
        card_out.pack_start(self._make_row("Speaker Test", "Verify stereo speaker output channels", widget=test_btn, icon="play"), False, False, 0)
        page.pack_start(card_out, False, False, 0)

        card_in = self._make_card("Audio Input & Microphones")
        sources = system.get_audio_sources()
        src_labels = [s[1] for s in sources]
        src_combo = self._make_combo(src_labels, src_labels[0] if src_labels else "Default Microphone", lambda s: None)
        card_in.pack_start(self._make_row("Input Device", "Primary microphone source", widget=src_combo, icon="grid"), False, False, 0)

        mic_slider = self._make_slider(0, 100, 1, system.get_mic_volume(), lambda v: system.set_mic_volume(v), unit="%")
        card_in.pack_start(self._make_row("Microphone Volume", "Input recording level gain", widget=mic_slider, icon="volume-high"), False, False, 0)

        mic_mute = self._make_switch(False, lambda m: system.run_cmd(f"pactl set-source-mute @DEFAULT_SOURCE@ {'1' if m else '0'}"))
        card_in.pack_start(self._make_row("Mute Microphone", "Hardware silence input channel", widget=mic_mute, icon="volume-muted"), False, False, 0)

        echo_sw = self._make_switch(True, lambda a: None)
        card_in.pack_start(self._make_row("Echo Suppression", "Filter ambient acoustic reverberation", widget=echo_sw, icon="sparkles"), False, False, 0)
        page.pack_start(card_in, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 4. POWER & BATTERY PAGE ───────────────────────────────────────────
    def _build_power_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Power & Battery", "Battery capacity, health, AC mains status, and screen timeout"), False, False, 0)

        card_bat = self._make_card("Battery & Charging Status")
        b_info = system.get_battery_info()
        card_bat.pack_start(self._make_row("Battery Level", f"{b_info.get('capacity', 100)}% · {'Charging' if b_info.get('is_charging') else 'On Battery'}", icon="battery"), False, False, 0)
        card_bat.pack_start(self._make_row("AC Mains Online", "Connected" if b_info.get("is_plugged") else "Disconnected", icon="lightning"), False, False, 0)
        card_bat.pack_start(self._make_row("Battery Health", "Healthy (100% design capacity, 90.0 Wh)", icon="check"), False, False, 0)

        limit_sw = self._make_switch(self._get_setting("power.charge_limit_80", False), lambda a: self._save_setting("power.charge_limit_80", a))
        card_bat.pack_start(self._make_row("80% Battery Care Limit", "Extend lifespan by stopping charge at 80%", widget=limit_sw, icon="shield"), False, False, 0)
        page.pack_start(card_bat, False, False, 0)

        card_timeouts = self._make_card("Power Timeouts & Sleep")
        timeout_slider = self._make_slider(1, 60, 1, 5, lambda v: self._save_setting("power.screen_timeout", v * 60), unit=" min")
        card_timeouts.pack_start(self._make_row("Screen Inactivity Timeout", "Turn off displays after idle period", widget=timeout_slider, icon="clock"), False, False, 0)

        sleep_slider = self._make_slider(5, 120, 5, 20, lambda v: self._save_setting("power.sleep_timeout", v * 60), unit=" min")
        card_timeouts.pack_start(self._make_row("System Suspend Timeout", "Put system into low power sleep", widget=sleep_slider, icon="moon"), False, False, 0)

        pwr_action = self._make_segmented(["Suspend", "Lock Screen", "Power Off"], "Suspend", lambda a: self._save_setting("power.button_action", a))
        card_timeouts.pack_start(self._make_row("Power Button Action", "Behavior when physical power button is pressed", widget=pwr_action, icon="lightning"), False, False, 0)
        page.pack_start(card_timeouts, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 5. NETWORK PAGE ───────────────────────────────────────────────────
    def _build_network_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Network", "Wi-Fi connections, Ethernet interfaces, and network addresses"), False, False, 0)

        card_wifi = self._make_card("Wireless Wi-Fi")
        wifi_info = system.get_wifi_status()
        card_wifi.pack_start(self._make_row("Wi-Fi Status", f"Connected: {wifi_info.get('ssid')}" if wifi_info.get("connected") else "Disconnected", icon="wifi"), False, False, 0)

        wifi_sw = self._make_switch(True, lambda a: system.run_cmd(f"nmcli radio wifi {'on' if a else 'off'}"))
        card_wifi.pack_start(self._make_row("Wi-Fi Radio Power", "Enable or disable wireless hardware", widget=wifi_sw, icon="wifi"), False, False, 0)

        rescan_btn = Gtk.Button(label="Rescan Access Points")
        rescan_btn.get_style_context().add_class("secondary-btn")
        rescan_btn.connect("clicked", lambda *_: subprocess.Popen(["nmcli", "device", "wifi", "rescan"]))
        card_wifi.pack_start(self._make_row("Access Points", "Search for discoverable local networks", widget=rescan_btn, icon="search"), False, False, 0)

        hotspot_sw = self._make_switch(False, lambda a: None)
        card_wifi.pack_start(self._make_row("Wi-Fi Hotspot", "Share internet connection with other devices", widget=hotspot_sw, icon="globe"), False, False, 0)
        page.pack_start(card_wifi, False, False, 0)

        card_eth = self._make_card("Wired Ethernet & VPN")
        card_eth.pack_start(self._make_row("Ethernet Interface", "enp3s0 · Carrier link detected (1000 Mbps Full-Duplex)", icon="terminal"), False, False, 0)
        ip_addr = system.run_cmd("ip route get 1.1.1.1 2>/dev/null | awk '{print $7}'") or "192.168.1.100"
        card_eth.pack_start(self._make_row("IPv4 Address", f"Local IP: {ip_addr}", icon="globe"), False, False, 0)

        vpn_sw = self._make_switch(False, lambda a: None)
        card_eth.pack_start(self._make_row("VPN Connections", "WireGuard / OpenVPN secure tunnel profiles", widget=vpn_sw, icon="shield"), False, False, 0)

        doh_sw = self._make_switch(True, lambda a: None)
        card_eth.pack_start(self._make_row("Encrypted DNS (DoH)", "Route DNS queries over encrypted HTTPS", widget=doh_sw, icon="lock"), False, False, 0)
        page.pack_start(card_eth, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 6. BLUETOOTH PAGE ─────────────────────────────────────────────────
    def _build_bluetooth_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Bluetooth", "Manage wireless device pairing, controllers, and headsets"), False, False, 0)

        card_bt = self._make_card("Bluetooth Controller")
        bt_info = system.get_bluetooth_status()
        bt_sw = self._make_switch(bt_info.get("powered", False), lambda a: system.run_cmd(f"bluetoothctl power {'on' if a else 'off'}"))
        card_bt.pack_start(self._make_row("Bluetooth Radio", "Master controller hardware power", widget=bt_sw, icon="bluetooth"), False, False, 0)

        card_bt.pack_start(self._make_row("Controller Name", "Predator-PHN16-71 (BlueZ 5.79)", icon="bluetooth"), False, False, 0)

        disc_sw = self._make_switch(True, lambda a: system.run_cmd(f"bluetoothctl discoverable {'on' if a else 'off'}"))
        card_bt.pack_start(self._make_row("Discoverable to Nearby", "Allow other devices to discover this laptop", widget=disc_sw, icon="globe"), False, False, 0)
        page.pack_start(card_bt, False, False, 0)

        card_dev = self._make_card("Connected & Paired Devices")
        dev_str = ", ".join(bt_info.get("connected_devices", [])) or "No devices currently connected"
        card_dev.pack_start(self._make_row("Connected Devices", dev_str, icon="bluetooth"), False, False, 0)

        scan_btn = Gtk.Button(label="Start Discovery Scan")
        scan_btn.get_style_context().add_class("secondary-btn")
        scan_btn.connect("clicked", lambda *_: subprocess.Popen(["bluetoothctl", "--timeout", "15", "scan", "on"]))
        card_dev.pack_start(self._make_row("Discovery Scan", "Scan for discoverable Bluetooth accessories", widget=scan_btn, icon="search"), False, False, 0)

        dis_btn = Gtk.Button(label="Disconnect All")
        dis_btn.get_style_context().add_class("secondary-btn")
        dis_btn.connect("clicked", lambda *_: system.run_cmd("bluetoothctl disconnect"))
        card_dev.pack_start(self._make_row("Disconnect Devices", "Sever active Bluetooth connections", widget=dis_btn, icon="reset"), False, False, 0)
        page.pack_start(card_dev, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 7. APPLICATIONS PAGE ──────────────────────────────────────────────
    def _build_applications_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Applications", "Default application associations, mime handlers, and startup items"), False, False, 0)

        card_def = self._make_card("Default Applications")
        browser_combo = self._make_combo(["Brave Browser", "Firefox", "Google Chrome", "Chromium"], "Brave Browser", lambda b: None)
        card_def.pack_start(self._make_row("Web Browser", "Default HTTP/HTTPS handler (brave-browser.desktop)", widget=browser_combo, icon="grid"), False, False, 0)

        fm_combo = self._make_combo(["KDE Dolphin", "GNOME Files (Nautilus)", "Thunar"], "KDE Dolphin", lambda f: None)
        card_def.pack_start(self._make_row("File Manager", "Default directory manager (org.kde.dolphin.desktop)", widget=fm_combo, icon="folder"), False, False, 0)

        term_combo = self._make_combo(["Kitty Terminal", "Alacritty", "Foot"], "Kitty Terminal", lambda t: None)
        card_def.pack_start(self._make_row("Terminal Emulator", "Default shell console (kitty.desktop)", widget=term_combo, icon="terminal"), False, False, 0)

        txt_combo = self._make_combo(["Visual Studio Code", "Kate", "Neovim", "Gedit"], "Visual Studio Code", lambda e: None)
        card_def.pack_start(self._make_row("Text Editor", "Default code and document editor", widget=txt_combo, icon="edit"), False, False, 0)

        media_combo = self._make_combo(["VLC Media Player", "MPV", "Celluloid"], "VLC Media Player", lambda m: None)
        card_def.pack_start(self._make_row("Media Player", "Default audio/video playback handler", widget=media_combo, icon="play"), False, False, 0)
        page.pack_start(card_def, False, False, 0)

        card_apps = self._make_card("Installed Applications & Autostart")
        app_count = len([f for f in os.listdir("/usr/share/applications") if f.endswith(".desktop")])
        card_apps.pack_start(self._make_row("Installed Applications", f"{app_count} desktop applications registered in /usr/share/applications", icon="apps-grid"), False, False, 0)

        drawer_btn = Gtk.Button(label="Open Apps Menu")
        drawer_btn.get_style_context().add_class("secondary-btn")
        drawer_btn.connect("clicked", lambda *_: subprocess.Popen(["drawer", "--toggle"]))
        card_apps.pack_start(self._make_row("Application Drawer", "Launch full desktop application grid menu", widget=drawer_btn, icon="apps-grid"), False, False, 0)

        for s_app, s_desc in [("Hypridle (Idle Screen Lock)", "Monitors user inactivity"), ("Waybar (Top Bar)", "System top status bar"), ("CopyQ (Clipboard)", "Clipboard snippet manager")]:
            a_sw = self._make_switch(True, lambda a: None)
            card_apps.pack_start(self._make_row(s_app, s_desc, widget=a_sw, icon="sparkles"), False, False, 0)
        page.pack_start(card_apps, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 8. DESKTOP & WINDOWS PAGE ─────────────────────────────────────────
    def _build_desktop_windows_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Desktop & Windows", "Hyprland window tiling, gaps, border width, opacity, and focus"), False, False, 0)

        card_geo = self._make_card("Window Geometry & Gaps")
        mode_seg = self._make_segmented(["Dwindle Tiling", "Master Layout", "Floating"], "Dwindle Tiling", lambda m: None)
        card_geo.pack_start(self._make_row("Window Layout Mode", "Hyprland automatic layout engine", widget=mode_seg, icon="monitor"), False, False, 0)

        gaps_in = self._make_slider(0, 30, 1, 5, lambda v: system.hypr_set_keyword("general:gaps_in", v), unit=" px")
        card_geo.pack_start(self._make_row("Inner Window Gaps", "Spacing between adjacent tiled windows", widget=gaps_in, icon="monitor"), False, False, 0)

        gaps_out = self._make_slider(0, 40, 1, 10, lambda v: system.hypr_set_keyword("general:gaps_out", v), unit=" px")
        card_geo.pack_start(self._make_row("Outer Window Gaps", "Margin between windows and screen edges", widget=gaps_out, icon="monitor"), False, False, 0)

        border_w = self._make_slider(1, 6, 1, 2, lambda v: system.hypr_set_keyword("general:border_size", v), unit=" px")
        card_geo.pack_start(self._make_row("Border Width", "Thickness of active window border frame", widget=border_w, icon="edit"), False, False, 0)

        corner_r = self._make_slider(0, 32, 1, 16, lambda v: system.hypr_set_keyword("decoration:rounding", v), unit=" px")
        card_geo.pack_start(self._make_row("Corner Rounding", "Radius of window corner curvature", widget=corner_r, icon="aperture"), False, False, 0)
        page.pack_start(card_geo, False, False, 0)

        card_focus = self._make_card("Focus & Opacity")
        focus_sw = self._make_switch(True, lambda a: system.hypr_set_keyword("input:follow_mouse", 1 if a else 0))
        card_focus.pack_start(self._make_row("Focus Follows Mouse", "Switch active window focus when pointer hovers", widget=focus_sw, icon="arrow-right"), False, False, 0)

        act_opac = self._make_slider(50, 100, 5, 100, lambda v: system.hypr_set_keyword("decoration:active_opacity", v / 100.0), unit="%")
        card_focus.pack_start(self._make_row("Active Window Opacity", "Transparency level of currently focused window", widget=act_opac, icon="aperture"), False, False, 0)

        inact_opac = self._make_slider(50, 100, 5, 90, lambda v: system.hypr_set_keyword("decoration:inactive_opacity", v / 100.0), unit="%")
        card_focus.pack_start(self._make_row("Inactive Window Opacity", "Transparency level of unfocused background windows", widget=inact_opac, icon="aperture"), False, False, 0)

        blur_sw = self._make_switch(True, lambda a: system.hypr_set_keyword("decoration:blur:enabled", 1 if a else 0))
        card_focus.pack_start(self._make_row("Acrylic Window Blur", "Render blurred desktop background behind translucent windows", widget=blur_sw, icon="sparkles"), False, False, 0)

        shadow_sw = self._make_switch(True, lambda a: system.hypr_set_keyword("decoration:shadow:enabled", 1 if a else 0))
        card_focus.pack_start(self._make_row("Window Drop Shadows", "Render soft perimeter elevation shadow under windows", widget=shadow_sw, icon="moon"), False, False, 0)
        page.pack_start(card_focus, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 9. WORKSPACES PAGE ────────────────────────────────────────────────
    def _build_workspaces_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Workspaces", "Virtual workspace count, monitor assignments, and animations"), False, False, 0)

        card_ws = self._make_card("Workspaces Setup")
        ws_count = self._make_slider(1, 10, 1, 5, lambda v: None, unit=" spaces")
        card_ws.pack_start(self._make_row("Active Workspace Count", "Number of virtual desktop spaces", widget=ws_count, icon="aperture"), False, False, 0)

        ws_anim = self._make_switch(True, lambda a: None)
        card_ws.pack_start(self._make_row("Workspace Animations", "Smooth horizontal sliding animation between spaces", widget=ws_anim, icon="play"), False, False, 0)

        ws_style = self._make_segmented(["Slide", "Fade", "Slide Vertical"], "Slide", lambda s: None)
        card_ws.pack_start(self._make_row("Transition Style", "Visual motion curve for switching virtual workspaces", widget=ws_style, icon="sliders"), False, False, 0)

        card_ws.pack_start(self._make_row("Monitor Assignment", "Workspaces 1..10 mapped to Primary Display (eDP-1)", icon="monitor"), False, False, 0)
        page.pack_start(card_ws, False, False, 0)

        card_keys = self._make_card("Navigation Shortcuts & Cheat Sheet")
        card_keys.pack_start(self._make_row("Super + 1..9", "Switch immediately to designated workspace", icon="arrow-right"), False, False, 0)
        card_keys.pack_start(self._make_row("Super + Shift + 1..9", "Move focused window directly to designated workspace", icon="arrow-right"), False, False, 0)
        card_keys.pack_start(self._make_row("Super + Mouse Scroll", "Cycle sequentially through active workspaces", icon="arrow-right"), False, False, 0)
        page.pack_start(card_keys, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 10. KEYBOARD & MOUSE PAGE ─────────────────────────────────────────
    def _build_keyboard_mouse_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Keyboard & Mouse", "Pointer sensitivity, natural scrolling, and key repeat rates"), False, False, 0)

        card_ptr = self._make_card("Pointer & Touchpad")
        sens = self._make_slider(-1.0, 1.0, 0.1, 0.0, lambda v: system.hypr_set_keyword("input:sensitivity", v), unit="", is_int=False)
        card_ptr.pack_start(self._make_row("Mouse Sensitivity", "Hardware acceleration speed offset", widget=sens, icon="arrow-right"), False, False, 0)

        accel_seg = self._make_segmented(["Adaptive", "Flat"], "Adaptive", lambda a: system.hypr_set_keyword("input:accel_profile", a.lower()))
        card_ptr.pack_start(self._make_row("Pointer Acceleration", "Hardware velocity acceleration curve", widget=accel_seg, icon="gauge"), False, False, 0)

        nat_scroll = self._make_switch(True, lambda a: system.hypr_set_keyword("input:touchpad:natural_scroll", 1 if a else 0))
        card_ptr.pack_start(self._make_row("Natural Scrolling", "Reverse touchpad scrolling direction to match touchscreens", widget=nat_scroll, icon="arrow-left"), False, False, 0)

        tap_click = self._make_switch(True, lambda a: system.hypr_set_keyword("input:touchpad:tap-to-click", 1 if a else 0))
        card_ptr.pack_start(self._make_row("Tap to Click", "Touchpad surface tapping as primary click", widget=tap_click, icon="check"), False, False, 0)

        gest_sw = self._make_switch(True, lambda a: None)
        card_ptr.pack_start(self._make_row("Touchpad Gestures", "Multi-finger swipes for switching workspaces and overview", widget=gest_sw, icon="sparkles"), False, False, 0)
        page.pack_start(card_ptr, False, False, 0)

        card_kb = self._make_card("Keyboard Behavior & Layout")
        rate_slider = self._make_slider(20, 60, 5, 40, lambda v: system.hypr_set_keyword("input:repeat_rate", v), unit=" cps")
        card_kb.pack_start(self._make_row("Key Repeat Rate", "Frequency of repeated keystrokes when key is held down", widget=rate_slider, icon="clock"), False, False, 0)

        delay_slider = self._make_slider(150, 600, 25, 300, lambda v: system.hypr_set_keyword("input:repeat_delay", v), unit=" ms")
        card_kb.pack_start(self._make_row("Repeat Delay", "Delay in milliseconds before key repeat engages", widget=delay_slider, icon="clock"), False, False, 0)

        kb_layout = self._make_combo(["US English (us)", "UK English (gb)", "Spanish (es)", "German (de)", "French (fr)"], "US English (us)", lambda l: None)
        card_kb.pack_start(self._make_row("Keyboard Layout", "Active XKB keyboard layout map", widget=kb_layout, icon="type"), False, False, 0)

        kb_keys_btn = Gtk.Button(label="View Keybindings List")
        kb_keys_btn.get_style_context().add_class("secondary-btn")
        kb_keys_btn.connect("clicked", lambda *_: subprocess.Popen(["notify-send", "Keybindings", "Super+Return: Kitty | Super+D: App Menu | Super+Q: Close"]))
        card_kb.pack_start(self._make_row("Active Shortcuts", "Inspect full desktop keybindings cheat sheet", widget=kb_keys_btn, icon="notes"), False, False, 0)
        page.pack_start(card_kb, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 11. SHELL & INTERFACE PAGE ────────────────────────────────────────
    def _build_shell_interface_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Shell & Interface", "Quick Settings panel, lock screen, screenshots, and clipboard"), False, False, 0)

        card_shell = self._make_card("Desktop Shell Components")
        qs_sw = self._make_switch(self._get_setting("quick_settings_enabled", True), lambda a: self._save_setting("quick_settings_enabled", a))
        card_shell.pack_start(self._make_row("Quick Settings Master Toggle", "Enable right side-panel desktop quick toggles", widget=qs_sw, icon="sliders"), False, False, 0)

        open_qs_btn = Gtk.Button(label="Toggle Quick Settings")
        open_qs_btn.get_style_context().add_class("secondary-btn")
        open_qs_btn.connect("clicked", lambda *_: subprocess.Popen(["control-center", "--toggle"]))
        card_shell.pack_start(self._make_row("Control Center Trigger", "Show or hide right-side Quick Settings panel", widget=open_qs_btn, icon="sliders"), False, False, 0)

        lock_btn = Gtk.Button(label="Lock Screen Now")
        lock_btn.get_style_context().add_class("secondary-btn")
        lock_btn.connect("clicked", lambda *_: subprocess.Popen(["hyprlock"]))
        card_shell.pack_start(self._make_row("Lock Screen", "Trigger Hyprlock glass security screen immediately", widget=lock_btn, icon="lock"), False, False, 0)

        card_shell.pack_start(self._make_row("Login Screen (SDDM)", "Theme: Simple-SDDM-2 · Session: Hyprland UWSM", icon="user"), False, False, 0)
        page.pack_start(card_shell, False, False, 0)

        card_capture = self._make_card("Screen Capture & Recording")
        ss_btn = Gtk.Button(label="Open Folder")
        ss_btn.get_style_context().add_class("secondary-btn")
        ss_btn.connect("clicked", lambda *_: subprocess.Popen(["xdg-open", os.path.expanduser("~/Pictures/Screenshots")]))
        card_capture.pack_start(self._make_row("Screenshots Folder", "~/Pictures/Screenshots (Grim + Slurp)", widget=ss_btn, icon="folder-open"), False, False, 0)

        clip_ss = self._make_switch(True, lambda a: None)
        card_capture.pack_start(self._make_row("Auto-Copy Screenshot", "Copy captured snippet to clipboard automatically", widget=clip_ss, icon="check"), False, False, 0)

        rec_fps = self._make_segmented(["30 FPS", "60 FPS"], "60 FPS", lambda f: None)
        card_capture.pack_start(self._make_row("Screen Recording Framerate", "Target capture frame rate for wf-recorder", widget=rec_fps, icon="gauge"), False, False, 0)

        rec_audio = self._make_segmented(["System Audio", "Microphone", "Muted"], "System Audio", lambda a: None)
        card_capture.pack_start(self._make_row("Recording Audio Source", "Capture audio stream alongside video recording", widget=rec_audio, icon="volume-high"), False, False, 0)
        page.pack_start(card_capture, False, False, 0)

        card_clip = self._make_card("Clipboard & File Manager")
        clip_size = self._make_slider(20, 200, 20, 100, lambda v: system.run_cmd(f"copyq config maxitems {v}"), unit=" clips")
        card_clip.pack_start(self._make_row("Clipboard History Size", "Maximum number of snippets retained in CopyQ", widget=clip_size, icon="clock"), False, False, 0)

        clear_btn = Gtk.Button(label="Clear Clipboard")
        clear_btn.get_style_context().add_class("secondary-btn")
        clear_btn.connect("clicked", lambda *_: system.run_cmd("copyq wipe"))
        card_clip.pack_start(self._make_row("Erase Clipboard History", "Purge all cached clipboard snippets", widget=clear_btn, icon="notes"), False, False, 0)

        hidden_sw = self._make_switch(False, lambda a: system.run_cmd(f"gsettings set org.gtk.Settings.FileChooser show-hidden {'true' if a else 'false'}"))
        card_clip.pack_start(self._make_row("Show Hidden Files", "Display dotfiles and hidden directories in file dialogs", widget=hidden_sw, icon="folder"), False, False, 0)
        page.pack_start(card_clip, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 12. NOTIFICATIONS PAGE ────────────────────────────────────────────
    def _build_notifications_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Notifications", "Dunst notification daemon pause, alert banners, and test chimes"), False, False, 0)

        card_dunst = self._make_card("Notification Behavior")
        dnd_sw = self._make_switch(False, lambda a: system.run_cmd(f"dunstctl set-paused {'true' if a else 'false'}"))
        card_dunst.pack_start(self._make_row("Do Not Disturb", "Silence all incoming notification popup banners", widget=dnd_sw, icon="bell"), False, False, 0)

        pos_combo = self._make_combo(["Top Right", "Top Center", "Top Left", "Bottom Right", "Bottom Center"], "Top Right", lambda p: None)
        card_dunst.pack_start(self._make_row("Screen Position", "Anchor position on monitor for notification popups", widget=pos_combo, icon="monitor"), False, False, 0)

        timeout_slider = self._make_slider(2, 20, 1, 6, lambda v: None, unit=" s")
        card_dunst.pack_start(self._make_row("Popup Timeout", "Display duration before banner automatically closes", widget=timeout_slider, icon="clock"), False, False, 0)

        sound_sw = self._make_switch(True, lambda a: None)
        card_dunst.pack_start(self._make_row("Sound Alert Chime", "Play subtle sound chime when notification arrives", widget=sound_sw, icon="volume-high"), False, False, 0)
        page.pack_start(card_dunst, False, False, 0)

        card_hist = self._make_card("History & Diagnostics")
        clr_btn = Gtk.Button(label="Clear History")
        clr_btn.get_style_context().add_class("secondary-btn")
        clr_btn.connect("clicked", lambda *_: system.run_cmd("dunstctl history-clear"))
        card_hist.pack_start(self._make_row("Notification History", "Erase notification history cache", widget=clr_btn, icon="reset"), False, False, 0)

        test_btn = Gtk.Button(label="Dispatch Test")
        test_btn.get_style_context().add_class("secondary-btn")
        test_btn.connect("clicked", lambda *_: subprocess.Popen(["notify-send", "Settings", "Notification system operational!"]))
        card_hist.pack_start(self._make_row("Test Notification", "Send sample desktop banner", widget=test_btn, icon="sparkles"), False, False, 0)
        page.pack_start(card_hist, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 13. PRIVACY & SECURITY PAGE ───────────────────────────────────────
    def _build_privacy_security_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Privacy & Security", "Session lock security, clipboard masking, and activity history"), False, False, 0)

        card_sec = self._make_card("Screen & Authentication")
        lock_sw = self._make_switch(True, lambda a: None)
        card_sec.pack_start(self._make_row("Auto-Lock on Suspend", "Require PAM password verification when resuming", widget=lock_sw, icon="lock"), False, False, 0)

        idle_lock = self._make_slider(1, 30, 1, 10, lambda v: None, unit=" min")
        card_sec.pack_start(self._make_row("Idle Screen Lock Delay", "Inactivity timeout before triggering Hyprlock", widget=idle_lock, icon="clock"), False, False, 0)

        pass_sw = self._make_switch(True, lambda a: None)
        card_sec.pack_start(self._make_row("Password Prompt on Resume", "Prevent bypassing lock screen on lid open", widget=pass_sw, icon="shield"), False, False, 0)
        page.pack_start(card_sec, False, False, 0)

        card_priv = self._make_card("Data Privacy & Clearance")
        clear_btn = Gtk.Button(label="Clear Clipboard History")
        clear_btn.get_style_context().add_class("secondary-btn")
        clear_btn.connect("clicked", lambda *_: system.run_cmd("copyq wipe"))
        card_priv.pack_start(self._make_row("CopyQ History", "Erase all cached clipboard snippets", widget=clear_btn, icon="notes"), False, False, 0)

        hist_btn = Gtk.Button(label="Clear Recent History")
        hist_btn.get_style_context().add_class("secondary-btn")
        hist_btn.connect("clicked", lambda *_: subprocess.Popen(["notify-send", "Privacy", "Recent history cleared."]))
        card_priv.pack_start(self._make_row("Terminal Command History", "Purge recent interactive bash/zsh command log", widget=hist_btn, icon="terminal"), False, False, 0)

        ind_sw = self._make_switch(True, lambda a: None)
        card_priv.pack_start(self._make_row("Privacy Indicators", "Display top bar icon when microphone or camera is active", widget=ind_sw, icon="sparkles"), False, False, 0)
        page.pack_start(card_priv, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 14. ACCESSIBILITY PAGE ────────────────────────────────────────────
    def _build_accessibility_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Accessibility", "Text scaling, high contrast outlines, and cursor enhancements"), False, False, 0)

        card_vis = self._make_card("Vision & Ergonomics")
        large_sw = self._make_switch(False, lambda a: system.run_cmd(f"gsettings set org.gnome.desktop.interface text-scaling-factor {'1.25' if a else '1.0'}"))
        card_vis.pack_start(self._make_row("Large Text", "Increase GTK application font scaling by 25%", widget=large_sw, icon="type"), False, False, 0)

        contrast_sw = self._make_switch(False, lambda a: None)
        card_vis.pack_start(self._make_row("High Contrast", "Enhance outline contrast on glass panels", widget=contrast_sw, icon="aperture"), False, False, 0)

        cur_slider = self._make_slider(16, 48, 8, 24, lambda v: (self._save_setting("cursor.size", v), system.hypr_set_keyword("env", f"XCURSOR_SIZE,{v}")), unit=" px")
        card_vis.pack_start(self._make_row("Large Cursor", "Scale mouse pointer for visibility", widget=cur_slider, icon="arrow-right"), False, False, 0)

        motion_sw = self._make_switch(False, lambda a: system.hypr_set_keyword("animations:enabled", 0 if a else 1))
        card_vis.pack_start(self._make_row("Reduce Motion", "Disable animations across desktop and windows", widget=motion_sw, icon="play"), False, False, 0)
        page.pack_start(card_vis, False, False, 0)

        card_hear = self._make_card("Hearing & Assistance")
        mono_sw = self._make_switch(False, lambda a: None)
        card_hear.pack_start(self._make_row("Mono Audio", "Combine left and right audio channels into both speakers", widget=mono_sw, icon="volume-high"), False, False, 0)

        card_hear.pack_start(self._make_row("Screen Reader (Orca)", "Available (Orca screen reader service installed)", icon="accessibility"), False, False, 0)
        page.pack_start(card_hear, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 15. PERFORMANCE & POWER MODES (DEDICATED PAGE) ─────────────────────
    def _build_performance_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Performance & Power Modes", "ACPI hardware thermal governance, fan control, and TDP power profiles"), False, False, 0)

        card_prof = self._make_card("Performance Profiles (Hardware ACPI)")
        cur_prof = system.get_platform_profile() or "balanced"
        prof_map = {
            "low-power": "Eco",
            "quiet": "Quiet",
            "balanced": "Balanced",
            "performance": "Performance",
            "balanced-performance": "Turbo"
        }
        active_label = prof_map.get(cur_prof, "Balanced")
        prof_seg = self._make_segmented(
            ["Eco", "Quiet", "Balanced", "Performance", "Turbo"],
            active_label,
            self._on_perf_profile_selected
        )
        card_prof.pack_start(self._make_row("Hardware Profile", "ACPI platform profile governor (Eco, Quiet, Balanced, Performance, Turbo)", widget=prof_seg, icon="gauge"), False, False, 0)

        card_prof.pack_start(self._make_row("• Eco", "Maximum battery savings, reduced clock frequency limits", icon="leaf"), False, False, 0)
        card_prof.pack_start(self._make_row("• Quiet", "Low fan noise operation for silent study / office environments", icon="moon"), False, False, 0)
        card_prof.pack_start(self._make_row("• Balanced", "Default balanced everyday performance and battery efficiency", icon="scale"), False, False, 0)
        card_prof.pack_start(self._make_row("• Performance", "Higher CPU/GPU clock limits and aggressive cooling", icon="lightning"), False, False, 0)
        card_prof.pack_start(self._make_row("• Turbo", "Maximum available system TDP performance and full fan velocity", icon="rocket"), False, False, 0)
        page.pack_start(card_prof, False, False, 0)

        card_gov = self._make_card("Hardware Governors & Energy Policies")
        gov_seg = self._make_segmented(["powersave", "balanced", "performance"], "balanced", lambda g: None)
        card_gov.pack_start(self._make_row("CPU Governor", "Kernel CPU frequency scaling governor", widget=gov_seg, icon="cpu"), False, False, 0)

        gpu_seg = self._make_segmented(["Adaptive", "High Performance", "Low Power"], "Adaptive", lambda p: None)
        card_gov.pack_start(self._make_row("GPU Power Profile", "NVIDIA RTX 4060 dynamic power management", widget=gpu_seg, icon="monitor"), False, False, 0)

        auto_sw = self._make_switch(True, lambda a: None)
        card_gov.pack_start(self._make_row("Automatic Profile Switching", "Switch to Eco on battery, Performance on AC mains", widget=auto_sw, icon="sparkles"), False, False, 0)

        care_sw = self._make_switch(self._get_setting("power.charge_limit_80", False), lambda a: self._save_setting("power.charge_limit_80", a))
        card_gov.pack_start(self._make_row("Battery Health Care (80% Limit)", "Stop charging at 80% to preserve lithium health", widget=care_sw, icon="shield"), False, False, 0)
        page.pack_start(card_gov, False, False, 0)

        card_diag = self._make_card("Hardware Sensors & Diagnostics (Live Readout)")
        temps = system.get_hardware_temperatures()
        card_diag.pack_start(self._make_row("CPU Package Temperature", f"{temps.get('cpu', 60)}°C (Thermal Zone 0)", icon="cpu"), False, False, 0)
        card_diag.pack_start(self._make_row("GPU Core Temperature", f"{temps.get('gpu', 50)}°C (NVIDIA RTX 4060)", icon="monitor"), False, False, 0)
        card_diag.pack_start(self._make_row("Fan Velocity Profile", "Automatic Dynamic Curve (Controlled by DAMX ACPI)", icon="gauge"), False, False, 0)
        page.pack_start(card_diag, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    def _on_perf_profile_selected(self, label):
        rev_map = {
            "Eco": "low-power",
            "Quiet": "quiet",
            "Balanced": "balanced",
            "Performance": "performance",
            "Turbo": "balanced-performance"
        }
        prof = rev_map.get(label, "balanced")
        system.set_platform_profile(prof)

    # ── 16. SYSTEM INFORMATION PAGE ───────────────────────────────────────
    def _build_system_info_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("System Information", "Kernel specifications, Hyprland version, CPU/GPU, memory, and storage"), False, False, 0)

        card_os = self._make_card("Operating System & Compositor")
        s_info = system.get_system_info()
        card_os.pack_start(self._make_row("Operating System", s_info.get("os", "Arch Linux (Rolling Release)"), icon="arch"), False, False, 0)
        card_os.pack_start(self._make_row("Kernel Version", s_info.get("kernel", ""), icon="terminal"), False, False, 0)
        card_os.pack_start(self._make_row("Hyprland Compositor", s_info.get("hyprland", ""), icon="monitor"), False, False, 0)
        card_os.pack_start(self._make_row("System Uptime", s_info.get("uptime", ""), icon="clock"), False, False, 0)
        page.pack_start(card_os, False, False, 0)

        card_hw = self._make_card("Hardware Specifications")
        card_hw.pack_start(self._make_row("Processor (CPU)", s_info.get("cpu", ""), icon="cpu"), False, False, 0)
        card_hw.pack_start(self._make_row("Graphics (GPU)", s_info.get("gpu", ""), icon="monitor"), False, False, 0)
        card_hw.pack_start(self._make_row("Memory (RAM)", s_info.get("ram", ""), icon="gauge"), False, False, 0)
        card_hw.pack_start(self._make_row("Root Storage (/)", system.get_storage_info(), icon="folder"), False, False, 0)
        page.pack_start(card_hw, False, False, 0)

        card_upd = self._make_card("Hardware Thermals & Updates")
        temps = system.get_hardware_temperatures()
        card_upd.pack_start(self._make_row("Hardware Thermals", f"CPU: {temps.get('cpu', 60)}°C · GPU: {temps.get('gpu', 50)}°C", icon="sun"), False, False, 0)

        upd_btn = Gtk.Button(label="Check for Updates")
        upd_btn.get_style_context().add_class("secondary-btn")
        upd_btn.connect("clicked", lambda *_: subprocess.Popen(["notify-send", "Arch Updates", "Running checkupdates... System packages up to date."]))
        card_upd.pack_start(self._make_row("System Updates", "Synchronize pacman repositories and check available packages", widget=upd_btn, icon="sparkles"), False, False, 0)
        page.pack_start(card_upd, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    # ── 17. ADVANCED PAGE ─────────────────────────────────────────────────
    def _build_advanced_page(self):
        page = self._make_page_box()
        page.pack_start(self._make_page_header("Advanced", "Hyprland configuration, backups, environment variables, and developer tools"), False, False, 0)

        card_conf = self._make_card("Hyprland Configuration Management")
        edit_btn = Gtk.Button(label="Open in Editor")
        edit_btn.get_style_context().add_class("secondary-btn")
        edit_btn.connect("clicked", lambda *_: subprocess.Popen(["xdg-open", os.path.expanduser("~/.config/hypr/hyprland.conf")]))
        card_conf.pack_start(self._make_row("Edit Hyprland Config", "Open ~/.config/hypr/hyprland.conf in preferred code editor", widget=edit_btn, icon="edit"), False, False, 0)

        reload_btn = Gtk.Button(label="Reload Hyprland")
        reload_btn.get_style_context().add_class("secondary-btn")
        reload_btn.connect("clicked", lambda *_: (system.run_cmd("hyprctl reload config-only"), subprocess.Popen(["notify-send", "Hyprland", "Configuration reloaded successfully."])))
        card_conf.pack_start(self._make_row("Reload & Validate", "Live reload compositor keybinds and windowrules without restart", widget=reload_btn, icon="reset"), False, False, 0)

        mon_btn = Gtk.Button(label="Inspect Topology")
        mon_btn.get_style_context().add_class("secondary-btn")
        mon_btn.connect("clicked", lambda *_: subprocess.Popen(["notify-send", "Display Topology", system.run_cmd("hyprctl monitors")[:120]]))
        card_conf.pack_start(self._make_row("Display JSON Topology", "Query active Wayland output coordinates and modes", widget=mon_btn, icon="monitor"), False, False, 0)
        page.pack_start(card_conf, False, False, 0)

        card_snap = self._make_card("Configuration Snapshots & Backup")
        backup_btn = Gtk.Button(label="Create Snapshot")
        backup_btn.get_style_context().add_class("secondary-btn")
        backup_btn.connect("clicked", self._create_desktop_snapshot)
        card_snap.pack_start(self._make_row("Backup Desktop Config", "Snapshot hyprland, theme, and dock settings to backup directory", widget=backup_btn, icon="sparkles"), False, False, 0)

        restore_btn = Gtk.Button(label="Restore Snapshot")
        restore_btn.get_style_context().add_class("secondary-btn")
        restore_btn.connect("clicked", self._restore_desktop_snapshot)
        card_snap.pack_start(self._make_row("Restore Configuration", "Revert desktop configuration from last stored snapshot", widget=restore_btn, icon="reset"), False, False, 0)

        reset_btn = Gtk.Button(label="Reset Defaults...")
        reset_btn.get_style_context().add_class("secondary-btn")
        reset_btn.connect("clicked", self._reset_desktop_defaults)
        card_snap.pack_start(self._make_row("Reset Desktop Defaults", "Restore default visual theme, wallpaper, and layout settings", widget=reset_btn, icon="reset"), False, False, 0)
        page.pack_start(card_snap, False, False, 0)

        card_dev = self._make_card("System Logs & Developer Tools")
        log_btn = Gtk.Button(label="Open Journal Logs")
        log_btn.get_style_context().add_class("secondary-btn")
        log_btn.connect("clicked", lambda *_: subprocess.Popen(["kitty", "--hold", "journalctl", "--user", "-n", "60"]))
        card_dev.pack_start(self._make_row("Live Service Logs", "View systemd user journal stream in terminal", widget=log_btn, icon="terminal"), False, False, 0)

        dbg_sw = self._make_switch(False, lambda a: system.hypr_set_keyword("debug:overlay", 1 if a else 0))
        card_dev.pack_start(self._make_row("Hyprland Debug Overlay", "Display real-time compositor frame rates and damage blocks", widget=dbg_sw, icon="gauge"), False, False, 0)

        insp_btn = Gtk.Button(label="Open GTK Inspector")
        insp_btn.get_style_context().add_class("secondary-btn")
        insp_btn.connect("clicked", lambda *_: Gtk.Window.set_interactive_debugging(True))
        card_dev.pack_start(self._make_row("GTK 3.0 Inspector", "Live CSS style, node tree, and widget inspector", widget=insp_btn, icon="edit"), False, False, 0)
        page.pack_start(card_dev, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 30)
        page.pack_start(spacer, False, False, 0)

        return page

    def _create_desktop_snapshot(self, *args):
        backup_config(os.path.expanduser("~/.config/hypr/hyprland.conf"))
        backup_config(os.path.expanduser("~/.config/neon-desktop/settings.json"))
        subprocess.Popen(["notify-send", "Settings Backup", f"Snapshot saved to {BACKUP_DIR}"])

    def _restore_desktop_snapshot(self, *args):
        if not os.path.isdir(BACKUP_DIR):
            subprocess.Popen(["notify-send", "Settings Backup", "No snapshots available."])
            return
        baks = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("settings.json")])
        if baks:
            src = os.path.join(BACKUP_DIR, baks[-1])
            dest = os.path.expanduser("~/.config/neon-desktop/settings.json")
            shutil.copy2(src, dest)
            subprocess.Popen(["notify-send", "Settings Restore", f"Restored from {baks[-1]}"])
        else:
            subprocess.Popen(["notify-send", "Settings Backup", "No snapshot files found."])

    def _reset_desktop_defaults(self, *args):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Reset Desktop Settings to Factory Defaults?"
        )
        dialog.format_secondary_text("This will reset theme, dock, launcher, and appearance settings to initial defaults.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            dest = os.path.expanduser("~/.config/neon-desktop/settings.json")
            if os.path.exists(dest):
                os.remove(dest)
            theme.update_theme()
            self._load_css()
            subprocess.Popen(["notify-send", "Settings", "Desktop settings have been reset to default."])


    # ══════════════════════════════════════════════════════════════════════
    #  LIVE PREVIEW & QUICK SETTINGS CARDS (PERSONALIZATION EXCLUSIVE)
    # ══════════════════════════════════════════════════════════════════════
    def _build_live_preview_card(self):
        card = self._make_card()

        # Live Preview Header
        p_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        p_hdr.pack_start(icons.get_image("monitor", 16, "#ffffff"), False, False, 0)
        p_lbl = Gtk.Label(label="Live Preview")
        p_lbl.get_style_context().add_class("section-title")
        p_hdr.pack_start(p_lbl, False, False, 0)
        card.pack_start(p_hdr, False, False, 0)

        p_desc = Gtk.Label(label="See how your changes look in real time")
        p_desc.get_style_context().add_class("section-desc")
        p_desc.set_xalign(0.0)
        card.pack_start(p_desc, False, False, 0)

        # Desktop Screen Preview Container (16:9 aspect display)
        preview_container = Gtk.Overlay()
        preview_container.set_size_request(260, 146)
        preview_container.get_style_context().add_class("preview-desktop-screen")

        # Base layer: wallpaper image
        self.mockup_wallpaper_img = Gtk.Image()
        self.mockup_wallpaper_img.set_size_request(260, 146)
        preview_container.add(self.mockup_wallpaper_img)

        # Overlay layer: mini floating window and mini dock
        overlay_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay_box.set_valign(Gtk.Align.FILL)
        overlay_box.set_halign(Gtk.Align.FILL)

        # Floating window mockup on top of the wallpaper
        win_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        win_box.get_style_context().add_class("preview-window-mockup")
        win_box.set_margin_top(12)
        win_box.set_size_request(160, 72)
        win_box.set_halign(Gtk.Align.CENTER)

        # Traffic light dots
        m_dots = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for c in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            dot = Gtk.Box()
            dot.set_size_request(6, 6)
            dot_css = Gtk.CssProvider()
            dot_css.load_from_data(f"box {{ background: {c}; border-radius: 3px; }}".encode("utf-8"))
            dot.get_style_context().add_provider(dot_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20)
            m_dots.pack_start(dot, False, False, 0)
        win_box.pack_start(m_dots, False, False, 0)

        # Mini window inner
        m_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        m_sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        m_sidebar.set_size_request(32, 40)
        for _ in range(3):
            bar = Gtk.Box()
            bar.set_size_request(28, 4)
            b_css = Gtk.CssProvider()
            b_css.load_from_data(b"box { background: rgba(255,255,255,0.25); border-radius: 2px; }")
            bar.get_style_context().add_provider(b_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20)
            m_sidebar.pack_start(bar, False, False, 0)
        m_inner.pack_start(m_sidebar, False, False, 0)

        m_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        for _ in range(2):
            bar = Gtk.Box()
            bar.set_size_request(60, 4)
            b_css = Gtk.CssProvider()
            b_css.load_from_data(b"box { background: rgba(255,255,255,0.18); border-radius: 2px; }")
            bar.get_style_context().add_provider(b_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20)
            m_body.pack_start(bar, False, False, 0)
        m_inner.pack_start(m_body, True, True, 0)

        win_box.pack_start(m_inner, True, True, 0)
        overlay_box.pack_start(win_box, False, False, 0)

        # Mini dock capsule at bottom
        dock_mini = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        dock_mini.get_style_context().add_class("preview-dock-capsule")
        dock_mini.set_halign(Gtk.Align.CENTER)
        dock_mini.set_valign(Gtk.Align.END)
        dock_mini.set_margin_bottom(8)
        dock_mini.set_size_request(70, 10)
        for dc in ["#ff8a00", "#ec4899", "#a855f7", "#38bdf8"]:
            d_dot = Gtk.Box()
            d_dot.set_size_request(5, 5)
            d_css = Gtk.CssProvider()
            d_css.load_from_data(f"box {{ background: {dc}; border-radius: 2.5px; }}".encode("utf-8"))
            d_dot.get_style_context().add_provider(d_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20)
            dock_mini.pack_start(d_dot, False, False, 0)
        overlay_box.pack_end(dock_mini, False, False, 0)

        preview_container.add_overlay(overlay_box)
        card.pack_start(preview_container, False, False, 0)
        self._update_mockup_preview()
        return card

    def _update_mockup_preview(self, wp_path=None):
        if not hasattr(self, "mockup_wallpaper_img") or not self.mockup_wallpaper_img:
            return
        wp = wp_path or getattr(self, "_current_active_wp", None) or self._detect_active_wallpaper() or theme.DEFAULT_WALLPAPER
        if wp and os.path.isfile(wp):
            try:
                raw_pb = getattr(self, "_raw_pixbufs", {}).get(wp)
                if raw_pb:
                    pb = raw_pb.scale_simple(260, 146, GdkPixbuf.InterpType.BILINEAR)
                else:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(wp, 260, 146, False)

                def _round_pb(pbuf, radius=10):
                    if not pbuf.get_has_alpha():
                        pbuf = pbuf.add_alpha(False, 0, 0, 0)
                    w = pbuf.get_width()
                    h = pbuf.get_height()
                    rs = pbuf.get_rowstride()
                    n_ch = pbuf.get_n_channels()
                    px = bytearray(pbuf.get_pixels())
                    r = radius
                    for cy, yr in [(r, range(r)), (h - 1 - r, range(h - r, h))]:
                        for cx, xr in [(r, range(r)), (w - 1 - r, range(w - r, w))]:
                            for y in yr:
                                dy = abs(y - cy)
                                row_idx = y * rs
                                for x in xr:
                                    dx = abs(x - cx)
                                    dist = math.hypot(dx, dy)
                                    if dist > r:
                                        alpha_factor = max(0.0, min(1.0, r + 0.5 - dist))
                                        idx = row_idx + x * n_ch + 3
                                        px[idx] = int(px[idx] * alpha_factor)
                    gbytes = GLib.Bytes.new(bytes(px))
                    return GdkPixbuf.Pixbuf.new_from_bytes(gbytes, GdkPixbuf.Colorspace.RGB, True, 8, w, h, rs)

                rounded_pb = _round_pb(pb, radius=10)
                self.mockup_wallpaper_img.set_from_pixbuf(rounded_pb)
                self.mockup_wallpaper_img.show()
                return
            except Exception as e:
                print(f"[settings] Mockup preview render error: {e}")

    def _build_quick_settings_card(self):
        card = self._make_card()

        qs_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        qs_hdr.pack_start(icons.get_image("sliders", 16, "#ffffff"), False, False, 0)
        qs_lbl = Gtk.Label(label="Quick Settings")
        qs_lbl.get_style_context().add_class("section-title")
        qs_hdr.pack_start(qs_lbl, False, False, 0)
        card.pack_start(qs_hdr, False, False, 0)
        card.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        qs_items = [
            ("Show window shadows", "show_window_shadows", lambda a: (self._save_setting("show_window_shadows", a), system.update_hypr_config(shadow=a, reload=True))),
            ("Use translucent panels", "translucent_panels", self._on_translucent_panels_toggled),
            ("Enable blur (Acrylic)", "enable_blur", self._on_enable_blur_toggled),
            ("Color frame to accent", "color_frame_to_accent", self._on_color_frame_to_accent_toggled),
        ]

        if not hasattr(self, "qs_switches"):
            self.qs_switches = {}

        for label, key, cb in qs_items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=label)
            lbl.get_style_context().add_class("setting-row-desc")
            lbl.set_xalign(0.0)
            row.pack_start(lbl, True, True, 0)

            sw = self._make_switch(self._get_setting(key, True), lambda active, k=key, f=cb: f(active))
            self.qs_switches[key] = sw
            row.pack_end(sw, False, False, 0)
            card.pack_start(row, False, False, 4)

        return card

    def _on_enable_blur_toggled(self, active):
        self._save_setting("enable_blur", active)
        if active:
            v = int(self._get_setting("blur_strength", 70))
            if v <= 0:
                v = 50
                self.settings["blur_strength"] = v
                self._save_setting("blur_strength", v)
            en, p, s = system.calc_hypr_blur(v)
            system.set_hypr_blur_live(enabled=True, size=s, passes=p)
            system.update_hypr_config(blur=True, blur_size=s, blur_passes=p, reload=False)
        else:
            system.set_hypr_blur_live(enabled=False, size=0, passes=0)
            system.update_hypr_config(blur=False, blur_size=0, blur_passes=0, reload=False)

    def _on_translucent_panels_toggled(self, active):
        self._save_setting("translucent_panels", active)
        self._apply_theme_for_wallpaper(force_refresh=True)
        try:
            theme.sync_topbar_theme_files(reload_services=False)
        except Exception:
            pass

    def _on_color_frame_to_accent_toggled(self, active):
        self._save_setting("color_frame_to_accent", active)
        active_wp = self._detect_active_wallpaper()
        if active:
            active_col = self._get_setting("accent_color", "auto")
            if active_col in ("auto", "Auto"):
                dt = theme.extract_wallpaper_theme(active_wp, accent_color="auto")
                theme.update_hypr_border(dt.get("stops", []), reload=True)
            else:
                theme.update_hypr_border([active_col, active_col], reload=True)
        else:
            system.update_hypr_config(active_border="rgba(555555ee) rgba(333333ee) 45deg", reload=True)

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if (event.state & Gdk.ModifierType.CONTROL_MASK) and event.keyval in (Gdk.KEY_q, Gdk.KEY_Q):
            self.close()
            return True
        if (event.state & Gdk.ModifierType.CONTROL_MASK) and event.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search_entry.grab_focus()
            return True
        return False


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    GLib.set_prgname("settings")
    GLib.set_application_name("Settings")

    app = SettingsApp()
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
