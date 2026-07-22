import asyncio
import json

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command="uv",
    args=["run", "--directory", "/Users/mini/ai-usage-hub", "python", "-m", "server.mcp_server"],
)


def _run(coro):
    return asyncio.run(coro)


async def _call_tool(tool_name: str, arguments: dict | None = None):
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool_name, arguments or {})


async def _list_tools():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.list_tools()


@pytest.mark.e2e
def test_list_tools():
    result = _run(_list_tools())
    names = [t.name for t in result.tools]
    assert "get_all_usage" in names
    assert "get_recommendation" in names
    assert "get_reset_schedule" in names
    assert "should_consolidate" in names
    assert "get_forecast" in names
    assert "get_spend_today" in names
    assert "get_provider_usage" in names


@pytest.mark.e2e
def test_get_all_usage():
    result = _run(_call_tool("get_all_usage"))
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)


@pytest.mark.e2e
def test_get_recommendation():
    result = _run(_call_tool("get_recommendation"))
    data = json.loads(result.content[0].text)
    assert "action" in data


@pytest.mark.e2e
def test_get_reset_schedule():
    result = _run(_call_tool("get_reset_schedule"))
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)


@pytest.mark.e2e
def test_should_consolidate():
    result = _run(_call_tool("should_consolidate", {"session_minutes": 30}))
    data = json.loads(result.content[0].text)
    assert isinstance(data, dict)


@pytest.mark.e2e
def test_get_spend_today():
    result = _run(_call_tool("get_spend_today"))
    data = json.loads(result.content[0].text)
    assert "total_usd_today" in data


@pytest.mark.e2e
def test_get_forecast():
    result = _run(_call_tool("get_forecast"))
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)
