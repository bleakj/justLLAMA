"""Tests for justllama.server.client.LlamaClient.

All HTTP calls are mocked — no real network requests are made.
"""

from unittest.mock import MagicMock, patch

import pytest

from justllama.server.client import LlamaClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(host: str = "http://localhost", port: int = 8080) -> LlamaClient:
    client = LlamaClient(host=host, port=port)
    # Replace the real Session with a mock we can control per-test.
    client._session = MagicMock()
    return client


# ---------------------------------------------------------------------------
# GET endpoint tests
# ---------------------------------------------------------------------------

def test_health_success():
    client = _make_client()
    client._session.get.return_value = MagicMock(
        json=MagicMock(return_value={"status": "ok"}),
        raise_for_status=MagicMock(),
    )

    result = client.health()

    assert result == {"status": "ok"}
    client._session.get.assert_called_once_with(
        "http://localhost:8080/health", timeout=10
    )


def test_models_success():
    client = _make_client()
    client._session.get.return_value = MagicMock(
        json=MagicMock(return_value={"data": [{"id": "m1"}]}),
        raise_for_status=MagicMock(),
    )

    result = client.models()

    assert result == [{"id": "m1"}]
    client._session.get.assert_called_once_with(
        "http://localhost:8080/v1/models", timeout=10
    )


def test_props_success():
    client = _make_client()
    props_payload = {"default_params": {}}
    client._session.get.return_value = MagicMock(
        json=MagicMock(return_value=props_payload),
        raise_for_status=MagicMock(),
    )

    result = client.props()

    assert result == props_payload
    client._session.get.assert_called_once_with(
        "http://localhost:8080/props", timeout=10
    )


# ---------------------------------------------------------------------------
# POST endpoint tests
# ---------------------------------------------------------------------------

def test_chat_completion():
    client = _make_client()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    expected_response = {"choices": [{"message": {"content": "hi"}}]}
    client._session.post.return_value = MagicMock(
        json=MagicMock(return_value=expected_response),
        raise_for_status=MagicMock(),
    )

    result = client.chat_completion(messages)

    # Verify the response is returned correctly.
    assert result == expected_response

    # Verify the POST was made to the right endpoint with the right payload.
    call_args = client._session.post.call_args
    assert call_args[0][0] == "http://localhost:8080/v1/chat/completions"

    payload = call_args[1]["json"]
    assert payload["messages"] == messages
    assert payload["model"] == "default"
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 2048
    assert payload["stream"] is False


def test_completion():
    client = _make_client()
    expected_response = {"content": "completion text", "n_predict": 128}
    client._session.post.return_value = MagicMock(
        json=MagicMock(return_value=expected_response),
        raise_for_status=MagicMock(),
    )

    result = client.completion("Once upon a time", max_tokens=128)

    assert result == expected_response

    call_args = client._session.post.call_args
    assert call_args[0][0] == "http://localhost:8080/completion"

    payload = call_args[1]["json"]
    assert payload["prompt"] == "Once upon a time"
    assert payload["n_predict"] == 128
    assert payload["stream"] is False


# ---------------------------------------------------------------------------
# Error propagation tests
# ---------------------------------------------------------------------------

def test_connection_error():
    client = _make_client()
    client._session.get.side_effect = ConnectionError("Connection refused")

    with pytest.raises(ConnectionError, match="Connection refused"):
        client.health()


def test_http_error():
    from requests.exceptions import HTTPError

    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = HTTPError("500 Server Error")
    client._session.get.return_value = mock_resp

    with pytest.raises(HTTPError, match="500"):
        client.health()


# ---------------------------------------------------------------------------
# Streaming test
# ---------------------------------------------------------------------------

def test_streaming_response():
    client = _make_client()
    messages = [{"role": "user", "content": "Tell me a story"}]

    # When stream=True, the response object is returned directly (not .json()).
    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = [
        b'data: {"choices":[{"delta":{"content":"Once"}}]}',
        b'data: {"choices":[{"delta":{"content":" upon"}}]}',
        b"data: [DONE]",
    ]
    mock_resp.raise_for_status = MagicMock()
    client._session.post.return_value = mock_resp

    result = client.chat_completion(messages, stream=True)

    # The raw response object should be returned.
    assert result is mock_resp

    # stream=True must be passed through to requests.
    call_args = client._session.post.call_args
    assert call_args[1]["stream"] is True

    payload = call_args[1]["json"]
    assert payload["stream"] is True

    # Verify we can iterate the SSE lines.
    lines = list(result.iter_lines())
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# set_base_url test
# ---------------------------------------------------------------------------

def test_set_base_url():
    client = _make_client()

    assert client.base_url == "http://localhost:8080"

    client.set_base_url("http://10.0.0.1", 9090)

    assert client.base_url == "http://10.0.0.1:9090"
