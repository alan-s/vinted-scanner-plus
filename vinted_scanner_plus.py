#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys

from managers.config_manager import load_configs_file_with_paths, load_configs_from_config_yaml
from managers.logging_manager import init_logger
from managers.query_manager import initialise, process_query
from managers.vinted_api_manager import initialise_vinted_session, close_session


def main():
    # Setup
    args = configure_args()
    init_logger(args.log_path)
    logger = logging.getLogger(__name__)

    logger.info("")
    logger.info("================================================================================")
    logger.info("                                  VINTED SCANNER PLUS                           ")
    logger.info("================================================================================")
    logger.info("")

    # Print what options app has been launched with
    args_str = " ".join(sys.argv[1:])
    logger.info(f"Launched with the following args: {args_str}")
    logger.info(f"Logging to '{args.log_path})'")

    # Get all the required file paths from config
    base_dir = pathlib.Path.cwd()
    config_file_path = base_dir / "configs" / "configs.yaml"
    config_yaml = load_configs_file_with_paths(config_file_path)
    all_configs = load_configs_from_config_yaml(config_yaml)

    # Load search queries
    search_config = all_configs['search_config']
    queries = search_config['queries']

    # No search queries
    if not queries:
        logger.info(f"Terminating; no search queries defined in '{search_config['file_path']}'")
        sys.exit(0)

    # Init session to be used for api calls
    session = initialise_vinted_session(search_config)

    # Loop through each search query defined in config
    initialise(all_configs)
    for query in queries:
        process_query(query, session, args)

    # Close api sessions
    close_session(session)
    logger.info("Completed processing all querie(s). Exiting")


def configure_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--log-path",
        dest="log_path",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent / "vinted_scanner_plus.log",
        help="Set the desire log path used"
    )

    parser.add_argument(
        "--log-filtering",
        action="store_true",
        dest="log_filtering",
        default=False,
        help="Enable logging when filtering items. By default, logging of filters is off"
    )

    parser.add_argument(
        "--enable-notifications",
        action="store_true",
        dest="enable_notifications",
        default=False,
        help="Enable notifications to external connectors e.g. Telegram. By default, no notifications are sent"
    )

    parser.add_argument(
        "--disable-state-file",
        action="store_true",
        dest="disable_state_file",
        default=False,
        help="Disable storing previously notified items in a state file. By default, notified items are stored"
    )

    return parser.parse_args()


if __name__ == "__main__":
    main()
