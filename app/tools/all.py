from .files import (
    EditFileBlocksTool,
    EditFilesTool,
    GitDiffTool,
    ListFilesTool,
    ReadFilesTool,
    SearchFilesTool,
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
