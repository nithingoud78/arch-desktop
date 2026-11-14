#!/usr/bin/env python3
"""
Neon Desktop — Adaptive Sunset Glass App Drawer (neon-drawer)
Matches the reference design of "Neon Glass App Launcher at Sunset"
Features:
- Ultra-glassy centered frosted card with glowing multi-stop neon gradient border
- 4-square grid button (matching the reference image)
- Pin tool button replacing tag: click to filter taskbar pinned apps
- 9 sidebar category pills with live application count badges
- 6-column squircle grid with compact 58x58 tiles and multi-line wrapped full app names
- Sleek glass List View with theme-harmonized dark cards
- Right-click context menu:
  - "Pin to taskbar" / "Unpin from taskbar" (live updates bottom dock)
  - "Rename" (menu-only custom display name stored in ~/.config/neon-desktop/app_names.json)
  - "Reset name" (reverts to original desktop app name)
  - "Open Application"
- Full wallpaper-derived reactive theming
"""

import os
import sys
import json
import socket
import select
import signal
import threading
import subprocess
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Gio', '2.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, Gdk, Gio, GdkPixbuf, GLib, Pango, GtkLayerShell

# Add shared modules to path
POSSIBLE_SHARED = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared")),
    "/home/nithin/Projects/arch-desktop/shared",
    "/home/nithin/Projects/neon-desktop/shared",
    os.path.expanduser("~/.config/neon-desktop/shared")
]
for p in POSSIBLE_SHARED:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

import theme
import icons
import dock_pin
import config

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
DRAWER_THEME_FILE = os.path.join(CONFIG_DIR, "drawer_theme.json")
DRAWER_CSS_FILE = os.path.join(CONFIG_DIR, "drawer.css")
APP_NAMES_FILE = os.path.join(CONFIG_DIR, "app_names.json")
PID_FILE = f"/tmp/neon-drawer-{os.getuid()}.pid"

CATEGORY_DEFINITIONS = [
    ("all", "All Apps", "apps-grid", []),
    ("dev", "Development", "code", ["Development", "IDE", "Programming", "Debugger", "Building"]),
    ("creative", "Creative", "palette", ["Graphics", "2DGraphics", "RasterGraphics", "VectorGraphics", "Photography", "AudioVideoEditing", "Design", "Art"]),
    ("internet", "Internet", "globe", ["Network", "WebBrowser", "Email", "Chat", "InstantMessaging", "FileTransfer"]),
    ("media", "Media", "play-circle", ["AudioVideo", "Audio", "Video", "Player", "Recorder", "Music"]),
    ("system", "System", "settings", ["System", "Settings", "PackageManager", "Monitor", "TerminalEmulator", "HardwareSettings"]),
    ("utility", "Utilities", "box", ["Utility", "Core", "FileManager", "Archiving", "Calculator", "TextEditor", "Office", "Spreadsheet", "WordProcessor"]),
    ("games", "Games", "gamepad", ["Game", "Emulator"]),
    ("other", "Other", "more", [])
]


def load_custom_names():
    if os.path.isfile(APP_NAMES_FILE):
        try:
            with open(APP_NAMES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_custom_names(names):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(APP_NAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(names, f, indent=2)


class NeonDrawerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self.active_category = "all"
        self.show_pinned_only = False
        self.view_mode = "grid"  # "grid" or "list"
        self.search_query = ""
        self.apps = []
        self.category_counts = {cat[0]: 0 for cat in CATEGORY_DEFINITIONS}
        self.category_widgets = {}
        self._active_modal = None

        # Theme mode
        self.theme_mode = config.load_settings().get("theme_mode", "Dark")
        if self.theme_mode not in ("Light", "Dark"):
            self.theme_mode = "Dark"
        self._icon_col = "#1e293b" if self.theme_mode == "Light" else "#ffffff"

        # Layer Shell setup
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        GtkLayerShell.set_namespace(self, "neon-drawer")

        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)

        self.set_name("drawer-window")
        self.set_decorated(False)
        self.set_app_paintable(True)

        # Style provider
        self.css_provider = Gtk.CssProvider()
        self._apply_css()

        # Load apps
        self._load_desktop_apps()

        # Build UI
        self._build_ui()

        # Key events & dismiss
        self.connect("key-press-event", self._on_key_press)

    def _apply_css(self):
        try:
            dt, colors = theme.load_drawer_theme()
            t_mode = getattr(self, "theme_mode", "Dark")
            css_data = theme.build_neon_drawer_css(dt, colors, theme_mode=t_mode)
            self.css_provider.load_from_data(css_data.encode("utf-8"))
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        except Exception:
            if not os.path.isfile(DRAWER_CSS_FILE):
                theme.sync_topbar_theme_files()
            try:
                if os.path.isfile(DRAWER_CSS_FILE):
                    with open(DRAWER_CSS_FILE, "r") as f:
                        css_data = f.read()
                    self.css_provider.load_from_data(css_data.encode("utf-8"))
                    Gtk.StyleContext.add_provider_for_screen(
                        Gdk.Screen.get_default(),
                        self.css_provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_USER
                    )
            except Exception as e:
                print(f"[neon-drawer] Error applying CSS: {e}")

    def _load_desktop_apps(self):
        all_apps = Gio.DesktopAppInfo.get_all()
        custom_names = load_custom_names()
        visible = []
        counts = {cat[0]: 0 for cat in CATEGORY_DEFINITIONS}

        for app in all_apps:
            if not app.should_show():
                continue

            app_id = app.get_id() or ""
            clean_id = app_id.replace(".desktop", "")
            orig_name = app.get_name() or clean_id
            display_name = custom_names.get(clean_id, orig_name)

            cats_str = app.get_categories() or ""
            cats = [c.strip() for c in cats_str.split(";") if c.strip()]
            comment = app.get_description() or ""
            executable = app.get_executable() or ""

            # Classify category
            assigned_cat = "other"
            for cat_id, _, _, keywords in CATEGORY_DEFINITIONS:
                if cat_id in ("all", "other"):
                    continue
                if any(kw in cats for kw in keywords):
                    assigned_cat = cat_id
                    break

            app_data = {
                "id": app_id,
                "clean_id": clean_id,
                "name": display_name,
                "original_name": orig_name,
                "is_custom_named": (clean_id in custom_names),
                "comment": comment,
                "executable": executable,
                "categories": cats,
                "category": assigned_cat,
                "app_info": app,
                "icon": app.get_icon()
            }
            visible.append(app_data)
            counts[assigned_cat] += 1

        # Sort alphabetically by current display name
        visible.sort(key=lambda a: a["name"].lower())
        counts["all"] = len(visible)

        self.apps = visible
        self.category_counts = counts

    def _build_ui(self):
        # Click-to-dismiss Backdrop (subtle tint letting wallpaper shine through)
        self.backdrop_event = Gtk.EventBox()
        self.backdrop_event.set_name("drawer-backdrop")
        self.backdrop_event.connect("button-press-event", self._on_backdrop_clicked)
        self.add(self.backdrop_event)

        # Centered Layout Box with breathing margin for outer glow
        center_align = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_align.set_halign(Gtk.Align.CENTER)
        center_align.set_valign(Gtk.Align.CENTER)
        center_align.set_margin_top(36)
        center_align.set_margin_bottom(36)
        center_align.set_margin_start(36)
        center_align.set_margin_end(36)
        self.backdrop_event.add(center_align)

        # Outer Glowing Multi-Stop Gradient Border Box
        self.card_border = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card_border.set_name("launcher-card-border")
        self.card_border.set_size_request(1060, 645)
        center_align.pack_start(self.card_border, False, False, 0)

        # Card Overlay for in-card modal prompts
        self.card_overlay = Gtk.Overlay()
        self.card_border.pack_start(self.card_overlay, True, True, 0)

        # Inner Translucent Frosted Glass Box
        self.card_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.card_inner.set_name("launcher-card-inner")
        self.card_overlay.add(self.card_inner)

        # 1. Header Area
        self._build_header()

        # 2. Main Horizontal Split (Sidebar + Content Area)
        main_body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        main_body.set_vexpand(True)
        self.card_inner.pack_start(main_body, True, True, 0)

        # 2a. Sidebar
        self._build_sidebar(main_body)

        # 2b. Content Area
        self._build_content_area(main_body)

    def _build_header(self):
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.set_name("launcher-header")

        # Left: Back Arrow Button
        back_btn = Gtk.Button()
        back_btn.set_name("back-btn")
        back_btn.set_relief(Gtk.ReliefStyle.NONE)
        back_btn.set_size_request(38, 38)
        back_img = icons.get_image("arrow-left", 18, self._icon_col)
        back_btn.add(back_img)
        back_btn.connect("clicked", lambda *_: self.close_drawer())
        header_box.pack_start(back_btn, False, False, 0)

        # Title & Subtitle
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.title_label = Gtk.Label(label="All Applications")
        self.title_label.set_name("header-title")
        self.title_label.set_xalign(0.0)

        self.subtitle_label = Gtk.Label(label="Installed applications on your system")
        self.subtitle_label.set_name("header-subtitle")
        self.subtitle_label.set_xalign(0.0)

        title_box.pack_start(self.title_label, False, False, 0)
        title_box.pack_start(self.subtitle_label, False, False, 0)
        header_box.pack_start(title_box, True, True, 4)

        # Right Tool Buttons
        tools_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # 1. Grid view button (4-squares matching reference image)
        self.btn_grid = Gtk.Button()
        self.btn_grid.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_grid.get_style_context().add_class("tool-btn")
        self.btn_grid.get_style_context().add_class("active")
        self.btn_grid.set_size_request(38, 38)
        self.btn_grid.set_tooltip_text("Grid View")
        grid_img = icons.get_image("apps-grid", 18, self._icon_col)
        self.btn_grid.add(grid_img)
        self.btn_grid.connect("clicked", lambda *_: self._set_view_mode("grid"))
        tools_box.pack_start(self.btn_grid, False, False, 0)

        # 2. List view button
        self.btn_list = Gtk.Button()
        self.btn_list.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_list.get_style_context().add_class("tool-btn")
        self.btn_list.set_size_request(38, 38)
        self.btn_list.set_tooltip_text("List View")
        list_img = icons.get_image("list", 18, self._icon_col)
        self.btn_list.add(list_img)
        self.btn_list.connect("clicked", lambda *_: self._set_view_mode("list"))
        tools_box.pack_start(self.btn_list, False, False, 0)

        # 3. Pin Filter button (replaces tag icon with pin icon)
        self.btn_pin = Gtk.Button()
        self.btn_pin.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_pin.get_style_context().add_class("tool-btn")
        self.btn_pin.set_size_request(38, 38)
        self.btn_pin.set_tooltip_text("Show Pinned Taskbar Apps")
        pin_img = icons.get_image("pin", 18, self._icon_col)
        self.btn_pin.add(pin_img)
        self.btn_pin.connect("clicked", self._on_pin_filter_clicked)
        tools_box.pack_start(self.btn_pin, False, False, 0)

        # 4. Settings button
        self.btn_settings = Gtk.Button()
        self.btn_settings.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_settings.get_style_context().add_class("tool-btn")
        self.btn_settings.set_size_request(38, 38)
        self.btn_settings.set_tooltip_text("Control Center & Settings")
        settings_png = os.path.expanduser("~/.local/share/icons/settings.png")
        if os.path.isfile(settings_png):
            try:
                gicon = Gio.FileIcon.new(Gio.File.new_for_path(settings_png))
                settings_img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.BUTTON)
                settings_img.set_pixel_size(20)
            except Exception:
                settings_img = icons.get_image("settings", 18, self._icon_col)
        else:
            settings_img = icons.get_image("settings", 18, self._icon_col)
        self.btn_settings.add(settings_img)
        self.btn_settings.connect("clicked", self._on_settings_clicked)
        tools_box.pack_start(self.btn_settings, False, False, 0)

        header_box.pack_end(tools_box, False, False, 0)
        self.card_inner.pack_start(header_box, False, False, 0)

    def _build_sidebar(self, parent_box):
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sidebar_box.set_name("launcher-sidebar")
        sidebar_box.set_size_request(210, -1)
        sidebar_box.set_vexpand(True)

        for cat_id, cat_name, icon_name, _ in CATEGORY_DEFINITIONS:
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("category-pill")
            if cat_id == self.active_category and not self.show_pinned_only:
                btn.get_style_context().add_class("active")

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

            # Icon
            cat_img = icons.get_image(icon_name, 16, self._icon_col)
            row_box.pack_start(cat_img, False, False, 0)

            # Label
            lbl = Gtk.Label(label=cat_name)
            lbl.set_xalign(0.0)
            row_box.pack_start(lbl, True, True, 0)

            # Count Badge
            count = self.category_counts.get(cat_id, 0)
            badge = Gtk.Label(label=str(count))
            badge.get_style_context().add_class("category-badge")
            row_box.pack_end(badge, False, False, 0)

            btn.add(row_box)
            btn.connect("clicked", self._on_category_clicked, cat_id, cat_name)
            sidebar_box.pack_start(btn, False, False, 0)
            self.category_widgets[cat_id] = btn

        parent_box.pack_start(sidebar_box, False, False, 0)

    def _build_content_area(self, parent_box):
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content_box.set_name("launcher-content")
        content_box.set_hexpand(True)
        content_box.set_vexpand(True)

        # 1. Search Bar Box (sleek, compact height without Ctrl+Space badge)
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        search_box.set_name("search-bar-box")
        search_box.set_size_request(-1, 36)

        s_col = "rgba(30, 41, 59, 0.45)" if self.theme_mode == "Light" else "rgba(255, 255, 255, 0.45)"
        search_icon = icons.get_image("search", 15, s_col)
        search_box.pack_start(search_icon, False, False, 4)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_name("search-entry")
        self.search_entry.set_placeholder_text("Search applications, files and settings...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activate)
        search_box.pack_start(self.search_entry, True, True, 0)

        content_box.pack_start(search_box, False, False, 0)

        # 2. Scrolled Window containing Apps View
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_name("launcher-scrolled")
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_hexpand(True)
        self.scrolled_window.set_vexpand(True)
        self.scrolled_window.set_overlay_scrolling(True)

        # Hide vertical scrollbar widget so it is not visible
        vscroll = self.scrolled_window.get_vscrollbar()
        if vscroll is not None:
            vscroll.set_no_show_all(True)
            vscroll.hide()
            vscroll.set_opacity(0.0)

        # Enable smooth wheel and touchpad scroll handling
        self.scrolled_window.connect("scroll-event", self._on_scrolled_window_scroll)

        self.view_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.scrolled_window.add(self.view_container)
        content_box.pack_start(self.scrolled_window, True, True, 0)

        parent_box.pack_start(content_box, True, True, 0)

        # Populate initial view
        self._refresh_apps_view()

    def _on_scrolled_window_scroll(self, widget, event):
        adj = widget.get_vadjustment()
        if adj is None:
            return False
        step = 55.0
        if event.direction == Gdk.ScrollDirection.UP:
            adj.set_value(max(adj.get_lower(), adj.get_value() - step))
            return True
        elif event.direction == Gdk.ScrollDirection.DOWN:
            adj.set_value(min(adj.get_upper() - adj.get_page_size(), adj.get_value() + step))
            return True
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            success, dx, dy = event.get_scroll_deltas()
            if success:
                adj.set_value(max(adj.get_lower(), min(adj.get_upper() - adj.get_page_size(), adj.get_value() + dy * step)))
                return True
        return False

    def _get_filtered_apps(self):
        query = self.search_query.strip().lower()
        res = []
        for app in self.apps:
            # Pinned filter
            if self.show_pinned_only:
                if not dock_pin.is_pinned(app["clean_id"]):
                    continue
            elif self.active_category != "all" and app["category"] != self.active_category:
                continue

            # Query filter
            if query:
                name_match = query in app["name"].lower()
                orig_match = query in app["original_name"].lower()
                exec_match = query in app["executable"].lower()
                comment_match = query in app["comment"].lower()
                id_match = query in app["id"].lower()
                if not (name_match or orig_match or exec_match or comment_match or id_match):
                    continue

            res.append(app)
        return res

    def _refresh_apps_view(self):
        # Clear existing children
        for child in self.view_container.get_children():
            self.view_container.remove(child)
            child.destroy()

        filtered = self._get_filtered_apps()

        if self.view_mode == "grid":
            self._render_grid_view(filtered)
        else:
            self._render_list_view(filtered)

        self.view_container.show_all()

    def _render_grid_view(self, filtered_apps):
        flow = Gtk.FlowBox()
        flow.set_valign(Gtk.Align.START)
        flow.set_max_children_per_line(6)
        flow.set_min_children_per_line(6)
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_column_spacing(16)
        flow.set_row_spacing(8)
        flow.set_homogeneous(True)

        for app in filtered_apps:
            tile_event = Gtk.EventBox()
            tile_event.set_visible_window(False)
            tile_event.connect("button-press-event", self._on_app_button_press, app)

            tile_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            tile_box.get_style_context().add_class("app-tile-box")
            tile_box.set_halign(Gtk.Align.CENTER)

            # Compact Squircle Icon Box (54x54)
            icon_box = Gtk.Box()
            icon_box.get_style_context().add_class("app-icon-squircle")
            icon_box.set_size_request(54, 54)
            icon_box.set_halign(Gtk.Align.CENTER)
            icon_box.set_valign(Gtk.Align.CENTER)

            # Centered App Icon (36x36)
            img = self._get_app_icon_image(app, 36)
            icon_box.pack_start(img, True, True, 0)
            tile_box.pack_start(icon_box, False, False, 0)

            # Full App Name wrapped to multi-lines (NEVER truncated with ...)
            lbl = Gtk.Label(label=app["name"])
            lbl.get_style_context().add_class("app-tile-label")
            lbl.set_line_wrap(True)
            lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_max_width_chars(13)
            lbl.set_halign(Gtk.Align.CENTER)
            tile_box.pack_start(lbl, False, False, 0)

            tile_event.add(tile_box)
            flow.add(tile_event)

        self.view_container.pack_start(flow, True, True, 0)

    def _render_list_view(self, filtered_apps):
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        list_box.set_name("app-list-box")

        for app in filtered_apps:
            row_event = Gtk.EventBox()
            row_event.set_visible_window(False)
            row_event.connect("button-press-event", self._on_app_button_press, app)

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row_box.get_style_context().add_class("app-list-row")

            # Squircle Icon Box (42x42)
            icon_box = Gtk.Box()
            icon_box.get_style_context().add_class("app-icon-squircle")
            icon_box.set_size_request(42, 42)
            icon_box.set_halign(Gtk.Align.CENTER)
            icon_box.set_valign(Gtk.Align.CENTER)
            img = self._get_app_icon_image(app, 26)
            icon_box.pack_start(img, True, True, 0)
            row_box.pack_start(icon_box, False, False, 2)

            # App Name & Comment
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name_lbl = Gtk.Label()
            name_lbl.set_xalign(0.0)
            name_lbl.set_markup(f"<span font='12.5' weight='bold' color='#ffffff'>{GLib.markup_escape_text(app['name'])}</span>")

            desc = app["comment"] or app["executable"]
            desc_lbl = Gtk.Label(label=desc)
            desc_lbl.set_xalign(0.0)
            desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            desc_lbl.set_max_width_chars(52)
            desc_lbl.get_style_context().add_class("app-list-desc")

            text_box.pack_start(name_lbl, False, False, 0)
            text_box.pack_start(desc_lbl, False, False, 0)
            row_box.pack_start(text_box, True, True, 0)

            # Category pill tag (uniform fixed-size badge with centered text)
            cat_tag = Gtk.Label(label=app["category"].capitalize())
            cat_tag.get_style_context().add_class("app-list-badge")
            cat_tag.set_size_request(76, 26)
            cat_tag.set_valign(Gtk.Align.CENTER)
            cat_tag.set_xalign(0.5)
            cat_tag.set_yalign(0.5)
            cat_tag.set_justify(Gtk.Justification.CENTER)
            row_box.pack_end(cat_tag, False, False, 6)

            row_event.add(row_box)
            list_box.pack_start(row_event, False, False, 0)

        self.view_container.pack_start(list_box, True, True, 0)

    def _get_app_icon_image(self, app, size=38):
        clean_id = app["clean_id"].lower()

        # macOS Terminal icon for Kitty
        if "kitty" in clean_id or app["executable"].endswith("kitty"):
            kitty_png = os.path.expanduser("~/.local/share/icons/kitty.png")
            if os.path.isfile(kitty_png):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(kitty_png, size, size, True)
                    return Gtk.Image.new_from_pixbuf(pb)
                except Exception:
                    pass

        # Official KDE Dolphin icon
        if "dolphin" in clean_id or app["executable"].endswith("dolphin"):
            dolphin_svg = "/usr/share/icons/hicolor/scalable/apps/org.kde.dolphin.svg"
            if os.path.isfile(dolphin_svg):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(dolphin_svg, size, size, True)
                    return Gtk.Image.new_from_pixbuf(pb)
                except Exception:
                    pass

        # macOS Settings icon for Desktop Settings
        if "setting" in clean_id or "settings" in app["executable"]:
            settings_png = os.path.expanduser("~/.local/share/icons/settings.png")
            if os.path.isfile(settings_png):
                try:
                    gicon = Gio.FileIcon.new(Gio.File.new_for_path(settings_png))
                    img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.DIALOG)
                    img.set_pixel_size(size)
                    return img
                except Exception:
                    pass

        # Standard icon from DesktopAppInfo
        if app["icon"]:
            try:
                img = Gtk.Image.new_from_gicon(app["icon"], Gtk.IconSize.DIALOG)
                img.set_pixel_size(size)
                return img
            except Exception:
                pass

        # Fallback
        img = Gtk.Image()
        img.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        img.set_pixel_size(size)
        return img

    def _on_app_button_press(self, widget, event, app):
        if event.button == 1:  # Left Click -> Launch
            self._launch_app(app)
            return True
        elif event.button == 3:  # Right Click -> Context Menu
            self._show_context_menu(widget, event, app)
            return True
        return False

    def _launch_app(self, app):
        try:
            app["app_info"].launch([], None)
        except Exception:
            try:
                subprocess.Popen([app["executable"]], start_new_session=True)
            except Exception as e:
                print(f"[neon-drawer] Error launching {app['name']}: {e}")
        self.close_drawer()

    def _show_context_menu(self, widget, event, app):
        menu = Gtk.Menu()
        menu.set_name("drawer-context-menu")

        clean_id = app["clean_id"]
        pinned = dock_pin.is_pinned(clean_id)

        # 1. Pin / Unpin Item
        pin_item = Gtk.MenuItem()
        pin_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pin_icon = Gtk.Label(label="❌" if pinned else "📌")
        pin_text = Gtk.Label(label="Unpin from taskbar" if pinned else "Pin to taskbar")
        pin_box.pack_start(pin_icon, False, False, 0)
        pin_box.pack_start(pin_text, False, False, 0)
        pin_item.add(pin_box)

        def _toggle_pin(_):
            if pinned:
                dock_pin.unpin(clean_id)
            else:
                dock_pin.pin(clean_id)
            if self.show_pinned_only:
                self._refresh_apps_view()

        pin_item.connect("activate", _toggle_pin)
        menu.append(pin_item)

        # 2. Rename Item (custom menu-only display name)
        rename_item = Gtk.MenuItem()
        rename_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rename_icon = Gtk.Label(label="✏️")
        rename_text = Gtk.Label(label="Rename")
        rename_box.pack_start(rename_icon, False, False, 0)
        rename_box.pack_start(rename_text, False, False, 0)
        rename_item.add(rename_box)
        rename_item.connect("activate", lambda *_: self._prompt_rename_app(app))
        menu.append(rename_item)

        # 3. Reset Name Item (visible only when custom name is active)
        if app.get("is_custom_named"):
            reset_item = Gtk.MenuItem()
            reset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            reset_icon = Gtk.Label(label="↺")
            reset_text = Gtk.Label(label=f"Reset name (to '{app['original_name']}')")
            reset_box.pack_start(reset_icon, False, False, 0)
            reset_box.pack_start(reset_text, False, False, 0)
            reset_item.add(reset_box)
            reset_item.connect("activate", lambda *_: self._reset_app_name(app))
            menu.append(reset_item)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # 4. Open Item
        open_item = Gtk.MenuItem()
        open_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        open_icon = Gtk.Label(label="🚀")
        open_text = Gtk.Label(label=f"Open {app['name']}")
        open_box.pack_start(open_icon, False, False, 0)
        open_box.pack_start(open_text, False, False, 0)
        open_item.add(open_box)
        open_item.connect("activate", lambda *_: self._launch_app(app))
        menu.append(open_item)

        menu.attach_to_widget(self, None)
        menu.show_all()
        if event is not None:
            try:
                menu.popup_at_pointer(event)
            except Exception:
                menu.popup(None, None, None, None, event.button, event.time)
        else:
            menu.popup_at_widget(widget, Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH, None)

    def _prompt_rename_app(self, app):
        if self._active_modal is not None:
            return

        # Modal shroud covering the card
        shroud = Gtk.EventBox()
        shroud.get_style_context().add_class("dialog-shroud")
        shroud.connect("button-press-event", lambda *_: True)

        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.set_valign(Gtk.Align.CENTER)
        shroud.add(center_box)

        dialog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        dialog_box.set_name("rename-dialog")
        dialog_box.set_size_request(420, -1)
        center_box.pack_start(dialog_box, False, False, 0)

        # Header Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_icon = Gtk.Label(label="✏️")
        title_lbl = Gtk.Label()
        title_lbl.set_markup("<span font='14' weight='bold' color='#ffffff'>Rename Application</span>")
        title_lbl.set_xalign(0.0)
        title_box.pack_start(title_icon, False, False, 0)
        title_box.pack_start(title_lbl, False, False, 0)
        dialog_box.pack_start(title_box, False, False, 0)

        # Subtitle / Description
        desc_lbl = Gtk.Label(label=f"Set a custom display name in the application menu for '{app['original_name']}':")
        desc_lbl.set_line_wrap(True)
        desc_lbl.set_xalign(0.0)
        desc_lbl.get_style_context().add_class("header-subtitle")
        dialog_box.pack_start(desc_lbl, False, False, 0)

        # Text Entry
        entry = Gtk.Entry()
        entry.set_name("rename-entry")
        entry.set_text(app["name"])
        entry.set_hexpand(True)
        dialog_box.pack_start(entry, False, False, 4)

        # Buttons Box
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(6)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.set_relief(Gtk.ReliefStyle.NONE)
        cancel_btn.get_style_context().add_class("dialog-btn-cancel")
        btn_box.pack_start(cancel_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save")
        save_btn.set_relief(Gtk.ReliefStyle.NONE)
        save_btn.get_style_context().add_class("dialog-btn-save")
        btn_box.pack_start(save_btn, False, False, 0)

        dialog_box.pack_start(btn_box, False, False, 0)

        def _close_modal():
            if self._active_modal is not None:
                self.card_overlay.remove(self._active_modal)
                self._active_modal = None
                self.search_entry.grab_focus()

        def _save():
            new_name = entry.get_text().strip()
            if new_name:
                self._save_app_rename(app, new_name)
            _close_modal()

        cancel_btn.connect("clicked", lambda *_: _close_modal())
        save_btn.connect("clicked", lambda *_: _save())
        entry.connect("activate", lambda *_: _save())

        self._active_modal = shroud
        self.card_overlay.add_overlay(shroud)
        shroud.show_all()
        entry.grab_focus()

    def _save_app_rename(self, app, new_name):
        clean_id = app["clean_id"]
        custom_names = load_custom_names()
        if new_name != app["original_name"]:
            custom_names[clean_id] = new_name
            app["name"] = new_name
            app["is_custom_named"] = True
        else:
            custom_names.pop(clean_id, None)
            app["name"] = app["original_name"]
            app["is_custom_named"] = False
        save_custom_names(custom_names)
        self._refresh_apps_view()

    def _reset_app_name(self, app):
        clean_id = app["clean_id"]
        custom_names = load_custom_names()
        if clean_id in custom_names:
            custom_names.pop(clean_id, None)
            save_custom_names(custom_names)
        app["name"] = app["original_name"]
        app["is_custom_named"] = False
        self._refresh_apps_view()

    def _on_category_clicked(self, widget, cat_id, cat_name):
        self.active_category = cat_id

        # Deactivate pin filter if active
        if self.show_pinned_only:
            self.show_pinned_only = False
            self.btn_pin.get_style_context().remove_class("active")

        # Update category buttons styling
        for cid, btn in self.category_widgets.items():
            if cid == cat_id:
                btn.get_style_context().add_class("active")
            else:
                btn.get_style_context().remove_class("active")

        # Update Header Title
        if cat_id == "all":
            self.title_label.set_text("All Applications")
            self.subtitle_label.set_text("Installed applications on your system")
        else:
            self.title_label.set_text(cat_name)
            self.subtitle_label.set_text(f"{self.category_counts.get(cat_id, 0)} applications in this category")

        self._refresh_apps_view()

    def _on_pin_filter_clicked(self, widget):
        self.show_pinned_only = not self.show_pinned_only

        if self.show_pinned_only:
            self.btn_pin.get_style_context().add_class("active")
            # Deactivate category pills styling
            for btn in self.category_widgets.values():
                btn.get_style_context().remove_class("active")
            self.title_label.set_text("Pinned Applications")
            self.subtitle_label.set_text("Applications pinned to the bottom dock taskbar")
        else:
            self.btn_pin.get_style_context().remove_class("active")
            # Re-activate selected category pill
            for cid, btn in self.category_widgets.items():
                if cid == self.active_category:
                    btn.get_style_context().add_class("active")
            if self.active_category == "all":
                self.title_label.set_text("All Applications")
                self.subtitle_label.set_text("Installed applications on your system")
            else:
                cat_tuple = next((c for c in CATEGORY_DEFINITIONS if c[0] == self.active_category), None)
                cat_name = cat_tuple[1] if cat_tuple else "Applications"
                self.title_label.set_text(cat_name)
                self.subtitle_label.set_text(f"{self.category_counts.get(self.active_category, 0)} applications in this category")

        self._refresh_apps_view()

    def _set_view_mode(self, mode):
        self.view_mode = mode
        if mode == "grid":
            self.btn_grid.get_style_context().add_class("active")
            self.btn_list.get_style_context().remove_class("active")
        else:
            self.btn_grid.get_style_context().remove_class("active")
            self.btn_list.get_style_context().add_class("active")
        self._refresh_apps_view()

    def _on_settings_clicked(self, widget):
        subprocess.Popen(["settings"], start_new_session=True)
        self.close_drawer()

    def _on_search_changed(self, entry):
        self.search_query = entry.get_text()
        self._refresh_apps_view()

    def _on_search_activate(self, entry):
        filtered = self._get_filtered_apps()
        if filtered:
            self._launch_app(filtered[0])

    def _on_backdrop_clicked(self, widget, event):
        alloc = self.card_border.get_allocation()
        if alloc.x <= event.x <= (alloc.x + alloc.width) and alloc.y <= event.y <= (alloc.y + alloc.height):
            return False
        if self._active_modal is not None:
            self.card_overlay.remove(self._active_modal)
            self._active_modal = None
            return True
        self.close_drawer()
        return True

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self._active_modal is not None:
                self.card_overlay.remove(self._active_modal)
                self._active_modal = None
                self.search_entry.grab_focus()
                return True
            self.close_drawer()
            return True
        return False

    def close_drawer(self):
        self.destroy()
        Gtk.main_quit()


def check_single_instance_or_toggle():
    """If another neon-drawer is already open, toggle it off and exit."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            os.kill(pid, signal.SIGTERM)
            sys.exit(0)
        except (OSError, ValueError):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass


def record_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup_pid():
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    check_single_instance_or_toggle()
    record_pid()

    app = NeonDrawerWindow()
    signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(app.close_drawer))

    app.show_all()

    # Grab focus on search entry
    GLib.idle_add(app.search_entry.grab_focus)

    try:
        Gtk.main()
    finally:
        cleanup_pid()


if __name__ == "__main__":
    main()
