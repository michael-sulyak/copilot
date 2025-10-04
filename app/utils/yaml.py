import os

import yaml


def load_yaml_file(path: str) -> dict:
    with open(path) as file:
        yaml_data = yaml.safe_load(file)

    if base_data_path := yaml_data.get('__base__'):
        yaml_data = {**load_yaml_file(os.path.join(os.path.dirname(path), base_data_path)), **yaml_data}

    return yaml_data
