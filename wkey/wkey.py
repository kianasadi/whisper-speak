import os
import subprocess
from dotenv import load_dotenv
import sounddevice as sd
import numpy as np
import openai
from pynput.keyboard import Controller as KeyboardController, Key, Listener
from scipy.io import wavfile

from wkey.whisper import apply_whisper
from wkey.utils import process_transcript, apply_gpt_correction
from wkey.key_config import get_config, get_hotkey, get_hotkey_label, get_auto_enter, get_language, get_use_llm

load_dotenv()

# Initialize key configuration (reads from config file or env var)
key_config = get_config()

PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_prompt")

def save_prompt(prompt):
    try:
        with open(PROMPT_FILE, "w") as f:
            f.write(prompt)
    except Exception:
        pass  # Silent failure

def load_prompt():
    try:
        if os.path.exists(PROMPT_FILE):
            with open(PROMPT_FILE, "r") as f:
                return f.read().strip()
    except Exception:
        pass
    return None

# This flag determines when to record
recording = False

# This is where we'll store the audio
audio_data = []

# This is the sample rate for the audio
sample_rate = 16000

# Keyboard controller
keyboard_controller = KeyboardController()

current_prompt = load_prompt()


def on_press(key):
    global recording
    global audio_data

    # Let key_config handle hotkey change mode (Ctrl+Shift+K)
    if key_config.handle_key_press(key):
        return  # Key was consumed by config handler

    # Skip if in key change mode
    if key_config.is_in_change_mode():
        return

    if key == get_hotkey():
        recording = True
        audio_data = []
        print("◉ Recording...", end="\r")

def on_release(key):
    global recording
    global audio_data

    # Let key_config track modifier releases
    key_config.handle_key_release(key)

    # Skip if in key change mode
    if key_config.is_in_change_mode():
        return

    if key == get_hotkey():
        recording = False
        print("○ Processing...   ", end="\r")

        try:
            audio_data_np = np.concatenate(audio_data, axis=0)
        except ValueError:
            print("              ", end="\r")  # Clear the line
            return

        audio_data_int16 = (audio_data_np * np.iinfo(np.int16).max).astype(np.int16)

        wavfile.write('recording.wav', sample_rate, audio_data_int16)

        # Convert to m4a for faster upload
        file_to_transcribe = 'recording.wav'
        try:
            subprocess.run(['ffmpeg', '-i', 'recording.wav', '-c:a', 'aac', '-b:a', '32k', 'recording.m4a', '-y'],
                         check=True, capture_output=True)
            file_to_transcribe = 'recording.m4a'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Silently fall back to WAV

        transcript = None
        try:
            language = get_language()
            transcript = apply_whisper(file_to_transcribe, 'transcribe', language=language)
        except openai.error.InvalidRequestError:
            print("✗ Transcription failed", end="\r")
            return

        if transcript:
            # Apply LLM correction only if enabled and prompt is set
            if get_use_llm() and current_prompt:
                transcript = apply_gpt_correction(transcript, current_prompt)

            processed_transcript = process_transcript(transcript)
            print(f"✓ \"{processed_transcript.strip()}\"")
            keyboard_controller.type(processed_transcript)

            # Press Enter if auto-enter is enabled
            if get_auto_enter():
                keyboard_controller.press(Key.enter)
                keyboard_controller.release(Key.enter)


def callback(indata, frames, time, status):
    if recording:
        audio_data.append(indata.copy())  # make sure to copy the indata

def on_hotkey_change(old_key, new_key):
    """Callback function when the hotkey is changed at runtime."""
    print(f"✓ Hotkey: {get_hotkey_label()}")


def _format_key(label):
    """Format a key label for display using Apple-style symbols."""
    key_symbols = {
        'ctrl_l': '⌃L', 'ctrl_r': '⌃R', 'ctrl': '⌃',
        'shift_l': '⇧L', 'shift_r': '⇧R', 'shift': '⇧',
        'alt_l': '⌥L', 'alt_r': '⌥R', 'alt': '⌥',
        'cmd_l': '⌘L', 'cmd_r': '⌘R', 'cmd': '⌘',
    }
    return key_symbols.get(label, label)


def main():
    global current_prompt

    # Set up hotkey change callback
    key_config.set_change_callback(on_hotkey_change)

    hotkey_display = _format_key(get_hotkey_label())
    auto_enter_status = "ON" if get_auto_enter() else "OFF"
    language = get_language()
    print(f"● wkey ready — {hotkey_display} dictate | lang:{language} | auto-enter:{auto_enter_status}")

    if get_use_llm() and current_prompt:
        print(f"  llm prompt: {current_prompt}")

    with Listener(on_press=on_press, on_release=on_release) as listener:
        # This is the stream callback
        with sd.InputStream(callback=callback, channels=1, samplerate=sample_rate):
            # Loop specifically for reading the prompt
            while True:
                try:
                    new_prompt = input()
                    if new_prompt.strip():
                        if new_prompt.strip().lower() == "no prompt":
                            current_prompt = None
                            if os.path.exists(PROMPT_FILE):
                                os.remove(PROMPT_FILE)
                            print("✓ Prompt off")
                        else:
                            current_prompt = new_prompt
                            save_prompt(current_prompt)
                            print(f"✓ Prompt: {current_prompt}")
                except (KeyboardInterrupt, EOFError):
                    print("\n○ Stopped")
                    break

if __name__ == "__main__":
    main()
