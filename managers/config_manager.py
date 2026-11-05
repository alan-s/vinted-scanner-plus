import logging
import managers.logging_manager as logging_manager
import managers.state_manager as state_manager
import managers.filter_manager as filter_manager
import utils.file_utils as file_utils

logging_manager.init_logger()
logger = logging.getLogger(__name__)

yaml_files = {'search_config', 'notification_config'}
filter_files = {'item_filters', 'seller_filters'}
csv_files = {'state'}

def get_config_file_paths(path):
    loaded_yaml = file_utils.load_yaml(path)

    configs = {}

    for config in loaded_yaml.get("configs", []):
        file_path = file_utils.build_file_path(
            config.get("file_name"),
            config.get("directory_name"),
            config.get("base_path")
        )

        configs[config["config"]] = file_path

    return configs

def load_configs_from_config_file(path):
    loaded_yaml = file_utils.load_yaml(path)

    configs = {}

    for config in loaded_yaml.get("configs", []):
        file_path = file_utils.build_file_path(
            config.get("file_name"),
            config.get("directory_name"),
            config.get("base_path")
        )

        if config["config"] in yaml_files:
            configs[config["config"]] = file_utils.load_yaml(file_path)

            if config["config"] == "search_config":
                logger.info(f"Loaded {len(configs['search_config']['queries'])} search querie(s) from {file_path}")
        elif config["config"] in csv_files:
            configs[config["config"]] = state_manager.load_already_notified_items(file_path)
        elif config["config"] in filter_files:
            configs[config["config"]] = filter_manager.load_filters(config["config"], file_path)

    return configs
