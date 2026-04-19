import base64
import os
import time
from typing import Any, Callable, Optional

import requests


GPT_IMAGE_SUPPORTED_SIZES = {"1024x1024", "1024x1536", "1536x1024"}


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



def _normalize_azure_endpoint(raw_endpoint: str) -> str:
    endpoint = (raw_endpoint or "").strip().rstrip("/")
    for suffix in ("/openai/v1", "/openai", "/models"):
        if endpoint.endswith(suffix):
            endpoint = endpoint[: -len(suffix)].rstrip("/")
    return endpoint



def _normalize_image_size(size: Optional[str]) -> str:
    normalized = (size or "").strip().lower()
    if normalized in GPT_IMAGE_SUPPORTED_SIZES:
        return normalized

    # المشروع الحالي يمرر أحيانًا 512x512. هذا غير مدعوم في GPT-image-1 series.
    if normalized:
        print(
            f"[Azure Image] ℹ️ Unsupported size '{normalized}' for GPT-image models; using 1024x1024 instead"
        )
    return "1024x1024"



def _build_image_payload(prompt: str, *, size: str) -> dict:
    payload = {
        "prompt": prompt,
        "n": 1,
        "size": _normalize_image_size(size),
        "quality": os.getenv("AZURE_OPENAI_IMAGE_QUALITY", "medium").strip().lower() or "medium",
        "output_format": os.getenv("AZURE_OPENAI_IMAGE_OUTPUT_FORMAT", "png").strip().lower() or "png",
    }

    model_name = os.getenv("AZURE_OPENAI_IMAGE_MODEL", "").strip()
    if model_name:
        payload["model"] = model_name

    background = os.getenv("AZURE_OPENAI_IMAGE_BACKGROUND", "").strip().lower()
    if background in {"auto", "opaque", "transparent"}:
        payload["background"] = background

    # صحح القيم غير المدعومة بدل إرسال Payload قديم من DALL-E 3.
    if payload["quality"] not in {"low", "medium", "high"}:
        print(
            f"[Azure Image] ℹ️ Unsupported quality '{payload['quality']}'; using 'medium'"
        )
        payload["quality"] = "medium"

    if payload["output_format"] not in {"png", "jpeg"}:
        print(
            f"[Azure Image] ℹ️ Unsupported output_format '{payload['output_format']}'; using 'png'"
        )
        payload["output_format"] = "png"

    # JPEG-only option
    output_compression = os.getenv("AZURE_OPENAI_IMAGE_OUTPUT_COMPRESSION", "").strip()
    if payload["output_format"] == "jpeg" and output_compression.isdigit():
        compression_value = int(output_compression)
        if 0 <= compression_value <= 100:
            payload["output_compression"] = compression_value

    return payload



def _extract_error_text(response: requests.Response) -> str:
    try:
        body = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text[:800]

    error_obj = body.get("error") if isinstance(body, dict) else None
    if isinstance(error_obj, dict):
        code = str(error_obj.get("code") or "").strip()
        message = str(error_obj.get("message") or "").strip()
        if code or message:
            return f"code={code} message={message}".strip()

    return str(body)[:800]



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

    endpoint = _normalize_azure_endpoint(os.getenv("AZURE_OPENAI_IMAGE_ENDPOINT", ""))
    api_key = os.getenv("AZURE_OPENAI_IMAGE_API_KEY", "").strip()
    # Docs now use 2025-04-01-preview for GPT-image-1 series.
    api_version = os.getenv("AZURE_OPENAI_IMAGE_API_VERSION", "2025-04-01-preview").strip()
    deployment = (azure_openai_image_deployment or "").strip()

    if not endpoint or not api_key or not deployment:
        print("[Azure Image] ⚠️ Missing endpoint/api_key/deployment")
        return None

    url = f"{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}"
    payload = _build_image_payload(prompt, size=size)
    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }

    last_error_text = ""
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            last_error_text = str(e)
            print(f"[Azure Image] ⚠️ Attempt {attempt + 1}/3 request error: {e}")
            time.sleep(2 * (attempt + 1))
            continue

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as e:
                print(f"[Azure Image] ❌ Invalid JSON response: {e}")
                return None

            if isinstance(data, dict) and data.get("error"):
                print(f"[Azure Image] ❌ API returned error object on 200: {data['error']}")
                return None

            if not data.get("data"):
                print("[Azure Image] ⚠️ Empty image response")
                return None

            first = data["data"][0]
            if first.get("b64_json"):
                return base64.b64decode(first["b64_json"])

            if first.get("url"):
                try:
                    img_response = requests.get(first["url"], timeout=60)
                    if img_response.status_code == 200:
                        return img_response.content
                    print(
                        f"[Azure Image] ⚠️ URL download failed with {img_response.status_code}"
                    )
                except requests.RequestException as e:
                    print(f"[Azure Image] ⚠️ Generated URL download failed: {e}")
                return None

            print("[Azure Image] ⚠️ No b64_json or url found in response")
            return None

        last_error_text = _extract_error_text(response)
        print(
            f"[Azure Image] ⚠️ Attempt {attempt + 1}/3 failed: {response.status_code} - {last_error_text}"
        )

        # الدوال الحالية لا تستطيع إصلاح deployment متقاعد أو موديل غير مدعوم.
        if response.status_code >= 500:
            time.sleep(3 * (attempt + 1))
            continue

        # أخطاء 4xx غالبًا تكشف payload أو deployment أو الوصول ولا تستفيد من retry.
        if response.status_code == 400 and (
            "InvalidPayload" in last_error_text
            or "invalid value" in last_error_text.lower()
            or "unsupported" in last_error_text.lower()
        ):
            print(f"[Azure Image] ❌ Invalid payload: {payload}")
        return None

    print(f"[Azure Image] ❌ Generation failed after retries: {last_error_text}")
    print(
        "[Azure Image] ℹ️ If this deployment is DALL-E 3, Azure retired it on 2026-03-04. "
        "Existing DALL-E 3 deployments are non-functional and must be replaced with gpt-image-1 or gpt-image-1.5."
    )
    return None
