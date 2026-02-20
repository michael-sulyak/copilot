import os
import subprocess
from pathlib import Path

from .additional_utils import resolve_path


class FileSystem:
    """
    Facade over filesystem operations restricted to work_dir.

    If .gitignore exists and use_git=True:
    - ignored paths are hidden from list operations
    - ignored paths cannot be read/written/created

    Implementation:
    - ignore checks: git check-ignore -q -- <path>
    - file listing (recursive): git ls-files --cached --others --exclude-standard

    No fallback matcher is implemented (by request). If git ignore cannot be enforced
    safely, initialization fails with RuntimeError (fail-closed).
    """

    def __init__(
        self,
        work_dir: Path,
        *,
        git_bin: str = 'git',
        use_git: bool = True,
        list_limit: int = 10_000,
    ) -> None:
        self.work_dir = Path(work_dir).resolve()
        self.gitignore_path = self.work_dir / '.gitignore'
        self.has_gitignore = self.gitignore_path.is_file()

        self.git_bin = str(git_bin)
        self.list_limit = int(list_limit)

        self._protected_top = {'.git'}
        self._ignored_cache: dict[str, bool] = {}

        self._use_git = bool(use_git) and self.has_gitignore
        if self._use_git:
            if not self._git_available():
                raise RuntimeError(
                    f'git binary is not available: git_bin={self.git_bin!r} work_dir={self.work_dir}'
                )
            if not self._git_is_inside_work_tree():
                raise RuntimeError(
                    f'work_dir is not a git work tree (cannot enforce .gitignore safely): {self.work_dir}'
                )
            if not self._git_check_ignore_supported():
                raise RuntimeError(
                    'git check-ignore is not available or not working in this environment '
                    f'for work_dir={self.work_dir}. Cannot enforce .gitignore safely.'
                )

    def resolve(self, path: str) -> Path:
        return resolve_path(self.work_dir, path)

    def to_rel_posix(self, p: Path) -> str:
        return p.resolve().relative_to(self.work_dir).as_posix()

    def read_text(self, path: str, *, encoding: str = 'utf-8') -> str:
        abs_p = self.resolve(path)
        rel = self.to_rel_posix(abs_p)
        self.assert_allowed(rel, is_dir=False, for_write=False)

        if not abs_p.exists():
            raise FileNotFoundError(rel)
        if abs_p.is_dir():
            raise IsADirectoryError(rel)
        if not abs_p.is_file():
            raise OSError(f'Not a regular file: {rel}')

        return abs_p.read_text(encoding=encoding, errors='ignore')

    def write_text(
        self,
        path: str,
        content: str,
        *,
        overwrite: bool = False,
        encoding: str = 'utf-8',
    ) -> Path:
        abs_p = self.resolve(path)
        rel = self.to_rel_posix(abs_p)
        self.assert_allowed(rel, is_dir=False, for_write=True)

        abs_p.parent.mkdir(parents=True, exist_ok=True)

        if abs_p.exists() and not overwrite:
            raise FileExistsError(rel)

        abs_p.write_text(content or '', encoding=encoding, errors='strict')
        return abs_p

    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> Path:
        abs_p = self.resolve(path)
        rel = self.to_rel_posix(abs_p)
        self.assert_allowed(rel, is_dir=True, for_write=True)

        if abs_p.exists() and abs_p.is_file():
            raise FileExistsError(f'File exists at folder path: {rel}')

        abs_p.mkdir(parents=parents, exist_ok=exist_ok)
        return abs_p

    def list_files(
        self,
        path: str = '.',
        *,
        recursive: bool = False,
        include_dirs: bool = False,
    ) -> list[str]:
        root = self.resolve(path)

        if not root.exists():
            raise FileNotFoundError(path)

        if not root.is_dir():
            raise NotADirectoryError(path)

        rel_root = self.to_rel_posix(root)

        # If the directory itself is ignored, return nothing
        if rel_root != '.' and self.is_ignored(rel_root, is_dir=True):
            return []

        # If gitignore enforcement is enabled, use git to list non-ignored files
        if self._use_git:
            files = self._git_list_allowed_files(rel_root)

            if not recursive:
                files = self._filter_direct_children(files, rel_root)

            out: list[str] = list(files)

            if include_dirs:
                dirs = self._fs_list_allowed_dirs(root, recursive=recursive)
                if not recursive:
                    dirs = self._filter_direct_children(dirs, rel_root)
                out.extend(dirs)

            out = sorted(set(out))
            if len(out) > self.list_limit:
                out = out[: self.list_limit]
            return out

        # Otherwise, plain filesystem listing (no ignore rules except protected)
        out: list[str] = []

        if not recursive:
            for p in root.iterdir():
                if not p.is_file() and not p.is_dir():
                    continue

                rel = self.to_rel_posix(p)

                if p.is_dir():
                    if not include_dirs:
                        continue
                    if not rel.endswith('/'):
                        rel += '/'

                if self.is_ignored(rel, is_dir=p.is_dir()):
                    continue

                out.append(rel)

                if len(out) >= self.list_limit:
                    break

            return sorted(out)

        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            abs_dir = Path(dirpath)
            rel_dir = self.to_rel_posix(abs_dir)

            # prune .git always
            dirnames[:] = [d for d in dirnames if d != '.git']

            # prune ignored/protected directories
            kept_dirs: list[str] = []
            for d in dirnames:
                rel_d = f'{rel_dir}/{d}' if rel_dir != '.' else d

                if self.is_ignored(rel_d, is_dir=True):
                    continue

                kept_dirs.append(d)

            dirnames[:] = kept_dirs

            if include_dirs:
                for d in kept_dirs:
                    rel_d = f'{rel_dir}/{d}' if rel_dir != '.' else d
                    rel_d = rel_d.rstrip('/') + '/'
                    out.append(rel_d)

                    if len(out) >= self.list_limit:
                        return sorted(out)

            for f in filenames:
                abs_f = abs_dir / f

                if not abs_f.is_file():
                    continue

                rel_f = self.to_rel_posix(abs_f)

                if self.is_ignored(rel_f, is_dir=False):
                    continue

                out.append(rel_f)

                if len(out) >= self.list_limit:
                    return sorted(out)

        return sorted(out)

    def _fs_list_allowed_dirs(self, root: Path, *, recursive: bool) -> list[str]:
        out: list[str] = []
        rel_root = self.to_rel_posix(root)

        if not recursive:
            for p in root.iterdir():
                if not p.is_dir():
                    continue

                rel = self.to_rel_posix(p)
                if self.is_ignored(rel, is_dir=True):
                    continue

                rel = rel.rstrip('/') + '/'
                out.append(rel)

                if len(out) >= self.list_limit:
                    break

            return out

        for dirpath, dirnames, _filenames in os.walk(root, topdown=True):
            abs_dir = Path(dirpath)
            rel_dir = self.to_rel_posix(abs_dir)

            # prune .git always
            dirnames[:] = [d for d in dirnames if d != '.git']

            kept_dirs: list[str] = []
            for d in dirnames:
                rel_d = f'{rel_dir}/{d}' if rel_dir != '.' else d

                if self.is_ignored(rel_d, is_dir=True):
                    continue

                kept_dirs.append(d)

            dirnames[:] = kept_dirs

            for d in kept_dirs:
                rel_d = f'{rel_dir}/{d}' if rel_dir != '.' else d
                rel_d = rel_d.rstrip('/') + '/'

                # do not include the listing root itself
                if rel_root not in ('', '.') and rel_d.rstrip('/') == rel_root.rstrip('/'):
                    continue

                out.append(rel_d)

                if len(out) >= self.list_limit:
                    return out

        return out

    def _filter_direct_children(self, files: list[str], rel_root: str) -> list[str]:
        """
        Keep only files that are direct children of rel_root (non-recursive listing).
        """
        rel_root = (rel_root or '.').strip().strip('/')

        if rel_root in ('', '.'):
            # direct children of repo root => no slash in the path
            return [f for f in files if '/' not in f.rstrip('/')]

        prefix = rel_root + '/'
        out: list[str] = []
        for f in files:
            if not f.startswith(prefix):
                continue
            rest = f[len(prefix):]
            if '/' in rest.rstrip('/'):
                continue
            out.append(f)
        return out

    def _is_protected(self, rel: str) -> bool:
        rel = rel.strip().lstrip('/').replace('\\', '/')

        if rel in ('', '.'):
            return False

        first = rel.split('/', 1)[0]
        return first in self._protected_top

    def is_ignored(self, rel: str, *, is_dir: bool = False) -> bool:
        rel = (rel or '.').strip().lstrip('/').replace('\\', '/')
        if rel == '':
            rel = '.'

        if rel == '.':
            return False

        if self._is_protected(rel):
            return True

        if not self._use_git:
            return False

        key = rel
        if is_dir and not key.endswith('/'):
            key += '/'

        cached = self._ignored_cache.get(key)
        if cached is not None:
            return cached

        ignored = self._git_check_ignore_one(key)
        self._ignored_cache[key] = ignored
        return ignored

    def assert_allowed(self, rel: str, *, is_dir: bool = False, for_write: bool = False) -> None:
        if self.is_ignored(rel, is_dir=is_dir):
            action = 'write' if for_write else 'access'
            raise PermissionError(f'Refusing to {action} ignored or protected path: {rel}')

    # ---------- git helpers (only) ----------

    def _git_available(self) -> bool:
        try:
            proc = subprocess.run(
                [self.git_bin, '--version'],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return False
        return proc.returncode == 0

    def _git_is_inside_work_tree(self) -> bool:
        try:
            proc = subprocess.run(
                [self.git_bin, 'rev-parse', '--is-inside-work-tree'],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return False

        if proc.returncode != 0:
            return False

        return (proc.stdout or '').strip().lower() == 'true'

    def _git_check_ignore_supported(self) -> bool:
        """
        Ensures `git check-ignore` exists and returns expected statuses.
        Must not accept 'unknown command' as a valid 'not ignored'.
        """
        try:
            proc = subprocess.run(
                [self.git_bin, 'check-ignore', '-q', '--', '__fs_probe__'],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return False

        stderr = (proc.stderr or '').lower()
        if 'is not a git command' in stderr or 'unknown subcommand' in stderr:
            return False

        # check-ignore should return 0 (ignored) or 1 (not ignored)
        return proc.returncode in (0, 1)

    def _git_check_ignore_one(self, rel: str) -> bool:
        """
        Returns True if ignored, False if not ignored.
        Raises RuntimeError on unexpected git failures (never fail-open).
        """
        try:
            proc = subprocess.run(
                [self.git_bin, 'check-ignore', '-q', '--', rel],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            raise RuntimeError(f'git check-ignore failed to execute: {e}') from e

        if proc.returncode == 0:
            return True
        if proc.returncode == 1:
            return False

        stderr = (proc.stderr or '').strip()
        stdout = (proc.stdout or '').strip()
        details = stderr or stdout or f'returncode={proc.returncode}'
        raise RuntimeError(f'git check-ignore returned unexpected status for {rel}: {details}')

    def _git_list_allowed_files(self, rel_root: str) -> list[str]:
        """
        Lists files that are either:
        - tracked (cached)
        - untracked but not ignored (others + exclude-standard)

        Output is paths relative to the repo root (work_dir).
        """
        rel_root = (rel_root or '.').strip().strip('/')

        cmd = [
            self.git_bin,
            'ls-files',
            '--cached',
            '--others',
            '--exclude-standard',
            '-z',
        ]

        # Use pathspec to restrict to a subdirectory
        if rel_root not in ('', '.'):
            cmd += ['--', rel_root]
        else:
            cmd += ['--']

        try:
            proc = subprocess.run(
                cmd,
                cwd=self.work_dir,
                capture_output=True,
                check=False,
            )
        except Exception as e:
            raise RuntimeError(f'git ls-files failed to execute: {e}') from e

        if proc.returncode != 0:
            stderr = (proc.stderr or b'').decode('utf-8', errors='ignore').strip()
            raise RuntimeError(f'git ls-files failed (code={proc.returncode}): {stderr}')

        raw = proc.stdout or b''
        items = [x.decode('utf-8', errors='ignore') for x in raw.split(b'\x00') if x]

        # Additionally block protected (.git) if it ever appears (defensive)
        out: list[str] = []
        for p in items:
            norm = p.strip().lstrip('/').replace('\\', '/')

            if not norm or norm == '.':
                continue

            if self._is_protected(norm):
                continue

            out.append(norm)

        return out