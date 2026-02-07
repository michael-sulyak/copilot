import difflib
import re

import subprocess
from pathlib import Path


def fence_code(text: str, lang: str = '') -> str:
    ticks = re.findall(r'`+', text)
    max_len = max((len(t) for t in ticks), default=0)
    fence = '`' * max(3, max_len + 1)
    lang_part = lang.strip()
    return f'{fence}{lang_part}\n{text}\n{fence}'


def spoiler(title: str, text: str) -> str:
    return f'<details><summary>{title}</summary>{text}</details>'


def resolve_path(base_dir: Path, path: str) -> Path:
    """
    Resolve path relative to base_dir and forbid escaping it.
    """
    base_dir = base_dir.resolve()
    p = Path(path).expanduser()

    if not p.is_absolute():
        p = (base_dir / p).resolve()
    else:
        p = p.resolve()

    if p != base_dir and base_dir not in p.parents:
        raise ValueError('Access outside the provided folder is forbidden')

    return p


def iter_all_files(base_dir: Path, *, limit: int = 10_000) -> list[str]:
    """
    Return relative paths (posix-like) for files under base_dir.
    Limited to avoid huge outputs on big repos.
    """
    files: list[str] = []
    for p in base_dir.rglob('*'):
        if not p.is_file():
            continue
        files.append(p.relative_to(base_dir).as_posix())
        if len(files) >= limit:
            break
    return files


def suggest_similar_paths(requested: str, candidates: list[str], *, limit: int = 10) -> list[str]:
    requested_norm = requested.strip().lower()
    req_name = Path(requested).name.lower()

    direct = [
        candidate for candidate in candidates
        if requested_norm and (
            requested_norm in candidate.lower()
            or req_name == Path(candidate).name.lower()
            or req_name in Path(candidate).name.lower()
        )
    ]

    fuzzy = difflib.get_close_matches(requested, candidates, n=limit, cutoff=0.35)

    # keep order, unique
    seen: set[str] = set()
    out: list[str] = []
    for x in direct + fuzzy:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
        if len(out) >= limit:
            break

    return out


def nearest_existing_dir(path: Path, base_dir: Path) -> Path:
    cur = path
    while True:
        if cur.exists() and cur.is_dir():
            return cur
        if cur == base_dir:
            return base_dir
        if base_dir not in cur.parents and cur != base_dir:
            return base_dir
        cur = cur.parent


def list_dir_entries_md(dir_path: Path, base_dir: Path, *, limit: int = 50) -> str:
    if not dir_path.exists() or not dir_path.is_dir():
        return ''

    entries: list[str] = []
    for p in sorted(dir_path.iterdir(), key=lambda x: x.name.lower()):
        rel = p.relative_to(base_dir).as_posix()
        if p.is_dir():
            rel = f'{rel}/'
        entries.append(rel)
        if len(entries) >= limit:
            break

    if not entries:
        return f'No entries in `{dir_path.relative_to(base_dir).as_posix()}/`'

    lines = '\n'.join(f'- `{e}`' for e in entries)
    rel_dir = dir_path.relative_to(base_dir).as_posix()
    return f'Files in directory `{rel_dir}/` (showing up to {limit}):\n{lines}'


def trim_text(text: str, limit: int = 12_000) -> str:
    if text is None:
        return ''

    if len(text) <= limit:
        return text

    return text[:limit] + '\n... truncated ...\n'


def get_changed_files(
    repo_dir: Path,
    *,
    staged: bool = False,
    ref: str | None = None,
) -> tuple[str, ...]:
    """
    Return a list of file paths changed in the git repository.
    """

    repo_dir = Path(repo_dir).resolve()

    cmd = ['git', 'diff', 'origin/master', '--name-only']

    if staged:
        cmd.append('--cached')

    if ref:
        cmd.append(ref)

    try:
        output = subprocess.check_output(
            cmd,
            cwd=repo_dir,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        return ()  # TODO: fix and check if project has git
        # raise RuntimeError(f'git diff failed: {e}') from e

    return tuple(line.strip() for line in output.splitlines() if line.strip())
