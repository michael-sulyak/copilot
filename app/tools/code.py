import os
import subprocess
import tempfile
import time

from app.models.openai.base import FunctionLLMTool, LLMToolParam
from app.models.openai.constants import LLMToolParamTypes
from .additional_utils import fence_code, trim_text
from .files import BaseLLMToolFabric


class RunPythonTool(BaseLLMToolFabric):
    description = FunctionLLMTool(
        name='run_python',
        description=(
            'Run Python code in a Docker container (isolated FS, network disabled, basic resource limits). '
            'Safer than host execution, but not a perfect sandbox.'
        ),
        parameters=(
            LLMToolParam(
                name='code',
                type=LLMToolParamTypes.STRING,
                description='Python code to run',
                required=True,
            ),
            LLMToolParam(
                name='stdin',
                type=LLMToolParamTypes.STRING,
                description='Stdin text passed to the program (default: empty)',
                required=False,
            ),
            LLMToolParam(
                name='timeout_seconds',
                type=LLMToolParamTypes.STRING,
                description='Timeout in seconds (default: 5). Example: "5" or "10".',
                required=False,
            ),
        ),
    )

    def __init__(
        self,
        *,
        docker_bin: str = 'docker',
        docker_image: str = 'python:3.12-slim',
    ) -> None:
        self.docker_bin = docker_bin
        self.docker_image = docker_image

    def run(
        self,
        *,
        code: str,
        stdin: str = '',
        timeout_seconds: str = '5',
    ) -> str:
        try:
            timeout = float(timeout_seconds)
        except Exception:
            timeout = 5.0
        if timeout <= 0:
            timeout = 5.0

        uid_gid = '1000:1000'
        try:
            uid_gid = f'{os.getuid()}:{os.getgid()}'
        except Exception:
            pass

        started_at = time.time()

        try:
            with tempfile.TemporaryDirectory(prefix='run_python_') as td:
                cmd = [
                    self.docker_bin,
                    'run',
                    '--rm',
                    '--network', 'none',
                    '--read-only',
                    '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges',
                    '--pids-limit', '64',
                    '--memory', '256m',
                    '--cpus', '1',
                    '--user', uid_gid,
                    '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m',
                    '-e', 'PYTHONUNBUFFERED=1',
                    '-e', 'PYTHONNOUSERSITE=1',
                    '-e', 'PYTHONDONTWRITEBYTECODE=1',
                    '-e', 'HOME=/tmp',
                    '-v', f'{td}:/work:rw',
                    '-w', '/work',
                    self.docker_image,
                    'python',
                    '-I',
                    '-S',
                    '-B',
                    '-c',
                    code or '',
                ]

                try:
                    proc = subprocess.run(
                        cmd,
                        input=stdin or '',
                        capture_output=True,
                        text=True,
                        timeout=timeout + 3.0,
                    )
                except FileNotFoundError:
                    return (
                        '# Python run\n\n'
                        '## ERROR: Docker not found\n\n'
                        f'- Tried to run: `{self.docker_bin}`\n\n'
                        '### Fix\n\n'
                        '- Install Docker and ensure it is available in PATH.\n'
                    )
                except subprocess.TimeoutExpired:
                    return (
                        '# Python run\n\n'
                        '## ERROR: Timeout\n\n'
                        f'- Timeout seconds: `{timeout}`\n'
                    )

                elapsed = time.time() - started_at
                stdout = trim_text(proc.stdout or '')
                stderr = trim_text(proc.stderr or '')

                return (
                    '# Python run\n\n'
                    f'- Image: `{self.docker_image}`\n'
                    f'- Exit code: `{proc.returncode}`\n'
                    f'- Timeout seconds: `{timeout}`\n'
                    f'- Elapsed seconds: `{elapsed:.3f}`\n\n'
                    '## Stdout\n\n'
                    f'{fence_code(stdout)}\n\n'
                    '## Stderr\n\n'
                    f'{fence_code(stderr)}\n'
                )

        except Exception as e:
            return (
                '# Python run\n\n'
                '## ERROR: Failed to execute\n\n'
                f'- Error: `{e}`\n'
            )
