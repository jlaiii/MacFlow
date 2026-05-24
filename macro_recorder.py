#!/usr/bin/env python3
"""
Macro Recorder — Record mouse & keyboard actions and replay them infinitely.
Auto-installs dependencies.  Hotkeys: F8=Rec  F9=Stop  F10=Play  F11=StopPlay
"""

from __future__ import annotations

import ctypes
import importlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

# ── hide console window on Windows ────────────────────────────────────────────
if sys.platform == "win32":
    ctypes.windll.user32.ShowWindow(
        ctypes.windll.kernel32.GetConsoleWindow(), 0
    )
    # shrink timer granularity from 15 ms → 1 ms so moveTo / sleep are precise
    ctypes.windll.winmm.timeBeginPeriod(1)

# ──────────────────────────────────────────────────────────────────────────────
#  Auto‑install missing packages (silent – no prompts)
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_PKGS = {
    "pynput":       "pynput",
    "pyautogui":    "pyautogui",
    "customtkinter":"customtkinter",
}


def _pip_install(pip_name: str) -> bool:
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _ensure_pkgs() -> None:
    missing = []
    for mod, pip_name in REQUIRED_PKGS.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append((mod, pip_name))
    if not missing:
        return
    print(f"Installing: {', '.join(p for _, p in missing)} ...")
    for _, pip_name in missing:
        ok = _pip_install(pip_name)
        print(f"  {'✓' if ok else '✗'} {pip_name}")


_ensure_pkgs()

# ──────────────────────────────────────────────────────────────────────────────
#  Library imports  (after auto‑install)
# ──────────────────────────────────────────────────────────────────────────────

PYNPUT_OK = False
PYAUTOGUI_OK = False

try:
    from pynput import keyboard, mouse
    from pynput.keyboard import Key
    PYNPUT_OK = True
except ImportError:
    Key = None          # type: ignore[assignment]

try:
    import pyautogui as pag
    pag.FAILSAFE = True
    pag.PAUSE = 0
    PYAUTOGUI_OK = True
except ImportError:
    pass

# direct OS cursor control — bypasses pyautogui's animation entirely
if sys.platform == "win32":
    _set_cursor = ctypes.windll.user32.SetCursorPos
else:
    def _set_cursor(x: int, y: int) -> None:
        pag.moveTo(x, y, duration=0, _pause=False)

import customtkinter as ctk


# ═══════════════════════════════════════════════════════════════════════════════
#  Data model
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Action:
    action_type: str
    delay: float = 0.0
    x: int | None = None
    y: int | None = None
    button: str | None = None
    pressed: bool | None = None
    key: str | None = None
    dx: int | None = None
    dy: int | None = None
    duration: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"action_type": self.action_type, "delay": self.delay}
        for fld in ("x", "y", "button", "pressed", "key", "dx", "dy", "duration"):
            v = getattr(self, fld)
            if v is not None:
                d[fld] = v
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Action:
        return cls(**d)

    def summary(self) -> str:
        t = self.action_type
        if t == "mouse_click":
            s = "DOWN" if self.pressed else "UP"
            return f"{self.button} {s} @ ({self.x}, {self.y})"
        if t == "mouse_move":
            return f"Move → ({self.x}, {self.y})"
        if t in ("key_press", "key_release"):
            s = "DOWN" if self.pressed else "UP"
            return f"'{self.key}' {s}"
        if t == "scroll":
            return f"Scroll ({self.dx:+d}, {self.dy:+d}) @ ({self.x}, {self.y})"
        if t == "wait":
            return f"WAIT {self.duration:.2f}s"
        return t


# ═══════════════════════════════════════════════════════════════════════════════
#  Recording engine
# ═══════════════════════════════════════════════════════════════════════════════

class Recorder:
    MOVE_THROTTLE = 0.020   # 50 fps capture
    MOVE_MIN_DIST = 1

    def __init__(self, on_add: Callable[[Action], None]):
        self.on_add = on_add
        self.actions: list[Action] = []
        self.active = False
        self._last = 0.0
        self._lock = threading.Lock()
        self._kbd: Any = None
        self._mse: Any = None
        self._stop_keys: set = {Key.esc, Key.f9} if PYNPUT_OK and Key else set()
        self._mv_time = 0.0
        self._mv_x = 0
        self._mv_y = 0

    def start(self):
        if not PYNPUT_OK:
            raise RuntimeError("pynput not installed")
        self.actions.clear()
        self.active = True
        self._last = time.perf_counter()
        self._mv_time = 0.0
        self._mse = mouse.Listener(
            on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll,
        )
        self._kbd = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mse.start()
        self._kbd.start()

    def stop(self) -> list[Action]:
        self.active = False
        if self._mse:
            self._mse.stop()
        if self._kbd:
            self._kbd.stop()
        return self.actions.copy()

    def _push(self, a: Action):
        if not self.active:
            return
        a.delay = time.perf_counter() - self._last
        self._last = time.perf_counter()
        with self._lock:
            self.actions.append(a)
        self.on_add(a)

    def _key_name(self, k: Any) -> str:
        try:
            return k.char
        except AttributeError:
            return str(k).removeprefix("Key.")

    def _on_click(self, x: int, y: int, btn: Any, pressed: bool):
        if not self.active:
            return
        self._push(Action(
            action_type="mouse_click", x=x, y=y,
            button=str(btn).removeprefix("Button."), pressed=pressed,
        ))

    def _on_scroll(self, x: int, y: int, dx: int, dy: int):
        if not self.active:
            return
        self._push(Action(action_type="scroll", x=x, y=y, dx=dx, dy=dy))

    def _on_move(self, x: int, y: int):
        if not self.active:
            return
        now = time.perf_counter()
        if now - self._mv_time < self.MOVE_THROTTLE:
            return
        if abs(x - self._mv_x) < self.MOVE_MIN_DIST and abs(y - self._mv_y) < self.MOVE_MIN_DIST:
            return
        self._mv_time = now
        self._mv_x = x
        self._mv_y = y
        self._push(Action(action_type="mouse_move", x=x, y=y))

    def _on_press(self, k: Any):
        if not self.active or k in self._stop_keys:
            return
        self._push(Action(action_type="key_press", key=self._key_name(k), pressed=True))

    def _on_release(self, k: Any):
        if not self.active or k in self._stop_keys:
            return
        self._push(Action(action_type="key_release", key=self._key_name(k), pressed=False))


# ═══════════════════════════════════════════════════════════════════════════════
#  Playback engine
# ═══════════════════════════════════════════════════════════════════════════════

_KEY_MAP: dict[str, str] = {
    "enter": "enter", "tab": "tab", "space": "space",
    "backspace": "backspace", "delete": "delete",
    "esc": "esc", "escape": "esc",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end", "page_up": "pageup", "page_down": "pagedown",
    "shift": "shift", "shift_r": "shift", "shift_l": "shift",
    "ctrl": "ctrl", "ctrl_r": "ctrl", "ctrl_l": "ctrl",
    "alt": "alt", "alt_r": "alt", "alt_l": "alt",
    "cmd": "win", "cmd_r": "win", "cmd_l": "win",
    "caps_lock": "capslock", "num_lock": "numlock",
    "print_screen": "printscreen", "scroll_lock": "scrolllock",
    "insert": "insert", "pause": "pause",
}
for _i in range(1, 25):
    _KEY_MAP[f"f{_i}"] = f"f{_i}"


def _pag_key(name: str) -> str:
    low = name.lower()
    return _KEY_MAP.get(low, name if len(name) == 1 else low)


class Player:
    def __init__(self):
        self.running = False
        self._thread: threading.Thread | None = None
        self._mse: Any = None
        self._kbd: Any = None
        self._last_auto = 0.0      # timestamp of last pyautogui action

    def play(self, actions: list[Action], speed: float, loops: int,
             on_done: Callable | None = None,
             on_step: Callable[[int], None] | None = None):
        if not PYAUTOGUI_OK:
            raise RuntimeError("pyautogui not installed")
        if self.running:
            return
        self.running = True
        self._start_input_watch()
        self._thread = threading.Thread(
            target=self._run, args=(actions, speed, loops, on_done, on_step), daemon=True
        )
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop_input_watch()

    # ── input monitor: any manual mouse-move / key stops playback ─────────

    def _start_input_watch(self):
        if not PYNPUT_OK:
            return
        try:
            self._mse = mouse.Listener(on_move=self._on_user_move)
            self._kbd = keyboard.Listener(on_press=self._on_user_key)
            self._mse.start()
            self._kbd.start()
        except Exception:
            self._mse = self._kbd = None

    def _stop_input_watch(self):
        for lst in (self._mse, self._kbd):
            if lst:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._mse = self._kbd = None

    def _on_user_move(self, x, y):
        if time.perf_counter() - self._last_auto > 0.08:
            self.running = False

    def _on_user_key(self, k):
        if time.perf_counter() - self._last_auto > 0.08:
            self.running = False

    def _mark_auto(self):
        self._last_auto = time.perf_counter()

    # ── playback loop ─────────────────────────────────────────────────────

    def _run(self, actions, speed, loops, on_done, on_step):
        try:
            for _ in range(loops):
                if not self.running:
                    return
                i = 0
                n = len(actions)
                while i < n and self.running:
                    # ── collect consecutive mouse_move actions ──────────────
                    batch_start = i
                    while i < n and actions[i].action_type == "mouse_move":
                        i += 1

                    if i > batch_start:
                        batch = actions[batch_start:i]
                        pts = [(a.x, a.y) for a in batch if a.x is not None and a.y is not None]
                        delays = [a.delay / (speed or 1) for a in batch]
                        total_d = sum(delays)

                        if pts:
                            self._smooth_path(pts, delays, total_d)

                        if on_step:
                            for j in range(batch_start, i):
                                on_step(j)
                        continue

                    # ── non-move action ─────────────────────────────────────
                    a = actions[i]
                    if on_step:
                        on_step(i)
                    d = a.delay / speed if speed > 0 else 0
                    if d > 0:
                        time.sleep(d)
                    self._mark_auto()
                    self._exec(a)
                    i += 1
            if on_done:
                on_done()
        except Exception as exc:
            print(f"[Player] {exc}")
        finally:
            self.running = False
            self._stop_input_watch()

    def _smooth_path(self, pts, delays, total_d):
        """Interpolate through waypoints at ~150 fps using direct OS calls."""
        n = len(pts)
        if n == 0:
            return
        if n == 1 or total_d < 0.003:
            self._mark_auto()
            _set_cursor(pts[-1][0], pts[-1][1])
            return

        # build cumulative time fractions per waypoint
        cum = [0.0]
        for d in delays:
            cum.append(cum[-1] + (d / total_d if total_d > 0 else 0))

        fps = 150
        frames = max(int(total_d * fps), n * 2)
        dt = total_d / frames

        seg = 0
        for f in range(1, frames + 1):
            if not self.running:
                return
            t = f / frames
            # advance segment
            while seg < n - 1 and cum[seg + 1] < t:
                seg += 1
            if seg >= n - 1:
                x, y = pts[-1]
            else:
                local = (t - cum[seg]) / (cum[seg + 1] - cum[seg]) if cum[seg + 1] > cum[seg] else 1.0
                if local > 1:
                    local = 1
                elif local < 0:
                    local = 0
                x1, y1 = pts[seg]
                x2, y2 = pts[seg + 1]
                x = int(x1 + (x2 - x1) * local)
                y = int(y1 + (y2 - y1) * local)
            self._mark_auto()
            _set_cursor(x, y)
            if f < frames:
                target = time.perf_counter() + dt
                pre = dt - 0.003
                if pre > 0.001:
                    time.sleep(pre)
                while time.perf_counter() < target:
                    time.sleep(0)

    def _exec(self, a: Action):
        t = a.action_type
        if t == "mouse_click":
            if a.x is not None and a.y is not None:
                _set_cursor(a.x, a.y)
                btn = a.button or "left"
                if a.pressed:
                    pag.mouseDown(button=btn, _pause=False)
                else:
                    pag.mouseUp(button=btn, _pause=False)
        elif t == "mouse_move":
            if a.x is not None and a.y is not None:
                _set_cursor(a.x, a.y)
        elif t == "key_press":
            if a.key:
                pag.keyDown(_pag_key(a.key), _pause=False)
        elif t == "key_release":
            if a.key:
                pag.keyUp(_pag_key(a.key), _pause=False)
        elif t == "scroll":
            if a.dy:
                pag.scroll(int(a.dy), x=a.x, y=a.y, _pause=False)
        elif t == "wait" and a.duration:
            time.sleep(a.duration)


# ═══════════════════════════════════════════════════════════════════════════════
#  GUI  (customtkinter — matching Human Typer theme)
# ═══════════════════════════════════════════════════════════════════════════════

FONT       = ("Segoe UI", 13)
FONT_SM    = ("Segoe UI", 11)
FONT_MONO  = ("Consolas", 11)
APPEARANCE = "dark"


class App:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Macro Recorder")
        self.root.geometry("840x620")
        self.root.minsize(600, 420)
        ctk.set_appearance_mode(APPEARANCE)

        self.actions: list[Action] = []
        self.recorder = Recorder(on_add=lambda _: self._defer(self._refresh))
        self.player = Player()
        self._file: str | None = None

        self.var_speed = ctk.StringVar(value="1.0")
        self.var_repeat = ctk.StringVar(value="1")
        self.var_status = ctk.StringVar(value="Ready — Record a macro or load one.")
        self.var_delay_on = ctk.BooleanVar(value=False)
        self.var_delay_sec = ctk.StringVar(value="5")
        self.var_kb_rec  = ctk.StringVar(value="f8")
        self.var_kb_stop = ctk.StringVar(value="f9")
        self.var_kb_play = ctk.StringVar(value="f10")
        self.var_kb_pstop= ctk.StringVar(value="f11")
        self.var_profile = ctk.StringVar(value="")
        self._infinite = False
        self._delaying = False
        self._profiles: dict[str, list[dict]] = {}
        self._profiles_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macflow_profiles.json")
        self._load_profiles()

        self._build_ui()
        self._global_hotkeys()

        if not PYNPUT_OK or not PYAUTOGUI_OK:
            missing = [n for ok, n in ((PYNPUT_OK, "pynput"), (PYAUTOGUI_OK, "pyautogui")) if not ok]
            self._defer(lambda: self._warn(
                f"Limited: {', '.join(missing)} missing.\nRe-run or: pip install {' '.join(missing)}"
            ))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _defer(self, fn, *args):
        self.root.after(0, fn, *args)

    def _warn(self, msg: str):
        self.var_status.set(msg)

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ═══ row 0 — main action buttons ═══
        btn_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=(14, 6))

        self.btn_rec = ctk.CTkButton(
            btn_bar, text="⏺  Record", command=self._rec_start,
            font=FONT, corner_radius=8, width=110, height=36,
            fg_color="#c42b1c", hover_color="#a02020",
        )
        self.btn_rec.pack(side="left", padx=2)

        self.btn_stop = ctk.CTkButton(
            btn_bar, text="⏹  Stop Rec", command=self._rec_stop,
            font=FONT, corner_radius=8, width=110, height=36,
            fg_color="#555555", hover_color="#444444", state="disabled",
        )
        self.btn_stop.pack(side="left", padx=2)

        self.btn_play = ctk.CTkButton(
            btn_bar, text="▶  Play", command=self._play_start,
            font=FONT, corner_radius=8, width=100, height=36,
            fg_color="#1a7a1a", hover_color="#145214",
        )
        self.btn_play.pack(side="left", padx=2)

        self.btn_play_stop = ctk.CTkButton(
            btn_bar, text="⏹  Stop Play", command=self._play_stop,
            font=FONT, corner_radius=8, width=110, height=36,
            fg_color="#555555", hover_color="#444444", state="disabled",
        )
        self.btn_play_stop.pack(side="left", padx=2)

        # ═══ row 0b — profile manager ═══
        profile_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        profile_bar.pack(fill="x", padx=14, pady=(0, 4))

        ctk.CTkLabel(profile_bar, text="Profile:", font=FONT_SM).pack(side="left", padx=(0, 4))
        self.profile_combo = ctk.CTkOptionMenu(
            profile_bar, values=[""], variable=self.var_profile,
            font=FONT_SM, width=160, corner_radius=6,
            command=lambda _: self._switch_profile(),
        )
        self.profile_combo.pack(side="left", padx=(0, 4))
        self.profile_entry = ctk.CTkEntry(
            profile_bar, textvariable=self.var_profile, font=FONT_SM,
            width=160, height=28, corner_radius=6,
        )
        self.profile_entry.pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            profile_bar, text="💾 Save Profile", command=self._save_profile,
            font=FONT_SM, corner_radius=6, width=110, height=28,
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            profile_bar, text="🗑 Delete", command=self._delete_profile,
            font=FONT_SM, corner_radius=6, width=70, height=28,
            fg_color="#c42b1c", hover_color="#a02020",
        ).pack(side="left", padx=2)
        self._refresh_profile_list()

        # ═══ row 1 — file & edit buttons ═══
        edit_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        edit_bar.pack(fill="x", padx=14, pady=(0, 6))

        for text, cmd, w in [
            ("💾  Save",      self._save,      90),
            ("📂  Load",      self._load,      90),
            ("🗑  Clear",     self._clear,     90),
            ("✕  Delete",    self._delete,    90),
            ("⏱  Add Wait",  self._add_wait,  100),
        ]:
            ctk.CTkButton(
                edit_bar, text=text, command=cmd,
                font=FONT_SM, corner_radius=8, width=w, height=32,
            ).pack(side="left", padx=2)

        # ═══ row 2 — action list ═══
        list_frame = ctk.CTkFrame(self.root, corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        list_label = ctk.CTkLabel(list_frame, text="Recorded Actions", font=FONT)
        list_label.pack(anchor="w", padx=12, pady=(10, 4))

        # Treeview with dark‑theme colours to match CTk
        import tkinter.ttk as ttk
        from tkinter import VERTICAL

        tree_bg  = "#2b2b2b"
        tree_fg  = "#dce4ee"
        tree_sel = "#1f538d"

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=tree_bg, foreground=tree_fg,
                        fieldbackground=tree_bg, font=FONT_MONO, rowheight=28)
        style.configure("Treeview.Heading",
                        background="#3b3b3b", foreground=tree_fg,
                        font=("Segoe UI", 11, "bold"), borderwidth=0)
        style.map("Treeview",
                  background=[("selected", tree_sel)],
                  foreground=[("selected", "white")])
        style.configure("Vertical.TScrollbar",
                        background="#3b3b3b", troughcolor=tree_bg,
                        arrowcolor=tree_fg, borderwidth=0)

        tree_container = ctk.CTkFrame(list_frame, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        cols = ("#", "Delay", "Type", "Details")
        self.tree = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("#", text="#");         self.tree.column("#", width=40, anchor="center")
        self.tree.heading("Delay", text="Delay"); self.tree.column("Delay", width=70, anchor="center")
        self.tree.heading("Type", text="Type");   self.tree.column("Type", width=110)
        self.tree.heading("Details", text="Details"); self.tree.column("Details", width=560)

        sb = ttk.Scrollbar(tree_container, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._edit_delay)

        # ═══ row 3 — bottom controls ═══
        bot_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        bot_bar.pack(fill="x", padx=14, pady=(0, 4))

        # speed
        spd_frame = ctk.CTkFrame(bot_bar, fg_color="transparent")
        spd_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(spd_frame, text="Speed:", font=FONT_SM).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            spd_frame, values=["0.25", "0.5", "0.75", "1.0", "1.5", "2.0", "3.0", "5.0", "10.0"],
            variable=self.var_speed, font=FONT_SM, width=70, corner_radius=6,
        ).pack(side="left")
        ctk.CTkLabel(spd_frame, text="×", font=FONT_SM).pack(side="left", padx=(2, 0))

        # repeat
        rep_frame = ctk.CTkFrame(bot_bar, fg_color="transparent")
        rep_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(rep_frame, text="Repeat:", font=FONT_SM).pack(side="left", padx=(0, 4))
        self.rep_entry = ctk.CTkEntry(
            rep_frame, textvariable=self.var_repeat, font=FONT_SM,
            width=55, height=28, corner_radius=6, justify="center",
        )
        self.rep_entry.pack(side="left", padx=(0, 4))
        self.btn_inf = ctk.CTkButton(
            rep_frame, text="∞", command=self._toggle_infinite,
            font=FONT_SM, width=32, height=28, corner_radius=6,
        )
        self.btn_inf.pack(side="left")

        # start delay
        dly_frame = ctk.CTkFrame(bot_bar, fg_color="transparent")
        dly_frame.pack(side="left", padx=(0, 10))
        self.dly_toggle = ctk.CTkCheckBox(
            dly_frame, text="Rec delay", variable=self.var_delay_on,
            font=FONT_SM, corner_radius=4,
        )
        self.dly_toggle.pack(side="left", padx=(0, 4))
        self.dly_entry = ctk.CTkEntry(
            dly_frame, textvariable=self.var_delay_sec, font=FONT_SM,
            width=40, height=28, corner_radius=6, justify="center",
        )
        self.dly_entry.pack(side="left")
        ctk.CTkLabel(dly_frame, text="s", font=FONT_SM).pack(side="left", padx=(2, 0))

        # keybinds
        kb_frame = ctk.CTkFrame(bot_bar, fg_color="transparent")
        kb_frame.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(kb_frame, text="Keys:", font=FONT_SM, text_color="gray").pack(side="left", padx=(0, 4))
        for var, lbl in [(self.var_kb_rec, "Rec"), (self.var_kb_stop, "Stop"),
                          (self.var_kb_play, "Play"), (self.var_kb_pstop, "PStop")]:
            ctk.CTkLabel(kb_frame, text=lbl, font=("Segoe UI", 9), text_color="gray").pack(side="left", padx=(4, 1))
            ctk.CTkOptionMenu(
                kb_frame, values=["f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
                                  "esc","tab","`","1","2","3","4","5","6","7","8","9","0"],
                variable=var, font=("Segoe UI", 9), width=50, corner_radius=4,
                command=lambda _: self._rebind_hotkeys(),
            ).pack(side="left", padx=(0, 6))

        # stats
        self.lbl_stats = ctk.CTkLabel(bot_bar, text="Actions: 0  |  Duration: 0.00 s",
                                       font=FONT_SM, text_color="gray")
        self.lbl_stats.pack(side="left", padx=20)

        # ═══ row 4 — status ═══
        status_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        status_frame.pack(fill="x", padx=14, pady=(2, 10))

        ctk.CTkLabel(status_frame, textvariable=self.var_status,
                     font=FONT_SM, text_color="gray").pack(side="left")

        # ESC closes app
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    # ── global hotkeys ────────────────────────────────────────────────────────

    def _global_hotkeys(self):
        if not PYNPUT_OK:
            return
        self._hk = None
        self._rebind_hotkeys()

    def _rebind_hotkeys(self, *_):
        if not PYNPUT_OK:
            return
        if self._hk:
            self._hk.stop()
        try:
            self._hk = keyboard.GlobalHotKeys({
                f"<{self.var_kb_rec.get()}>":   lambda: self._defer(self._rec_start),
                f"<{self.var_kb_stop.get()}>":  lambda: self._defer(self._rec_stop),
                f"<{self.var_kb_play.get()}>":  lambda: self._defer(self._play_start),
                f"<{self.var_kb_pstop.get()}>": lambda: self._defer(self._play_stop),
            })
            self._hk.start()
        except Exception:
            pass

    # ── tree refresh ──────────────────────────────────────────────────────────

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, a in enumerate(self.actions, 1):
            self.tree.insert("", "end", values=(i, f"{a.delay:.3f}", a.action_type, a.summary()))
        if self.actions:
            self.tree.see(self.tree.get_children()[-1])
        dur = sum(a.delay for a in self.actions)
        self.lbl_stats.configure(text=f"Actions: {len(self.actions)}  |  Duration: {dur:.2f} s")
        if not self.recorder.active and not self.player.running:
            self.btn_play.configure(state="normal" if self.actions else "disabled")

    # ── recording ─────────────────────────────────────────────────────────────

    def _rec_start(self):
        if self.recorder.active or self.player.running:
            return
        if self.var_delay_on.get():
            try:
                dly = float(self.var_delay_sec.get())
            except ValueError:
                dly = 5
            if dly > 0:
                self._delaying = True
                self._ui_recording(True)
                self._rec_countdown(int(dly))
                return
        self._launch_recording()

    def _rec_countdown(self, remaining: int):
        if not self._delaying:
            return
        if remaining <= 0:
            self._delaying = False
            self._launch_recording()
            return
        self.var_status.set(f"Recording starts in {remaining}s...")
        self.root.after(1000, self._rec_countdown, remaining - 1)

    def _launch_recording(self):
        try:
            self.recorder.start()
        except RuntimeError as e:
            self.var_status.set(str(e))
            self._ui_recording(False)
            return
        self._ui_recording(True)
        self.var_status.set("●  RECORDING — do your actions, then Esc / F9 / Stop Rec")

    def _rec_stop(self):
        self._delaying = False
        if not self.recorder.active:
            return
        self.actions = self.recorder.stop()
        self._ui_recording(False)
        self._refresh()
        self.var_status.set(f"Stopped — {len(self.actions)} actions captured")

    # ── playback ──────────────────────────────────────────────────────────────

    def _play_start(self):
        if self.player.running or self.recorder.active:
            return
        if not self.actions:
            self.var_status.set("Nothing to play — record or load a macro first.")
            return
        try:
            loops = int(self.var_repeat.get())
        except ValueError:
            loops = 1
        try:
            speed = float(self.var_speed.get())
        except ValueError:
            speed = 1.0
        try:
            self.player.play(
                self.actions, speed, loops,
                on_done=lambda: self._defer(self._play_stop),
                on_step=lambda i: self._defer(self._highlight, i),
            )
        except RuntimeError as e:
            self.var_status.set(str(e))
            return
        self._ui_playing(True)
        self.var_status.set(f"▶  PLAYING — {loops}× at {speed}× speed  (F11 to stop)")

    def _play_stop(self):
        self._delaying = False
        self.player.stop()
        self._ui_playing(False)
        self.var_status.set("Playback stopped")

    def _play_done(self):
        self._ui_playing(False)
        self.var_status.set("✓  Playback complete")

    def _highlight(self, idx: int):
        kids = self.tree.get_children()
        if idx < len(kids):
            self.tree.selection_set(kids[idx])
            self.tree.see(kids[idx])

    # ── UI state helpers ──────────────────────────────────────────────────────

    def _ui_recording(self, on: bool):
        self.btn_rec.configure(state="disabled" if on else "normal")
        self.btn_stop.configure(state="normal" if on else "disabled")
        self.btn_play.configure(state="disabled" if on else ("normal" if self.actions else "disabled"))
        self.btn_play_stop.configure(state="disabled")

    def _ui_playing(self, on: bool):
        self.btn_play.configure(state="disabled" if on else ("normal" if self.actions else "disabled"))
        self.btn_play_stop.configure(state="normal" if on else "disabled")
        self.btn_rec.configure(state="disabled" if on else "normal")
        self.btn_stop.configure(state="disabled")

    # ── file I/O ──────────────────────────────────────────────────────────────

    def _save(self):
        if not self.actions:
            return
        path = ctk.filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Macro", "*.json"), ("All files", "*.*")],
            initialfile="macro.json",
        )
        if not path:
            return
        data = {
            "version": 1,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "actions": [a.to_dict() for a in self.actions],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self._file = os.path.basename(path)
        self.var_status.set(f"Saved → {self._file}")
        self.root.title(f"Macro Recorder — {self._file}")

    def _load(self):
        path = ctk.filedialog.askopenfilename(filetypes=[("Macro", "*.json"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "r") as f:
            data = json.load(f)
        self.actions = [Action.from_dict(a) for a in data.get("actions", [])]
        self._file = os.path.basename(path)
        self._refresh()
        self.var_status.set(f"Loaded ← {self._file}  ({len(self.actions)} actions)")
        self.root.title(f"Macro Recorder — {self._file}")

    # ── profile manager ────────────────────────────────────────────────────────

    def _load_profiles(self):
        try:
            with open(self._profiles_file, "r") as f:
                self._profiles = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._profiles = {}

    def _save_profiles_to_disk(self):
        with open(self._profiles_file, "w") as f:
            json.dump(self._profiles, f, indent=2)

    def _refresh_profile_list(self):
        names = list(self._profiles.keys())
        self.profile_combo.configure(values=[""] + names)

    def _save_profile(self):
        name = self.var_profile.get().strip()
        if not name:
            self.var_status.set("Enter a profile name first")
            return
        if not self.actions:
            self.var_status.set("No actions to save — record something first")
            return
        self._profiles[name] = [a.to_dict() for a in self.actions]
        self._save_profiles_to_disk()
        self._refresh_profile_list()
        self.var_status.set(f"Profile '{name}' saved ({len(self.actions)} actions)")

    def _switch_profile(self):
        name = self.var_profile.get().strip()
        if not name or name not in self._profiles:
            return
        self.actions = [Action.from_dict(a) for a in self._profiles[name]]
        self._refresh()
        self.var_profile.set(name)
        self.var_status.set(f"Loaded profile '{name}' ({len(self.actions)} actions)")

    def _delete_profile(self):
        name = self.var_profile.get().strip()
        if not name or name not in self._profiles:
            return
        del self._profiles[name]
        self._save_profiles_to_disk()
        self._refresh_profile_list()
        self.var_profile.set("")
        self.var_status.set(f"Deleted profile '{name}'")

    # ── editing ───────────────────────────────────────────────────────────────

    def _clear(self):
        if self.recorder.active or self.player.running:
            return
        if not self.actions:
            return
        self.actions.clear()
        self._refresh()
        self.var_status.set("Cleared")

    def _delete(self):
        if self.recorder.active or self.player.running:
            return
        sel = self.tree.selection()
        if not sel:
            return
        indices = sorted((int(self.tree.item(i, "values")[0]) - 1 for i in sel), reverse=True)
        for i in indices:
            del self.actions[i]
        self._refresh()
        self.var_status.set(f"Deleted {len(indices)} action(s)")

    def _add_wait(self):
        if self.recorder.active or self.player.running:
            return
        dlg = ctk.CTkInputDialog(text="Wait duration in seconds:", title="Add Wait")
        ans = dlg.get_input()
        if ans:
            try:
                v = float(ans)
                if 0.1 <= v <= 300:
                    self.actions.append(Action(action_type="wait", duration=v))
                    self._refresh()
            except ValueError:
                pass

    def _edit_delay(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(self.tree.item(sel[0], "values")[0]) - 1
        cur = self.actions[i].delay
        dlg = ctk.CTkInputDialog(text=f"New delay in seconds (current: {cur:.3f}):", title="Edit Delay")
        ans = dlg.get_input()
        if ans:
            try:
                v = float(ans)
                if 0 <= v <= 300:
                    self.actions[i].delay = v
                    self._refresh()
            except ValueError:
                pass

    def _toggle_infinite(self):
        if self._infinite:
            self._infinite = False
            self.var_repeat.set("1")
            self.btn_inf.configure(text="∞", fg_color="#1f538d")
        else:
            self._infinite = True
            self.var_repeat.set("999999999")
            self.btn_inf.configure(text="1", fg_color="#c42b1c")

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    App().run()
