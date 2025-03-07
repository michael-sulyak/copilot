import os

import yaml
from jinja2 import Template as Jinja2Template

from .. import config


def load_prompts_from_files(directory: str) -> list[dict[str, str]]:
    prompts = []

    for file_name in sorted(os.listdir(directory)):
        if not file_name.endswith(('.yaml', '.yml',)):
            continue

        file_path = os.path.join(directory, file_name)

        with open(file_path, 'r') as file:
            content = file.read().strip()

        yaml_data = yaml.safe_load(content)
        name = Jinja2Template(yaml_data['name'])
        prompt = Jinja2Template(yaml_data['prompt'])
        versions = yaml_data.get('versions')

        if versions is None:
            prompts.append({
                'name': name.render(),
                'text': prompt.render(),
            })
        else:
            for version in versions:
                prompts.append({
                    'name': name.render(**version),
                    'text': prompt.render(**version),
                })

    return prompts


PROMPTS = load_prompts_from_files(config.PROMPTS_DIR)
