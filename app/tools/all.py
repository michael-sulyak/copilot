from .files import CreateFilesTool, CreateFolderTool, GitDiffTool, ListFilesTool, ReadFilesTool, SearchFilesTool


TOOLS = (
    ReadFilesTool,
    ListFilesTool,
    SearchFilesTool,
    GitDiffTool,
    CreateFilesTool,
    CreateFolderTool,
)

TOOLS_MAP = {
    tool.description.name: tool
    for tool in TOOLS
}
