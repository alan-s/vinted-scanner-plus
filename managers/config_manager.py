import logging
import sys

import managers.filter_manager as filter_manager
import managers.logging_manager as logging_manager
import managers.state_manager as state_manager
import utils.file_utils as file_utils

logging_manager.init_logger()
logger = logging.getLogger(__name__)

ALL_YAML_FILES = {'search_config', 'item_filters_config', 'seller_filters_config', 'notification_config'}
FILTER_YAML_FILES = {'item_filters_config', 'seller_filters_config'}
CSV_FILES = {'state_config'}


def load_configs_file_with_paths(path):
    try:
        configs = file_utils.load_yaml(path)
        file_configs = configs['file_configs']

        for config_name, config in file_configs.items():
            file_path = file_utils.build_file_path(config['file_name'], config['directory_name'], config['base_path'])

            config['file_path'] = file_path

        logger.info("Loaded 'configs.yaml' from '%s'", path)

        return configs

    except FileNotFoundError, IOError:
        logger.info(f"No 'configs.yaml' found at %s", path)
        sys.exit(1)
    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


def load_configs_from_config_yaml(yaml_config):
    meta_configs = yaml_config['file_configs']
    file_configs = {}

    for config_name, config in meta_configs.items():

        if config_name in FILTER_YAML_FILES:
            file_configs[config_name] = filter_manager.load_filters(config_name, config['file_path'])

        elif config_name in ALL_YAML_FILES.difference(FILTER_YAML_FILES):
            file_configs[config_name] = file_utils.load_yaml(config['file_path'])

            if config_name == "search_config":
                logger.info(
                    f"Loaded {len(file_configs['search_config']['queries'])} search querie(s) from '{config['file_path']}'")
        elif config_name in CSV_FILES:
            file_configs[config_name] = state_manager.load_already_notified_items(config['file_path'])
        else:
            file_configs[config_name] = None

        file_configs[config_name]['file_path'] = config['file_path']

    return file_configs
