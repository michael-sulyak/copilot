from .files import EditFilesTool, CreateFolderTool, GitDiffTool, ListFilesTool, ReadFilesTool, SearchFilesTool


TOOLS = (
    ReadFilesTool,
    ListFilesTool,
    SearchFilesTool,
    GitDiffTool,
    EditFilesTool,
    # CreateFolderTool,
)

TOOLS_MAP = {
    tool.description.name: tool
    for tool in TOOLS
}
