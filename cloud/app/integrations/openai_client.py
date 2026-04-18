from typing import Any, Callable, Dict, List, Optional
from xmlrpc import client


def _chat_client_and_model(
    openai_client,
    azure_openai_client=None,
    openai_model: Optional[str] = None,
    azure_chat_deployment: Optional[str] = None,
    prefer_azure: bool = True,
    model_hint: Optional[str] = None,
):
    """Select chat client/model with Azure-first strategy when configured."""
    if prefer_azure and azure_openai_client is not None:
        model_name = model_hint or azure_chat_deployment or openai_model
        return azure_openai_client, model_name

    model_name = model_hint or openai_model
    return openai_client, model_name



def create_chat_completion(
    messages: List[Dict[str, Any]],
    openai_client,
    azure_openai_client=None,
    openai_model: Optional[str] = None,
    azure_chat_deployment: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 500,
    response_format: Optional[Dict[str, Any]] = None,
    prefer_azure: bool = True,
    model_hint: Optional[str] = None,
):
    """Unified chat completion helper for Azure/OpenAI with optional structured output."""
    client, model_name = _chat_client_and_model(
        openai_client=openai_client,
        azure_openai_client=azure_openai_client,
        openai_model=openai_model,
        azure_chat_deployment=azure_chat_deployment,
        prefer_azure=prefer_azure,
        model_hint=model_hint,
    )

    kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if response_format is not None:
        kwargs["response_format"] = response_format

    print(f"[Chat Route] provider={'azure' if client is azure_openai_client and azure_openai_client is not None else 'openai'} model={model_name}")
    return client.chat.completions.create(**kwargs)


def make_chat_completion_fn(
    openai_client,
    azure_openai_client=None,
    openai_model: Optional[str] = None,
    azure_chat_deployment: Optional[str] = None,
) -> Callable[..., Any]:
    """Return a project-local create_chat_completion function with bound clients/config."""

    def _bound_create_chat_completion(
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 500,
        response_format: Optional[Dict[str, Any]] = None,
        prefer_azure: bool = True,
        model_hint: Optional[str] = None,
    ):
        return create_chat_completion(
            messages=messages,
            openai_client=openai_client,
            azure_openai_client=azure_openai_client,
            openai_model=openai_model,
            azure_chat_deployment=azure_chat_deployment,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            prefer_azure=prefer_azure,
            model_hint=model_hint,
        )

    return _bound_create_chat_completion