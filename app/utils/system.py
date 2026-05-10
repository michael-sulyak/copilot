import asyncio
import logging


async def get_pids_using_port(port: int) -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        'lsof',
        '-t',
        f'-i:{port}',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        return []

    return [
        line.strip()
        for line in stdout.decode().splitlines()
        if line.strip()
    ]


async def ask_gui_confirmation(*, title: str, text: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        'zenity',
        '--question',
        f'--title={title}',
        f'--text={text}',
        '--width=420',
        '--height=180',
    )

    await proc.communicate()

    # Zenity returns:
    # 0 = Yes / OK
    # 1 = No / Cancel
    return proc.returncode == 0


async def kill_pids(pids: list[str], *, signal: str) -> None:
    for pid in pids:
        proc = await asyncio.create_subprocess_exec(
            'kill',
            signal,
            pid,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logging.warning(
                'Failed to kill PID %s with signal %s: %s',
                pid,
                signal,
                stderr.decode().strip(),
            )

async def get_processes_using_port(port: int) -> str:
    if not isinstance(port, int) or port < 1 or port > 65535:
        return f'Invalid port: {port}. Please provide a port number between 1 and 65535.'

    try:
        proc = await asyncio.create_subprocess_exec(
            'lsof',
            '-nP',
            f'-i:{port}',
            '-F',
            'pcun',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

    except FileNotFoundError:
        return '"lsof" is not installed or not available on this system.'

    except Exception as exc:
        return f'Failed to check port {port}: {exc}'

    if proc.returncode != 0:
        return f'No process is currently using port {port}.'

    output = stdout.decode(errors='replace').strip()

    if not output:
        return f'No process is currently using port {port}.'

    processes = []
    current = {}

    for line in output.splitlines():
        if not line:
            continue

        field = line[0]
        value = line[1:]

        if field == 'p':
            if current:
                processes.append(current)
            current = {'pid': value}
        elif field == 'c':
            current['command'] = value
        elif field == 'u':
            current['user_id'] = value
        elif field == 'n':
            current['name'] = value

    if current:
        processes.append(current)

    if not processes:
        return f'Port {port} is in use, but no process details were available.'

    lines = [
        f'Port {port} is currently in use.',
        '',
        'Processes using this port:',
    ]

    for process in processes:
        command = process.get('command', 'unknown')
        pid = process.get('pid', 'unknown')
        user_id = process.get('user_id', 'unknown')
        name = process.get('name', 'unknown')

        lines.append(
            f'- "{command}" with PID "{pid}", user ID "{user_id}", connection "{name}"',
        )

    return '\n'.join(lines)
