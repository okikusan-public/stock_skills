"""LLM Tool — マルチLLM呼び出しファサード.

tools/ 層は API 呼び出しのみを担う。判断ロジックは含めない。
Gemini / GPT / Grok を共通インターフェースで呼び出す。
APIキー未設定時は None を返す（呼び出し元が Claude にフォールバック）。
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

_ENDPOINTS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "gpt": "https://api.openai.com/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
}

_API_KEY_ENVS = {
    "gemini": "GEMINI_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "grok": "XAI_API_KEY",
}

_VALID_PROVIDERS = set(_ENDPOINTS.keys())


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def call_llm(
    provider: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    timeout: int = 60,
) -> Optional[str]:
    """LLM を呼び出してテキストを返す.

    Parameters
    ----------
    provider : str
        "gemini" | "gpt" | "grok"
    model : str
        モデル名（例: "gemini-3.1-pro", "gpt-5.4", "grok-4"）
    prompt : str
        ユーザープロンプト
    system_prompt : str, optional
        システムプロンプト
    timeout : int
        リクエストタイムアウト秒数（デフォルト 60）

    Returns
    -------
    str or None
        レスポンステキスト。APIキー未設定またはエラー時は None。
    """
    if provider not in _VALID_PROVIDERS:
        return None

    api_key = os.environ.get(_API_KEY_ENVS[provider])
    if not api_key:
        return None

    t0 = time.time()
    try:
        if provider == "gemini":
            result = _call_gemini(api_key, model, prompt, system_prompt, timeout)
        elif provider == "gpt":
            result = _call_openai_compatible(
                api_key, _ENDPOINTS["gpt"], model, prompt, system_prompt, timeout,
            )
        elif provider == "grok":
            result = _call_openai_compatible(
                api_key, _ENDPOINTS["grok"], model, prompt, system_prompt, timeout,
            )
        else:
            return None
    except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
        elapsed = time.time() - t0
        print(
            f"[llm] FAIL {provider}/{model} ({elapsed:.1f}s): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None

    elapsed = time.time() - t0
    length = len(result) if result else 0
    print(
        f"[llm] OK {provider}/{model} ({elapsed:.1f}s, {length} chars)",
        file=sys.stderr,
    )
    return result


def is_provider_available(provider: str) -> bool:
    """指定プロバイダの API キーが設定されているか."""
    env_var = _API_KEY_ENVS.get(provider)
    if not env_var:
        return False
    return bool(os.environ.get(env_var))


def get_available_providers() -> list[str]:
    """利用可能なプロバイダの一覧を返す."""
    return [p for p in _VALID_PROVIDERS if is_provider_available(p)]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _call_openai_compatible(
    api_key: str,
    endpoint: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    timeout: int,
) -> Optional[str]:
    """OpenAI 互換 API（GPT / Grok）を呼び出す."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages},
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_gemini(
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    timeout: int,
) -> Optional[str]:
    """Google Gemini API を呼び出す."""
    url = _ENDPOINTS["gemini"].format(model=model)

    payload: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    response = requests.post(
        url,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


__all__ = [
    "call_llm",
    "is_provider_available",
    "get_available_providers",
]
