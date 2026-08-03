from .files import (
    EditFilesTool,
    GitDiffTool,
    ListFilesTool,
    ReadFilesTool,
    SearchFilesTool,
    EditFileBlocksTool,
)
from .web_searching import WebSearchTool

TOOLS = (
    ReadFilesTool,
    ListFilesTool,
    SearchFilesTool,
    GitDiffTool,
    EditFilesTool,
    EditFileBlocksTool,
    WebSearchTool,
    # CreateFolderTool,
)

TOOLS_MAP = {
    tool.description.name: tool
    for tool in TOOLS
}
