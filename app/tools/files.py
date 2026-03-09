import abc
import dataclasses
import re
import subprocess
import typing
from pathlib import Path

from .additional_utils import fence_code, suggest_similar_paths
from .file_system import FileSystem
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
        self.fs = FileSystem(Path(work_dir).resolve())

    def run(self, *, paths: typing.Sequence[str]) -> str:
        candidates_cache: list[str] | None = None
        parts: list[str] = ['**Read files:**\n']

        for path_str in paths:
            parts.append('\n---\n')
            parts.append(f'`{path_str}`\n')

            try:
                content = self.fs.read_text(path_str, encoding='utf-8')
                parts.append(fence_code(content, lang=''))
                continue
            except FileNotFoundError:
                if candidates_cache is None:
                    # Suggest only allowed (non-ignored) files
                    candidates_cache = self.fs.list_files('.', recursive=True)

                suggestions = suggest_similar_paths(path_str, candidates_cache, limit=10)

                parts.append('**ERROR:** File not found.\n\n')
                parts.append(f'- Requested: `{path_str}`\n')
                if suggestions:
                    parts.append('\nDid you mean one of these?\n')
                    parts.extend(f'- `{s}`\n' for s in suggestions)
                    parts.append('\n')
                continue
            except IsADirectoryError:
                parts.append('**ERROR:** Path is a directory.\n\n')
                parts.append('Tip: use `list_files` for directories.\n')
                continue
            except PermissionError as e:
                parts.append('**ERROR:** Permission denied.\n\n')
                parts.append(f'- Error: `{e}`\n')
                continue
            except ValueError as e:
                parts.append('**ERROR:** Invalid path.\n\n')
                parts.append(f'- Error: `{e}`\n')
                continue
            except OSError as e:
                parts.append('**ERROR:** Failed to read file.\n\n')
                parts.append(f'- Error: `{e}`\n')
                continue

        return ''.join(parts).strip()


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
        self.fs = FileSystem(Path(work_dir).resolve())

    def run(self, *, path: str = '.', recursive: bool = False) -> str:
        try:
            files = self.fs.list_files(path, recursive=bool(recursive), include_dirs=True)
        except ValueError as e:
            return (
                '**ERROR:** Invalid path\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`\n'
            )
        except FileNotFoundError:
            return (
                '**ERROR:** Path not found\n\n'
                f'- Requested: `{path}`\n'
            )
        except NotADirectoryError:
            return (
                '**ERROR:** Not a directory\n\n'
                f'- Requested: `{path}`\n'
            )
        except OSError as e:
            return (
                '**ERROR:** Failed to list files\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`\n'
            )

        rel_dir = self.fs.to_rel_posix(self.fs.resolve(path))

        if not files:
            return f'Files in `{rel_dir}/`\n\nNo files found.\n'

        lines = '\n'.join(f'- `{f}`' for f in sorted(files))
        return f'Files in `{rel_dir}/`\n\n{lines}'


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
                    'Interpret queries as Python regular expressions to search by row. '
                    'You can use it also to search different words using one tool calling'
                ),
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.fs = FileSystem(Path(work_dir).resolve())

    def run(
        self,
        *,
        queries: typing.Sequence[str],
        path: str = '.',
        use_regex: bool = False,
    ) -> str:
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

        try:
            files = self.fs.list_files(path, recursive=True)
        except ValueError as e:
            return (
                '**ERROR:** Invalid path\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`\n'
            )
        except FileNotFoundError:
            return (
                '**ERROR:** Path not found\n\n'
                f'- Requested: `{path}`\n'
            )
        except NotADirectoryError:
            return (
                '**ERROR:** Not a directory\n\n'
                f'- Requested: `{path}`\n'
            )
        except OSError as e:
            return (
                '**ERROR:** Failed to search files\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`\n'
            )

        matches: list[str] = []
        for rel_file in files:
            try:
                text = self.fs.read_text(rel_file, encoding='utf-8')
            except (PermissionError, FileNotFoundError, IsADirectoryError, OSError):
                # If something changes during traversal or is blocked, skip it.
                continue

            for i, line in enumerate(text.splitlines(), start=1):
                for query, pattern in zip(queries, patterns):
                    found = pattern.search(line) if use_regex else (pattern in line)
                    if found:
                        matches.append(f'{rel_file}:{i}: [{query}] {line.strip()}')
                        break

                if len(matches) >= 500:
                    break

            if len(matches) >= 500:
                break

        rel_dir = self.fs.to_rel_posix(self.fs.resolve(path))

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
                ['git', 'diff', 'origin/master'],  # TODO: Add check that the branch updated
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


class EditFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='edit_files',
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
        self.fs = FileSystem(Path(work_dir).resolve())

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
                self.fs.write_text(
                    path,
                    content or '',
                    overwrite=bool(overwrite),
                    encoding=encoding,
                )
                size = len((content or '').encode(encoding, errors='ignore'))
                results.append(f'- `{path}`: written {size} bytes')
                written += 1

            except FileExistsError:
                results.append(f'- `{path}`: already exists (overwrite=false)')
            except PermissionError as e:
                results.append(f'- `{path}`: permission denied ({e})')
            except ValueError as e:
                results.append(f'- `{path}`: invalid path ({e})')
            except OSError as e:
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
        self.fs = FileSystem(Path(work_dir).resolve())

    def run(self, *, path: str, parents: bool = True, exist_ok: bool = True) -> str:
        try:
            folder_path = self.fs.mkdir(path, parents=bool(parents), exist_ok=bool(exist_ok))
            rel = self.fs.to_rel_posix(folder_path)
            return (
                'Folder created\n\n'
                f'- Path: `{rel}/`'
            )
        except PermissionError as e:
            return (
                '**ERROR:** Permission denied\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`'
            )
        except ValueError as e:
            return (
                '**ERROR:** Invalid path\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`'
            )
        except FileExistsError as e:
            return (
                '**ERROR:** Cannot create folder\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`'
            )
        except OSError as e:
            return (
                '**ERROR:** Failed to create folder\n\n'
                f'- Requested: `{path}`\n'
                f'- Error: `{e}`'
            )


class ApplyDiffsTool(BaseLLMToolFabric):
    class PatchApplyError(RuntimeError):
        pass

    _UNIFIED_HUNK_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

    description = FunctionLLMTool(
        name='apply_diffs',
        description=(
            'Apply unified diffs (patches) to existing text files inside the provided folder.\n\n'
            'Input format:\n'
            '- Provide `edits` as a list of objects: `{ "path": "...", "diff": "..." }`.\n'
            '- Each `diff` must be a *single-file* unified diff containing one or more hunks with `@@` headers.\n'
            '- Diff headers like `diff --git`, `index`, `---`, `+++` are allowed and ignored.\n\n'
            'Behavior:\n'
            '- The tool reads the current file content, applies hunks with strict context matching, then overwrites the file.\n'
            '- If the file does not exist or the patch does not apply cleanly, the tool returns an error for that item.\n'
            '- Paths are restricted by the sandbox FileSystem (ignored/protected paths are blocked).\n'
        ),
        parameters=(
            LLMToolParam(
                name='edits',
                type=LLMToolParamTypes.ARRAY,
                items=LLMToolParams(
                    parameters=(
                        LLMToolParam(
                            name='path',
                            type=LLMToolParamTypes.STRING,
                            description='Target file path relative to base folder (must already exist)',
                            required=True,
                        ),
                        LLMToolParam(
                            name='diff',
                            type=LLMToolParamTypes.STRING,
                            description='Unified diff for that file (must contain @@ hunk headers)',
                            required=True,
                        ),
                    )
                ),
                description='List of patch operations: each item contains `path` and `diff`',
                required=True,
            ),
            LLMToolParam(
                name='encoding',
                type=LLMToolParamTypes.STRING,
                description='Text encoding for reading/writing (default: utf-8)',
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.fs = FileSystem(Path(work_dir).resolve())

    def _detect_eol(self, text: str) -> str:
        return '\r\n' if '\r\n' in (text or '') else '\n'

    def _apply_unified_diff_to_text(self, original: str, diff_text: str) -> str:
        if diff_text is None:
            raise self.PatchApplyError('Diff is empty')

        diff_lines = (diff_text or '').splitlines()
        if not diff_lines:
            raise self.PatchApplyError('Diff is empty')

        eol = self._detect_eol(original)
        orig_lines = (original or '').splitlines()

        out: list[str] = []
        idx = 0

        in_hunk = False
        hunk_seen = False

        expected_old_count: int | None = None
        expected_new_count: int | None = None
        seen_old = 0
        seen_new = 0

        def finish_hunk_if_any() -> None:
            nonlocal expected_old_count, expected_new_count, seen_old, seen_new, in_hunk
            if not in_hunk:
                return

            if expected_old_count is not None and seen_old != expected_old_count:
                raise self.PatchApplyError(
                    f'Hunk old-count mismatch: expected {expected_old_count}, saw {seen_old}'
                )
            if expected_new_count is not None and seen_new != expected_new_count:
                raise self.PatchApplyError(
                    f'Hunk new-count mismatch: expected {expected_new_count}, saw {seen_new}'
                )

            expected_old_count = None
            expected_new_count = None
            seen_old = 0
            seen_new = 0
            in_hunk = False

        for line in diff_lines:
            m = self._UNIFIED_HUNK_RE.match(line)
            if m:
                finish_hunk_if_any()

                hunk_seen = True
                in_hunk = True

                old_start = int(m.group(1))
                old_count = int(m.group(2) or '1')
                new_count = int(m.group(4) or '1')

                expected_old_count = old_count
                expected_new_count = new_count
                seen_old = 0
                seen_new = 0

                target = max(0, old_start - 1)

                if target < idx:
                    raise self.PatchApplyError(
                        f'Hunk applies before current position: target={target} idx={idx}'
                    )
                if target > len(orig_lines):
                    raise self.PatchApplyError(
                        f'Hunk start beyond end of file: target={target} file_lines={len(orig_lines)}'
                    )

                out.extend(orig_lines[idx:target])
                idx = target
                continue

            if not in_hunk:
                if (
                    line.startswith('diff ')
                    or line.startswith('index ')
                    or line.startswith('--- ')
                    or line.startswith('+++ ')
                ):
                    continue
                continue

            if not line:
                raise self.PatchApplyError('Invalid diff: empty line inside hunk')

            op = line[0]
            payload = line[1:]

            if op == ' ':
                if idx >= len(orig_lines):
                    raise self.PatchApplyError(
                        f'Context line beyond EOF at original index {idx}: {payload!r}'
                    )
                if orig_lines[idx] != payload:
                    raise self.PatchApplyError(
                        'Context mismatch\n'
                        f'- At original line: {idx + 1}\n'
                        f'- Expected: {payload!r}\n'
                        f'- Found:    {orig_lines[idx]!r}\n'
                    )
                out.append(payload)
                idx += 1
                seen_old += 1
                seen_new += 1

            elif op == '-':
                if idx >= len(orig_lines):
                    raise self.PatchApplyError(
                        f'Removal beyond EOF at original index {idx}: {payload!r}'
                    )
                if orig_lines[idx] != payload:
                    raise self.PatchApplyError(
                        'Removal mismatch\n'
                        f'- At original line: {idx + 1}\n'
                        f'- Expected remove: {payload!r}\n'
                        f'- Found:           {orig_lines[idx]!r}\n'
                    )
                idx += 1
                seen_old += 1

            elif op == '+':
                out.append(payload)
                seen_new += 1

            elif op == '\\':
                continue

            else:
                raise self.PatchApplyError(f'Invalid hunk operation {op!r} in line: {line!r}')

        finish_hunk_if_any()

        if not hunk_seen:
            raise self.PatchApplyError('No hunks found in diff (missing @@ -a,b +c,d @@ headers)')

        out.extend(orig_lines[idx:])

        had_trailing_newline = (original or '').endswith('\n') or (original or '').endswith('\r\n')
        new_text = eol.join(out)
        if had_trailing_newline and (new_text != '' or (original or '') != ''):
            new_text += eol

        return new_text

    def run(
        self,
        *,
        edits: typing.Sequence[dict],
        encoding: str = 'utf-8',
    ) -> str:
        if not edits:
            return '**ERROR:** `edits` list is empty'

        results: list[str] = []
        patched = 0

        for i, spec in enumerate(edits, start=1):
            path = (spec or {}).get('path')
            diff = (spec or {}).get('diff')

            if not path:
                results.append(f'- Item {i}: missing `path`')
                continue
            if diff is None:
                results.append(f'- `{path}`: missing `diff`')
                continue
            if path.endswith(('/', '\\')):
                results.append(f'- `{path}`: looks like a folder, not a file')
                continue

            try:
                abs_p = self.fs.resolve(path)
                rel = self.fs.to_rel_posix(abs_p)
                self.fs.assert_allowed(rel, is_dir=False, for_write=True)

                original = self.fs.read_text(path, encoding=encoding)
                new_text = self._apply_unified_diff_to_text(original, diff)

                self.fs.write_text(path, new_text, overwrite=True, encoding=encoding)
                size = len(new_text.encode(encoding, errors='ignore'))
                results.append(f'- `{path}`: patched and written {size} bytes')
                patched += 1

            except FileNotFoundError:
                results.append(f'- `{path}`: not found (file must exist)')
            except self.PatchApplyError as e:
                results.append(f'- `{path}`: patch failed ({e})')
            except PermissionError as e:
                results.append(f'- `{path}`: permission denied ({e})')
            except ValueError as e:
                results.append(f'- `{path}`: invalid path ({e})')
            except OSError as e:
                results.append(f'- `{path}`: write failed ({e})')
            except Exception as e:
                results.append(f'- `{path}`: unexpected error ({e})')

        return (
            'Apply diffs result:\n\n'
            f'- Edits requested: {len(edits)}\n'
            f'- Edits applied: {patched}\n\n'
            + '\n'.join(results)
        )
