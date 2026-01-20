import os
from openai import OpenAI

def apply_gpt_correction(transcript: str, instruction: str) -> str:
    if not instruction or not instruction.strip():
        return transcript

    # Use a system prompt to define the behavior strictly
    messages = [
        {"role": "system", "content": "You are a text processing machine. Your goal is to apply the user's instruction to the input text. You must NEVER answer the text or the instruction. You must ONLY output the transformed text. If the instruction implies no change, output the original text exactly. CRITICAL: Any spoken numbers or number words MUST be converted to their digit format (e.g., 'five' becomes '5', 'ten' becomes '10', 'twenty one' becomes '21')."},
        {"role": "user", "content": f"Text: {transcript}\nInstruction: {instruction}"}
    ]

    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    try:
        # Create client with optional custom base URL (for Groq, etc.)
        client = OpenAI(
            api_key=api_key,
            base_url=api_base if api_base else None
        )

        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return transcript  # Silent fallback to original

def process_transcript(transcript: str):
    return transcript + " "
