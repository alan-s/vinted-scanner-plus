#!/usr/bin/env python3
import argparse
import pathlib
import sys

import managers.config_manager as config_manager
import managers.logging_manager as logging_manager
import managers.query_manager as query_manager
import managers.vinted_api_manager as vinted_api_manager


def main():
    # Setup
    args = configure_args()
    logging_manager.init_logger()

    logging_manager.info("")
    logging_manager.info("================================================================================")
    logging_manager.info("                                  VINTED SCANNER PLUS                           ")
    logging_manager.info("================================================================================")
    logging_manager.info("")

    # Print what options app has been launched with
    args_str = " ".join(sys.argv[1:])
    logging_manager.info(f"Launched with the following args: {args_str}")

    # Get all the required file paths from config
    base_dir = pathlib.Path.cwd()
    config_file_path = base_dir / "configs" / "configs.yaml"
    config_yaml = config_manager.load_configs_file_with_paths(config_file_path)
    all_configs = config_manager.load_configs_from_config_yaml(config_yaml)

    # Load search queries
    search_config = all_configs['search_config']
    queries = search_config['queries']

    # No search queries
    if not queries:
        logging_manager.info(f"Terminating; no search queries defined in '{search_config['file_path']}'")
        sys.exit(0)

    # Init session to be used for api calls
    session = vinted_api_manager.initialise_vinted_session(search_config)

    # Loop through each search query defined in config
    query_manager.initialise(all_configs)
    for query in queries:
        query_manager.process_query(query, session, args)

    # Close api sessions
    vinted_api_manager.close_session(session)
    logging_manager.info("Completed processing all querie(s). Exiting")


def configure_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--log_filtering",
        action="store_true",
        dest="log_filtering",
        default=False,
        help="Enable logging when filtering items. By default, logging of filters is off"
    )

    parser.add_argument(
        "--enable_notifications",
        action="store_true",
        dest="enable_notifications",
        default=False,
        help="Enable notifications to external connectors e.g. Telegram. By default, no notifications are sent"
    )

    parser.add_argument(
        "--disable_state_file",
        action="store_true",
        dest="disable_state_file",
        default=False,
        help="Disable storing previously notified items in a state file. By default, notified items are stored"
    )

    return parser.parse_args()


if __name__ == "__main__":
    main()
