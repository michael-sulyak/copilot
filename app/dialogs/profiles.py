import abc
import os
import typing
from functools import lru_cache

import yaml

from .. import config
from ..models.openai.constants import NOTSET


class BaseProfile(abc.ABC):
    temperature: float | NOTSET = NOTSET
    top_p: float | NOTSET = NOTSET
    reasoning_effort: str | NOTSET = NOTSET
    search_context_size: str | NOTSET = NOTSET

    @abc.abstractmethod
    def get_context(self) -> str:
        pass


class BaseFileProfile(BaseProfile, abc.ABC):
    file_path: typing.ClassVar[str]

    @lru_cache(maxsize=1)
    def get_context(self) -> str:
        with open(self.file_path) as file:
            return file.read().strip()


class BaseTextProfile(BaseProfile, abc.ABC):
    instruction: typing.ClassVar[str | type[NOTSET]] = NOTSET

    def get_context(self) -> str | None:
        if self.instruction is NOTSET:
            return None

        return self.instruction


def load_profile(path: str) -> dict:
    with open(path) as file:
        config = yaml.safe_load(file)

    return config


def load_profiles_from_files(directory: str) -> dict[str, BaseProfile]:
    profiles = {}

    for file_name in sorted(os.listdir(directory)):
        if not file_name.endswith(('.yaml', '.yml')):
            continue

        file_path = os.path.join(directory, file_name)
        yaml_data = load_profile(file_path)

        if base_data_path := yaml_data.get('__base__'):
            yaml_data = {**load_profile(os.path.join(directory, base_data_path)), **yaml_data}

        slug = file_name.rsplit('.', 1)[0]
        profiles[slug] = type(f'{slug.title()}Profile', (BaseTextProfile,), yaml_data)()

    return profiles


PROFILES = load_profiles_from_files(config.PROFILES_DIR)
