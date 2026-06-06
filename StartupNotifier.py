# -*- coding: utf-8 -*-
import argparse
import base64
import json
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
import ctypes
from io import BytesIO

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
SECONDARY = "#eaf1ff"
SECONDARY_HOVER = "#dbeafe"
SECONDARY_DOWN = "#bfdbfe"
SECONDARY_TEXT = "#12325f"
BORDER = "#d7e0ee"
SUCCESS = "#16a34a"
WARNING = "#f59e0b"
ERROR = "#dc2626"
TRANSPARENT = "#ff00ff"

EXIT_OK = 0
EXIT_RETRY = 10
EXIT_CANCEL = 20
APP_USER_MODEL_ID = "CMCC.AutoLogin"


class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("hwnd", ctypes.c_void_p),
        ("dwFlags", ctypes.c_uint),
        ("uCount", ctypes.c_uint),
        ("dwTimeout", ctypes.c_uint),
    ]


def create_round_photo(width, height, radius, fill, bg, outline=None):
    width = max(2, int(width))
    height = max(2, int(height))

    if Image is None or ImageDraw is None:
        img = tk.PhotoImage(width=width, height=height)
        img.put(fill, to=(0, 0, width, height))
        return img

    scale = 3
    sw, sh = width * scale, height * scale
    image = Image.new("RGB", (sw, sh), bg)
    draw = ImageDraw.Draw(image)
    inset = 1 * scale
    draw.rounded_rectangle(
        [inset, inset, sw - inset, sh - inset],
        radius=radius * scale,
        fill=fill,
        outline=outline or fill,
        width=scale if outline else 0,
    )
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return tk.PhotoImage(data=base64.b64encode(buffer.getvalue()).decode("ascii"))


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


class CapsuleButton(tk.Canvas):
    def __init__(self, master, text, command, width=128, height=42, variant="secondary"):
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
        )
        self._text = text
        self._command = command
        self._width = width
        self._height = height
        self._variant = variant
        self._hover = False
        self._pressed = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _colors(self):
        if self._variant == "primary":
            if self._pressed:
                return PRIMARY_DOWN, PRIMARY_DOWN, "#ffffff"
            if self._hover:
                return PRIMARY_HOVER, PRIMARY_HOVER, "#ffffff"
            return PRIMARY, PRIMARY, "#ffffff"
        if self._pressed:
            return SECONDARY_DOWN, "#9ab7e5", SECONDARY_TEXT
        if self._hover:
            return SECONDARY_HOVER, "#b7c9e8", SECONDARY_TEXT
        return SECONDARY, BORDER, SECONDARY_TEXT

    def _draw(self):
        self.delete("all")
        fill, outline, fg = self._colors()
        self._bg_image = create_round_photo(self._width, self._height, self._height // 2, fill, self.cget("bg"), outline)
        self.create_image(0, 0, image=self._bg_image, anchor=tk.NW)
        font_spec = ("Microsoft YaHei", 10, "bold" if self._variant == "primary" else "normal")
        self.create_text(
            self._width // 2,
            self._height // 2,
            text=self._text,
            fill=fg,
            font=font_spec,
            anchor=tk.CENTER,
        )

    def _on_enter(self, _event):
        self._hover = True
        self._draw()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event):
        self._pressed = True
        self._draw()

    def _on_release(self, event):
        inside = 0 <= event.x <= self._width and 0 <= event.y <= self._height
        self._pressed = False
        self._draw()
        if inside:
            self._command()


class StartupNotice:
    def __init__(self, title, message, kind, buttons, state_file="", response_file=""):
        self.exit_code = EXIT_CANCEL
        self.state_file = state_file
        self.response_file = response_file
        self._state_mtime = 0
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(title)
        self.root.overrideredirect(True)
        self.root.configure(bg=SURFACE)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.finish(EXIT_CANCEL))
        self.root.bind("<Escape>", lambda _event: self.finish(EXIT_CANCEL))
        self._apply_icon()

        self.width = 500
        self.message_top = 98
        self.message_width = self.width - 132
        self.button_bottom_padding = 28
        self.button_height = 42
        self.button_gap = 28
        self.message = message
        self.title = title
        self.kind = kind
        self.buttons = buttons
        self.button_frame = None
        self.button_window = None
        self.drag_x = 0
        self.drag_y = 0
        self.message_font = tkfont.Font(family="Microsoft YaHei", size=10)
        self.height = self._measure_height(message)
        self._build()
        self._center()
        self.root.update_idletasks()
        self._show_in_taskbar()
        self._apply_round_window()
        self.root.deiconify()
        self.root.update_idletasks()
        self._show_in_taskbar()
        self.root.lift()
        self.root.after(30, lambda: self.root.attributes("-topmost", True))
        self.root.after(60, self._show_in_taskbar)
        self.root.after(80, self._flash_taskbar)
        self.root.after(320, lambda: self.root.attributes("-topmost", False))
        if self.state_file:
            self.root.after(200, self._poll_state_file)

    def _kind_color(self):
        if self.kind == "success":
            return SUCCESS
        if self.kind == "error":
            return ERROR
        return WARNING

    def _measure_height(self, message):
        line_count = self._wrapped_line_count(message, self.message_width)
        line_height = max(20, self.message_font.metrics("linespace") + 4)
        needed = self.message_top + line_count * line_height + self.button_gap + self.button_height + self.button_bottom_padding
        max_height = max(330, min(560, self.root.winfo_screenheight() - 96))
        return max(246, min(max_height, needed))

    def _wrapped_line_count(self, message, width):
        if not message:
            return 1

        total = 0
        for paragraph in message.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not paragraph:
                total += 1
                continue

            lines = 1
            current = ""
            for char in paragraph:
                candidate = current + char
                if current and self.message_font.measure(candidate) > width:
                    lines += 1
                    current = char
                else:
                    current = candidate
            total += lines

        return max(1, total)

    def _build(self):
        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=SURFACE,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self._draw_window()

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)

        self._draw_buttons()

    def _draw_buttons(self):
        if self.button_window is not None:
            self.canvas.delete(self.button_window)
            self.button_window = None
        if self.button_frame is not None:
            try:
                self.button_frame.destroy()
            except Exception:
                pass
        if self.buttons == "none":
            return

        button_frame = tk.Frame(self.canvas, bg=SURFACE)
        button_defs = self._button_defs()
        total_width = sum(128 for _ in button_defs) + max(0, len(button_defs) - 1) * 10
        for label, code, variant in button_defs:
            CapsuleButton(button_frame, label, lambda c=code: self.finish(c), variant=variant).pack(side=tk.RIGHT, padx=(10, 0))
        button_center_y = self.height - self.button_bottom_padding - self.button_height / 2
        self.button_frame = button_frame
        self.button_window = self.canvas.create_window(self.width - 34 - total_width / 2, button_center_y, window=button_frame, anchor=tk.CENTER)

    def _draw_window(self):
        color = self._kind_color()
        self.canvas.delete("decor")
        self.canvas.create_rectangle(0, 0, self.width, self.height, fill=SURFACE, outline=SURFACE, tags="decor")

        self.canvas.create_oval(38, 44, 60, 66, fill=color, outline=color, tags="decor")
        mark = "!" if self.kind == "warning" else ("x" if self.kind == "error" else "✓")
        self.canvas.create_text(49, 55, text=mark, fill="#ffffff", font=("Microsoft YaHei", 10, "bold"), tags="decor")
        self.canvas.create_text(74, 54, text=self.title, fill=TEXT, font=("Microsoft YaHei", 16, "bold"), anchor=tk.W, tags="decor")

        self.canvas.create_text(
            74,
            self.message_top,
            text=self.message,
            fill="#334155",
            font=self.message_font,
            anchor=tk.NW,
            width=self.message_width,
            tags="decor",
        )

        self.canvas.create_oval(self.width - 58, 34, self.width - 34, 58, fill="#f1f5f9", outline="#e2e8f0", tags=("close", "decor"))
        self.canvas.create_text(self.width - 46, 46, text="×", fill=MUTED, font=("Microsoft YaHei", 13, "bold"), tags=("close", "decor"))
        self.canvas.tag_bind("close", "<ButtonRelease-1>", lambda _event: self.finish(EXIT_CANCEL))

    def _apply_state(self, state):
        self.title = state.get("title", self.title)
        self.message = state.get("message", self.message)
        self.kind = state.get("kind", self.kind)
        self.buttons = state.get("buttons", self.buttons)
        new_height = self._measure_height(self.message)
        if new_height != self.height:
            self.height = new_height
            self.canvas.configure(height=self.height)
            self.root.geometry(f"{self.width}x{self.height}+{self.root.winfo_x()}+{self.root.winfo_y()}")
        self._draw_window()
        self._draw_buttons()
        self._flash_taskbar()
        auto_close_ms = int(state.get("auto_close_ms") or 0)
        if auto_close_ms > 0:
            self.root.after(auto_close_ms, lambda: self.finish(EXIT_OK))

    def _poll_state_file(self):
        try:
            if os.path.exists(self.state_file):
                mtime = os.path.getmtime(self.state_file)
                if mtime != self._state_mtime:
                    self._state_mtime = mtime
                    with open(self.state_file, "r", encoding="utf-8-sig") as f:
                        self._apply_state(json.load(f))
        except Exception:
            pass
        self.root.after(200, self._poll_state_file)

    def _apply_round_window(self):
        if os.name != "nt":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            preference = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference))
        except Exception:
            pass

    def _show_in_taskbar(self):
        if os.name != "nt":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            gwl_exstyle = -20
            ws_ex_toolwindow = 0x00000080
            ws_ex_appwindow = 0x00040000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        except Exception:
            pass

    def _flash_taskbar(self):
        if os.name != "nt":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            flash_all = 0x00000003
            info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, flash_all, 5, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            pass

    def _button_defs(self):
        if self.buttons == "confirm-cancel":
            return [("取消", EXIT_CANCEL, "secondary"), ("确定", EXIT_OK, "primary")]
        if self.buttons == "retry-cancel":
            return [("取消", EXIT_CANCEL, "secondary"), ("重试", EXIT_RETRY, "primary")]
        if self.buttons == "yes-no":
            return [("保留自启", EXIT_CANCEL, "secondary"), ("关闭自启", EXIT_OK, "primary")]
        return [("确定", EXIT_OK, "primary")]

    def _center(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - self.width) // 2
        y = (self.root.winfo_screenheight() - self.height) // 2
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _start_drag(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def _drag(self, event):
        self.root.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def _apply_icon(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        exe_dir = os.path.dirname(sys.executable)
        frozen_dir = getattr(sys, "_MEIPASS", "")
        candidates = [
            os.path.join(exe_dir, "assets", "app_icon.ico"),
            os.path.join(frozen_dir, "assets", "app_icon.ico") if frozen_dir else "",
            os.path.join(base_dir, "assets", "app_icon.ico"),
            os.path.join(exe_dir, "_internal", "assets", "app_icon.ico"),
        ]
        for icon_path in candidates:
            if icon_path and os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(default=icon_path)
                    return
                except Exception:
                    pass

    def finish(self, code):
        self.exit_code = code
        if self.response_file:
            try:
                with open(self.response_file, "w", encoding="utf-8") as f:
                    json.dump({"exit_code": code}, f)
            except Exception:
                pass
        try:
            self.root.quit()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.exit_code


def parse_args():
    parser = argparse.ArgumentParser(description="CMCC startup notification window")
    parser.add_argument("--payload", default="")
    parser.add_argument("--title", default="校园网自动登录提示")
    parser.add_argument("--message", default="")
    parser.add_argument("--kind", choices=("success", "warning", "error"), default="warning")
    parser.add_argument("--buttons", choices=("ok", "retry-cancel", "yes-no", "confirm-cancel", "none"), default="ok")
    parser.add_argument("--state-file", default="")
    parser.add_argument("--response-file", default="")
    args = parser.parse_args()
    if args.payload:
        data = json.loads(base64.b64decode(args.payload).decode("utf-8"))
        args.title = data.get("title", args.title)
        args.message = data.get("message", args.message)
        args.kind = data.get("kind", args.kind)
        args.buttons = data.get("buttons", args.buttons)
        args.state_file = data.get("state_file", args.state_file)
        args.response_file = data.get("response_file", args.response_file)
    return args


def main():
    set_app_user_model_id()
    set_dpi_awareness()
    args = parse_args()
    notice = StartupNotice(args.title, args.message, args.kind, args.buttons, args.state_file, args.response_file)
    return notice.run()


if __name__ == "__main__":
    sys.exit(main())
