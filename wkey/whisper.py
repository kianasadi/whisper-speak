import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "whisper-1")

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError(
        "OPENAI_API_KEY environment variable is not set. "
        "Please set it in your .env file or environment."
    )

# Create client with optional custom base URL (for Groq, etc.)
api_base = os.environ.get("OPENAI_API_BASE")
client = OpenAI(
    api_key=api_key,
    base_url=api_base if api_base else None
)


def apply_whisper(filepath: str, mode: str, language: str = None, initial_prompt: str = None) -> str:

    if mode not in ("translate", "transcribe"):
        raise ValueError(f"Invalid mode: {mode}")

    with open(filepath, "rb") as audio_file:
        kwargs = {"model": WHISPER_MODEL, "file": audio_file}
        if language:
            kwargs['language'] = language
        if initial_prompt:
            kwargs['prompt'] = initial_prompt

        if mode == "translate":
            response = client.audio.translations.create(**kwargs)
        elif mode == "transcribe":
            response = client.audio.transcriptions.create(**kwargs)

    return response.text
