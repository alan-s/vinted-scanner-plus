from pathlib import Path
import logging
import managers.logging_manager as logging_manager
import sys
import yaml

logging_manager.init_logger()
logger = logging.getLogger(__name__)


def load_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            loaded_yaml = yaml.safe_load(file)

        return loaded_yaml

    except yaml.YAMLError as e:
        logger.error("Error: invalid YAML syntax. Error: %s", e)
        sys.exit(1)

    except OSError as e:
        logger.error("Error: Unable to read YAML file [%s]. Error: %s", path, e)
        sys.exit(1)


def build_file_path(filename: str, directory_name: str, base_path: str = None) -> Path:
    file_path = Path(base_path) if base_path else Path.cwd() / directory_name
    return file_path / filename