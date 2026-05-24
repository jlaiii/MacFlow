# MacFlow

> Record mouse and keyboard actions. Replay them infinitely.
> A tape recorder for your computer.

MacFlow captures mouse events and keystrokes with microsecond precision. Press Record, perform your actions, press Stop, then press Play to repeat them as many times as needed. Edit delays, delete steps, insert pauses — full control over every recorded action.

Built with a modern dark GUI using customtkinter. Dependencies auto-install on first launch. Windows-first, with 150 fps cursor replay via direct OS calls.

<p align="center">
  <a href="https://jlaiii.github.io/MacFlow/"><strong>Website</strong></a>
  &nbsp;|&nbsp;
  <a href="#quick-start"><strong>Quick Start</strong></a>
  &nbsp;|&nbsp;
  <a href="#features"><strong>Features</strong></a>
  &nbsp;|&nbsp;
  <a href="#hotkeys"><strong>Hotkeys</strong></a>
</p>

---

## Quick Start

```bash
git clone https://github.com/jlaiii/MacFlow.git
cd MacFlow
python macro_recorder.py
```

No manual `pip install` required — missing packages are detected and installed silently on first launch.

---

## Features

| Feature | Detail |
|---|---|
| **Record** | Captures mouse clicks, cursor movement, scroll wheel, and all keystrokes |
| **Smooth replay** | 150 fps path interpolation via direct OS cursor calls — the cursor glides, no teleporting |
| **Auto-stop** | Move the mouse or press any key during playback to halt instantly |
| **Profile manager** | Name, save, and switch between recorded macros without leaving the app |
| **Edit macros** | Double-click any action to tweak its delay, delete unwanted steps, insert manual waits |
| **Save / Load** | JSON files — share macros, version-control them, build a personal library |
| **Speed control** | 0.25x to 10x playback speed |
| **Loop / infinite** | Repeat N times or near-forever |
| **Record delay** | Optional countdown before recording starts — switch to your target window first |
| **Configurable hotkeys** | Rebind Record, Stop, Play, and Stop Play to any F-key, Esc, Tab, or number |
| **Dark theme** | Clean customtkinter UI with modern aesthetics |
| **Auto-dependency** | Silently installs `pynput`, `pyautogui`, `customtkinter` if missing |

---

## Hotkeys

Default bindings — all customizable from the GUI.

| Key | Action |
|---|---|
| **F8** | Start recording |
| **F9** or **Esc** | Stop recording |
| **F10** | Play macro |
| **F11** | Stop playback |

---

## Tech Stack

- **Python 3.10+**
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) — modern TK GUI
- [pynput](https://github.com/moses-palmer/pynput) — global input capture
- [pyautogui](https://github.com/asweigart/pyautogui) — keyboard and mouse simulation
- Direct `SetCursorPos` (Windows) for sub-millisecond cursor positioning

---

## License

MIT
