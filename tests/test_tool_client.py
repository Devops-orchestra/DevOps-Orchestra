"""HTTP tool client: mocked network, no live tool server."""

from unittest.mock import MagicMock, patch

from shared_modules.pipeline import tool_client


def test_call_tool_returns_json_on_success() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "ok", "output": {"path": "/tmp/r"}}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(tool_client.httpx, "post", return_value=mock_resp) as post:
        out = tool_client.call_tool("clone", {"repo": "https://github.com/a/b.git"})

    post.assert_called_once()
    assert out["status"] == "ok"
    assert out["output"]["path"] == "/tmp/r"


def test_call_tool_returns_error_dict_on_http_failure() -> None:
    with patch.object(tool_client.httpx, "post", side_effect=ConnectionError("connection refused")):
        out = tool_client.call_tool("clone", {})

    assert out["status"] == "error"
    assert "message" in out["output"]
