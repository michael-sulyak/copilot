import base64
from functools import cached_property
from io import StringIO

import pandas as pd

from .local_file_storage import File


class FileProcessor:
    file: File

    def __init__(self, file: File) -> None:
        self.file = file

    def to_base64(self) -> str:
        with open(self.file.path, 'rb') as file:
            encoded_string = base64.b64encode(file.read()).decode('utf-8')

        return f'data:{self.file.mime_type};base64,{encoded_string}'

    def to_bytes(self) -> bytes:
        with open(self.file.path, 'rb') as file:
            return file.read()

    def to_txt(self) -> str:
        if self.file.mime_type in (
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ):
            file = pd.read_excel(self.file.path)
            buffer = StringIO()
            file.to_csv(buffer, index=False, header=True)
            return buffer.getvalue()

        if self._can_parse_via_docling():
            return self._parse_via_docling()

        if self.file.mime_type.startswith('text/') or self.file.is_plain_text:
            with open(self.file.path) as file:
                return file.read()

        raise ValueError(f'Unsupported file type (for {self.file.mime_type})')

    def _can_parse_via_docling(self) -> bool:
        supported_mime_types = {
            # *FormatToMimeType[InputFormat.DOCX],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.template',

            # *FormatToMimeType[InputFormat.PPTX],
            'application/vnd.openxmlformats-officedocument.presentationml.template',
            'application/vnd.openxmlformats-officedocument.presentationml.slideshow',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',

            # *FormatToMimeType[InputFormat.PDF],
            'application/pdf',
        }

        return self.file.mime_type in supported_mime_types

    def _parse_via_docling(self) -> str:
        result = self._docling_converter.convert(self.file.path)
        return result.document.export_to_markdown()

    @cached_property
    def _docling_converter(self):
        try:
            from docling.document_converter import DocumentConverter
        except ModuleNotFoundError as e:
            raise RuntimeError('You need to run `poetry install --with file_parsing` to parse some file formats.') from e

        return DocumentConverter()
