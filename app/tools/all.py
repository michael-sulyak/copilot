from .files import (
    EditFilesTool,
    GitDiffTool,
    ListFilesTool,
    ReadFilesTool,
    SearchFilesTool,
    EditFileBlocksTool,
)


TOOLS = (
    ReadFilesTool,
    ListFilesTool,
    SearchFilesTool,
    GitDiffTool,
    EditFilesTool,
    EditFileBlocksTool,
    # CreateFolderTool,
)

TOOLS_MAP = {
    tool.description.name: tool
    for tool in TOOLS
}
