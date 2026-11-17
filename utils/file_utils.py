import sys
from pathlib import Path

import yaml

import managers.logging_manager as logging_manager


def load_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            loaded_yaml = yaml.safe_load(file)

        return loaded_yaml

    except yaml.YAMLError as e:
        logging_manager.error("Error: invalid YAML syntax. Error: %s", e)
        sys.exit(1)

    except OSError as e:
        logging_manager.error("Error: Unable to read YAML file [%s]. Error: %s", path, e)
        sys.exit(1)


def build_file_path(filename: str, directory_name: str | None, base_path: str | None = None) -> Path:
    file_path = Path(base_path) if base_path else Path.cwd()

    if directory_name:
        file_path /= directory_name

    return file_path / filename
