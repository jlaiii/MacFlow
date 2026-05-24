# MacFlow 🎬

> Record mouse & keyboard actions. Replay them infinitely.  
> A tape recorder for your computer.

Macro Recorder captures mouse events and keystrokes — just like a tape recorder. Press **Record**, perform your actions, press **Stop**, then press **Play** to repeat them as many times as you want.

Built with a modern dark GUI (customtkinter). Auto-installs its own dependencies. Windows-first, with smooth 150 fps cursor replay.

<p align="center">
  <a href="https://jlaiii.github.io/MacFlow/"><strong>🌐 Website</strong></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="#-quick-start"><strong>⚡ Quick Start</strong></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="#-features"><strong>✨ Features</strong></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="#-hotkeys"><strong>⌨ Hotkeys</strong></a>
</p>

---

## ⚡ Quick Start

```bash
# 1. Clone
git clone https://github.com/jlaiii/MacFlow.git
cd MacFlow

# 2. Run (auto-installs everything it needs)
python macro_recorder.py
```

That's it. No `pip install` needed — missing packages are detected and installed silently on first launch.

---

## ✨ Features

| Feature | Detail |
|---|---|
| **Record** | Captures mouse clicks, movement, scroll, and all keystrokes |
| **Smooth replay** | 150 fps path interpolation — cursor glides, doesn't teleport |
| **Auto-stop** | Move the mouse or press any key during playback to halt instantly |
| **Edit macros** | Double-click any action to tweak its delay, delete unwanted steps, insert manual waits |
| **Save / Load** | JSON files — share macros, version-control them |
| **Speed control** | 0.25× to 10× playback speed |
| **Loop / infinite** | Repeat N times or near-forever (9999×) |
| **Record delay** | Optional countdown before recording starts — switch to your target window |
| **Configurable global hotkeys** | Rebind F8–F12 to any F-key, Esc, Tab, or number |
| **Dark theme** | Clean customtkinter UI matching macOS/Windows 11 aesthetics |
| **Auto-dependency** | Silently installs `pynput`, `pyautogui`, `customtkinter` if missing |

---

## ⌨ Hotkeys (customizable)

| Key (default) | Action |
|---|---|
| **F8** | Start recording |
| **F9** or **Esc** | Stop recording |
| **F10** | Play macro |
| **F11** | Stop playback |

All bindings can be changed from the bottom bar dropdowns.

---

## 🖼 Screenshots

<p align="center">
  <em>Dark-mode GUI with action list, speed/repeat controls, and configurable keybinds</em>
</p>

---

## 🧱 Tech Stack

- **Python 3.10+**
- [`customtkinter`](https://github.com/TomSchimansky/CustomTkinter) — modern TK GUI
- [`pynput`](https://github.com/moses-palmer/pynput) — global input capture
- [`pyautogui`](https://github.com/asweigart/pyautogui) — keyboard/mouse simulation
- Direct `SetCursorPos` for sub-millisecond cursor positioning

---

## 📄 License

MIT — do whatever you want. PRs welcome.
