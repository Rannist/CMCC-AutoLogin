# -*- coding: utf-8 -*-
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import socket
import ctypes
import ctypes.wintypes
import traceback
import xml.etree.ElementTree as ET
import binascii
from io import BytesIO
from datetime import datetime

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk
except ImportError:
    print("Error: tkinter not found")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None

APP_BG = "#edf4fc"
SURFACE = "#ffffff"
TEXT = "#0f172a"
MUTED = "#64748b"
PRIMARY = "#1d4ed8"
PRIMARY_HOVER = "#1e40af"
PRIMARY_DOWN = "#1e3a8a"
PRIMARY_DISABLED = "#93c5fd"
SECONDARY = "#eaf1ff"
SECONDARY_HOVER = "#dbeafe"
SECONDARY_DOWN = "#bfdbfe"
SECONDARY_DISABLED = "#e5e7eb"
SECONDARY_TEXT = "#12325f"
BORDER = "#d7e0ee"
SUCCESS = "#16a34a"
WARNING = "#f59e0b"
ERROR = "#dc2626"
SHADOW = "#dfe7f2"
CARD_SHADOW = "#cfdaea"
LOG_BG = "#f8fafc"
TRANSPARENT = "#ff00ff"
UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"
APP_USER_MODEL_ID = "CMCC.AutoLogin"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def get_script_dir():
    if hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)


def draw_round_rect(canvas, x0, y0, x1, y1, radius, fill, outline="", width=1, tags=None):
    radius = max(1, min(radius, int((x1 - x0) / 2), int((y1 - y0) / 2)))
    points = [
        x0 + radius, y0, x0 + radius, y0,
        x1 - radius, y0, x1 - radius, y0,
        x1, y0, x1, y0 + radius,
        x1, y0 + radius, x1, y1 - radius,
        x1, y1 - radius, x1, y1,
        x1 - radius, y1, x1 - radius, y1,
        x0 + radius, y1, x0 + radius, y1,
        x0, y1, x0, y1 - radius,
        x0, y1 - radius, x0, y0 + radius,
        x0, y0 + radius, x0, y0,
    ]
    canvas.create_polygon(
        points,
        fill=fill,
        outline=outline,
        width=width,
        smooth=True,
        splinesteps=16,
        tags=tags,
    )


def create_round_photo(width, height, radius, fill, bg, outline=None, shadow=False):
    width = max(2, int(width))
    height = max(2, int(height))
    if Image is None or ImageDraw is None:
        img = tk.PhotoImage(width=width, height=height)
        radius = max(1, min(radius, width // 2, height // 2))
        shadow_offset = 4 if shadow else 0

        def inside(px, py, w, h, r):
            if px < 0 or py < 0 or px >= w or py >= h:
                return False
            if r <= px < w - r or r <= py < h - r:
                return True
            cx = r if px < r else w - r - 1
            cy = r if py < r else h - r - 1
            return (px - cx) ** 2 + (py - cy) ** 2 <= r ** 2

        for y in range(height):
            row = []
            for x in range(width):
                color = bg
                if shadow and inside(x - shadow_offset, y - shadow_offset, width - shadow_offset, height - shadow_offset, radius):
                    color = CARD_SHADOW
                if inside(x, y, width - shadow_offset, height - shadow_offset, radius):
                    color = fill
                    if outline and (
                        not inside(x - 1, y, width - shadow_offset, height - shadow_offset, radius)
                        or not inside(x + 1, y, width - shadow_offset, height - shadow_offset, radius)
                        or not inside(x, y - 1, width - shadow_offset, height - shadow_offset, radius)
                        or not inside(x, y + 1, width - shadow_offset, height - shadow_offset, radius)
                    ):
                        color = outline
                row.append(color)
            img.put("{" + " ".join(row) + "}", to=(0, y))
        return img
    scale = 3
    sw, sh = width * scale, height * scale
    sr = radius * scale
    transparent_bg = bg == TRANSPARENT
    image = Image.new("RGBA" if transparent_bg else "RGB", (sw, sh), (0, 0, 0, 0) if transparent_bg else bg)
    draw = ImageDraw.Draw(image)
    inset = 1 * scale
    shadow_offset = 4 * scale if shadow else 0
    if shadow:
        draw.rounded_rectangle(
            [shadow_offset, shadow_offset + scale, sw - inset, sh - inset],
            radius=sr,
            fill=CARD_SHADOW,
        )
    rect = [inset, inset, sw - inset - shadow_offset, sh - inset - shadow_offset]
    draw.rounded_rectangle(rect, radius=sr, fill=fill, outline=outline or fill, width=scale if outline else 0)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return tk.PhotoImage(data=base64.b64encode(buffer.getvalue()).decode("ascii"))


def write_ui_backend_log():
    try:
        with open(os.path.join(get_script_dir(), "ui_backend.log"), "w", encoding="utf-8") as f:
            f.write("Pillow=" + ("yes" if Image is not None and ImageDraw is not None else "no") + "\n")
    except Exception:
        pass


def apply_dwm_round_corners(window):
    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        preference = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference))
    except Exception:
        pass


def apply_window_round_region(window, width, height, radius):
    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
        ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
    except Exception:
        pass


def dpapi_protect(data):
    if os.name != "nt":
        raise RuntimeError("DPAPI 仅支持 Windows")
    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def dpapi_unprotect(data):
    if os.name != "nt":
        raise RuntimeError("DPAPI 仅支持 Windows")
    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class RoundedPanel(tk.Frame):
    def __init__(self, master, radius=24, fill=SURFACE, shadow=True, border=BORDER, content_pad=(14, 12), **kwargs):
        kwargs.pop("bd", None)
        kwargs.pop("highlightthickness", None)
        kwargs.pop("padx", None)
        kwargs.pop("pady", None)
        super().__init__(master, bg=master.cget("bg"), bd=0, highlightthickness=0, **kwargs)
        self.radius = radius
        self.fill = fill
        self.border = border
        self.shadow = shadow
        self.canvas = tk.Canvas(self, bg=master.cget("bg"), bd=0, highlightthickness=0, relief=tk.FLAT)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.tk.call("lower", self.canvas._w)
        padx, pady = content_pad
        self.body = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        self.body.pack(fill=tk.BOTH, expand=True, padx=padx, pady=pady)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 4 or height <= 4:
            return
        self.canvas.delete("panel")
        self._bg_image = create_round_photo(width, height, self.radius, self.fill, self.master.cget("bg"), shadow=self.shadow)
        self.canvas.create_image(0, 0, image=self._bg_image, anchor=tk.NW, tags="panel")
        self.canvas.tag_lower("panel")

    def cget(self, key):
        if key == "bg":
            return self.fill
        return super().cget(key)


class RoundedBox(tk.Frame):
    def __init__(self, master, radius=10, fill=LOG_BG, border=BORDER, **kwargs):
        kwargs.pop("bd", None)
        kwargs.pop("highlightthickness", None)
        super().__init__(master, bg=master.cget("bg"), bd=0, highlightthickness=0, **kwargs)
        self.radius = radius
        self.fill = fill
        self.border = border
        self.canvas = tk.Canvas(self, bg=master.cget("bg"), bd=0, highlightthickness=0, relief=tk.FLAT)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.tk.call("lower", self.canvas._w)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 4 or height <= 4:
            return
        self.canvas.delete("box")
        self._bg_image = create_round_photo(width, height, self.radius, self.fill, self.master.cget("bg"), outline="#dfe7f2")
        self.canvas.create_image(0, 0, image=self._bg_image, anchor=tk.NW, tags="box")
        self.canvas.tag_lower("box")

    def cget(self, key):
        if key == "bg":
            return self.fill
        return super().cget(key)


class CapsuleButton(tk.Canvas):
    def __init__(
        self,
        master,
        text,
        command=None,
        image=None,
        width=164,
        height=44,
        variant="secondary",
        **kwargs,
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=master.cget("bg"),
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
            takefocus=0,
            cursor="hand2",
            **kwargs,
        )
        self._text = text
        self._command = command
        self._image = image
        self._width = width
        self._height = height
        self._variant = variant
        self._state = tk.NORMAL
        self._hover = False
        self._pressed = False
        self._layout_text_width = 0
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _colors(self):
        if self._variant == "title":
            if self._pressed:
                return SECONDARY_DOWN, SECONDARY_DOWN, PRIMARY
            if self._hover:
                return SECONDARY_HOVER, SECONDARY_HOVER, PRIMARY
            return APP_BG, APP_BG, MUTED

        if self._variant == "close":
            if self._pressed:
                return "#fecaca", "#fecaca", "#b91c1c"
            if self._hover:
                return "#fee2e2", "#fee2e2", "#dc2626"
            return "#fef2f2", "#fef2f2", "#ef4444"

        if self._variant == "primary":
            if self._state == tk.DISABLED:
                return PRIMARY_DISABLED, PRIMARY_DISABLED, "#eff6ff"
            if self._pressed:
                return PRIMARY_DOWN, PRIMARY_DOWN, "#ffffff"
            if self._hover:
                return PRIMARY_HOVER, PRIMARY_HOVER, "#ffffff"
            return PRIMARY, PRIMARY, "#ffffff"

        if self._variant == "green":
            if self._state == tk.DISABLED:
                return "#a7f3d0", "#a7f3d0", "#ecfdf5"
            if self._pressed:
                return "#0f766e", "#0f766e", "#ffffff"
            if self._hover:
                return "#0d9488", "#0d9488", "#ffffff"
            return "#14b8a6", "#14b8a6", "#ffffff"

        if self._variant == "purple":
            if self._state == tk.DISABLED:
                return "#c4b5fd", "#c4b5fd", "#f5f3ff"
            if self._pressed:
                return "#5b21b6", "#5b21b6", "#ffffff"
            if self._hover:
                return "#6d28d9", "#6d28d9", "#ffffff"
            return "#7c3aed", "#7c3aed", "#ffffff"

        if self._state == tk.DISABLED:
            return SECONDARY_DISABLED, SECONDARY_DISABLED, "#94a3b8"
        if self._pressed:
            return SECONDARY_DOWN, "#9ab7e5", SECONDARY_TEXT
        if self._hover:
            return SECONDARY_HOVER, "#b7c9e8", SECONDARY_TEXT
        return SECONDARY, BORDER, SECONDARY_TEXT

    def _draw_pill(self, fill, outline):
        self._bg_image = create_round_photo(self._width, self._height, self._height // 2, fill, self.cget("bg"))
        self.create_image(0, 0, image=self._bg_image, anchor=tk.NW)

    def _draw(self):
        self.delete("all")
        fill, outline, fg = self._colors()
        self._draw_pill(fill, outline)

        has_image = self._image is not None
        font_spec = (
            UI_FONT,
            13 if self._variant == "close" else 9 if len(self._text) >= 5 else 10,
            "bold" if self._variant in ("primary", "close") else "normal",
        )
        try:
            text_width = tkfont.Font(font=font_spec).measure(self._text)
        except Exception:
            text_width = max(len(self._text) * 10, 18)
        self._layout_text_width = max(self._layout_text_width, text_width)
        try:
            icon_width = self._image.width() if has_image else 0
        except Exception:
            icon_width = 22 if has_image else 0
        if has_image:
            gap = 8
            group_width = icon_width + gap + self._layout_text_width
            start_x = max(10, (self._width - group_width) // 2)
            icon_x = start_x + icon_width // 2
            text_x = start_x + icon_width + gap
            self.create_image(icon_x, self._height // 2, image=self._image)
            if text_width < self._layout_text_width:
                text_x += (self._layout_text_width - text_width) // 2
            anchor = tk.W
        else:
            text_x = self._width // 2
            anchor = tk.CENTER

        self.create_text(
            text_x,
            self._height // 2,
            text=self._text,
            fill=fg,
            font=font_spec,
            anchor=anchor,
        )

    def _on_enter(self, _event):
        if self._state == tk.DISABLED:
            return
        self._hover = True
        self._draw()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event):
        if self._state == tk.DISABLED:
            return
        self._pressed = True
        self._draw()

    def _on_release(self, event):
        if self._state == tk.DISABLED:
            return
        inside = 0 <= event.x <= self._width and 0 <= event.y <= self._height
        self._pressed = False
        self._draw()
        if inside and self._command:
            self._command()

    def config(self, cnf=None, **kwargs):
        return self.configure(cnf, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        redraw = False
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            redraw = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self.configure(cursor="arrow" if self._state == tk.DISABLED else "hand2")
            redraw = True
        if "image" in kwargs:
            self._image = kwargs.pop("image")
            redraw = True
        if kwargs:
            super().configure(**kwargs)
        if redraw:
            self._draw()

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)


class HoverTip:
    def __init__(self, owner, text):
        self.owner = owner
        self.text = text
        self.widget = None
        self._image = None

    def show_for_widget(self, target):
        self.hide()
        width, height = 154, 30
        canvas = tk.Canvas(self.owner, width=width, height=height, bg=SURFACE, bd=0, highlightthickness=0, relief=tk.FLAT)
        self._image = create_round_photo(width, height, 14, "#f8fbff", SURFACE, outline="#cfe0f6")
        canvas.create_image(0, 0, image=self._image, anchor=tk.NW)
        canvas.create_text(
            width // 2,
            height // 2,
            text=self.text,
            fill=PRIMARY,
            font=(UI_FONT, 8),
            anchor=tk.CENTER,
        )
        x = target.winfo_x() + max(0, (target.winfo_width() - width) // 2)
        y = max(0, target.winfo_y() - height - 10)
        canvas.place(x=x, y=y)
        canvas.tk.call("raise", canvas._w)
        self.widget = canvas

    def hide(self):
        if self.widget is not None:
            try:
                self.widget.destroy()
            except Exception:
                pass
            self.widget = None


class AutoLogin:
    def __init__(self, master):
        self.master = master
        self.master.title("校园网自动登录")
        self.master.overrideredirect(True)

        self.script_dir = get_script_dir()
        self.scripts_dir = os.path.join(self.script_dir, "scripts")
        if not os.path.isdir(self.scripts_dir) and not getattr(sys, "frozen", False):
            self.scripts_dir = self.script_dir
        self.config_file = os.path.join(self.script_dir, "config.json")
        self.settings_file = os.path.join(self.script_dir, "settings.json")
        self.login_script = os.path.join(self.scripts_dir, "AutoLogin.ps1")
        self.startup_login_script = os.path.join(self.scripts_dir, "StartupAutoLogin.ps1")
        self.startup_launcher_script = os.path.join(self.scripts_dir, "StartupAutoLogin.vbs")
        self.startup_script = os.path.join(self.scripts_dir, "install_scheduled_task.ps1")
        self.uninstall_startup_script = os.path.join(self.scripts_dir, "uninstall_scheduled_task.ps1")
        self.startup_task_name = "CMCCAutoLogin"

        self.icons = {}
        self.busy_buttons = set()
        self.log_entries = []
        self.log_expanded = False
        self.is_logging_in = False
        self.is_refreshing = False
        self.is_editing_account = False
        self.is_connected = False
        self.login_hover_tip = None
        self.last_diagnostic_text = ""
        self.internet_cache = {"time": 0, "value": False}
        self.message_queue = []
        self.message_active = False
        self.message_token = 0
        self.message_min_duration_ms = 1800
        self.notice_dedupe_seconds = 2.0
        self.notice_last_shown = {}
        self.drag_x = 0
        self.drag_y = 0
        self.content_scroll_y = 0
        self.content_max_scroll_y = 0
        self.auto_mode = len(sys.argv) > 1 and sys.argv[1] == "--auto"

        self.ensure_config_exists()
        self.load_settings()
        self.center_window(self.settings["window_width"], self.settings["window_height"])
        self.master.minsize(620, 850)
        self.master.resizable(True, True)
        self.load_icons()
        self.apply_window_icon()
        self.create_widgets()
        self.master.after(120, self.ensure_taskbar_visible)

        if self.auto_mode:
            self.master.after(120, self.auto_login_mode)
        else:
            self.master.after(450, self.check_status)
            self.update_login_button_text()

    def ensure_config_exists(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8-sig") as f:
                    config = json.load(f)
                changed = False
                if "CredentialVerified" not in config:
                    config["CredentialVerified"] = False
                    changed = True
                if "CredentialVerifiedAt" not in config:
                    config["CredentialVerifiedAt"] = ""
                    changed = True
                if "PasswordFormat" not in config and config.get("ProtectedPassword"):
                    config["PasswordFormat"] = "legacy-base64"
                    changed = True
                if changed:
                    with open(self.config_file, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return
        default_config = {
            "UserName": "",
            "ProtectedPassword": "",
            "PasswordFormat": "dpapi",
            "CreatedTime": json.dumps({"__type": "DateTime", "iso": "2024-01-01T00:00:00Z"}),
            "CredentialVerified": False,
            "CredentialVerifiedAt": "",
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)

    def load_settings(self):
        self.settings = {"window_width": 620, "window_height": 860, "first_run_completed": False}
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except Exception:
                pass
        self.settings["window_width"] = max(int(self.settings.get("window_width", 620)), 620)
        self.settings["window_height"] = max(int(self.settings.get("window_height", 860)), 850)

    def save_settings(self):
        try:
            self.settings["window_width"] = max(self.master.winfo_width(), 620)
            self.settings["window_height"] = max(self.master.winfo_height(), 850)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def center_window(self, width, height):
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.master.geometry(f"{width}x{height}+{x}+{y}")

    def load_icons(self):
        icon_names = [
            "network",
            "account",
            "save",
            "login",
            "login_white",
            "refresh",
            "startup",
            "log",
            "message",
            "success",
            "warning",
            "error",
        ]
        for name in icon_names:
            path = resource_path(os.path.join("assets", "icons", f"{name}.png"))
            try:
                self.icons[name] = tk.PhotoImage(file=path)
            except Exception:
                self.icons[name] = None

    def apply_window_icon(self):
        icon_path = resource_path(os.path.join("assets", "app_icon.ico"))
        try:
            self.master.iconbitmap(icon_path)
        except Exception:
            pass

    def ensure_taskbar_visible(self):
        if os.name != "nt":
            return
        try:
            self.master.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.master.winfo_id()) or self.master.winfo_id()
            gwl_exstyle = -20
            ws_ex_appwindow = 0x00040000
            ws_ex_toolwindow = 0x00000080
            exstyle = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            exstyle = (exstyle | ws_ex_appwindow) & ~ws_ex_toolwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, exstyle)
            ctypes.windll.user32.ShowWindow(hwnd, 0)
            ctypes.windll.user32.ShowWindow(hwnd, 5)
            self.master.lift()
        except Exception:
            pass

    def redraw_window_shell(self, event=None):
        width = event.width if event else self.master.winfo_width()
        height = event.height if event else self.master.winfo_height()
        if width <= 24 or height <= 24:
            return
        self.window_canvas.delete("shell")
        draw_round_rect(self.window_canvas, 1, 1, width - 2, height - 2, 22, APP_BG, APP_BG, tags="shell")
        self.window_canvas.tag_lower("shell")
        requested_height = 1
        try:
            requested_height = self.window_body.winfo_reqheight()
        except Exception:
            pass
        self.window_canvas.itemconfigure(
            self.window_item,
            width=max(1, width - 20),
            height=max(1, height - 20, requested_height),
        )
        self.update_content_scrollregion()

    def update_content_scrollregion(self, _event=None):
        try:
            requested_height = self.window_body.winfo_reqheight()
            visible_height = max(1, self.window_canvas.winfo_height() - 20)
            self.window_canvas.itemconfigure(self.window_item, height=max(1, visible_height, requested_height))
            self.content_max_scroll_y = max(0, requested_height - visible_height)
            self.content_scroll_y = min(max(0, self.content_scroll_y), self.content_max_scroll_y)
            self.window_canvas.coords(self.window_item, 10, 10 - self.content_scroll_y)
            self.window_canvas.configure(scrollregion=(0, 0, self.window_canvas.winfo_width(), self.window_canvas.winfo_height()))
        except Exception:
            pass

    def is_descendant_widget(self, widget, parent):
        try:
            current = widget
            while current is not None:
                if current == parent:
                    return True
                current = current.master
        except Exception:
            pass
        return False

    def on_mousewheel(self, event):
        try:
            widget = getattr(event, "widget", None)
            if not self.is_descendant_widget(widget, self.master):
                return
            if isinstance(widget, tk.Text):
                return
            self.update_content_scrollregion()
            if self.content_max_scroll_y <= 0:
                self.content_scroll_y = 0
                self.window_canvas.coords(self.window_item, 10, 10)
                return
            delta = getattr(event, "delta", 0)
            if delta:
                step = -1 * int(delta / 120) * 40
            elif getattr(event, "num", None) == 4:
                step = -40
            elif getattr(event, "num", None) == 5:
                step = 40
            else:
                return
            self.content_scroll_y = min(max(0, self.content_scroll_y + step), self.content_max_scroll_y)
            self.window_canvas.coords(self.window_item, 10, 10 - self.content_scroll_y)
            return "break"
        except Exception:
            pass

    def icon(self, name):
        return self.icons.get(name)

    def encrypt_password(self, password):
        encrypted = dpapi_protect(password.encode("utf-16-le"))
        return binascii.hexlify(encrypted).decode("ascii")

    def decrypt_password(self, encrypted):
        if not encrypted:
            return ""
        try:
            if all(c in "0123456789abcdefABCDEF" for c in encrypted) and len(encrypted) % 2 == 0:
                data = dpapi_unprotect(binascii.unhexlify(encrypted))
                return data.decode("utf-16-le")
        except Exception:
            pass
        return base64.b64decode(encrypted.encode("ascii")).decode("utf-8")

    def migrate_password_to_dpapi_if_needed(self, config):
        if not self.has_account_config(config) or config.get("PasswordFormat") == "dpapi":
            return config
        try:
            password = self.decrypt_password(config.get("ProtectedPassword", ""))
            config["ProtectedPassword"] = self.encrypt_password(password)
            config["PasswordFormat"] = "dpapi"
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.log("旧密码格式已迁移为 Windows DPAPI", SUCCESS, "配置")
        except Exception as e:
            self.log(f"旧密码格式迁移失败: {e}", WARNING, "配置")
        return config

    def create_widgets(self):
        self.master.configure(bg=TRANSPARENT)
        try:
            self.master.attributes("-transparentcolor", TRANSPARENT)
        except Exception:
            self.master.configure(bg=APP_BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Thin.Horizontal.TProgressbar", troughcolor="#e2e8f0", background="#14b8a6")

        self.window_canvas = tk.Canvas(self.master, bg=TRANSPARENT, bd=0, highlightthickness=0, relief=tk.FLAT)
        self.window_canvas.pack(fill=tk.BOTH, expand=True)
        self.window_body = tk.Frame(self.window_canvas, bg=APP_BG, bd=0, highlightthickness=0)
        self.window_item = self.window_canvas.create_window(10, 10, window=self.window_body, anchor=tk.NW)
        self.window_canvas.bind("<Configure>", self.redraw_window_shell)
        self.window_body.bind("<Configure>", self.update_content_scrollregion)
        self.window_canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.window_canvas.bind_all("<Button-4>", self.on_mousewheel)
        self.window_canvas.bind_all("<Button-5>", self.on_mousewheel)

        self.title_bar = tk.Frame(self.window_body, bg=APP_BG, height=40)
        self.title_bar.pack(fill=tk.X)
        self.title_bar.bind("<ButtonPress-1>", self.start_window_drag)
        self.title_bar.bind("<B1-Motion>", self.drag_window)
        self.create_icon_label(self.title_bar, "network", bg=APP_BG).pack(side=tk.LEFT, padx=(10, 6))
        self.close_button = CapsuleButton(
            self.title_bar,
            "×",
            command=self.on_closing,
            width=44,
            height=44,
            variant="close",
        )
        self.close_button.pack(side=tk.RIGHT, padx=(2, 10), pady=0)

        self.main_container = tk.Frame(self.window_body, bg=APP_BG, padx=18, pady=10)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(self.main_container, bg=APP_BG)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="校园网自动登录", bg=APP_BG, fg=TEXT, font=(UI_FONT, 20, "bold")).pack(anchor=tk.W)
        tk.Label(header, text="网络状态、账号配置和开机自启集中管理", bg=APP_BG, fg=MUTED, font=(UI_FONT, 10)).pack(anchor=tk.W, pady=(4, 0))

        self.status_panel_shell = self.create_panel(self.main_container)
        self.status_panel_shell.pack(fill=tk.X, pady=(0, 8))
        self.status_panel = self.status_panel_shell.body
        self.status_panel.grid_columnconfigure((0, 1, 2, 3), weight=1)
        tk.Label(self.status_panel, text="系统状态", bg=SURFACE, fg=TEXT, font=(UI_FONT, 11, "bold")).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))

        self.network_label = self.create_status_item(0, "network", "网络状态", "检测中...")
        self.config_label = self.create_status_item(1, "success", "配置状态", "检测中...")
        self.startup_label = self.create_status_item(2, "startup", "自启状态", "检测中...")
        self.account_label = self.create_status_item(3, "account", "账号状态", "未保存")

        self.refresh_button = CapsuleButton(
            self.status_panel,
            "刷新状态",
            command=self.check_status,
            image=self.icon("refresh"),
            width=146,
            variant="secondary",
        )
        self.refresh_button.grid(row=0, column=3, sticky=tk.E, pady=(0, 8))

        account_panel_shell = self.create_panel(self.main_container)
        account_panel_shell.pack(fill=tk.X, pady=(0, 8))
        account_panel = account_panel_shell.body
        account_panel.grid_columnconfigure(1, weight=1)
        tk.Label(account_panel, text="账号设置", bg=SURFACE, fg=TEXT, font=(UI_FONT, 11, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        self.input_grid = tk.Frame(account_panel, bg=SURFACE)
        self.input_grid.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
        self.input_grid.grid_columnconfigure(1, weight=1)

        self.account_input_label = self.create_label(self.input_grid, "账号")
        self.account_input_label.grid(row=0, column=0, sticky=tk.W, pady=6)
        self.account_entry_box = RoundedBox(self.input_grid, fill="#ffffff", radius=10)
        self.account_entry_box.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(12, 0), pady=6)
        self.account_entry = tk.Entry(
            self.account_entry_box,
            width=28,
            font=(UI_FONT, 10),
            bg="#ffffff",
            fg=TEXT,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            insertbackground=TEXT,
        )
        self.account_entry.pack(fill=tk.X, padx=10, pady=6)

        self.password_label = self.create_label(self.input_grid, "密码")
        self.password_label.grid(row=1, column=0, sticky=tk.W, pady=6)
        self.password_entry_box = RoundedBox(self.input_grid, fill="#ffffff", radius=10)
        self.password_entry_box.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(12, 0), pady=6)
        self.password_entry = tk.Entry(
            self.password_entry_box,
            width=28,
            font=(UI_FONT, 10),
            bg="#ffffff",
            fg=TEXT,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            insertbackground=TEXT,
        )
        self.password_entry.pack(fill=tk.X, padx=10, pady=6)

        action_panel_shell = self.create_panel(self.main_container)
        action_panel_shell.pack(fill=tk.X, pady=(0, 8))
        action_panel = action_panel_shell.body
        action_panel.grid_columnconfigure((0, 1, 2), weight=1)
        tk.Label(action_panel, text="快捷操作", bg=SURFACE, fg=TEXT, font=(UI_FONT, 11, "bold")).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))

        self.login_button = CapsuleButton(
            action_panel,
            "立即登录",
            command=self.start_login,
            image=self.icon("login_white"),
            width=158,
            variant="primary",
        )
        self.login_button.grid(row=1, column=0, sticky=tk.W, padx=(0, 8))
        self.login_button.bind("<Enter>", self.show_login_hover_tip, add="+")
        self.login_button.bind("<Leave>", self.hide_login_hover_tip, add="+")

        self.save_button = CapsuleButton(
            action_panel,
            "保存账号",
            command=self.save_account,
            image=self.icon("save"),
            width=158,
            variant="green",
        )
        self.save_button.grid(row=1, column=1, padx=8)

        self.startup_button = CapsuleButton(
            action_panel,
            "开机自启",
            command=self.toggle_startup,
            image=self.icon("startup"),
            width=158,
            variant="purple",
        )
        self.startup_button.grid(row=1, column=2, sticky=tk.E, padx=(8, 0))
        self.check_initial_state()

        self.progress_bar = ttk.Progressbar(self.main_container, mode="indeterminate", style="Thin.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        self.progress_bar.pack_forget()

        message_panel_shell = self.create_panel(self.main_container)
        message_panel_shell.pack(fill=tk.X, pady=(0, 8))
        message_panel = message_panel_shell.body
        self.create_section_header(message_panel, "message", "提示消息").pack(fill=tk.X, pady=(0, 8))
        self.message_label = tk.Label(message_panel, text="", bg=SURFACE, fg=TEXT, anchor="w", justify=tk.LEFT, wraplength=560, font=(UI_FONT, 10))
        self.message_label.pack(fill=tk.X)

        self.log_panel_shell = self.create_panel(self.main_container)
        self.log_panel_shell.pack(fill=tk.BOTH, expand=True)
        self.log_panel = self.log_panel_shell.body
        header = self.create_section_header(self.log_panel, "log", "操作日志")
        header.pack(fill=tk.X, pady=(0, 8))
        header.bind("<Button-1>", lambda _e: self.toggle_log())
        self.log_toggle = CapsuleButton(
            header,
            "展开",
            command=self.toggle_log,
            width=76,
            height=32,
            variant="secondary",
        )
        self.log_toggle.pack(side=tk.RIGHT)
        self.copy_diagnostic_button = CapsuleButton(
            header,
            "复制诊断",
            command=self.copy_diagnostic_info,
            width=96,
            height=32,
            variant="secondary",
        )
        self.copy_diagnostic_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.diagnostic_button = CapsuleButton(
            header,
            "诊断",
            command=self.run_diagnostics,
            width=76,
            height=32,
            variant="secondary",
        )
        self.diagnostic_button.pack(side=tk.RIGHT, padx=(0, 8))

        self.log_summary_box = RoundedBox(self.log_panel, radius=12, fill=LOG_BG)
        self.log_summary_box.pack(fill=tk.X)
        self.log_summary = tk.Text(
            self.log_summary_box,
            height=5,
            state=tk.DISABLED,
            font=(MONO_FONT, 9),
            bg=LOG_BG,
            fg="#334155",
            wrap=tk.WORD,
            relief=tk.FLAT,
            highlightthickness=0,
            padx=8,
            pady=6,
        )
        self.log_summary.pack(fill=tk.X, padx=5, pady=5)

        self.log_full_frame = RoundedBox(self.log_panel, radius=12, fill=LOG_BG)
        self.log_full_frame.grid_columnconfigure(0, weight=1)
        self.log_full_frame.grid_rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            self.log_full_frame,
            height=9,
            state=tk.DISABLED,
            font=(MONO_FONT, 9),
            bg=LOG_BG,
            fg="#334155",
            wrap=tk.WORD,
            relief=tk.FLAT,
            highlightthickness=0,
            padx=8,
            pady=8,
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0), pady=5)
        v_scrollbar = ttk.Scrollbar(self.log_full_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S), padx=(0, 5), pady=5)
        self.log_text.configure(yscrollcommand=v_scrollbar.set)

        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_panel(self, parent):
        return RoundedPanel(parent, radius=22, shadow=True, content_pad=(14, 12), highlightthickness=0, bd=0)

    def create_label(self, parent, text):
        return tk.Label(parent, text=text, bg=SURFACE, fg="#334155", font=(UI_FONT, 10))

    def create_icon_label(self, parent, name, bg=SURFACE):
        image = self.icon(name)
        return tk.Label(parent, image=image, bg=bg) if image else tk.Label(parent, text="", bg=bg)

    def create_section_header(self, parent, icon_name, text):
        frame = tk.Frame(parent, bg=SURFACE, cursor="hand2")
        self.create_icon_label(frame, icon_name).pack(side=tk.LEFT)
        tk.Label(frame, text=text, bg=SURFACE, fg=TEXT, font=(UI_FONT, 11, "bold"), cursor="hand2").pack(side=tk.LEFT, padx=(8, 0))
        return frame

    def create_status_item(self, column, icon_name, label_text, value_text):
        item = tk.Frame(self.status_panel, bg=SURFACE)
        item.grid(row=1, column=column, sticky=(tk.W, tk.E), padx=(0 if column == 0 else 10, 0))
        self.create_icon_label(item, icon_name).pack(anchor=tk.W)
        tk.Label(item, text=label_text, bg=SURFACE, fg=MUTED, font=(UI_FONT, 9)).pack(anchor=tk.W, pady=(6, 1))
        value = tk.Label(item, text=value_text, bg=SURFACE, fg=TEXT, font=(UI_FONT, 10, "bold"))
        value.pack(anchor=tk.W)
        return value

    def set_button_busy(self, button, text=None):
        if button in self.busy_buttons:
            return False
        self.busy_buttons.add(button)
        if text:
            button.config(text=text)
        button.config(state=tk.DISABLED)
        self.master.update_idletasks()
        return True

    def restore_button(self, button):
        self.busy_buttons.discard(button)
        try:
            button.config(state=tk.NORMAL)
        except Exception:
            pass

    def start_window_drag(self, event):
        self.drag_x = event.x_root - self.master.winfo_x()
        self.drag_y = event.y_root - self.master.winfo_y()

    def drag_window(self, event):
        self.master.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def check_initial_state(self):
        config = self.get_config()
        has_config = bool(config.get("UserName") and config.get("ProtectedPassword"))
        if has_config:
            self.account_entry_box.grid_forget()
            self.password_entry_box.grid_forget()
            self.password_label.grid_forget()
            if hasattr(self, "account_info_label"):
                self.account_info_label.destroy()
            self.account_info_label = self.create_label(self.input_grid, config["UserName"])
            self.account_info_label.grid(row=0, column=1, sticky=tk.W, padx=(12, 0), pady=6)
            self.is_editing_account = False
            self.save_button.config(text="更改账户", command=self.enable_account_edit)
        else:
            if hasattr(self, "account_info_label"):
                self.account_info_label.destroy()
            self.account_input_label.grid(row=0, column=0, sticky=tk.W, pady=6)
            self.account_entry_box.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(12, 0), pady=6)
            self.password_label.grid(row=1, column=0, sticky=tk.W, pady=6)
            self.password_entry_box.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(12, 0), pady=6)
            self.is_editing_account = True
            self.save_button.config(text="保存账号", command=self.save_account)

    def enable_account_edit(self):
        if not self.set_button_busy(self.save_button, "处理中"):
            return

        def work():
            config = self.get_config()
            if self.is_credential_verified(config):
                code = self.notify_user_wait(
                    "确认更改账户",
                    "当前账号密码已验证通过。更改后会重置验证状态，需要重新验证登录。确定要更改吗？",
                    "warning",
                    "confirm-cancel",
                )
                if code != 0:
                    def cancel_update():
                        self.restore_button(self.save_button)
                        self.check_initial_state()

                    self.master.after(0, cancel_update)
                    return

            def update():
                self.is_editing_account = True
                if hasattr(self, "account_info_label"):
                    self.account_info_label.destroy()
                self.account_input_label.grid(row=0, column=0, sticky=tk.W, pady=6)
                self.account_entry_box.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(12, 0), pady=6)
                self.password_label.grid(row=1, column=0, sticky=tk.W, pady=6)
                self.password_entry_box.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(12, 0), pady=6)
                self.password_entry.delete(0, tk.END)
                self.save_button.config(text="保存账号", command=self.save_account)
                self.restore_button(self.save_button)

            self.master.after(0, update)

        threading.Thread(target=work, daemon=True).start()

    def on_closing(self):
        self.hide_login_hover_tip()
        self.save_settings()
        self.force_exit()

    def force_exit(self):
        try:
            self.window_canvas.unbind_all("<MouseWheel>")
            self.window_canvas.unbind_all("<Button-4>")
            self.window_canvas.unbind_all("<Button-5>")
        except Exception:
            pass
        try:
            self.master.quit()
        except Exception:
            pass
        try:
            self.master.destroy()
        except Exception:
            pass

    def show_message(self, message, color=TEXT, replace=False):
        def enqueue():
            if replace:
                self.message_queue.clear()
                self.message_token += 1
                token = self.message_token
                self.message_active = True
                self.message_label.config(text=message, fg=color)
                self.master.after(self.message_min_duration_ms, lambda: self.finish_message_display(token))
                return
            if self.message_queue and self.message_queue[-1][0] == message:
                self.message_queue[-1] = (message, color)
            else:
                self.message_queue.append((message, color))
            if len(self.message_queue) > 8:
                self.message_queue = self.message_queue[-8:]
            self.process_message_queue()

        self.master.after(0, enqueue)

    def process_message_queue(self):
        if self.message_active or not self.message_queue:
            return
        message, color = self.message_queue.pop(0)
        self.message_active = True
        self.message_token += 1
        token = self.message_token
        self.message_label.config(text=message, fg=color)
        self.master.after(self.message_min_duration_ms, lambda: self.finish_message_display(token))

    def finish_message_display(self, token=None):
        if token is not None and token != self.message_token:
            return
        self.message_active = False
        self.process_message_queue()

    def notify_user(self, title, message, kind="warning", buttons="ok"):
        if self.should_skip_duplicate_notice(title, message, kind, buttons):
            return 0
        payload = {
            "title": title or "校园网自动登录",
            "message": message,
            "kind": kind,
            "buttons": buttons,
        }
        encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
        candidates = [
            [os.path.join(self.script_dir, "notifier", "StartupNotifier.exe"), "--payload", encoded],
            [os.path.join(self.script_dir, "internal", "StartupNotifier", "StartupNotifier.exe"), "--payload", encoded],
            [os.path.join(self.script_dir, "internal", "StartupNotifier.exe"), "--payload", encoded],
            [os.path.join(self.script_dir, "StartupNotifier.exe"), "--payload", encoded],
        ]
        notifier_py = os.path.join(self.script_dir, "StartupNotifier.py")
        if os.path.exists(notifier_py):
            candidates.append([sys.executable, notifier_py, "--payload", encoded])

        for command in candidates:
            if os.path.exists(command[0]):
                try:
                    subprocess.Popen(
                        command,
                        cwd=self.script_dir,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    return 0
                except Exception as e:
                    self.log(f"提示窗口启动失败: {e}", WARNING, "错误")
                    return 20
        self.log("提示程序缺失，已跳过弹窗", WARNING, "错误")
        return 20

    def notify_user_wait(self, title, message, kind="warning", buttons="ok"):
        if self.should_skip_duplicate_notice(title, message, kind, buttons):
            return 20
        payload = {
            "title": title or "校园网自动登录",
            "message": message,
            "kind": kind,
            "buttons": buttons,
        }
        encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
        candidates = [
            [os.path.join(self.script_dir, "notifier", "StartupNotifier.exe"), "--payload", encoded],
            [os.path.join(self.script_dir, "internal", "StartupNotifier", "StartupNotifier.exe"), "--payload", encoded],
            [os.path.join(self.script_dir, "internal", "StartupNotifier.exe"), "--payload", encoded],
            [os.path.join(self.script_dir, "StartupNotifier.exe"), "--payload", encoded],
        ]
        notifier_py = os.path.join(self.script_dir, "StartupNotifier.py")
        if os.path.exists(notifier_py):
            candidates.append([sys.executable, notifier_py, "--payload", encoded])
        for command in candidates:
            if os.path.exists(command[0]):
                try:
                    result = subprocess.run(command, cwd=self.script_dir, creationflags=subprocess.CREATE_NO_WINDOW)
                    return result.returncode
                except Exception as e:
                    self.log(f"确认窗口启动失败: {e}", WARNING, "错误")
                    return 20
        self.log("提示程序缺失，确认操作已取消", WARNING, "错误")
        return 20

    def should_skip_duplicate_notice(self, title, message, kind, buttons):
        now = time.monotonic()
        signature = (title or "校园网自动登录", message or "", kind or "warning", buttons or "ok")
        last_shown_at = self.notice_last_shown.get(signature, 0)
        if now - last_shown_at < self.notice_dedupe_seconds:
            self.log("已忽略重复提示弹窗", MUTED, "提示")
            return True
        self.notice_last_shown[signature] = now
        if len(self.notice_last_shown) > 32:
            expired_before = now - self.notice_dedupe_seconds * 4
            self.notice_last_shown = {
                key: value
                for key, value in self.notice_last_shown.items()
                if value >= expired_before
            }
        return False

    def log(self, message, color=TEXT, category="后台"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = (f"{timestamp} [{category}] {message}", color)
        self.log_entries.append(entry)
        if len(self.log_entries) > 500:
            self.log_entries = self.log_entries[-500:]

        def update():
            self.refresh_log_views()

        self.master.after(0, update)

    def refresh_log_views(self):
        recent = self.log_entries[-3:]
        self.log_summary.config(state=tk.NORMAL)
        self.log_summary.delete("1.0", tk.END)
        for message, color in recent:
            tag = f"summary_{len(message)}_{time.time()}"
            self.log_summary.insert(tk.END, message + "\n", tag)
            self.log_summary.tag_config(tag, foreground=color)
        self.log_summary.config(state=tk.DISABLED)

        if self.log_expanded:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            for message, color in self.log_entries:
                tag = f"full_{len(message)}_{time.time()}"
                self.log_text.insert(tk.END, message + "\n", tag)
                self.log_text.tag_config(tag, foreground=color)
            self.log_text.config(state=tk.DISABLED)
            self.log_text.yview_moveto(1.0)

    def toggle_log(self):
        self.log_expanded = not self.log_expanded
        if self.log_expanded:
            self.log_summary_box.pack_forget()
            self.log_full_frame.pack(fill=tk.BOTH, expand=True)
            self.log_toggle.config(text="收起")
        else:
            self.log_full_frame.pack_forget()
            self.log_summary_box.pack(fill=tk.X)
            self.log_toggle.config(text="展开")
        self.refresh_log_views()

    def test_internet(self):
        now = time.time()
        if now - self.internet_cache.get("time", 0) < 1.5:
            return self.internet_cache.get("value", False)
        try:
            request = urllib.request.Request(
                "http://www.msftconnecttest.com/connecttest.txt",
                headers={"User-Agent": "Microsoft NCSI"},
            )
            response = urllib.request.urlopen(request, timeout=0.6)
            content = response.read().decode("utf-8", errors="ignore").strip()
            value = response.status == 200 and "Microsoft Connect Test" in content
        except Exception:
            value = False
        self.internet_cache = {"time": time.time(), "value": value}
        return value

    def check_proxy_enabled(self):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                return proxy_enable == 1
        except Exception:
            return False

    def get_cached_login_url(self):
        url_file = os.path.join(self.script_dir, "login_url.txt")
        if os.path.exists(url_file):
            try:
                with open(url_file, "r", encoding="utf-8-sig") as f:
                    url = f.read().strip()
                if url.startswith("http"):
                    return url
            except Exception:
                pass
        return ""

    def test_portal_reachable(self):
        try:
            login_url = self.get_cached_login_url()
            if not login_url:
                return False
            parsed = urllib.parse.urlparse(login_url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            with socket.create_connection((parsed.hostname, port), timeout=0.6):
                return True
        except Exception:
            return False

    def get_required_script_status(self):
        required = [
            "AutoLogin.ps1",
            "StartupAutoLogin.ps1",
            "StartupAutoLogin.vbs",
            "install_scheduled_task.ps1",
            "uninstall_scheduled_task.ps1",
            "manage.ps1",
        ]
        missing = [name for name in required if not os.path.exists(os.path.join(self.scripts_dir, name))]
        return missing

    def repair_missing_scripts(self, missing_scripts):
        repaired = []
        still_missing = []
        if not missing_scripts:
            return repaired, still_missing

        try:
            os.makedirs(self.scripts_dir, exist_ok=True)
        except Exception as e:
            self.log(f"创建脚本目录失败: {e}", ERROR, "诊断")
            return repaired, list(missing_scripts)

        for name in missing_scripts:
            target = os.path.join(self.scripts_dir, name)
            candidates = [
                os.path.join(self.script_dir, name),
                resource_path(os.path.join("bundled_scripts", name)),
            ]
            source = next((path for path in candidates if os.path.exists(path) and os.path.abspath(path) != os.path.abspath(target)), "")
            if not source:
                still_missing.append(name)
                continue
            try:
                shutil.copy2(source, target)
                repaired.append(name)
                self.log(f"已自动补全脚本: scripts/{name}", SUCCESS, "诊断")
            except Exception as e:
                still_missing.append(name)
                self.log(f"自动补全脚本失败 {name}: {e}", ERROR, "诊断")

        return repaired, still_missing

    def build_diagnostic_report(self):
        config = self.get_config()
        has_account = self.has_account_config(config)
        verified = self.is_credential_verified(config)
        missing_scripts = self.get_required_script_status()
        repaired_scripts, unrepaired_scripts = self.repair_missing_scripts(missing_scripts)
        if repaired_scripts:
            missing_scripts = self.get_required_script_status()
        startup_status, _ = self.check_startup_status()
        task_action = self.get_startup_task_action()
        notifier_path = os.path.join(self.script_dir, "notifier", "StartupNotifier.exe")
        legacy_notifier_onedir_path = os.path.join(self.script_dir, "internal", "StartupNotifier", "StartupNotifier.exe")
        legacy_notifier_path = os.path.join(self.script_dir, "internal", "StartupNotifier.exe")
        notifier_exists = (
            os.path.exists(notifier_path)
            or os.path.exists(legacy_notifier_onedir_path)
            or os.path.exists(legacy_notifier_path)
        )
        online = self.test_internet()
        proxy_enabled = self.check_proxy_enabled()
        portal_reachable = self.test_portal_reachable()

        lines = [
            "校园网自动登录诊断",
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"程序目录: {self.script_dir}",
            f"脚本目录: {self.scripts_dir}",
            f"网络: {'已联网' if online else '未确认联网'}",
            f"系统代理: {'已开启' if proxy_enabled else '未开启'}",
            f"认证站端口: {'可达' if portal_reachable else '不可达或未连接校园网'}",
            f"账号配置: {'已保存' if has_account else '未保存'}",
            f"账号验证: {'已验证' if verified else '未验证'}",
            f"开机自启: {startup_status}",
            f"通知程序: {'存在' if notifier_exists else '缺失'}",
            f"脚本文件: {'完整' if not missing_scripts else '缺失 ' + ', '.join(missing_scripts)}",
        ]
        if repaired_scripts:
            lines.append(f"自动修复脚本: 已补全 {', '.join(repaired_scripts)}")
        if unrepaired_scripts:
            lines.append(f"未能自动补全脚本: {', '.join(unrepaired_scripts)}")
        if task_action:
            lines.extend(
                [
                    f"任务执行程序: {task_action.get('Execute', '')}",
                    f"任务参数: {task_action.get('Arguments', '')}",
                    f"任务工作目录: {task_action.get('WorkingDirectory', '')}",
                ]
            )

        problems = []
        if proxy_enabled:
            problems.append("关闭系统代理后重试")
        if not has_account:
            problems.append("先保存账号密码")
        if startup_status == "需修复":
            problems.append("点击“修复自启”重装计划任务")
        if missing_scripts:
            problems.append("缺失脚本无法自动补全，请重新解压完整发布包")
        if not notifier_exists:
            problems.append("确认 notifier/StartupNotifier.exe 存在")
        if not online and not portal_reachable:
            problems.append("检查 WLAN 是否打开并连接 CMCC 校园网")
        lines.append("建议: " + ("；".join(problems) if problems else "当前未发现明显配置问题"))
        return "\n".join(lines)

    def run_diagnostics(self):
        if not self.set_button_busy(self.diagnostic_button, "诊断中"):
            return
        self.log("开始执行诊断", PRIMARY, "诊断")

        def work():
            try:
                report = self.build_diagnostic_report()
                summary = report.splitlines()[-1].replace("建议: ", "")
                self.last_diagnostic_text = report
                for line in report.splitlines():
                    self.log(line, TEXT, "诊断")
                if "未发现" not in summary:
                    self.show_message(summary, WARNING, replace=True)
            except Exception as e:
                self.show_message(f"诊断失败: {e}", ERROR, replace=True)
                self.log(f"诊断失败: {e}", ERROR, "诊断")
            finally:
                self.master.after(0, lambda: self.restore_button(self.diagnostic_button))
                self.master.after(0, lambda: self.diagnostic_button.config(text="诊断"))

        threading.Thread(target=work, daemon=True).start()

    def copy_diagnostic_info(self):
        if not self.last_diagnostic_text:
            self.last_diagnostic_text = self.build_diagnostic_report()
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(self.last_diagnostic_text)
            self.log("诊断信息已复制到剪贴板", SUCCESS, "诊断")
        except Exception as e:
            self.show_message(f"复制诊断信息失败: {e}", ERROR, replace=True)
            self.log(f"复制诊断信息失败: {e}", ERROR, "诊断")

    def get_config(self):
        if not os.path.exists(self.config_file):
            self.ensure_config_exists()
        try:
            with open(self.config_file, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            self.ensure_config_exists()
            return {"UserName": "", "ProtectedPassword": ""}

    def has_account_config(self, config=None):
        config = config or self.get_config()
        return bool(config.get("UserName") and config.get("ProtectedPassword"))

    def is_credential_verified(self, config=None):
        config = config or self.get_config()
        return config.get("CredentialVerified") is True

    def mark_credential_verified(self):
        try:
            config = self.get_config()
            if not self.has_account_config(config):
                return
            config = self.migrate_password_to_dpapi_if_needed(config)
            config["CredentialVerified"] = True
            config["CredentialVerifiedAt"] = datetime.now().isoformat(timespec="seconds")
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.log("账号验证状态已写入配置", SUCCESS, "配置")
        except Exception as e:
            self.log(f"更新账号验证状态失败: {e}", WARNING, "错误")

    def update_network_status_ui(self, status, color):
        self.network_label.config(text=status, fg=color)

    def update_config_status_ui(self, status, color, account):
        self.config_label.config(text=status, fg=color)
        self.account_label.config(text="已保存" if account else "未保存", fg=TEXT if account else MUTED)

    def update_account_entry_ui(self, username):
        self.account_entry.delete(0, tk.END)
        self.account_entry.insert(0, username)

    def update_startup_status_ui(self, status, color):
        self.startup_label.config(text=status, fg=color)
        if status == "已开启":
            text = "关闭自启"
        elif status == "需修复":
            text = "修复自启"
        else:
            text = "开机自启"
        self.startup_button.config(text=text)

    def get_startup_task_action(self):
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", self.startup_task_name, "/XML"],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        xml_text = result.stdout.strip()
        root = ET.fromstring(xml_text)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        exec_node = root.find(".//t:Actions/t:Exec", ns)
        if exec_node is None:
            exec_node = root.find(".//Actions/Exec")
        if exec_node is None:
            return {}

        def read_text(name):
            node = exec_node.find(f"t:{name}", ns)
            if node is None:
                node = exec_node.find(name)
            return node.text if node is not None and node.text else ""

        return {
            "Execute": read_text("Command"),
            "Arguments": read_text("Arguments"),
            "WorkingDirectory": read_text("WorkingDirectory"),
        }

    def is_startup_task_action_valid(self, action):
        if not action:
            return False
        execute = str(action.get("Execute") or "").strip('"').lower()
        arguments = str(action.get("Arguments") or "").replace('"', "").lower()
        working_dir = str(action.get("WorkingDirectory") or "").strip('"')
        expected_launcher = os.path.abspath(self.startup_launcher_script).lower()
        expected_workdir = os.path.abspath(self.script_dir).lower()
        return (
            bool(working_dir)
            and
            execute.endswith("wscript.exe")
            and expected_launcher in arguments
            and os.path.abspath(working_dir).lower() == expected_workdir
            and os.path.exists(self.startup_launcher_script)
        )

    def check_startup_status(self):
        try:
            action = self.get_startup_task_action()
            if action is not None:
                if self.is_startup_task_action_valid(action):
                    return "已开启", SUCCESS
                return "需修复", WARNING

            startup_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            for name in ("AutoLogin.lnk", "CmccAutoLogin.lnk", "CmccAutoLogin.cmd", "CMCC_AutoLogin.lnk"):
                if os.path.exists(os.path.join(startup_dir, name)):
                    return "需修复", WARNING
            return "未开启", ERROR
        except Exception:
            return "未知", WARNING

    def check_status(self):
        if self.is_refreshing:
            self.log("正在检测中，已忽略重复刷新", WARNING)
            return
        if hasattr(self, "refresh_button") and not self.set_button_busy(self.refresh_button, "检测中"):
            return
        self.is_refreshing = True
        self.log("开始检测系统状态")

        def work():
            results = {}
            threads = [
                threading.Thread(target=lambda: results.update(is_connected=self.test_internet()), daemon=True),
                threading.Thread(target=lambda: results.update(startup=self.check_startup_status()), daemon=True),
            ]
            for thread in threads:
                thread.start()
            config = self.get_config()
            has_config = bool(config.get("UserName") and config.get("ProtectedPassword"))
            for thread in threads:
                thread.join()
            is_connected = results.get("is_connected", False)
            startup_status, startup_color = results.get("startup", ("未知", WARNING))

            def update():
                self.is_connected = is_connected
                if is_connected:
                    self.update_network_status_ui("已连接", SUCCESS)
                else:
                    self.update_network_status_ui("需要登录", WARNING)

                if has_config:
                    self.update_config_status_ui("已配置", SUCCESS, config["UserName"])
                    self.update_account_entry_ui(config["UserName"])
                else:
                    self.update_config_status_ui("未配置", ERROR, "")

                self.update_startup_status_ui(startup_status, startup_color)
                self.update_login_button_text()
                self.log(
                    f"状态检测完成: 网络={'已连接' if is_connected else '需要登录'}，账号={'已配置' if has_config else '未配置'}，自启={startup_status}"
                )
                self.is_refreshing = False
                self.restore_button(self.refresh_button)
                self.refresh_button.config(text="刷新状态")

            self.master.after(0, update)

        threading.Thread(target=work, daemon=True).start()

    def update_login_button_text(self):
        config = self.get_config()
        has_config = bool(config.get("UserName") and config.get("ProtectedPassword"))
        if self.is_connected:
            self.login_button.config(text="已联网")
            if self.login_button not in self.busy_buttons:
                self.login_button.config(state=tk.DISABLED)
            return
        if self.login_button not in self.busy_buttons:
            self.login_button.config(state=tk.NORMAL)
        self.login_button.config(text="立即登录" if has_config else "验证登录")

    def show_login_hover_tip(self, _event=None):
        if self.is_connected:
            if self.login_hover_tip is None:
                self.login_hover_tip = HoverTip(self.login_button.master, "当前已联网，无需登录")
            self.login_hover_tip.show_for_widget(self.login_button)

    def hide_login_hover_tip(self, _event=None):
        if self.login_hover_tip is not None:
            self.login_hover_tip.hide()

    def save_account(self):
        if not self.set_button_busy(self.save_button, "保存中"):
            return
        username = self.account_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            self.notify_user("校园网自动登录", "请输入账号和密码。", "warning")
            self.restore_button(self.save_button)
            self.save_button.config(text="保存账号")
            return

        try:
            encrypted_pwd = self.encrypt_password(password)
            config = {
                "UserName": username,
                "ProtectedPassword": encrypted_pwd,
                "PasswordFormat": "dpapi",
                "CreatedTime": json.dumps({"__type": "DateTime", "iso": "2024-01-01T00:00:00Z"}),
                "CredentialVerified": False,
                "CredentialVerifiedAt": "",
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.show_message("账号密码已保存，尚未验证，请点击验证登录", WARNING)
            self.log("账号配置已保存，验证状态已重置", SUCCESS, "配置")
            self.notify_user("账号尚未验证", "账号密码已保存，但当前账号尚未通过认证验证。请点击“验证登录”确认账号密码正确。", "warning")
            self.check_initial_state()
            self.update_config_status_ui("已配置", SUCCESS, username)
            self.update_login_button_text()
        except Exception as e:
            self.show_message(f"保存失败: {e}", ERROR)
            self.log(f"保存账号失败: {e}", ERROR, "错误")
            self.notify_user("保存失败", f"保存失败: {e}", "error")
        finally:
            self.restore_button(self.save_button)

    def start_login(self):
        if self.is_logging_in:
            return
        username = self.account_entry.get().strip()
        password = self.password_entry.get().strip()
        editing = self.is_editing_account
        if self.is_connected or self.test_internet():
            self.is_connected = True
            self.update_network_status_ui("已连接", SUCCESS)
            self.update_login_button_text()
            if editing and username and password:
                self.save_config_for_login(username, password)
                self.check_initial_state()
                self.log("当前已联网，仅保存账号，未标记验证通过", WARNING, "配置")
                self.notify_user(
                    "校园网自动登录",
                    "当前已联网，无法通过认证站验证账号密码。本次只保存账号密码，下次需要校园网认证时会自动验证。",
                    "warning",
                )
            else:
                self.notify_user("校园网自动登录", "当前已联网，无需登录。", "success")
            return
        if not self.set_button_busy(self.login_button, "登录中"):
            return
        self.is_logging_in = True
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        self.progress_bar.start()
        self.log("开始后台登录")

        threading.Thread(target=self.login_flow, args=(editing, username, password), daemon=True).start()

    def finish_login_ui(self, popup=None):
        def update():
            try:
                if popup:
                    kind, title, text = popup
                    notify_kind = "success" if kind == "info" else kind
                    self.notify_user(title, text, notify_kind)
            finally:
                self.is_logging_in = False
                self.restore_button(self.login_button)
                self.update_login_button_text()
                self.progress_bar.stop()
                self.progress_bar.pack_forget()

        self.master.after(0, update)

    def login_flow(self, editing, username, password):
        popup = None
        try:
            if self.test_internet():
                self.is_connected = True
                if editing and username and password:
                    self.save_config_for_login(username, password)
                    self.master.after(0, self.check_initial_state)
                    self.log("当前已联网，仅保存账号，未标记验证通过", WARNING, "配置")
                    popup = (
                        "warning",
                        "校园网自动登录",
                        "当前已联网，无法通过认证站验证账号密码。本次只保存账号密码，下次需要校园网认证时会自动验证。",
                    )
                else:
                    popup = ("info", "校园网自动登录", "当前已连接网络，无需登录。")
                return

            if editing and username and password:
                self.save_config_for_login(username, password)
                self.log("账号配置已保存，准备执行登录脚本", SUCCESS, "配置")
            else:
                config = self.get_config()
                if not config.get("UserName") or not config.get("ProtectedPassword"):
                    self.show_message("请先设置账号密码", WARNING)
                    self.log("登录流程中止: 缺少账号配置", WARNING)
                    popup = ("warning", "警告", "请先设置账号密码。")
                    return

            popup = self.execute_login_core()
            self.master.after(0, self.check_initial_state)
        except Exception as e:
            self.show_message(f"登录错误: {e}", ERROR)
            self.log(f"登录流程异常: {e}", ERROR, "错误")
            popup = ("error", "错误", f"登录错误: {e}")
        finally:
            self.finish_login_ui(popup)

    def save_config_for_login(self, username, password):
        encrypted_pwd = self.encrypt_password(password)
        config = {
            "UserName": username,
            "ProtectedPassword": encrypted_pwd,
            "PasswordFormat": "dpapi",
            "CreatedTime": json.dumps({"__type": "DateTime", "iso": "2024-01-01T00:00:00Z"}),
            "CredentialVerified": False,
            "CredentialVerifiedAt": "",
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def execute_login_core(self):
        self.log("正在运行登录脚本", PRIMARY, "脚本")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", self.login_script, "-Quiet"],
                capture_output=True,
                text=True,
                timeout=45,
                cwd=self.script_dir,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            self.show_message("登录超时", ERROR)
            self.log("登录脚本超时", ERROR, "错误")
            return ("error", "错误", "登录超时。")

        self.log(f"登录脚本退出码: {result.returncode}", TEXT, "脚本")
        if result.returncode == 0:
            self.mark_credential_verified()
            self.log("登录脚本完成，联网验证通过", SUCCESS, "脚本")
            self.master.after(0, lambda: self.update_network_status_ui("已连接", SUCCESS))
            return None

        if result.returncode == 2:
            self.show_message("登录请求已提交，请稍后检查网络", WARNING)
            self.log("登录请求已提交，联网验证未立即通过", WARNING, "脚本")
            self.master.after(0, lambda: self.update_network_status_ui("等待中", WARNING))
            return None

        if result.returncode == 3:
            self.show_message("缺少账号配置", WARNING)
            self.log("登录脚本返回缺少账号配置", WARNING, "脚本")
            return ("warning", "警告", "请先设置账号密码。")

        if result.returncode == 4:
            skip_message = "当前网络不可用或认证站不可达，已快速跳过登录。请检查 WLAN 是否打开、是否已连接 CMCC 校园网。"
            self.show_message(skip_message, WARNING)
            self.log("网络不可用或认证站不可达，快速跳过登录", WARNING, "脚本")
            self.master.after(0, lambda: self.update_network_status_ui("未连接", WARNING))
            return None

        if result.returncode == 8:
            self.show_message("已有登录任务正在运行", WARNING)
            self.log("检测到已有登录脚本正在运行，已跳过重复登录", WARNING, "脚本")
            self.master.after(0, lambda: self.update_network_status_ui("检测中", WARNING))
            return None

        self.show_message("登录失败", ERROR)
        self.log("登录脚本返回失败", ERROR, "脚本")
        if self.check_proxy_enabled():
            return ("error", "错误", "登录失败。\n\n检测到您的系统代理已开启，请关闭代理后重试。")
        return ("error", "错误", "登录失败，请检查账号密码是否正确。")

    def auto_login_mode(self):
        if self.test_internet():
            self.force_exit()
            return
        config = self.get_config()
        if not config.get("UserName") or not config.get("ProtectedPassword"):
            self.force_exit()
            return
        threading.Thread(target=self.execute_silent_login, daemon=True).start()

    def execute_silent_login(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", self.startup_login_script, "-StartupNotify"],
                capture_output=True,
                text=True,
                timeout=35,
                cwd=self.script_dir,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                self.master.after(0, self.show_success_and_exit)
            else:
                self.master.after(0, self.force_exit)
        except Exception:
            self.master.after(0, self.force_exit)

    def show_success_and_exit(self):
        try:
            self.notify_user("登录成功", "校园网已自动登录成功，网络已连接。", "success")
        finally:
            self.force_exit()

    def toggle_startup(self):
        if not self.set_button_busy(self.startup_button, "处理中"):
            return
        self.log("开始处理开机自启")

        def work():
            status, _ = self.check_startup_status()
            script = self.uninstall_startup_script if status == "已开启" else self.startup_script
            ok_text = "开机自启动删除操作完成" if status == "已开启" else ("开机自启动修复成功" if status == "需修复" else "开机自启动添加成功")
            fail_text = "开机自启动删除失败" if status == "已开启" else ("开机自启动修复失败" if status == "需修复" else "开机自启动添加失败")

            try:
                if status != "已开启":
                    config = self.get_config()
                    if not self.has_account_config(config):
                        self.show_message("请先保存账号密码后再开启开机自启", WARNING, replace=True)
                        self.log("开机自启开启被阻止: 缺少账号配置", WARNING)
                        self.master.after(0, lambda: self.notify_user("校园网自动登录", "请先保存账号密码后再开启开机自启。", "warning"))
                        return
                    if not self.is_credential_verified(config):
                        unverified_text = "账号密码尚未验证；已允许开启开机自启。下次开机自启会自动尝试验证，验证成功后不再提醒。"
                        self.show_message(unverified_text, WARNING, replace=True)
                        self.log("账号未验证，继续安装计划任务并等待下次自启验证", WARNING)
                        self.master.after(0, lambda: self.notify_user("账号未验证", unverified_text, "warning"))

                if not os.path.exists(script):
                    raise FileNotFoundError(script)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.script_dir,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in (result.stdout or "").splitlines():
                    if line.strip():
                        self.log(line.strip(), TEXT, "脚本")
                for line in (result.stderr or "").splitlines():
                    if line.strip():
                        self.log(line.strip(), ERROR, "脚本")
                if result.returncode != 0:
                    raise RuntimeError(f"退出码: {result.returncode}")
                self.log(f"计划任务脚本执行完成: {ok_text}", SUCCESS, "脚本")
            except Exception as e:
                self.show_message(f"{fail_text}: {e}", ERROR, replace=True)
                self.log(f"{fail_text}: {e}", ERROR, "错误")
                self.master.after(0, lambda: self.notify_user("开机自启错误", f"{fail_text}: {e}", "error"))
            finally:
                self.master.after(0, self.refresh_startup_status)
                self.master.after(0, lambda: self.restore_button(self.startup_button))

        threading.Thread(target=work, daemon=True).start()

    def refresh_startup_status(self):
        def work():
            startup_status, startup_color = self.check_startup_status()
            self.master.after(0, lambda: self.update_startup_status_ui(startup_status, startup_color))

        threading.Thread(target=work, daemon=True).start()


def set_dpi_awareness():
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def set_app_user_model_id():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def run_external_notice(title, message, kind="warning"):
    script_dir = get_script_dir()
    payload = {
        "title": title,
        "message": message,
        "kind": kind,
        "buttons": "ok",
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    candidates = [
        [os.path.join(script_dir, "notifier", "StartupNotifier.exe"), "--payload", encoded],
        [os.path.join(script_dir, "internal", "StartupNotifier", "StartupNotifier.exe"), "--payload", encoded],
        [os.path.join(script_dir, "internal", "StartupNotifier.exe"), "--payload", encoded],
        [os.path.join(script_dir, "StartupNotifier.exe"), "--payload", encoded],
    ]
    notifier_py = os.path.join(script_dir, "StartupNotifier.py")
    if os.path.exists(notifier_py):
        candidates.append([sys.executable, notifier_py, "--payload", encoded])
    for command in candidates:
        if os.path.exists(command[0]):
            try:
                subprocess.run(command, cwd=script_dir, creationflags=subprocess.CREATE_NO_WINDOW)
                return
            except Exception:
                return


_single_instance_mutex = None


def claim_single_instance():
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, "Local\\CMCC_AutoLogin_Main_Instance")
        if not handle:
            return True
        global _single_instance_mutex
        _single_instance_mutex = handle
        return ctypes.get_last_error() != 183
    except Exception:
        return True


if __name__ == "__main__":
    try:
        set_app_user_model_id()
        set_dpi_awareness()
        write_ui_backend_log()
        if not claim_single_instance():
            run_external_notice("校园网自动登录", "主程序已经在运行，请不要重复打开。", "warning")
            sys.exit(0)
        root = tk.Tk()
        try:
            root.tk.call("tk", "scaling", max(1.0, root.winfo_fpixels("1i") / 72.0))
        except Exception:
            pass
        app = AutoLogin(root)
        root.mainloop()
    except Exception:
        try:
            with open(os.path.join(get_script_dir(), "startup_error.log"), "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise

