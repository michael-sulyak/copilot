import codecs
import contextlib
import dataclasses
import datetime
import io
import logging
import mimetypes
import os
import pathlib
import typing
import uuid
from functools import cached_property, lru_cache

import aiofiles
import magic
from aiohttp import web

from app import config


@dataclasses.dataclass(frozen=True)
class File:
    id: str
    name: str
    path: str
    uploaded_at: datetime.datetime
    url: str | None = None

    @cached_property
    def mime_type(self) -> str:
        mime_type, _ = mimetypes.guess_type(self.name)

        if mime_type:
            return mime_type

        mime = magic.Magic(mime=True)

        with open(self.path, 'rb') as file_io:
            try:
                mime_type = mime.from_buffer(file_io.read(8192))
            except magic.MagicException as e:
                raise ValueError(f'Could not detect file type for "{self.name}"') from e

        return mime_type

    @cached_property
    def is_plain_text(self) -> bool:
        try:
            with open(self.path, 'rb') as file_io:
                sample = file_io.read(8192)

                # A sample can end partway through a valid UTF-8 character.
                codecs.getincrementaldecoder('utf-8')().decode(sample, final=False)
        except (OSError, UnicodeDecodeError):
            return False
        else:
            return True

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith('image/')

    @property
    def is_tabular(self) -> bool:
        return self.mime_type in (
            'text/csv',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def get_meta_info(self) -> dict[str, typing.Any]:
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'uploaded_at': self.uploaded_at.isoformat(),
        }

    @contextlib.contextmanager
    def open(self, mode: str = 'rb') -> typing.Iterator[typing.IO]:
        with open(self.path, mode) as file:
            yield file


class LocalFileStorage:
    target_directory: str
    showed_directory: str
    _files_map: dict[str, File]

    def __init__(self, *, target_directory: str, showed_directory: str) -> None:
        self.target_directory = target_directory
        self.showed_directory = showed_directory
        self._files_map = {}
        os.makedirs(self.target_directory, exist_ok=True)

    def get(self, file_id: str) -> File | None:
        return self._files_map.get(file_id)

    async def save_files(self, request: web.Request) -> list[File]:
        reader = await request.multipart()
        saved_files = []
        created_paths = []
        total_bytes = 0

        try:
            while (part := await reader.next()) is not None:
                if not part.filename:
                    raise web.HTTPBadRequest(text='Every upload part must be a file.')

                if len(saved_files) >= config.MAX_UPLOAD_FILES:
                    raise web.HTTPBadRequest(text=f'At most {config.MAX_UPLOAD_FILES} files are allowed.')

                file_name = pathlib.PurePosixPath(part.filename.replace('\\', '/')).name
                file_extension = pathlib.Path(file_name).suffix
                file_id = str(uuid.uuid4())
                stored_name = f'{file_id}{file_extension}'
                file_path = os.path.join(self.target_directory, stored_name)
                created_paths.append(file_path)
                file_bytes = 0

                async with aiofiles.open(file_path, 'wb') as file:
                    while chunk := await part.read_chunk():
                        file_bytes += len(chunk)
                        total_bytes += len(chunk)
                        if file_bytes > config.MAX_UPLOAD_FILE_BYTES:
                            raise web.HTTPRequestEntityTooLarge(
                                max_size=config.MAX_UPLOAD_FILE_BYTES, actual_size=file_bytes,
                            )
                        if total_bytes > config.MAX_UPLOAD_TOTAL_BYTES:
                            raise web.HTTPRequestEntityTooLarge(
                                max_size=config.MAX_UPLOAD_TOTAL_BYTES, actual_size=total_bytes,
                            )
                        await file.write(chunk)

                saved_files.append(File(
                    id=file_id,
                    name=file_name,
                    path=file_path,
                    url=f'{self.showed_directory.rstrip("/")}/{stored_name}',
                    uploaded_at=datetime.datetime.now(),
                ))
        except BaseException:
            # Roll back partial uploads on validation errors, disconnects and cancellation.
            for file_path in created_paths:
                pathlib.Path(file_path).unlink(missing_ok=True)

            raise

        self._files_map.update((file.id, file) for file in saved_files)
        return saved_files

    async def save_file(self, file_name: str, buffer: io.BytesIO) -> File:
        file_extension = pathlib.Path(file_name).suffix
        file_id = str(uuid.uuid4())
        new_file_name = f'{file_id}{file_extension}'
        file_path = os.path.join(self.target_directory, new_file_name)

        buffer.seek(0)
        chunk_size = 8192

        async with aiofiles.open(file_path, 'wb') as file:
            while True:
                chunk = buffer.read(chunk_size)

                if not chunk:
                    break

                await file.write(chunk)

        file_info = File(
            id=file_id,
            name=file_name,
            path=file_path,
            url=f'{self.showed_directory.rstrip("/")}/{new_file_name}',
            uploaded_at=datetime.datetime.now(),
        )

        self._files_map[file_info.id] = file_info

        return file_info


@lru_cache(maxsize=1)
def get_file_storage() -> LocalFileStorage:
    file_storage_path = os.path.join(config.UPLOADS_DIR, str(uuid.uuid4()))

    if not os.path.exists(file_storage_path):
        os.makedirs(file_storage_path)

    logging.info('File storage path: %s', file_storage_path)

    return LocalFileStorage(
        target_directory=file_storage_path,
        showed_directory=config.SHOWED_UPLOADS_DIR,
    )
