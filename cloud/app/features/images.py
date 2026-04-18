import re


def is_image_generation_request(message: str) -> bool:
    """Detect if user asks for image generation."""
    text = (message or "").strip().lower()
    triggers = [
        "ارسم",
        "رسمة",
        "صمم صورة",
        "ولّد صورة",
        "generate image",
        "draw",
    ]
    return any(t in text for t in triggers)


def extract_image_prompt(message: str) -> str:
    """Extract prompt text for image generation."""
    text = (message or "").strip()
    text = re.sub(r"^(?:/image|/img)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?:ارسم|رسمة|صمم صورة|ول\s*د صورة|ولّد صورة|generate image|draw)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text