# Whisper Keyboard - CLAUDE.md

## Project Overview

Whisper Keyboard is a voice-to-text automation tool that allows dictation anywhere on the computer. Hold a hotkey to record voice, release to transcribe and auto-type the text.

**Core Flow:**
1. Hold hotkey → Start recording
2. Release hotkey → Stop recording
3. Audio sent to Whisper API → Transcription
4. Optional LLM processing (GPT/Llama) → Text correction
5. Text auto-typed into active window
6. Optional auto-send (Enter or Cmd+Enter)

## Project Structure

```
whisper-keyboard/
├── wkey/                     # Main package
│   ├── gui.py               # customtkinter GUI (legacy)
│   ├── gui_pyqt.py          # PyQt6 GUI (recommended, main entry point)
│   ├── key_config.py        # Hotkey configuration and persistence
│   ├── wkey.py              # Legacy CLI application
│   ├── whisper.py           # Whisper API wrapper
│   ├── utils.py             # Text processing, GPT correction
│   ├── find_key.py          # Key code discovery utility
│   └── .last_prompt         # Persistent prompt storage
├── scripts/
│   ├── wkey                 # CLI entry point
│   ├── wkey-gui             # customtkinter GUI entry point
│   └── fkey                 # Key finder entry point
├── .env                     # Environment config (API keys) - NOT in git
├── .env.template            # Template for .env setup
├── setup.py                 # Package configuration (version 3)
└── requirements.txt         # Dependencies
```

## Key Technologies

- **Python 3.x**
- **PyQt6** - Modern cross-platform GUI framework (recommended)
- **customtkinter** - Alternative GUI with Apple-style dark mode
- **pynput** - Global keyboard listening and typing simulation
- **sounddevice** - Microphone audio capture
- **scipy** - WAV file handling
- **openai** (>=1.0.0) - OpenAI SDK for Whisper and Chat Completions
- **ffmpeg** (optional) - Audio compression

## GUI Options

### PyQt6 GUI (`wkey/gui_pyqt.py`) - Recommended

The main GUI application featuring:

- **Status indicator** - Green (ready), Red (recording), Orange (processing)
- **Two recording hotkeys**:
  - **Transcription hotkey**: Regular recording, types text
  - **Auto-enter hotkey**: Recording + automatic Enter/Cmd+Enter after typing
- **Send mode toggle** (⏎/⌘⏎): Choose between Enter and Cmd+Enter for auto-send
- **LLM processing toggle**: Enable/disable AI text correction
- **Instructions dialog**: Edit LLM prompt in a modal dialog
- **Language dropdown**: 18 languages supported (default: Swedish)
- **Start with computer**: macOS LaunchAgent autostart
- **API Keys dialog**: Configure API keys, base URL, and models
- **Help mode**: Toggle (?) to show tooltips on hover

**New in PyQt6 GUI:**
- API Keys configuration dialog (saved to `~/.whisper-speak/.env`)
- Instructions dialog for LLM prompts
- Custom toggle switch widget
- Instant tooltips in help mode

### customtkinter GUI (`wkey/gui.py`) - Legacy

The original GUI with similar features using customtkinter.

## Configuration

### Runtime Config (persisted to `~/.wkey_config`)

```json
{
  "hotkey": "ctrl_l",
  "auto_enter_key": "shift_r",
  "send_mode": "cmd+enter",
  "language": "sv",
  "use_llm": false,
  "autostart": false
}
```

### Environment Variables

**Development mode:** `.env` file in project root

**Bundled app:** `~/.whisper-speak/.env`

```bash
# Required
OPENAI_API_KEY=your_key_here

# Optional - API provider override (for Groq)
OPENAI_API_BASE=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.1-8b-instant
WHISPER_MODEL=whisper-large-v3-turbo
```

**Current Setup:** Project is configured to use Groq API with Llama models.

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Install package
pip install -e .

# Run PyQt6 GUI (recommended)
python -m wkey.gui_pyqt

# Run customtkinter GUI (legacy)
python -m wkey.gui
wkey-gui

# Run legacy CLI application
wkey

# Find keyboard key codes
fkey
```

## Key Files

| File | Purpose |
|------|---------|
| `wkey/gui_pyqt.py` | PyQt6 GUI - main application with API keys dialog |
| `wkey/gui.py` | customtkinter GUI (legacy) |
| `wkey/key_config.py` | Hotkey configuration, persistence, LaunchAgent management |
| `wkey/whisper.py` | `apply_whisper()` - Sends audio to Whisper API |
| `wkey/utils.py` | `apply_gpt_correction()` - LLM text processing |

## Important Code Locations

### gui_pyqt.py (PyQt6)
- **Main window**: `WKeyGUI` class
- **Keyboard listener**: `_start_keyboard_listener()`, `_on_key_press()`, `_on_key_release()`
- **Audio recording**: `_start_audio_stream()`, `_audio_callback()`
- **Transcription**: `_process_audio()` - includes silence/hallucination detection
- **API Keys dialog**: `APIKeysDialog` class - configure API settings
- **Instructions dialog**: `InstructionsDialog` class - edit LLM prompt
- **Environment management**: `_get_env_file_path()`, `_load_env_values()`, `_save_env_values()`
- **Custom widgets**: `ToggleSwitch`, `InstantTooltipFilter`

### gui.py (customtkinter)
- **Keyboard listener**: `_start_keyboard_listener()`, `_on_key_press()`, `_on_key_release()`
- **Audio recording**: `_start_audio_stream()`, `_audio_callback()`
- **Transcription**: `_process_audio()` - includes silence/hallucination detection
- **Auto-send logic**: `_process_audio()` - uses `get_send_mode()` to choose Enter/Cmd+Enter
- **Help mode**: `_toggle_help_mode()`, `_show_tooltip()`, `_hide_tooltip()`

### key_config.py
- **Config persistence**: `_load_config()`, `_save_config()` → `~/.wkey_config`
- **Hotkey capture**: `_capture_new_hotkey()`, `_capture_new_auto_enter_key()`
- **LaunchAgent**: `_create_launch_agent()`, `_remove_launch_agent()` → `~/Library/LaunchAgents/com.wkey.autostart.plist`
- **Autostart uses**: `python -m wkey.gui_pyqt` as the startup command

## Silence & Hallucination Detection

`_process_audio()` filters out bad transcriptions:

1. **Audio duration check**: Skip if < 0.5 seconds
2. **RMS energy check**: Skip if audio is too quiet (RMS < 0.005)
3. **Transcript length check**: Skip if < 2 characters
4. **Hallucination phrases**: Filter common Whisper hallucinations like "thanks for watching", "tack alla som tittat", etc.

## Dependencies

```
customtkinter>=5.2.0
numpy
openai>=1.0.0
pynput==1.7.6
PyQt6>=6.4.0
python-dotenv==1.0.0
scipy>=1.9.0
sounddevice==0.4.6
```

## Platform Requirements

- **macOS:** Requires Microphone + Accessibility + Input Monitoring permissions
- **Linux:** Requires `portaudio19-dev` library
- **Windows:** Not officially tested

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Hold transcription hotkey | Start recording |
| Release transcription hotkey | Stop recording, transcribe, type |
| Hold auto-enter hotkey | Start recording (with auto-send) |
| Release auto-enter hotkey | Stop, transcribe, type, send |
| Ctrl+Shift+K | Enter hotkey change mode (CLI) |
| Ctrl+Shift+E | Toggle auto-enter (CLI) |
| Esc | Cancel key selection |
| Backspace | Disable auto-enter key (during selection) |

## File Locations

| File | Path |
|------|------|
| Config file | `~/.wkey_config` |
| Autostart plist | `~/Library/LaunchAgents/com.wkey.autostart.plist` |
| API keys (bundled) | `~/.whisper-speak/.env` |
| API keys (dev) | `./env` in project root |
| Error log | `~/whisper-speak-error.log` |
| Startup logs | `~/Library/Logs/wkey.out.log`, `~/Library/Logs/wkey.err.log` |

## Debugging Tips

- Check terminal output for timing and error information
- Verify API key with: `echo $OPENAI_API_KEY`
- Test audio: Status should turn red when hotkey held
- If no typing occurs: Check Accessibility permissions (macOS)
- Check error log: `cat ~/whisper-speak-error.log`
- Check autostart logs: `cat ~/Library/Logs/wkey.out.log`
