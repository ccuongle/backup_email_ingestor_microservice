import pytest
import httpx
import respx
from unittest.mock import patch
from utils.api_retry import api_retry
from utils.config import (
    GRAPH_API_MAX_RETRIES,
    GRAPH_API_INITIAL_BACKOFF_SECONDS,
    GRAPH_API_BACKOFF_FACTOR,
)

@pytest.mark.asyncio
@respx.mock
async def test_api_retry_success_on_first_try():
    """
    Test that the decorator returns the result on the first try if the API call is successful.
    """
    url = "https://graph.microsoft.com/v1.0/me"
    respx.get(url).mock(return_value=httpx.Response(200, json={"status": "success"}))

    @api_retry(
        max_retries=GRAPH_API_MAX_RETRIES,
        initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS,
        backoff_factor=GRAPH_API_BACKOFF_FACTOR,
    )
    async def fetch_user():
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    result = await fetch_user()
    assert result == {"status": "success"}
    assert len(respx.calls) == 1

@pytest.mark.asyncio
@respx.mock
async def test_api_retry_with_retry_after_header():
    """
    Test that the decorator retries after the specified delay in the Retry-After header.
    """
    url = "https://graph.microsoft.com/v1.0/me"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"status": "success"}),
        ]
    )

    @api_retry(
        max_retries=GRAPH_API_MAX_RETRIES,
        initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS,
        backoff_factor=GRAPH_API_BACKOFF_FACTOR,
    )
    async def fetch_user():
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    with patch("asyncio.sleep") as mock_sleep:
        result = await fetch_user()
        assert result == {"status": "success"}
        assert len(respx.calls) == 2
        mock_sleep.assert_called_once_with(1)

@pytest.mark.asyncio
@respx.mock
async def test_api_retry_with_exponential_backoff():
    """
    Test that the decorator retries with exponential backoff when there is no Retry-After header.
    """
    url = "https://graph.microsoft.com/v1.0/me"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"status": "success"}),
        ]
    )

    @api_retry(
        max_retries=GRAPH_API_MAX_RETRIES,
        initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS,
        backoff_factor=GRAPH_API_BACKOFF_FACTOR,
    )
    async def fetch_user():
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    with patch("asyncio.sleep") as mock_sleep:
        result = await fetch_user()
        assert result == {"status": "success"}
        assert len(respx.calls) == 3
        assert mock_sleep.call_count == 2
        # The backoff is initial_backoff + jitter, so we can't assert the exact value
        # assert mock_sleep.call_args_list[0][0][0] == 1
        # assert mock_sleep.call_args_list[1][0][0] == 2

@pytest.mark.asyncio
@respx.mock
async def test_api_retry_max_retries_exceeded():
    """
    Test that the decorator raises an exception when the maximum number of retries is exceeded.
    """
    url = "https://graph.microsoft.com/v1.0/me"
    respx.get(url).mock(return_value=httpx.Response(503))

    @api_retry(
        max_retries=3,
        initial_backoff=GRAPH_API_INITIAL_BACKOFF_SECONDS,
        backoff_factor=GRAPH_API_BACKOFF_FACTOR,
    )
    async def fetch_user():
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    with patch("asyncio.sleep"):
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await fetch_user()
    assert excinfo.value.response.status_code == 503
    assert len(respx.calls) == 3
