import base64
from typing import Any, Callable, Optional

import requests


def analyze_image_with_azure(
    image_bytes: bytes,
    prompt: str,
    *,
    create_chat_completion_fn: Callable[..., Any],
    azure_openai_vision_deployment: Optional[str] = None,
    azure_openai_chat_deployment: Optional[str] = None,
    openai_model: Optional[str] = None,
) -> str:
    """Analyze image bytes using Azure/OpenAI multimodal chat."""
    if not image_bytes:
        return "[think] ما قدرت أحلل الصورة حالياً."

    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{image_b64}"
        model_hint = (
            azure_openai_vision_deployment
            or azure_openai_chat_deployment
            or openai_model
        )

        response = create_chat_completion_fn(
            messages=[
                {
                    "role": "system",
                    "content": "حلل الصورة بدقة وباختصار باللغة العربية مع نقاط عملية.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=450,
            prefer_azure=True,
            model_hint=model_hint,
        )
        return (
            response.choices[0].message.content
            or "[think] تم التحليل لكن ما في وصف واضح."
        ).strip()
    except Exception as e:
        print(f"[Azure Vision] ❌ Analysis failed: {e}")
        return "[think] صار خلل أثناء تحليل الصورة. جرب مرة ثانية."


def generate_image_with_azure(
    prompt: str,
    *,
    azure_openai_client: Any,
    azure_openai_image_deployment: Optional[str],
    size: str = "1024x1024",
) -> Optional[bytes]:
    """Generate image with Azure OpenAI and return image bytes."""
    if not prompt:
        return None

    if azure_openai_client is None or not azure_openai_image_deployment:
        print("[Azure Image] ⚠️ Missing Azure OpenAI client or image deployment")
        return None

    try:
        result = azure_openai_client.images.generate(
            model=azure_openai_image_deployment,
            prompt=prompt,
            size=size,
        )

        if not getattr(result, "data", None):
            print("[Azure Image] ⚠️ Empty image response")
            return None

        first = result.data[0]

        if getattr(first, "b64_json", None):
            return base64.b64decode(first.b64_json)

        if getattr(first, "url", None):
            response = requests.get(first.url, timeout=30)
            if response.status_code == 200:
                return response.content
            print(f"[Azure Image] ⚠️ URL download failed with {response.status_code}")

    except Exception as e:
        print(f"[Azure Image] ❌ Generation failed: {e}")

    return None