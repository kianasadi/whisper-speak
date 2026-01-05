import os

from dotenv import load_dotenv
import openai

load_dotenv()
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "whisper-1")
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError(
        "OPENAI_API_KEY environment variable is not set. "
        "Please set it in your .env file or environment."
    )
openai.api_key = api_key

if os.environ.get("OPENAI_API_BASE"):
    openai.api_base = os.environ.get("OPENAI_API_BASE")


def apply_whisper(filepath: str, mode: str, language: str = None, initial_prompt: str = None) -> str:

    if mode not in ("translate", "transcribe"):
        raise ValueError(f"Invalid mode: {mode}")

    with open(filepath, "rb") as audio_file:
        kwargs = {}
        if language:
            kwargs['language'] = language
        if initial_prompt:
            kwargs['prompt'] = initial_prompt

        if mode == "translate":
            response = openai.Audio.translate(WHISPER_MODEL, audio_file, **kwargs)
        elif mode == "transcribe":
            response = openai.Audio.transcribe(WHISPER_MODEL, audio_file, **kwargs)

    transcript = response["text"]
    return transcript

