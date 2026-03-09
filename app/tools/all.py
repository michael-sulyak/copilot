from .files import (
    ApplyDiffsTool, EditFilesTool, GitDiffTool, ListFilesTool, ReadFilesTool,
    SearchFilesTool,
)


TOOLS = (
    ReadFilesTool,
    ListFilesTool,
    SearchFilesTool,
    GitDiffTool,
    EditFilesTool,
    ApplyDiffsTool,
    # CreateFolderTool,
)

TOOLS_MAP = {
    tool.description.name: tool
    for tool in TOOLS
}
