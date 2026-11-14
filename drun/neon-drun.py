#!/usr/bin/env python3
"""
Neon Desktop — Adaptive Glass Drun Launcher (neon-drun)
Matches the reference design of "Neon Launcher with Zoro Sunset Banner"
Features:
- Live pinned apps from taskbar (~/.config/neon-desktop/pinned.json via dock_pin)
- Live recently used apps tracking (~/.config/neon-desktop/recent_apps.json)
- Real Hyprland keybindings lookup (e.g. Super+Return, Super+B, Super+E, Super+C)
- No fake/mock shortcuts: only displays badges for apps with actual bindings
- Clean 80% transparency frosted glass with Hyprland background blur
- Feathered bottom banner blending seamlessly into glass search area
- No Ctrl+Space text inside search bar
- No permanent hover/active glow on recent items
"""

import os
import sys
import re
import json
import signal
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
    os.path.expanduser("~/Projects/arch-desktop/shared"),
    os.path.expanduser("~/Projects/neon-desktop/shared"),
]
for p in POSSIBLE_SHARED:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

import theme
import icons
import dock_pin

CONFIG_DIR = os.path.expanduser("~/.config/neon-desktop")
DRUN_THEME_FILE = os.path.join(CONFIG_DIR, "drun_theme.json")
DRUN_CSS_FILE = os.path.join(CONFIG_DIR, "drun.css")
RECENT_APPS_FILE = os.path.join(CONFIG_DIR, "recent_apps.json")
PID_FILE = f"/tmp/neon-drun-{os.getuid()}.pid"


def _spawn_detached(cmd):
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True
        )
    except Exception as e:
        print(f"[neon-drun] Failed to spawn {cmd}: {e}")


def load_recent_app_ids():
    if os.path.isfile(RECENT_APPS_FILE):
        try:
            with open(RECENT_APPS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:
            pass
    # Live default recent apps based on installed favorites
    return ["desktop-settings", "brave-browser", "kitty", "org.kde.dolphin"]


def record_recent_app_id(clean_id):
    if not clean_id:
        return
    recent = load_recent_app_ids()
    recent = [r for r in recent if r != clean_id]
    recent.insert(0, clean_id)
    recent = recent[:20]
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(RECENT_APPS_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=2)
    except Exception:
        pass


def get_real_app_keybindings():
    """
    Parses ~/.config/hypr/hyprland.conf to discover real user keybindings.
    Returns mapping of lowercase identifiers/commands to formatted shortcut string (e.g. 'Super + Enter').
    """
    conf_path = os.path.expanduser("~/.config/hypr/hyprland.conf")
    if not os.path.isfile(conf_path):
        return {}

    vars_map = {"mainmod": "Super"}
    raw_bindings = []

    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                var_match = re.match(r"^\$([a-zA-Z0-9_-]+)\s*=\s*(.+)$", line)
                if var_match:
                    k, v = var_match.group(1).lower(), var_match.group(2).strip()
                    vars_map[k] = v
                    continue

                bind_match = re.match(r"^bind\s*=\s*([^,]*),\s*([^,]+),\s*exec\s*,\s*(.+)$", line)
                if bind_match:
                    mods_raw, key_raw, cmd_raw = bind_match.groups()
                    cmd_clean = cmd_raw.split("#")[0].strip()

                    mod_parts = []
                    for m in mods_raw.split():
                        m = m.strip().lstrip("$")
                        if m.lower() in vars_map and vars_map[m.lower()] == "Super":
                            mod_parts.append("Super")
                        elif m.lower() == "mainmod":
                            mod_parts.append("Super")
                        elif m.lower() == "shift":
                            mod_parts.append("Shift")
                        elif m.lower() in ("ctrl", "control"):
                            mod_parts.append("Ctrl")
                        elif m.lower() == "alt":
                            mod_parts.append("Alt")
                        elif m:
                            mod_parts.append(m.capitalize())

                    key_fmt = key_raw.strip()
                    if key_fmt.upper() == "RETURN":
                        key_fmt = "Enter"
                    elif len(key_fmt) == 1:
                        key_fmt = key_fmt.upper()

                    shortcut = " + ".join(mod_parts + [key_fmt])
                    raw_bindings.append((cmd_clean, shortcut))
    except Exception as e:
        print(f"[neon-drun] Error parsing keybindings: {e}")
        return {}

    bindings = {}
    for cmd, sc in raw_bindings:
        resolved = cmd
        for vk, vv in vars_map.items():
            resolved = re.sub(r"(?i)\$" + re.escape(vk) + r"\b", vv, resolved)
        bindings[resolved.lower()] = sc
        tokens = [os.path.basename(t.strip()) for t in resolved.split() if t.strip()]
        for t in tokens:
            t_clean = t.lower().replace(".desktop", "")
            if t_clean not in bindings:
                bindings[t_clean] = sc

    return bindings


class NeonDrunWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self.apps = []
        self.search_results = []
        self.selected_index = 0
        self.search_query = ""

        # Real system keybindings
        self.keybindings = get_real_app_keybindings()

        # Layer Shell setup
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        GtkLayerShell.set_namespace(self, "neon-drun")

        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)

        self.set_name("drun-window")
        self.set_decorated(False)
        self.set_app_paintable(True)

        # Apply CSS
        self.css_provider = Gtk.CssProvider()
        self._apply_css()

        # Load desktop applications
        self._load_desktop_apps()

        # Build UI
        self._build_ui()

        # Key events
        self.connect("key-press-event", self._on_key_press)

    def _apply_css(self):
        if not os.path.isfile(DRUN_CSS_FILE):
            theme.sync_topbar_theme_files(reload_services=False)

        try:
            if os.path.isfile(DRUN_CSS_FILE):
                with open(DRUN_CSS_FILE, "r") as f:
                    css_data = f.read()
                self.css_provider.load_from_data(css_data.encode("utf-8"))
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(),
                    self.css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_USER
                )
        except Exception as e:
            print(f"[neon-drun] Error applying CSS: {e}")

    def _load_desktop_apps(self):
        all_apps = Gio.DesktopAppInfo.get_all()
        visible = []

        for app in all_apps:
            if not app.should_show():
                continue

            app_id = app.get_id() or ""
            clean_id = app_id.replace(".desktop", "")
            orig_name = app.get_name() or clean_id
            comment = app.get_description() or ""
            executable = app.get_executable() or ""

            gicon = app.get_icon()

            visible.append({
                "id": app_id,
                "clean_id": clean_id,
                "name": orig_name,
                "comment": comment,
                "executable": executable,
                "gicon": gicon,
                "app_info": app,
            })

        visible.sort(key=lambda x: x["name"].lower())
        self.apps = visible

    def _get_app_shortcut(self, app):
        """Returns real shortcut string if mapped in Hyprland, else None."""
        if not app:
            return None
        cid = app["clean_id"].lower()
        exe = os.path.basename(app["executable"]).lower()

        # Direct checks
        if cid in self.keybindings:
            return self.keybindings[cid]
        if exe in self.keybindings:
            return self.keybindings[exe]

        # Common aliases & keywords
        if "kitty" in cid or "kitty" in exe:
            return self.keybindings.get("kitty")
        if "dolphin" in cid or "dolphin" in exe:
            return self.keybindings.get("dolphin")
        if "brave" in cid or "brave" in exe:
            return self.keybindings.get("brave")
        if "control-center" in cid or "settings" in cid:
            return self.keybindings.get("control-center") or self.keybindings.get("settings")
        if "neon-drawer" in cid or "drawer" in cid:
            return self.keybindings.get("neon-drawer")

        return None

    def _build_ui(self):
        # Backdrop EventBox (dismisses when clicking outside card)
        backdrop = Gtk.EventBox()
        backdrop.set_name("drun-backdrop")
        backdrop.connect("button-press-event", self._on_backdrop_clicked)
        self.add(backdrop)

        # Center Alignment Box
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.set_valign(Gtk.Align.CENTER)
        backdrop.add(center_box)

        # Outer card container
        card_event = Gtk.EventBox()
        card_event.set_name("drun-card-border")
        card_event.connect("button-press-event", lambda *_: True)
        center_box.pack_start(card_event, False, False, 0)

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.card.set_name("drun-card-inner")
        self.card.set_size_request(720, 500)
        card_event.add(self.card)

        # ── 1. Top Header Row ─────────────────────────────────────────────
        self.header_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.header_banner.set_name("drun-header-banner")
        self.card.pack_start(self.header_banner, False, False, 0)

        # Top-left Arch logo + Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        title_box.set_valign(Gtk.Align.START)

        arch_img = icons.get_image("arch", 32, color="#5ea2ef")
        arch_img.set_valign(Gtk.Align.CENTER)
        title_box.pack_start(arch_img, False, False, 0)

        text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_vbox.set_valign(Gtk.Align.CENTER)

        title_lbl = Gtk.Label(label="Launcher")
        title_lbl.set_name("drun-title")
        title_lbl.set_xalign(0)
        text_vbox.pack_start(title_lbl, False, False, 0)

        sub_lbl = Gtk.Label(label="Search apps, files and tools...")
        sub_lbl.set_name("drun-subtitle")
        sub_lbl.set_xalign(0)
        text_vbox.pack_start(sub_lbl, False, False, 0)

        title_box.pack_start(text_vbox, False, False, 0)
        self.header_banner.pack_start(title_box, False, False, 0)

        spacer = Gtk.Box()
        self.header_banner.pack_start(spacer, True, True, 0)

        # Top-right 4 Mode Buttons
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mode_box.set_valign(Gtk.Align.START)

        # 1. Apps Grid button (Active)
        btn_grid = Gtk.Button()
        btn_grid.set_relief(Gtk.ReliefStyle.NONE)
        btn_grid.set_focus_on_click(False)
        btn_grid.get_style_context().add_class("drun-mode-btn")
        btn_grid.get_style_context().add_class("active")
        btn_grid.add(icons.get_image("apps-grid", 16, color="#ffffff"))
        btn_grid.connect("clicked", lambda *_: self._reset_search())
        mode_box.pack_start(btn_grid, False, False, 0)

        # 2. Files button
        btn_files = Gtk.Button()
        btn_files.set_relief(Gtk.ReliefStyle.NONE)
        btn_files.set_focus_on_click(False)
        btn_files.get_style_context().add_class("drun-mode-btn")
        btn_files.add(icons.get_image("folder", 16, color="#ffffff"))
        btn_files.connect("clicked", lambda *_: self._launch_files())
        mode_box.pack_start(btn_files, False, False, 0)

        # 3. Terminal button
        btn_term = Gtk.Button()
        btn_term.set_relief(Gtk.ReliefStyle.NONE)
        btn_term.set_focus_on_click(False)
        btn_term.get_style_context().add_class("drun-mode-btn")
        btn_term.add(icons.get_image("terminal", 16, color="#ffffff"))
        btn_term.connect("clicked", lambda *_: self._launch_terminal())
        mode_box.pack_start(btn_term, False, False, 0)

        # 4. Settings button
        btn_settings = Gtk.Button()
        btn_settings.set_relief(Gtk.ReliefStyle.NONE)
        btn_settings.set_focus_on_click(False)
        btn_settings.get_style_context().add_class("drun-mode-btn")
        btn_settings.add(icons.get_image("settings", 16, color="#ffffff"))
        btn_settings.connect("clicked", lambda *_: self._launch_settings())
        mode_box.pack_start(btn_settings, False, False, 0)

        self.header_banner.pack_start(mode_box, False, False, 0)

        # ── 2. Search Bar (Feathered transition, no Ctrl+Space badge) ───────
        search_wrap = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        search_wrap.set_name("drun-search-container")
        search_wrap.set_size_request(672, 36)

        search_icon = icons.get_image("search", 16, color="rgba(255, 255, 255, 0.70)")
        search_icon.set_valign(Gtk.Align.CENTER)
        search_wrap.pack_start(search_icon, False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_name("drun-search-entry")
        self.search_entry.set_placeholder_text("Search applications...")
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activated)
        search_wrap.pack_start(self.search_entry, True, True, 0)

        self.card.pack_start(search_wrap, False, False, 0)

        # ── 3. Dynamic Content Area ───────────────────────────────────────
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.content_stack.set_transition_duration(120)
        self.card.pack_start(self.content_stack, True, True, 0)

        # Page A: Default Home View (Pinned + Recent)
        self.home_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._build_home_view()
        self.content_stack.add_named(self.home_view, "home")

        # Page B: Search Results View
        self.search_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._build_search_view()
        self.content_stack.add_named(self.search_view, "search")

        self.content_stack.set_visible_child_name("home")

    def _build_home_view(self):
        # ── Pinned Section (Live Taskbar Pinned Apps) ───────────────────────
        pinned_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        pinned_hdr.get_style_context().add_class("drun-section-header")

        p_left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        p_star = icons.get_image("pin", 16, color="#ffffff")
        p_lbl = Gtk.Label(label="Pinned")
        p_lbl.get_style_context().add_class("drun-section-title")
        p_left.pack_start(p_star, False, False, 0)
        p_left.pack_start(p_lbl, False, False, 0)
        pinned_hdr.pack_start(p_left, False, False, 0)

        self.home_view.pack_start(pinned_hdr, False, False, 0)

        # Horizontal Box for live pinned taskbar apps
        pinned_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        pinned_box.get_style_context().add_class("drun-pinned-box")

        live_pinned = self._load_live_pinned_items()
        for item in live_pinned:
            card = Gtk.Button()
            card.set_relief(Gtk.ReliefStyle.NONE)
            card.set_focus_on_click(False)
            card.get_style_context().add_class("drun-pinned-card")
            card.set_size_request(54, 54)
            card.set_tooltip_text(item["name"])

            img = self._create_app_icon(item)
            card.add(img)

            card.connect("clicked", lambda _, it=item: self._launch_item(it))
            pinned_box.pack_start(card, True, True, 0)

        self.home_view.pack_start(pinned_box, False, False, 0)

        # ── Recent Section (Live Recently Used Apps) ───────────────────────
        recent_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        recent_hdr.get_style_context().add_class("drun-section-header")

        r_left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        r_clock = icons.get_image("clock", 16, color="#ffffff")
        r_lbl = Gtk.Label(label="Recent")
        r_lbl.get_style_context().add_class("drun-section-title")
        r_left.pack_start(r_clock, False, False, 0)
        r_left.pack_start(r_lbl, False, False, 0)
        recent_hdr.pack_start(r_left, False, False, 0)

        r_spacer = Gtk.Box()
        recent_hdr.pack_start(r_spacer, True, True, 0)

        r_all = Gtk.Button()
        r_all.get_style_context().add_class("drun-section-action")
        a_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        a_lbl = Gtk.Label(label="All Apps →")
        a_box.pack_start(a_lbl, False, False, 0)
        r_all.add(a_box)
        r_all.connect("clicked", lambda *_: self._open_all_apps())
        recent_hdr.pack_start(r_all, False, False, 0)

        self.home_view.pack_start(recent_hdr, False, False, 0)

        # Vertical Box for live recent apps
        recent_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        recent_box.get_style_context().add_class("drun-recent-box")

        live_recent = self._load_live_recent_items()
        self.recent_row_widgets = []
        for app in live_recent:
            row_btn = Gtk.Button()
            row_btn.set_relief(Gtk.ReliefStyle.NONE)
            row_btn.set_focus_on_click(False)
            row_btn.get_style_context().add_class("drun-list-row")
            # NO row is active by default (clean subtle glass)
            row_btn.set_size_request(672, 46)

            r_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

            # Real App Icon
            ic = self._get_app_icon(app, 26)
            ic.set_valign(Gtk.Align.CENTER)
            r_content.pack_start(ic, False, False, 0)

            # Real App Labels
            lbl_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_vbox.set_valign(Gtk.Align.CENTER)
            t_lbl = Gtk.Label(label=app["name"])
            t_lbl.get_style_context().add_class("drun-list-title")
            t_lbl.set_xalign(0)
            desc = app["comment"] or "Application"
            if len(desc) > 65:
                desc = desc[:62] + "..."
            s_lbl = Gtk.Label(label=desc)
            s_lbl.get_style_context().add_class("drun-list-subtitle")
            s_lbl.set_xalign(0)
            lbl_vbox.pack_start(t_lbl, False, False, 0)
            lbl_vbox.pack_start(s_lbl, False, False, 0)
            r_content.pack_start(lbl_vbox, False, False, 0)

            # Expander
            row_spacer = Gtk.Box()
            r_content.pack_start(row_spacer, True, True, 0)

            # Real Keybinding Shortcut Badge (ONLY IF mapped in Hyprland)
            sc = self._get_app_shortcut(app)
            if sc:
                s_badge = Gtk.Label(label=sc)
                s_badge.get_style_context().add_class("drun-shortcut-badge")
                s_badge.set_valign(Gtk.Align.CENTER)
                r_content.pack_start(s_badge, False, False, 0)

            row_btn.add(r_content)
            row_btn.connect("clicked", lambda _, a=app: self._launch_app(a))
            recent_box.pack_start(row_btn, False, False, 0)
            self.recent_row_widgets.append(row_btn)

        self.home_view.pack_start(recent_box, False, False, 0)

    def _build_search_view(self):
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_name("drun-scrolled")
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_size_request(672, 280)
        self.scrolled_window.set_overlay_scrolling(True)

        # Hide vertical scrollbar widget so it is not visible
        vscroll = self.scrolled_window.get_vscrollbar()
        if vscroll is not None:
            vscroll.set_no_show_all(True)
            vscroll.hide()
            vscroll.set_opacity(0.0)

        # Enable smooth wheel and touchpad scroll handling
        self.scrolled_window.connect("scroll-event", self._on_scrolled_window_scroll)

        self.search_view.pack_start(self.scrolled_window, True, True, 0)

        self.search_results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.search_results_box.set_margin_top(8)
        self.search_results_box.set_margin_bottom(12)
        self.scrolled_window.add(self.search_results_box)

    def _on_scrolled_window_scroll(self, widget, event):
        adj = widget.get_vadjustment()
        if adj is None:
            return False
        step = 45.0
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

    def _load_live_pinned_items(self):
        """Loads real applications pinned to the taskbar via dock_pin."""
        raw_pinned = dock_pin.load_pinned()
        items = []

        for p in raw_pinned:
            pid = p.get("id") or ""
            pname = p.get("name") or pid
            picon = p.get("icon") or ""
            matches = [m.lower() for m in p.get("match", [pid])]

            # Find matching installed desktop app
            matched_app = None
            for app in self.apps:
                if any(m in app["clean_id"].lower() or m in app["executable"].lower() for m in matches):
                    matched_app = app
                    break

            items.append({
                "id": pid,
                "name": matched_app["name"] if matched_app else pname,
                "icon_str": picon,
                "matched_app": matched_app,
                "fallback_cmd": pid
            })

        return items

    def _load_live_recent_items(self):
        """Loads real recently used apps from history, up to 3-4 items."""
        recent_ids = load_recent_app_ids()
        recent_apps = []

        for rid in recent_ids:
            rid_clean = rid.lower().replace(".desktop", "")
            for app in self.apps:
                if app["clean_id"].lower() == rid_clean or rid_clean in app["executable"].lower():
                    if app not in recent_apps:
                        recent_apps.append(app)
                    break
            if len(recent_apps) >= 3:
                break

        # Fallback if fewer than 3: fill with popular installed apps
        if len(recent_apps) < 3:
            for fallback_id in ["brave-browser", "kitty", "org.kde.dolphin", "antigravity-ide", "code-oss"]:
                for app in self.apps:
                    if fallback_id in app["clean_id"].lower() and app not in recent_apps:
                        recent_apps.append(app)
                        break
                if len(recent_apps) >= 3:
                    break

        return recent_apps[:3]

    def _get_app_icon(self, app, size=26):
        cid = (app.get("clean_id") or "").lower()
        exe = (app.get("executable") or "").lower()
        if "setting" in cid or "settings" in exe:
            settings_png = os.path.expanduser("~/.local/share/icons/settings.png")
            if os.path.isfile(settings_png):
                try:
                    gicon = Gio.FileIcon.new(Gio.File.new_for_path(settings_png))
                    img = Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.DIALOG)
                    img.set_pixel_size(size)
                    return img
                except Exception:
                    pass
        if "kitty" in cid or exe.endswith("kitty"):
            kitty_png = os.path.expanduser("~/.local/share/icons/kitty.png")
            if os.path.isfile(kitty_png):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(kitty_png, size, size, True)
                    return Gtk.Image.new_from_pixbuf(pb)
                except Exception:
                    pass
        if "dolphin" in cid or exe.endswith("dolphin"):
            dolphin_svg = "/usr/share/icons/hicolor/scalable/apps/org.kde.dolphin.svg"
            if os.path.isfile(dolphin_svg):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(dolphin_svg, size, size, True)
                    return Gtk.Image.new_from_pixbuf(pb)
                except Exception:
                    pass
        if app.get("gicon") is not None:
            ic = Gtk.Image.new_from_gicon(app["gicon"], Gtk.IconSize.DND)
            ic.set_pixel_size(size)
            return ic
        return icons.get_image("apps-grid", size)

    def _create_app_icon(self, item):
        picon = item["icon_str"]
        # 1. Custom icon path (e.g. ~/.local/share/icons/kitty.png)
        if picon and (picon.startswith("/") or picon.startswith("~")):
            expanded = os.path.expanduser(picon)
            if os.path.isfile(expanded):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(expanded, 30, 30, True)
                    return Gtk.Image.new_from_pixbuf(pb)
                except Exception:
                    pass

        # 2. Desktop app
        if item.get("matched_app"):
            return self._get_app_icon(item["matched_app"], 30)

        # 3. Named theme icon
        if picon and Gtk.IconTheme.get_default().has_icon(picon):
            img = Gtk.Image()
            img.set_from_icon_name(picon, Gtk.IconSize.DIALOG)
            img.set_pixel_size(30)
            return img

        # 4. Built-in icons vector SVG
        if picon in icons.ICONS:
            return icons.get_image(picon, 30)

        return icons.get_image("apps-grid", 30, color="#ffffff")

    def _on_search_changed(self, entry):
        query = entry.get_text().strip().lower()
        self.search_query = query

        if not query:
            self.content_stack.set_visible_child_name("home")
            return

        self.content_stack.set_visible_child_name("search")
        self._render_search_results(query)

    def _render_search_results(self, query):
        for child in self.search_results_box.get_children():
            self.search_results_box.remove(child)

        matches = []
        for app in self.apps:
            score = 0
            name_lower = app["name"].lower()
            comment_lower = app["comment"].lower()
            exec_lower = app["executable"].lower()

            if name_lower.startswith(query):
                score = 100
            elif query in name_lower:
                score = 80
            elif query in comment_lower or query in exec_lower:
                score = 50

            if score > 0:
                matches.append((score, app))

        matches.sort(key=lambda x: (-x[0], x[1]["name"].lower()))
        self.search_results = [m[1] for m in matches[:15]]
        self.selected_index = 0

        if hasattr(self, "scrolled_window"):
            adj = self.scrolled_window.get_vadjustment()
            if adj is not None:
                adj.set_value(adj.get_lower())

        self.result_widgets = []
        for idx, app in enumerate(self.search_results):
            row_btn = Gtk.Button()
            row_btn.set_relief(Gtk.ReliefStyle.NONE)
            row_btn.set_focus_on_click(False)
            row_btn.get_style_context().add_class("drun-list-row")
            if idx == self.selected_index:
                row_btn.get_style_context().add_class("active")
            row_btn.set_size_request(654, 46)

            r_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

            # Real Icon
            ic = self._get_app_icon(app, 26)
            ic.set_valign(Gtk.Align.CENTER)
            r_content.pack_start(ic, False, False, 0)

            # Real App Name & Description
            lbl_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_vbox.set_valign(Gtk.Align.CENTER)
            t_lbl = Gtk.Label(label=app["name"])
            t_lbl.get_style_context().add_class("drun-list-title")
            t_lbl.set_xalign(0)
            desc = app["comment"] or "Application"
            if len(desc) > 65:
                desc = desc[:62] + "..."
            s_lbl = Gtk.Label(label=desc)
            s_lbl.get_style_context().add_class("drun-list-subtitle")
            s_lbl.set_xalign(0)
            lbl_vbox.pack_start(t_lbl, False, False, 0)
            lbl_vbox.pack_start(s_lbl, False, False, 0)
            r_content.pack_start(lbl_vbox, False, False, 0)

            # Expander
            row_spacer = Gtk.Box()
            r_content.pack_start(row_spacer, True, True, 0)

            # Real Shortcut Badge (ONLY IF mapped in Hyprland)
            sc = self._get_app_shortcut(app)
            if sc:
                s_badge = Gtk.Label(label=sc)
                s_badge.get_style_context().add_class("drun-shortcut-badge")
                s_badge.set_valign(Gtk.Align.CENTER)
                r_content.pack_start(s_badge, False, False, 0)

            row_btn.add(r_content)
            row_btn.connect("clicked", lambda _, a=app: self._launch_app(a))
            self.search_results_box.pack_start(row_btn, False, False, 0)
            self.result_widgets.append(row_btn)

        self.search_results_box.show_all()

    def _update_selection(self):
        for idx, w in enumerate(self.result_widgets):
            ctx = w.get_style_context()
            if idx == self.selected_index:
                ctx.add_class("active")
                if hasattr(self, "scrolled_window"):
                    adj = self.scrolled_window.get_vadjustment()
                    alloc = w.get_allocation()
                    if adj and alloc.height > 0:
                        val = adj.get_value()
                        page = adj.get_page_size()
                        if alloc.y < val:
                            adj.set_value(alloc.y)
                        elif alloc.y + alloc.height > val + page:
                            adj.set_value(alloc.y + alloc.height - page)
            else:
                ctx.remove_class("active")

    def _on_search_activated(self, _entry):
        if self.search_results and 0 <= self.selected_index < len(self.search_results):
            self._launch_app(self.search_results[self.selected_index])
        elif self.search_results:
            self._launch_app(self.search_results[0])

    def _on_key_press(self, _widget, event):
        val = event.keyval

        # Escape closes launcher
        if val == Gdk.KEY_Escape:
            self.close_launcher()
            return True

        # Arrow navigation in search results
        if self.content_stack.get_visible_child_name() == "search" and self.search_results:
            if val == Gdk.KEY_Down:
                self.selected_index = min(len(self.search_results) - 1, self.selected_index + 1)
                self._update_selection()
                return True
            elif val == Gdk.KEY_Up:
                self.selected_index = max(0, self.selected_index - 1)
                self._update_selection()
                return True

        return False

    def _on_backdrop_clicked(self, _widget, _event):
        self.close_launcher()
        return True

    def _launch_item(self, item):
        if item.get("matched_app"):
            self._launch_app(item["matched_app"])
        else:
            _spawn_detached([item["fallback_cmd"]])
            self.close_launcher()

    def _launch_app(self, app):
        record_recent_app_id(app["clean_id"])
        try:
            app["app_info"].launch([], None)
        except Exception:
            try:
                _spawn_detached([app["executable"]])
            except Exception as e:
                print(f"[neon-drun] Error launching {app['name']}: {e}")
        self.close_launcher()

    def _launch_files(self):
        _spawn_detached(["dolphin", os.path.expanduser("~")])
        self.close_launcher()

    def _launch_terminal(self):
        _spawn_detached(["kitty"])
        self.close_launcher()

    def _launch_settings(self):
        _spawn_detached(["settings"])
        self.close_launcher()

    def _open_all_apps(self):
        _spawn_detached(["neon-drawer"])
        self.close_launcher()

    def _manage_pinned(self):
        _spawn_detached(["neon-dock-pin"])
        self.close_launcher()

    def _reset_search(self):
        self.search_entry.set_text("")
        self.content_stack.set_visible_child_name("home")
        self.search_entry.grab_focus()

    def close_launcher(self):
        self.destroy()
        Gtk.main_quit()


def check_single_instance_or_toggle():
    if os.path.isfile(PID_FILE):
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

    app = NeonDrunWindow()
    signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(app.close_launcher))

    app.show_all()

    if len(sys.argv) > 1:
        query = " ".join([a for a in sys.argv[1:] if not a.startswith("-")])
        if query:
            app.search_entry.set_text(query)
            app.search_entry.set_position(-1)

    GLib.idle_add(app.search_entry.grab_focus)

    try:
        Gtk.main()
    finally:
        cleanup_pid()


if __name__ == "__main__":
    main()
