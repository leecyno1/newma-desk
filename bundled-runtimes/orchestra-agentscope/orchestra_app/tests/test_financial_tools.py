import asyncio

from orchestra_app.financial_tools import financial_function_tools
from agentscope.tool import Toolkit


def test_financial_tools_expose_read_only_data_channels() -> None:
    async def scenario() -> None:
        tools = financial_function_tools()
        expected = {
            "tushare_query",
            "a_stock_data",
            "global_stock_data",
            "tavily_search",
            "ima_knowledge_search",
        }
        assert {tool.name for tool in tools} == expected
        assert all(tool.is_read_only for tool in tools)
        schemas = await Toolkit(tools=tools).get_tool_schemas()
        assert {schema["function"]["name"] for schema in schemas} == expected

    asyncio.run(scenario())
