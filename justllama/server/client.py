"""REST API client for llama-server."""

import requests


class LlamaClient:
    """Communicates with a running llama-server via its HTTP API."""

    def __init__(
        self,
        host: str = "http://localhost",
        port: int | None = 8080,
        api_key: str | None = None,
        base_url: str | None = None,
        api_prefix: str = "/v1",
    ):
        self.api_prefix = api_prefix
        if base_url:
            self._base = base_url.rstrip("/")
        else:
            self._base = f"{host}:{port}" if port is not None else host
        self._session = requests.Session()
        if api_key:
            self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def health(self, timeout: float = 10) -> dict:
        """GET /health — returns server health status."""
        resp = self._session.get(self._url("/health"), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def models(self, timeout: float = 10) -> list[dict]:
        """GET <api_prefix>/models — list available models."""
        resp = self._session.get(self._url(f"{self.api_prefix}/models"), timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def props(self, timeout: float = 10) -> dict:
        """GET /props — server properties (model info, default params)."""
        resp = self._session.get(self._url("/props"), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_completion(
        self,
        messages: list[dict],
        *,
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        tools: list[dict] = None,
        tool_choice: str | dict = None,
        timeout: float = 120,
        **kwargs,
    ) -> dict:
        """POST <api_prefix>/chat/completions — OpenAI-compatible chat completion.

        Args:
            messages: List of {"role": str, "content": str}.
            model: Model name (default uses server's loaded model).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stream: If True, returns a streaming iterator (SSE).
            timeout: Request timeout in seconds.
        """
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        resp = self._session.post(
            self._url(f"{self.api_prefix}/chat/completions"),
            json=payload,
            timeout=timeout,
            stream=stream,
        )
        resp.raise_for_status()
        if stream:
            return resp
        return resp.json()

    def completion(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        timeout: float = 120,
        **kwargs,
    ) -> dict:
        """POST /completion — non-OpenAI raw completion endpoint."""
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stream": stream,
            **kwargs,
        }
        resp = self._session.post(
            self._url("/completion"),
            json=payload,
            timeout=timeout,
            stream=stream,
        )
        resp.raise_for_status()
        if stream:
            return resp
        return resp.json()

    def embeddings(
        self,
        input_text: str | list[str],
        *,
        model: str = "default",
        timeout: float = 30,
    ) -> list[list[float]]:
        """POST <api_prefix>/embeddings — get embeddings for text.

        Useful for RAG pipeline when llama-server supports embedding.
        """
        payload = {
            "input": input_text,
            "model": model,
        }
        resp = self._session.post(
            self._url(f"{self.api_prefix}/embeddings"),
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [item["embedding"] for item in data]

    def slots(self, timeout: float = 5) -> list[dict]:
        """GET /slots — get slot information including token usage.

        Returns list of slot dictionaries with keys like:
        - id: slot ID
        - n_ctx: total context size for this slot
        - n_token_usage: number of tokens currently used
        - is_processing: whether the slot is currently generating
        """
        try:
            resp = self._session.get(self._url("/slots"), timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []

    def clear_kv_cache(self, slot_id: int = -1, timeout: float = 5) -> bool:
        """PATCH /slots/{slot_id} — clear the KV cache for a slot.

        Args:
            slot_id: Slot ID to clear (-1 for all slots).
            timeout: Request timeout in seconds.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Use PATCH to update slot with action to erase cache
            payload = {"action": "erase"}
            resp = self._session.patch(
                self._url(f"/slots/{slot_id}"),
                json=payload,
                timeout=timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def set_base_url(self, host: str, port: int):
        """Update the server base URL."""
        if not isinstance(port, int) or not (1024 <= port <= 65535):
            raise ValueError(f"Port must be an int in 1024-65535, got {port!r}")
        self._base = f"{host}:{port}"


    @property
    def base_url(self) -> str:
        return self._base
