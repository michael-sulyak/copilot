import contextlib
import dataclasses
import datetime
import mimetypes
import os
import pathlib
import shutil
import typing
import uuid
from functools import cached_property

import magic
from aiohttp import web


@dataclasses.dataclass(frozen=True)
class File:
    id: str
    name: str
    path: str
    uploaded_at: datetime.datetime

    @cached_property
    def mime_type(self) -> str:
        mime_type, _ = mimetypes.guess_type(self.name)

        if mime_type:
            return mime_type

        mime = magic.Magic(mime=True)

        with open(self.path, 'rb') as file_io:
            try:
                mime_type = mime.from_buffer(file_io.read())
            except magic.MagicException:
                raise ValueError(f'Could not detect file type for "{self.name}"')

        return mime_type

    @cached_property
    def is_plain_text(self) -> bool:
        try:
            with open(self.path, 'rb') as file_io:
                file_io.read()
            return True
        except (UnicodeDecodeError, IOError,):
            return False

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
            'path': self.path,
            'uploaded_at': self.uploaded_at.isoformat(),
        }

    @contextlib.contextmanager
    def open(self, mode: str = 'rb') -> typing.Iterator[typing.IO]:
        with open(self.path, mode) as file:
            yield file


class LocalFileStorage:
    _files_map: dict[str, File] = {}

    def __init__(self, *, target_directory: str) -> None:
        self.target_directory = target_directory
        shutil.rmtree(self.target_directory)
        os.makedirs(self.target_directory)

    def get(self, file_id: str) -> File | None:
        return self._files_map.get(file_id)

    async def save_files(self, request: web.Request) -> list[File]:
        reader = await request.multipart()
        saved_files = []

        while True:
            part = await reader.next()
            if part is None:
                break

            if part.filename:
                file_extension = pathlib.Path(part.filename).suffix
                file_id = str(uuid.uuid4())
                file_path = os.path.join(self.target_directory, f'{file_id}{file_extension}')

                with open(file_path, 'wb') as file:
                    while True:
                        chunk = await part.read_chunk()

                        if not chunk:
                            break

                        file.write(chunk)

                file_info = File(
                    id=file_id,
                    name=part.filename,
                    path=file_path,
                    uploaded_at=datetime.datetime.now(),
                )

                saved_files.append(file_info)
                self._files_map[file_info.id] = file_info

        return saved_files
