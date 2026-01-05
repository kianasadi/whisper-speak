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
│   ├── gui.py               # Apple-style GUI application (main entry point)
│   ├── key_config.py        # Hotkey configuration and persistence
│   ├── wkey.py              # Legacy CLI application
│   ├── whisper.py           # Whisper API wrapper
│   ├── utils.py             # Text processing, GPT correction
│   ├── find_key.py          # Key code discovery utility
│   └── .last_prompt         # Persistent prompt storage
├── scripts/
│   ├── wkey                 # CLI entry point
│   └── fkey                 # Key finder entry point
├── .env                     # Environment config (API keys) - NOT in git
├── .env.template            # Template for .env setup
├── setup.py                 # Package configuration
└── requirements.txt         # Dependencies
```

## Key Technologies

- **Python 3.x**
- **customtkinter** - Modern GUI with Apple-style dark mode
- **pynput** - Global keyboard listening and typing simulation
- **sounddevice** - Microphone audio capture
- **scipy** - WAV file handling
- **openai** (0.27.8) - Legacy OpenAI SDK for Whisper and ChatCompletion
- **ffmpeg** (optional) - Audio compression

## GUI Features

The GUI (`wkey/gui.py`) provides:

- **Status indicator** - Green (ready), Red (recording), Orange (processing)
- **Two recording hotkeys**:
  - **Hotkey** (top right): Regular recording, just types text
  - **Auto-enter key**: Recording + automatic Enter/Cmd+Enter after typing
- **Send mode toggle** (⏎/⌘⏎): Choose between Enter and Cmd+Enter for auto-send
- **Always on top toggle**: Keep window floating above others
- **Start with computer**: macOS LaunchAgent autostart
- **Language dropdown**: 18 languages supported (default: Swedish)
- **LLM processing toggle**: Enable/disable GPT text correction
- **Prompt input**: Custom instruction for LLM processing

## Configuration

### Runtime Config (persisted to `~/.wkey_config`)

```json
{
  "hotkey": "ctrl",
  "auto_enter_key": "shift",
  "send_mode": "cmd+enter",
  "language": "sv",
  "use_llm": false,
  "autostart": false
}
```

### Environment Variables (`.env`)

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

# Run GUI application (recommended)
python -m wkey.gui

# Run legacy CLI application
wkey

# Find keyboard key codes
fkey
```

## Key Files

| File | Purpose |
|------|---------|
| `wkey/gui.py` | Apple-style GUI, audio recording, keyboard listener, transcription |
| `wkey/key_config.py` | Hotkey configuration, persistence, LaunchAgent management |
| `wkey/whisper.py` | `apply_whisper()` - Sends audio to Whisper API |
| `wkey/utils.py` | `apply_gpt_correction()` - LLM text processing |

## Important Code Locations

### gui.py
- **Keyboard listener**: `_start_keyboard_listener()`, `_on_key_press()`, `_on_key_release()`
- **Audio recording**: `_start_audio_stream()`, `_audio_callback()`
- **Transcription**: `_process_audio()` - includes silence/hallucination detection
- **Auto-send logic**: `_process_audio()` - uses `get_send_mode()` to choose Enter/Cmd+Enter

### key_config.py
- **Config persistence**: `_load_config()`, `_save_config()` → `~/.wkey_config`
- **Hotkey capture**: `_capture_new_hotkey()`, `_capture_new_auto_enter_key()`
- **LaunchAgent**: `_create_launch_agent()`, `_remove_launch_agent()` → `~/Library/LaunchAgents/com.wkey.autostart.plist`

## Silence & Hallucination Detection

`_process_audio()` filters out bad transcriptions:

1. **Audio duration check**: Skip if < 0.5 seconds
2. **RMS energy check**: Skip if audio is too quiet (RMS < 0.005)
3. **Transcript length check**: Skip if < 2 characters
4. **Hallucination phrases**: Filter common Whisper hallucinations like "thanks for watching", "tack alla som tittat", etc.

## Dependencies

```
numpy
openai==0.27.8
pynput==1.7.6
python-dotenv==1.0.0
scipy==1.8.0
sounddevice==0.4.6
customtkinter
```

**Note:** Uses legacy openai SDK (0.27.8). Migration to v1.x would require significant changes.

## Platform Requirements

- **macOS:** Requires Microphone + Accessibility + Input Monitoring permissions
- **Linux:** Requires `portaudio19-dev` library
- **Windows:** Not officially tested

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Hold hotkey | Start recording |
| Release hotkey | Stop recording, transcribe, type |
| Hold auto-enter key | Start recording (with auto-send) |
| Release auto-enter key | Stop, transcribe, type, send |
| Ctrl+Shift+K | Enter hotkey change mode (CLI) |
| Ctrl+Shift+E | Toggle auto-enter (CLI) |
| Esc | Cancel key selection |
| Backspace | Disable auto-enter key |

## Debugging Tips

- Check terminal output for timing and error information
- Verify API key with: `echo $OPENAI_API_KEY`
- Test audio: Status should turn red when hotkey held
- If no typing occurs: Check Accessibility permissions (macOS)
- Config file location: `~/.wkey_config`
- Autostart plist: `~/Library/LaunchAgents/com.wkey.autostart.plist`
