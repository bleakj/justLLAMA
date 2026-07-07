"""REST API client for llama-server."""

import requests


class LlamaClient:
    """Communicates with a running llama-server via its HTTP API."""

    def __init__(self, host: str = "http://localhost", port: int = 8080):
        self._base = f"{host}:{port}"
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def health(self, timeout: float = 10) -> dict:
        """GET /health — returns server health status."""
        resp = self._session.get(self._url("/health"), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def models(self, timeout: float = 10) -> list[dict]:
        """GET /v1/models — list available models."""
        resp = self._session.get(self._url("/v1/models"), timeout=timeout)
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
        timeout: float = 120,
        **kwargs,
    ) -> dict:
        """POST /v1/chat/completions — OpenAI-compatible chat completion.

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
        resp = self._session.post(
            self._url("/v1/chat/completions"),
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
        """POST /v1/embeddings — get embeddings for text.

        Useful for RAG pipeline when llama-server supports embedding.
        """
        payload = {
            "input": input_text,
            "model": model,
        }
        resp = self._session.post(
            self._url("/v1/embeddings"),
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [item["embedding"] for item in data]

    def set_base_url(self, host: str, port: int):
        """Update the server base URL."""
        self._base = f"{host}:{port}"

    @property
    def base_url(self) -> str:
        return self._base
