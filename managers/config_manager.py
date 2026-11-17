import logging
import sys

from managers.filter_manager import load_filters
from managers.state_manager import load_already_notified_items
from utils.file_utils import load_yaml, build_file_path

logger = logging.getLogger(__name__)

ALL_YAML_FILES = {'search_config', 'item_filters_config', 'seller_filters_config', 'notification_config'}
FILTER_YAML_FILES = {'item_filters_config', 'seller_filters_config'}
CSV_FILES = {'state_config'}


def load_configs_file_with_paths(path):
    try:
        configs = load_yaml(path)

        validation_passed = validate_file_configs(configs)
        if validation_passed is not True:
            raise validation_passed

        file_configs = configs['file_configs']

        for config_name, config in file_configs.items():
            file_path = build_file_path(config['file_name'], config['directory_name'], config['base_path'])

            config['file_path'] = file_path

        logger.info("Loaded 'configs.yaml' from '%s'", path)

        return configs

    except ValueError as e:
        logger.error(f"Configs file at '%s' failed validation: %s", path, e)
        sys.exit(1)
    except FileNotFoundError, IOError:
        logger.error(f"No configs file found at '%s'", path)
        sys.exit(1)
    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


def load_configs_from_config_yaml(yaml_config):
    meta_configs = yaml_config['file_configs']
    file_configs = {}

    for config_name, config in meta_configs.items():

        if config_name in FILTER_YAML_FILES:
            file_configs[config_name] = load_filters(config_name, config['file_path'])

        elif config_name in ALL_YAML_FILES.difference(FILTER_YAML_FILES):
            file_configs[config_name] = load_yaml(config['file_path'])

            if config_name == "search_config":
                logger.info(
                    f"Loaded {len(file_configs['search_config']['queries'])} search querie(s) from '{config['file_path']}'")
        elif config_name in CSV_FILES:
            file_configs[config_name] = load_already_notified_items(config['file_path'])
        else:
            file_configs[config_name] = None

        file_configs[config_name]['file_path'] = config['file_path']

    return file_configs


def validate_file_configs(yaml_content: dict) -> bool | ValueError:
    allowed_sections = {
        "search_config",
        "state_config",
        "item_filters_config",
        "seller_filters_config",
        "notification_config",
    }

    allowed_keys = {
        "base_path",
        "directory_name",
        "file_name",
    }

    if not isinstance(yaml_content, dict):
        return ValueError("YAML content must be a dictionary.")

    if set(yaml_content.keys()) != {"file_configs"}:
        return ValueError("Only the 'file_configs' top-level key is allowed.")

    file_configs = yaml_content["file_configs"]

    if not isinstance(file_configs, dict):
        return ValueError("'file_configs' must be a dictionary.")

    invalid_sections = set(file_configs.keys()) - allowed_sections
    if invalid_sections:
        return ValueError(f"Invalid file config sections: {invalid_sections}")

    missing_sections = allowed_sections - set(file_configs.keys())
    if missing_sections:
        return ValueError(f"Missing file config sections: {missing_sections}")

    for section_name, section_config in file_configs.items():

        if not isinstance(section_config, dict):
            return ValueError(f"'{section_name}' must be a dictionary.")

        invalid_keys = set(section_config.keys()) - allowed_keys
        if invalid_keys:
            return ValueError(
                f"Invalid keys in '{section_name}': {invalid_keys}"
            )

        if not section_config.get("file_name"):
            return ValueError(
                f"'file_name' is mandatory and must have a value "
                f"in '{section_name}'."
            )

    return True
