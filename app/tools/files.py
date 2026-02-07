import abc
import dataclasses
import re
import subprocess
import typing
from pathlib import Path

from .additional_utils import (
    fence_code, iter_all_files, list_dir_entries_md, nearest_existing_dir, resolve_path, suggest_similar_paths,
)
from ..models.openai.base import FunctionLLMTool, LLMToolCall, LLMToolParam, LLMToolParams
from ..models.openai.constants import LLMToolParamTypes


class BaseLLMToolFabric(abc.ABC):
    description: typing.ClassVar[FunctionLLMTool]

    @abc.abstractmethod
    def run(self, *args, **kwargs) -> str:
        """
        Tool executor used by the LLM loop.
        NOTE: BaseLLM.execute calls tool.func(call), so we accept LLMToolCall here.
        """
        pass

    def describe(self) -> FunctionLLMTool:
        params = {
            field.name: getattr(self.description, field.name)
            for field in dataclasses.fields(self.description)
        }

        def wrapper(call: LLMToolCall) -> str:
            try:
                return self.run(**(call.args or {}))
            except TypeError as e:
                return (
                    '**ERROR:** Invalid tool arguments\n\n'
                    f'- Tool: `{self.description.name}`\n'
                    f'- Provided args: `{call.args}`\n'
                    f'- Error: `{e}`\n'
                )
            except Exception as e:
                return (
                    '**ERROR:** Tool execution failed\n\n'
                    f'- Tool: `{self.description.name}`\n'
                    f'- Provided args: `{call.args}`\n'
                    f'- Error: `{e}`\n'
                )

        params['func'] = wrapper
        return FunctionLLMTool(**params)


class ReadFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='read_files',
        description='Read one or more files by relative path inside the provided folder',
        parameters=(
            LLMToolParam(
                name='paths',
                type=LLMToolParamTypes.ARRAY,
                items=LLMToolParams(type=LLMToolParamTypes.STRING),
                description='List of relative file paths',
                required=True,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(self, *, paths: typing.Sequence[str]) -> str:
        all_files_cache: list[str] | None = None
        parts: list[str] = ['**Read files:**\n']

        for path_str in paths:
            parts.append(f'---\n')
            parts.append(f'`{path_str}`\n')

            try:
                target = resolve_path(self.work_dir, path_str)
            except Exception as e:
                parts.append(
                    '**ERROR:** Invalid path.\n\n'
                    f'- Requested: `{path_str}`\n'
                    f'- Error: `{e}`\n'
                )
                continue

            if target.exists() and target.is_dir():
                rel_dir = target.relative_to(self.work_dir).as_posix()
                parts.append(f'**ERROR:** Path is a directory: `{rel_dir}/`\n\n')
                parts.append(list_dir_entries_md(target, self.work_dir) + '\n')
                parts.append('Tip: use `list_files` for directories.\n')
                continue

            if not target.exists():
                if all_files_cache is None:
                    all_files_cache = iter_all_files(self.work_dir)

                suggestions = suggest_similar_paths(path_str, all_files_cache, limit=10)

                parts.append('**ERROR:** File not found.\n\n')
                parts.append(f'- Requested: `{path_str}`\n')

                if suggestions:
                    parts.append('\nDid you mean one of these?\n')
                    parts.extend(f'- `{s}`\n' for s in suggestions)
                    parts.append('\n')
                else:
                    requested_parent = resolve_path(self.work_dir, str(Path(path_str).parent or '.'))
                    nearest_dir = nearest_existing_dir(requested_parent, self.work_dir)
                    listing = list_dir_entries_md(nearest_dir, self.work_dir, limit=50)
                    if listing:
                        parts.append('\n' + listing + '\n')
                    else:
                        parts.append('\nNo files found to suggest.\n')

                continue

            if not target.is_file():
                parts.append('**ERROR:** Path exists but is not a regular file.\n\n')
                continue

            try:
                content = target.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                parts.append(
                    '**ERROR:** Failed to read file.\n\n'
                    f'- Error: `{e}`\n'
                )
                continue

            # rel = target.relative_to(self.work_dir).as_posix()
            # parts.append(f'Path: `{rel}`\n\n')
            parts.append(fence_code(content, lang='') + '\n')

        return ''.join(parts).strip() + '\n'


class ListFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='list_files',
        description='List files in a directory inside the provided folder',
        parameters=(
            LLMToolParam(
                name='path',
                type=LLMToolParamTypes.STRING,
                description='Directory path relative to base folder (default: root)',
                required=False,
            ),
            LLMToolParam(
                name='recursive',
                type=LLMToolParamTypes.BOOLEAN,
                description='Recursively list files',
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(self, *, path: str = '.', recursive: bool = False) -> str:
        try:
            target = resolve_path(self.work_dir, path)
        except Exception as e:
            return (
                '**ERROR:** Invalid path\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`\n'
            )

        if not target.exists():
            return (
                '**ERROR:** Path not found\n\n'
                f'- Requested: `{path}`\n'
            )

        if not target.is_dir():
            rel = target.relative_to(self.work_dir).as_posix()
            return (
                '**ERROR:** Not a directory\n\n'
                f'- Requested: `{path}`\n'
                f'- Resolved: `{rel}`\n'
            )

        if recursive:
            files = [
                p.relative_to(self.work_dir).as_posix()
                for p in target.rglob('*')
                if p.is_file()
            ]
        else:
            files = [
                p.relative_to(self.work_dir).as_posix()
                for p in target.iterdir()
                if p.is_file()
            ]

        rel_dir = target.relative_to(self.work_dir).as_posix()
        if not files:
            return f'Files in `{rel_dir}/`\n\nNo files found.\n'

        lines = '\n'.join(f'- `{f}`' for f in sorted(files))
        return f'Files in `{rel_dir}/`\n\n{lines}\n'


class SearchFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='search_files',
        description='Search text across files inside the provided folder',
        parameters=(
            LLMToolParam(
                name='queries',
                type=LLMToolParamTypes.ARRAY,
                items=LLMToolParams(type=LLMToolParamTypes.STRING),
                description='List of search queries or regex patterns',
                required=True,
            ),
            LLMToolParam(
                name='path',
                type=LLMToolParamTypes.STRING,
                description='Directory path relative to base folder',
                required=False,
            ),
            LLMToolParam(
                name='use_regex',
                type=LLMToolParamTypes.BOOLEAN,
                description=(
                    'Interpret queries as Python regular expressions. '
                    'You can use it also to search different words using one tool calling'
                ),
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(
        self,
        *,
        queries: typing.Sequence[str],
        path: str = '.',
        use_regex: bool = False,
    ) -> str:
        try:
            target = resolve_path(self.work_dir, path)
        except Exception as e:
            return (
                '**ERROR:** Invalid path\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`\n'
            )

        if not target.exists():
            return (
                '**ERROR:** Path not found\n\n'
                f'- Requested: `{path}`\n'
            )

        if not target.is_dir():
            rel = target.relative_to(self.work_dir).as_posix()
            return (
                '**ERROR:** Not a directory\n\n'
                f'- Requested: `{path}`\n'
                f'- Resolved: `{rel}`\n'
            )

        if not queries:
            return '**ERROR:** No queries provided\n'

        # Prepare search patterns
        patterns: list[typing.Any] = []
        if use_regex:
            for q in queries:
                try:
                    patterns.append(re.compile(q))
                except re.error as e:
                    return (
                        '**ERROR:** Invalid regular expression\n\n'
                        f'- Pattern: `{q}`\n'
                        f'- Error: `{e}`\n'
                    )
        else:
            patterns = list(queries)

        matches: list[str] = []

        for file in target.rglob('*'):
            if not file.is_file():
                continue

            try:
                text = file.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            rel_file = file.relative_to(self.work_dir).as_posix()

            for i, line in enumerate(text.splitlines(), start=1):
                for query, pattern in zip(queries, patterns):
                    found = (
                        pattern.search(line)
                        if use_regex
                        else pattern in line
                    )

                    if found:
                        matches.append(
                            f'{rel_file}:{i}: [{query}] {line.strip()}'
                        )
                        break

                if len(matches) >= 500:
                    break

            if len(matches) >= 500:
                break

        rel_dir = target.relative_to(self.work_dir).as_posix()

        if not matches:
            return (
                'Search results\n\n'
                f'- Queries: `{list(queries)}`\n'
                f'- Path: `{rel_dir}/`\n\n'
                'No matches found.\n'
            )

        return (
            'Search results\n\n'
            f'- Queries: `{list(queries)}`\n'
            f'- Path: `{rel_dir}/`\n\n'
            + fence_code('\n'.join(matches), lang='') + '\n'
        )


class GitDiffTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='git_diff',
        description='Show git diff for the provided folder',
        parameters=(),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(self) -> str:
        try:
            diff = subprocess.check_output(
                ['git', 'diff', 'origin/master'],
                # ['git', 'diff', '--cached'],
                cwd=self.work_dir,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            return (
                'ERROR: git diff failed\n\n'
                f'- Error: `{e}`\n'
            )

        if not diff.strip():
            return 'No diff.'

        return f'Git diff\n\n{fence_code(diff, lang="diff")}\n'


class CreateFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='create_files',
        description=(
            'Create or overwrite multiple text files inside the provided folder. '
            'Creates parent folders if needed.'
        ),
        parameters=(
            LLMToolParam(
                name='files',
                type=LLMToolParamTypes.ARRAY,
                items=LLMToolParams(
                    parameters=(
                        LLMToolParam(
                            name='path',
                            type=LLMToolParamTypes.STRING,
                            description='Single file path relative to base folder',
                            required=True,
                        ),
                        LLMToolParam(
                            name='content',
                            type=LLMToolParamTypes.STRING,
                            description='Single file content (default: empty)',
                            required=True,
                        ),
                    ),
                ),
                description=(
                    'List of files to create. '
                    'Each item must contain `path` and optional `content`.'
                ),
                required=True,
            ),
            LLMToolParam(
                name='overwrite',
                type=LLMToolParamTypes.BOOLEAN,
                description='Overwrite files if they already exist (default: false)',
                required=False,
            ),
            LLMToolParam(
                name='encoding',
                type=LLMToolParamTypes.STRING,
                description='Text encoding (default: utf-8)',
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(
        self,
        *,
        files: typing.Sequence[dict],
        overwrite: bool = False,
        encoding: str = 'utf-8',
    ) -> str:
        if not files:
            return '**ERROR:** `files` list is empty'

        results: list[str] = []
        written = 0

        for i, spec in enumerate(files, start=1):
            path = spec.get('path')
            content = spec.get('content', '')

            if not path:
                results.append(f'- Item {i}: missing `path`')
                continue

            if path.endswith(('/', '\\')):
                results.append(f'- `{path}`: looks like a folder, not a file')
                continue

            try:
                file_path = resolve_path(self.work_dir, path)
            except Exception as e:
                results.append(f'- `{path}`: invalid path ({e})')
                continue

            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                results.append(f'- `{path}`: failed to create parent folders ({e})')
                continue

            if file_path.exists() and not overwrite:
                rel = file_path.relative_to(self.work_dir).as_posix()
                results.append(f'- `{rel}`: already exists (overwrite=false)')
                continue

            try:
                file_path.write_text(content or '', encoding=encoding, errors='strict')
                size = len((content or '').encode(encoding, errors='ignore'))
                rel = file_path.relative_to(self.work_dir).as_posix()
                results.append(f'- `{rel}`: written {size} bytes')
                written += 1
            except Exception as e:
                results.append(f'- `{path}`: write failed ({e})')

        return (
            'File creation result:\n\n'
            f'- Files requested: {len(files)}\n'
            f'- Files written: {written}\n\n'
            + '\n'.join(results)
        )


class CreateFolderTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='create_folder',
        description='Create a folder inside the provided base folder',
        parameters=(
            LLMToolParam(
                name='path',
                type=LLMToolParamTypes.STRING,
                description='Folder path relative to base folder',
                required=True,
            ),
            LLMToolParam(
                name='parents',
                type=LLMToolParamTypes.BOOLEAN,
                description='Create parent folders if needed (default: true)',
                required=False,
            ),
            LLMToolParam(
                name='exist_ok',
                type=LLMToolParamTypes.BOOLEAN,
                description='Do not error if folder already exists (default: true)',
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(self, *, path: str, parents: bool = True, exist_ok: bool = True) -> str:
        try:
            folder_path = resolve_path(self.work_dir, path)
        except Exception as e:
            return (
                '**ERROR:** Invalid path\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`'
            )

        if folder_path.exists() and folder_path.is_file():
            rel = folder_path.relative_to(self.work_dir).as_posix()
            return (
                '**ERROR:** Cannot create folder because a file exists at that path\n\n'
                f'- Path: `{rel}`'
            )

        try:
            folder_path.mkdir(parents=parents, exist_ok=exist_ok)
        except Exception as e:
            rel = folder_path.relative_to(self.work_dir).as_posix()
            return (
                '**ERROR:** Failed to create folder\n\n'
                f'- Folder: `{rel}/`\n'
                f'- Error: `{e}`'
            )

        rel = folder_path.relative_to(self.work_dir).as_posix()
        return (
            'Folder created\n\n'
            f'- Path: `{rel}/`'
        )
