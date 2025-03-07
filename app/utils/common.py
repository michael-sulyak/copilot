import datetime
import json
import logging
import re
import typing
from contextlib import contextmanager

import numpy as np


def escape_markdown(text: str) -> str:
    parse = re.sub(r'([_*\[\]()~`>\#\+\-=|\.!])', r'\\\1', text)
    reparse = re.sub(r'\\\\([_*\[\]()~`>\#\+\-=|\.!])', r'\1', parse)
    return reparse


def chunk_generator(sequence: typing.Sequence, *, chunk_size: int) -> typing.Generator[typing.Sequence, None, None]:
    for chunk in range(0, len(sequence), chunk_size):
        yield sequence[chunk: chunk + chunk_size]


@contextmanager
def timeit(name: str) -> typing.Iterator:
    started_at = datetime.datetime.now()

    try:
        yield
    finally:
        finished_at = datetime.datetime.now()
        logging.info(f'{name} took {finished_at - started_at}')


def cosine_similarity(a: typing.List[float], b: typing.List[float]) -> float:
    return round(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), 4)


def gen_optimized_json(obj: typing.Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':',))
