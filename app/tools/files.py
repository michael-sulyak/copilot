import abc
import dataclasses
import re
import subprocess
import typing
from pathlib import Path

from .additional_utils import gen_tool_error, suggest_similar_paths
from .file_system import FileSystem
from ..models.openai.base import FunctionLLMTool, LLMFunctionCall, LLMToolParam, LLMToolParams
from ..models.openai.constants import LLMToolParamTypes
from ..utils.common import gen_optimized_json


class BaseLLMToolFabric(abc.ABC):
    description: typing.ClassVar[FunctionLLMTool]

    @abc.abstractmethod
    def run(self, *args, **kwargs) -> str:
        """
        Tool executor used by the LLM loop.
        NOTE: BaseLLM.execute calls tool.func(call), so we accept LLMToolCall here.
        """

    def describe(self) -> FunctionLLMTool:
        params = {
            field.name: getattr(self.description, field.name)
            for field in dataclasses.fields(self.description)
        }

        def wrapper(call: LLMFunctionCall) -> str:
            try:
                return self.run(**(call.args or {}))
            except TypeError as e:
                return gen_tool_error(
                    tool=self.description.name,
                    error_type='InvalidArguments',
                    message=str(e),
                    provided_args=call.args or {},
                )
            except Exception as e:
                return gen_tool_error(
                    tool=self.description.name,
                    error_type='ToolExecutionFailed',
                    message=str(e),
                    provided_args=call.args or {},
                )

        params['func'] = wrapper
        return FunctionLLMTool(**params)


class ReadFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='read_files',
        showed_name='📄 File reading',
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
        if isinstance(paths, (str, bytes)) or paths is None:
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='`paths` must be an array of strings',
                provided_paths=paths,
            )

        candidates_cache: list[str] | None = None
        results: list[dict[str, typing.Any]] = []
        read_count = 0

        for path_str in paths:
            item: dict[str, typing.Any] = {'path': path_str}
            try:
                content = self.fs.read_text(path_str, encoding='utf-8')
                item.update(
                    {
                        'status': 'ok',
                        'content': content,
                        'bytes': len(content.encode('utf-8', errors='ignore')),
                    },
                )
                read_count += 1

            except FileNotFoundError:
                if candidates_cache is None:
                    # Suggest only allowed non-ignored files.
                    candidates_cache = self.fs.list_files('.', recursive=True)

                suggestions = suggest_similar_paths(path_str, candidates_cache, limit=10)
                item.update(
                    {
                        'status': 'error',
                        'error': {
                            'type': 'FileNotFound',
                            'message': f'File not found: {path_str}',
                        },
                        'suggestions': suggestions,
                    },
                )

            except IsADirectoryError:
                item.update(
                    {
                        'status': 'error',
                        'error': {
                            'type': 'IsDirectory',
                            'message': 'Path is a directory. Use list_files for directories.',
                        },
                    },
                )

            except PermissionError as e:
                item.update(
                    {
                        'status': 'error',
                        'error': {
                            'type': 'PermissionDenied',
                            'message': str(e),
                        },
                    },
                )

            except ValueError as e:
                item.update(
                    {
                        'status': 'error',
                        'error': {
                            'type': 'InvalidPath',
                            'message': str(e),
                        },
                    },
                )

            except OSError as e:
                item.update(
                    {
                        'status': 'error',
                        'error': {
                            'type': 'ReadFailed',
                            'message': str(e),
                        },
                    },
                )

            results.append(item)

        error_count = sum(1 for item in results if item.get('status') != 'ok')
        return gen_optimized_json(
            {
                'ok': error_count == 0,
                'tool': self.description.name,
                'results': results,
                'summary': {
                    'requested': len(list(paths)),
                    'read': read_count,
                    'errors': error_count,
                },
            },
        )


class ListFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='list_files',
        showed_name='📋 File listing',
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
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidPath',
                message=str(e),
                path=path,
            )
        except FileNotFoundError:
            return gen_tool_error(
                tool=self.description.name,
                error_type='PathNotFound',
                message=f'Path not found: {path}',
                path=path,
            )
        except NotADirectoryError:
            return gen_tool_error(
                tool=self.description.name,
                error_type='NotADirectory',
                message=f'Not a directory: {path}',
                path=path,
            )
        except OSError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='ListFailed',
                message=str(e),
                path=path,
            )

        rel_dir = self.fs.to_rel_posix(self.fs.resolve(path))
        return gen_optimized_json(
            {
                'ok': True,
                'tool': self.description.name,
                'path': rel_dir,
                'recursive': bool(recursive),
                'entries': sorted(files),
                'count': len(files),
            },
        )


class SearchFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='search_files',
        showed_name='🔎 File search',
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
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='No queries provided',
            )

        # Prepare search patterns
        patterns: list[typing.Any] = []
        if use_regex:
            for q in queries:
                try:
                    patterns.append(re.compile(q))
                except re.error as e:
                    return gen_tool_error(
                        tool=self.description.name,
                        error_type='InvalidRegex',
                        message=str(e),
                        pattern=q,
                    )
        else:
            patterns = list(queries)

        try:
            files = self.fs.list_files(path, recursive=True)
        except ValueError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidPath',
                message=str(e),
                path=path,
            )
        except FileNotFoundError:
            return gen_tool_error(
                tool=self.description.name,
                error_type='PathNotFound',
                message=f'Path not found: {path}',
                path=path,
            )
        except NotADirectoryError:
            return gen_tool_error(
                tool=self.description.name,
                error_type='NotADirectory',
                message=f'Not a directory: {path}',
                path=path,
            )
        except OSError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='SearchFailed',
                message=str(e),
                path=path,
            )

        matches: list[dict[str, typing.Any]] = []
        truncated = False

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
                        matches.append(
                            {
                                'path': rel_file,
                                'line': i,
                                'query': query,
                                'text': line.strip(),
                            },
                        )
                        break

                if len(matches) >= 500:
                    truncated = True
                    break

            if len(matches) >= 500:
                truncated = True
                break

        rel_dir = self.fs.to_rel_posix(self.fs.resolve(path))
        return gen_optimized_json(
            {
                'ok': True,
                'tool': self.description.name,
                'queries': list(queries),
                'path': rel_dir,
                'use_regex': bool(use_regex),
                'matches': matches,
                'count': len(matches),
                'truncated': truncated,
                'max_matches': 500,
            },
        )


class GitDiffTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='git_diff',
        showed_name='📑 GIT diff',
        description='Show git diff for the provided folder',
        parameters=(),
    )

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir).resolve()

    def run(self) -> str:
        try:
            proc = subprocess.run(
                ['git', 'diff', 'origin/master'],  # TODO: Add check that the branch updated
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='ExecutionFailed',
                message=str(e),
            )

        if proc.returncode != 0:
            return gen_tool_error(
                tool=self.description.name,
                error_type='GitDiffFailed',
                message=(proc.stderr or proc.stdout or '').strip() or f'Exit code: {proc.returncode}',
                exit_code=proc.returncode,
            )

        diff = proc.stdout or ''
        return gen_optimized_json(
            {
                'ok': True,
                'tool': self.description.name,
                'has_diff': bool(diff.strip()),
                'diff': diff,
            },
        )


class EditFilesTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='edit_files',
        showed_name='📝 File editing',
        description=(
            'Create or overwrite multiple text files inside the provided folder. '
            'Creates parent folders if needed. '
            'For efficient partial edits, prefer the edit_file_blocks tool.'
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
                            description='Single file content',
                            required=True,
                        ),
                    ),
                ),
                description='List of files to create or overwrite.',
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
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='`files` list is empty',
            )

        if isinstance(files, (str, bytes)):
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='`files` must be an array of objects',
            )

        results: list[dict[str, typing.Any]] = []
        written = 0

        for i, spec in enumerate(files, start=1):
            if not isinstance(spec, dict):
                results.append(
                    {
                        'index': i,
                        'status': 'error',
                        'error': {
                            'type': 'InvalidItem',
                            'message': 'Item must be an object with `path` and `content`',
                        },
                    },
                )
                continue

            path = spec.get('path')
            content = spec.get('content', '')

            if not path:
                results.append(
                    {
                        'index': i,
                        'status': 'error',
                        'error': {
                            'type': 'MissingPath',
                            'message': 'Missing `path`',
                        },
                    },
                )
                continue

            if not isinstance(content, str):
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'InvalidContent',
                            'message': '`content` must be a string',
                        },
                    },
                )
                continue

            if path.endswith(('/', '\\')):
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'InvalidPath',
                            'message': 'Path looks like a folder, not a file',
                        },
                    },
                )
                continue

            try:
                self.fs.write_text(
                    path,
                    content,
                    overwrite=bool(overwrite),
                    encoding=encoding,
                )
                size = len(content.encode(encoding))
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'written',
                        'bytes': size,
                    },
                )
                written += 1

            except FileExistsError:
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'AlreadyExists',
                            'message': 'File already exists and overwrite is false',
                        },
                    },
                )
            except UnicodeEncodeError as e:
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'EncodingError',
                            'message': str(e),
                        },
                    },
                )
            except LookupError as e:
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'InvalidEncoding',
                            'message': str(e),
                        },
                    },
                )
            except PermissionError as e:
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'PermissionDenied',
                            'message': str(e),
                        },
                    },
                )
            except ValueError as e:
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'InvalidPath',
                            'message': str(e),
                        },
                    },
                )
            except OSError as e:
                results.append(
                    {
                        'index': i,
                        'path': path,
                        'status': 'error',
                        'error': {
                            'type': 'WriteFailed',
                            'message': str(e),
                        },
                    },
                )

        error_count = sum(1 for r in results if r.get('status') != 'written')
        return gen_optimized_json(
            {
                'ok': error_count == 0,
                'tool': self.description.name,
                'summary': {
                    'requested': len(files),
                    'written': written,
                    'errors': error_count,
                },
                'results': results,
            },
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
            rel = self.fs.to_rel_posix(folder_path).rstrip('/') + '/'
            return gen_optimized_json(
                {
                    'ok': True,
                    'tool': self.description.name,
                    'path': rel,
                },
            )
        except PermissionError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='PermissionDenied',
                message=str(e),
                path=path,
            )
        except ValueError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidPath',
                message=str(e),
                path=path,
            )
        except FileExistsError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='AlreadyExists',
                message=str(e),
                path=path,
            )
        except OSError as e:
            return gen_tool_error(
                tool=self.description.name,
                error_type='CreateFolderFailed',
                message=str(e),
                path=path,
            )


class EditFileBlocksTool(BaseLLMToolFabric):
    class EditApplyError(RuntimeError):
        def __init__(self, error_type: str, message: str) -> None:
            super().__init__(message)
            self.error_type = error_type
            self.message = message

    _OP_ENUM = (
        'create',
        'overwrite',
        'replace',
        'delete',
        'insert_before',
        'insert_after',
        'replace_between',
        'append',
        'prepend',
    )

    description = FunctionLLMTool(
        name='edit_file_blocks',
        showed_name='✏️ File block editing',
        description=(
            'Efficiently edit text files without sending whole file contents.\n\n'
            'Use structured operations for deterministic edits:\n'
            '- create: create a new file with full `content`\n'
            '- overwrite: overwrite or create a file with full `content`\n'
            '- replace: replace exact `old` text with `new`\n'
            '- delete: delete exact `old` text\n'
            '- insert_before: insert `text` before exact `anchor`\n'
            '- insert_after: insert `text` after exact `anchor`\n'
            '- replace_between: replace text between `start` and `end` markers with `new`\n'
            '- append: append `text` to an existing file\n'
            '- prepend: prepend `text` to an existing file\n\n'
            'Important rules for LLMs:\n'
            '- Prefer `replace` with exact old text copied from read_files output.\n'
            '- Use `expected_replacements` or `expected_anchors` to prevent accidental broad edits.\n'
            '- If an anchor is not unique, read more context and use a larger exact block.\n'
            '- The tool validates all edits first. If one edit fails, no files are written.'
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
                            description='Target file path relative to base folder',
                            required=True,
                        ),
                        LLMToolParam(
                            name='op',
                            type=LLMToolParamTypes.STRING,
                            enum=_OP_ENUM,
                            description='Operation to perform',
                            required=True,
                        ),
                        LLMToolParam(
                            name='old',
                            type=LLMToolParamTypes.STRING,
                            description='Exact old text for replace or delete',
                            required=False,
                        ),
                        LLMToolParam(
                            name='new',
                            type=LLMToolParamTypes.STRING,
                            description='New text for replace or replace_between',
                            required=False,
                        ),
                        LLMToolParam(
                            name='anchor',
                            type=LLMToolParamTypes.STRING,
                            description='Exact anchor for insert_before or insert_after',
                            required=False,
                        ),
                        LLMToolParam(
                            name='text',
                            type=LLMToolParamTypes.STRING,
                            description='Text for insert_before, insert_after, append, or prepend',
                            required=False,
                        ),
                        LLMToolParam(
                            name='start',
                            type=LLMToolParamTypes.STRING,
                            description='Start marker for replace_between',
                            required=False,
                        ),
                        LLMToolParam(
                            name='end',
                            type=LLMToolParamTypes.STRING,
                            description='End marker for replace_between',
                            required=False,
                        ),
                        LLMToolParam(
                            name='content',
                            type=LLMToolParamTypes.STRING,
                            description='Full file content for create or overwrite',
                            required=False,
                        ),
                        LLMToolParam(
                            name='expected_replacements',
                            type=LLMToolParamTypes.STRING,
                            description='Optional positive integer or numeric string. Default: 1',
                            required=False,
                        ),
                        LLMToolParam(
                            name='expected_anchors',
                            type=LLMToolParamTypes.STRING,
                            description='Optional positive integer or numeric string. Default: 1',
                            required=False,
                        ),
                        LLMToolParam(
                            name='expected_sections',
                            type=LLMToolParamTypes.STRING,
                            description='Optional positive integer or numeric string for replace_between. Default: 1',
                            required=False,
                        ),
                        LLMToolParam(
                            name='include_markers',
                            type=LLMToolParamTypes.BOOLEAN,
                            description='For replace_between: replace markers too. Default: false',
                            required=False,
                        ),
                    ),
                ),
                description='List of structured file edit operations',
                required=True,
            ),
            LLMToolParam(
                name='encoding',
                type=LLMToolParamTypes.STRING,
                description='Text encoding for reading/writing. Default: utf-8',
                required=False,
            ),
        ),
    )

    def __init__(self, work_dir: Path) -> None:
        self.fs = FileSystem(Path(work_dir).resolve())

    def _validate_file_path(self, path: typing.Any) -> tuple[str, Path]:
        if not isinstance(path, str) or not path:
            raise self.EditApplyError('MissingPath', 'Missing `path`')

        if path.endswith(('/', '\\')):
            raise self.EditApplyError('InvalidPath', 'Path looks like a folder, not a file')

        abs_p = self.fs.resolve(path)
        rel = self.fs.to_rel_posix(abs_p)
        self.fs.assert_allowed(rel, is_dir=False, for_write=True)

        return rel, abs_p

    def _get_str_field(
            self,
            spec: dict[str, typing.Any],
            field: str,
            *,
            default: str = '',
            allow_empty: bool = True,
            error_type: str = 'InvalidField',
    ) -> str:
        value = spec.get(field, default)

        if value is None:
            value = default

        if not isinstance(value, str):
            raise self.EditApplyError(error_type, f'`{field}` must be a string')

        if not allow_empty and value == '':
            raise self.EditApplyError(error_type, f'`{field}` must be a non-empty string')

        return value

    def _parse_positive_int(
            self,
            value: typing.Any,
            *,
            default: int,
            field: str,
    ) -> int:
        if value is None:
            return default

        if isinstance(value, bool):
            raise self.EditApplyError(
                'InvalidCount',
                f'`{field}` must be a positive integer, not a boolean',
            )

        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
        else:
            raise self.EditApplyError(
                'InvalidCount',
                f'`{field}` must be a positive integer or numeric string',
            )

        if parsed < 1:
            raise self.EditApplyError(
                'InvalidCount',
                f'`{field}` must be greater than or equal to 1',
            )

        return parsed

    def _parse_bool(
            self,
            value: typing.Any,
            *,
            default: bool,
            field: str,
    ) -> bool:
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        raise self.EditApplyError(
            'InvalidBoolean',
            f'`{field}` must be a boolean',
        )

    def _replace_between(
            self,
            *,
            text: str,
            start: str,
            end: str,
            new: str,
            include_markers: bool,
            expected_sections: int,
    ) -> str:
        out: list[str] = []
        pos = 0
        count = 0

        while True:
            start_index = text.find(start, pos)
            if start_index == -1:
                break

            after_start = start_index + len(start)
            end_index = text.find(end, after_start)

            if end_index == -1:
                raise self.EditApplyError(
                    'EndMarkerNotFound',
                    'End marker was not found after start marker',
                )

            count += 1

            if include_markers:
                out.append(text[pos:start_index])
                out.append(new)
                pos = end_index + len(end)
            else:
                out.append(text[pos:after_start])
                out.append(new)
                pos = end_index

        out.append(text[pos:])

        if count != expected_sections:
            raise self.EditApplyError(
                'SectionCountMismatch',
                f'Expected {expected_sections} section(s), but found {count}',
            )

        return ''.join(out)

    def _failed_response(
            self,
            *,
            requested: int,
            prepared_results: list[dict[str, typing.Any]],
            index: int,
            path: typing.Any,
            error_type: str,
            message: str,
            written: int = 0,
    ) -> str:
        error_item: dict[str, typing.Any] = {
            'index': index,
            'status': 'error',
            'error': {
                'type': error_type,
                'message': message,
            },
        }

        if isinstance(path, str) and path:
            error_item['path'] = path

        return gen_optimized_json(
            {
                'ok': False,
                'tool': self.description.name,
                'summary': {
                    'requested': requested,
                    'prepared': len(prepared_results),
                    'written': written,
                    'errors': 1,
                },
                'results': prepared_results + [error_item],
            },
        )

    def run(
            self,
            *,
            edits: typing.Sequence[dict],
            encoding: str = 'utf-8',
    ) -> str:
        if edits is None or isinstance(edits, (str, bytes)):
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='`edits` must be an array of objects',
            )

        try:
            edit_list = list(edits)
        except TypeError:
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='`edits` must be an array of objects',
            )

        if not edit_list:
            return gen_tool_error(
                tool=self.description.name,
                error_type='InvalidArguments',
                message='`edits` list is empty',
            )

        requested = len(edit_list)

        originals: dict[str, str | None] = {}
        texts: dict[str, str] = {}
        prepared_results: list[dict[str, typing.Any]] = []

        def load_existing_file(rel: str, abs_p: Path, path_for_errors: typing.Any) -> str:
            if rel in texts:
                return texts[rel]

            if not abs_p.exists():
                raise FileNotFoundError(str(path_for_errors))

            if abs_p.is_dir():
                raise IsADirectoryError(str(path_for_errors))

            original = self.fs.read_text(rel, encoding=encoding)
            originals[rel] = original
            texts[rel] = original

            return original

        def set_file_text(rel: str, content: str, original: str | None) -> None:
            if rel not in originals:
                originals[rel] = original

            texts[rel] = content

        for index, spec in enumerate(edit_list, start=1):
            path: typing.Any = None

            try:
                if not isinstance(spec, dict):
                    raise self.EditApplyError(
                        'InvalidItem',
                        'Edit item must be an object',
                    )

                path = spec.get('path')
                rel, abs_p = self._validate_file_path(path)

                op = spec.get('op')

                if not isinstance(op, str) or not op.strip():
                    raise self.EditApplyError(
                        'MissingOperation',
                        f'Missing `op`. Use one of: {", ".join(self._OP_ENUM)}',
                    )

                op = op.strip().lower()

                if op not in self._OP_ENUM:
                    raise self.EditApplyError(
                        'UnknownOperation',
                        f'Unsupported operation: {op}. Use one of: {", ".join(self._OP_ENUM)}',
                    )

                if op == 'create':
                    content = self._get_str_field(
                        spec,
                        'content',
                        default='',
                        allow_empty=True,
                        error_type='InvalidContent',
                    )

                    if rel in texts or abs_p.exists():
                        raise self.EditApplyError(
                            'AlreadyExists',
                            'File already exists',
                        )

                    set_file_text(rel, content, None)

                elif op == 'overwrite':
                    content = self._get_str_field(
                        spec,
                        'content',
                        default='',
                        allow_empty=True,
                        error_type='InvalidContent',
                    )

                    if rel in texts:
                        original = originals.get(rel)
                    elif abs_p.exists():
                        if abs_p.is_dir():
                            raise IsADirectoryError(str(path))

                        original = self.fs.read_text(rel, encoding=encoding)
                    else:
                        original = None

                    set_file_text(rel, content, original)

                elif op == 'replace':
                    text = load_existing_file(rel, abs_p, path)

                    old = self._get_str_field(
                        spec,
                        'old',
                        allow_empty=False,
                        error_type='InvalidOldText',
                    )
                    new = self._get_str_field(
                        spec,
                        'new',
                        default='',
                        allow_empty=True,
                        error_type='InvalidNewText',
                    )
                    expected = self._parse_positive_int(
                        spec.get('expected_replacements'),
                        default=1,
                        field='expected_replacements',
                    )

                    actual = text.count(old)
                    if actual != expected:
                        raise self.EditApplyError(
                            'ReplaceCountMismatch',
                            f'Expected {expected} occurrence(s), but found {actual}',
                        )

                    texts[rel] = text.replace(old, new, expected)

                elif op == 'delete':
                    text = load_existing_file(rel, abs_p, path)

                    old = self._get_str_field(
                        spec,
                        'old',
                        allow_empty=False,
                        error_type='InvalidOldText',
                    )
                    expected = self._parse_positive_int(
                        spec.get('expected_replacements'),
                        default=1,
                        field='expected_replacements',
                    )

                    actual = text.count(old)
                    if actual != expected:
                        raise self.EditApplyError(
                            'DeleteCountMismatch',
                            f'Expected {expected} occurrence(s), but found {actual}',
                        )

                    texts[rel] = text.replace(old, '', expected)

                elif op == 'insert_before':
                    text = load_existing_file(rel, abs_p, path)

                    anchor = self._get_str_field(
                        spec,
                        'anchor',
                        allow_empty=False,
                        error_type='InvalidAnchor',
                    )
                    insert_text = self._get_str_field(
                        spec,
                        'text',
                        default='',
                        allow_empty=True,
                        error_type='InvalidText',
                    )
                    expected = self._parse_positive_int(
                        spec.get('expected_anchors'),
                        default=1,
                        field='expected_anchors',
                    )

                    actual = text.count(anchor)
                    if actual != expected:
                        raise self.EditApplyError(
                            'AnchorCountMismatch',
                            f'Expected {expected} anchor occurrence(s), but found {actual}',
                        )

                    texts[rel] = text.replace(anchor, insert_text + anchor, expected)

                elif op == 'insert_after':
                    text = load_existing_file(rel, abs_p, path)

                    anchor = self._get_str_field(
                        spec,
                        'anchor',
                        allow_empty=False,
                        error_type='InvalidAnchor',
                    )
                    insert_text = self._get_str_field(
                        spec,
                        'text',
                        default='',
                        allow_empty=True,
                        error_type='InvalidText',
                    )
                    expected = self._parse_positive_int(
                        spec.get('expected_anchors'),
                        default=1,
                        field='expected_anchors',
                    )

                    actual = text.count(anchor)
                    if actual != expected:
                        raise self.EditApplyError(
                            'AnchorCountMismatch',
                            f'Expected {expected} anchor occurrence(s), but found {actual}',
                        )

                    texts[rel] = text.replace(anchor, anchor + insert_text, expected)

                elif op == 'replace_between':
                    text = load_existing_file(rel, abs_p, path)

                    start = self._get_str_field(
                        spec,
                        'start',
                        allow_empty=False,
                        error_type='InvalidStartMarker',
                    )
                    end = self._get_str_field(
                        spec,
                        'end',
                        allow_empty=False,
                        error_type='InvalidEndMarker',
                    )
                    new = self._get_str_field(
                        spec,
                        'new',
                        default='',
                        allow_empty=True,
                        error_type='InvalidNewText',
                    )
                    expected_sections = self._parse_positive_int(
                        spec.get('expected_sections'),
                        default=1,
                        field='expected_sections',
                    )
                    include_markers = self._parse_bool(
                        spec.get('include_markers'),
                        default=False,
                        field='include_markers',
                    )

                    texts[rel] = self._replace_between(
                        text=text,
                        start=start,
                        end=end,
                        new=new,
                        include_markers=include_markers,
                        expected_sections=expected_sections,
                    )

                elif op == 'append':
                    text = load_existing_file(rel, abs_p, path)

                    append_text = self._get_str_field(
                        spec,
                        'text',
                        default='',
                        allow_empty=True,
                        error_type='InvalidText',
                    )

                    texts[rel] = text + append_text

                elif op == 'prepend':
                    text = load_existing_file(rel, abs_p, path)

                    prepend_text = self._get_str_field(
                        spec,
                        'text',
                        default='',
                        allow_empty=True,
                        error_type='InvalidText',
                    )

                    texts[rel] = prepend_text + text

                prepared_results.append(
                    {
                        'index': index,
                        'path': rel,
                        'op': op,
                        'status': 'prepared',
                    },
                )

            except self.EditApplyError as e:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type=e.error_type,
                    message=e.message,
                )
            except FileNotFoundError:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='FileNotFound',
                    message='File must exist for this operation',
                )
            except IsADirectoryError:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='IsDirectory',
                    message='Path is a directory, not a file',
                )
            except UnicodeDecodeError as e:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='EncodingError',
                    message=str(e),
                )
            except LookupError as e:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='InvalidEncoding',
                    message=str(e),
                )
            except PermissionError as e:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='PermissionDenied',
                    message=str(e),
                )
            except ValueError as e:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='InvalidPath',
                    message=str(e),
                )
            except OSError as e:
                return self._failed_response(
                    requested=requested,
                    prepared_results=prepared_results,
                    index=index,
                    path=path,
                    error_type='ReadFailed',
                    message=str(e),
                )

        changed_files: list[dict[str, typing.Any]] = []

        try:
            for rel, new_text in texts.items():
                old_text = originals.get(rel)

                if old_text == new_text:
                    continue

                changed_files.append(
                    {
                        'path': rel,
                        'status': 'created' if old_text is None else 'modified',
                        'bytes': len(new_text.encode(encoding)),
                    },
                )
        except UnicodeEncodeError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='EncodingError',
                message=str(e),
            )
        except LookupError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='InvalidEncoding',
                message=str(e),
            )

        written = 0

        try:
            for rel, new_text in texts.items():
                old_text = originals.get(rel)

                if old_text == new_text:
                    continue

                self.fs.write_text(rel, new_text, overwrite=True, encoding=encoding)
                written += 1

        except UnicodeEncodeError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='EncodingError',
                message=str(e),
                written=written,
            )
        except LookupError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='InvalidEncoding',
                message=str(e),
                written=written,
            )
        except PermissionError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='PermissionDenied',
                message=str(e),
                written=written,
            )
        except ValueError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='InvalidPath',
                message=str(e),
                written=written,
            )
        except OSError as e:
            return self._failed_response(
                requested=requested,
                prepared_results=prepared_results,
                index=0,
                path=None,
                error_type='WriteFailed',
                message=str(e),
                written=written,
            )

        return gen_optimized_json(
            {
                'ok': True,
                'tool': self.description.name,
                'summary': {
                    'requested': requested,
                    'prepared': len(prepared_results),
                    'changed_files': len(changed_files),
                    'written': written,
                    'errors': 0,
                },
                'results': prepared_results,
                'changed_files': changed_files,
            },
        )
