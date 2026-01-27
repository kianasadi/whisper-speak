# Viska

Voice-to-text for macOS. Hold a hotkey, speak, release — your words are typed instantly.

## Download

**[Download Viska-1.0.0-macOS.zip](https://github.com/kianasadi/whisper-speak/releases/latest)**

1. Download the zip from the latest release
2. Unzip and drag **Viska.app** to your Applications folder
3. Open Viska and grant the required permissions (see below)

## Features

- **Hold-to-record**: Hold a hotkey to record, release to transcribe and type
- **Two hotkeys**: One for regular dictation, one for auto-send (Enter/Cmd+Enter)
- **Fast transcription**: Uses Groq's Whisper API (free tier available)
- **Optional LLM processing**: Clean up transcriptions with AI
- **18 languages supported**: Swedish, English, Spanish, and more
- **Start with macOS**: Optional autostart on login
- **Minimal UI**: Small status window, stays out of your way

## Setup

### 1. Get a Groq API Key (free)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up and create an API key
3. Open Viska, click the gear icon, and enter your API key

### 2. Grant Permissions

On first launch, macOS will ask for permissions. Go to **System Settings > Privacy & Security** and enable:

- **Microphone**: Required to record your voice
- **Accessibility**: Required to type text into other apps
- **Input Monitoring**: Required to detect hotkey presses

Restart Viska after granting permissions.

## Usage

| Action | Result |
|--------|--------|
| Hold transcription hotkey | Start recording (status turns red) |
| Release transcription hotkey | Transcribe and type text |
| Hold auto-enter hotkey | Start recording |
| Release auto-enter hotkey | Transcribe, type, and send (Enter or Cmd+Enter) |

### Settings

- **Language**: Choose your primary language for better accuracy
- **Send mode** (⏎/⌘⏎): Toggle between Enter and Cmd+Enter for auto-send
- **LLM toggle**: Enable AI text correction
- **Instructions**: Customize the LLM prompt
- **Start with computer**: Launch Viska on login

## API Configuration

Viska uses Groq by default (fast and free tier available). You can also use OpenAI.

| Setting | Default |
|---------|---------|
| API Base | `https://api.groq.com/openai/v1` |
| Whisper Model | `whisper-large-v3-turbo` |
| LLM Model | `llama-3.1-8b-instant` |

## Building from Source

```bash
# Clone the repo
git clone https://github.com/kianasadi/whisper-speak.git
cd whisper-speak

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-build.txt

# Run from source
python -m wkey.gui_pyqt

# Build the app
./build_universal.sh
```

## License

MIT
