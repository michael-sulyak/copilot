import typing

from app.models.openai.base import BaseLLMTool


class WebSearchTool(BaseLLMTool):
    name = 'web_search'

    @staticmethod
    def dump() -> dict[str, typing.Any]:
        return {
            'type': 'web_search',
        }


TOOLS = (
    WebSearchTool,
)

TOOLS_MAP = {
    tool.name: tool for tool in TOOLS
}
