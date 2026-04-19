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


import base64
import os
from typing import Any, Optional

import requests


def generate_image_with_azure(
    prompt: str,
    *,
    azure_openai_client: Any,
    azure_openai_image_deployment: Optional[str],
    size: str = "1024x1024",
) -> Optional[bytes]:
    """Generate image with Azure OpenAI via direct REST and return image bytes."""
    if not prompt:
        return None

    endpoint = os.getenv("AZURE_OPENAI_IMAGE_ENDPOINT", "").strip().rstrip("/")
    api_key = os.getenv("AZURE_OPENAI_IMAGE_API_KEY", "").strip()
    api_version = os.getenv("AZURE_OPENAI_IMAGE_API_VERSION", "2024-02-01").strip()
    deployment = (azure_openai_image_deployment or "").strip()

    if not endpoint or not api_key or not deployment:
        print("[Azure Image] ⚠️ Missing endpoint/api_key/deployment")
        return None

    url = f"{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}"

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "size": size,
        "quality": "standard", # تم التغيير من medium إلى standard
        "n": 1
    }

    try:
        import time

        last_error_text = ""

        for attempt in range(3):
            response = requests.post(url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                print(f"[Azure Image] Detailed Error: {response.text}")
                break

            last_error_text = response.text
            print(f"[Azure Image] ⚠️ Attempt {attempt + 1}/3 failed: {response.status_code} - {response.text}")

            if response.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue

            print(f"[Azure Image] ❌ Generation failed: {response.status_code} - {response.text}")
            return None
        else:
            print(f"[Azure Image] ❌ Generation failed after retries: {last_error_text}")
            return None
        data = response.json()

        if not data.get("data"):
            print("[Azure Image] ⚠️ Empty image response")
            return None
        

        first = data["data"][0]

        if first.get("b64_json"):
            return base64.b64decode(first["b64_json"])

        if first.get("url"):
            img_response = requests.get(first["url"], timeout=60)
            if img_response.status_code == 200:
                return img_response.content
            print(f"[Azure Image] ⚠️ URL download failed with {img_response.status_code}")

    except Exception as e:
        print(f"[Azure Image] ❌ Generation failed: {e}")

    return None