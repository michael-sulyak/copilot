from .files import (
    EditFileBlocksTool,
    EditFilesTool,
    GitDiffTool,
    ListFilesTool,
    ReadFilesTool,
    SearchFilesTool,
)
from .web_searching import WebSearchTool, AIWebSearchTool

TOOLS = (
    ReadFilesTool,
    ListFilesTool,
    SearchFilesTool,
    GitDiffTool,
    EditFilesTool,
    EditFileBlocksTool,
    WebSearchTool,
    AIWebSearchTool,
    # CreateFolderTool,
)

TOOLS_MAP = {
    tool.description.name: tool
    for tool in TOOLS
}
