from pathlib import Path
import logging
import managers.logging_manager as logging_manager
import re
import sys
import utils.file_utils as file_utils
import utils.text_utils as text_utils

logging_manager.init_logger()
logger = logging.getLogger(__name__)


def load_filters(filter_type, path):
    try:
        filter_config = file_utils.load_yaml(path)
        validate_filters(filter_config)

    except ValueError as e:
        logger.error("Invalid filter configuration in %s. Error: %s",path, e)
        sys.exit(1)

    # No YAML content means no filters
    filter_config = filter_config or {"filters": []}

    logger.info(
        "Loaded %s [%s] filter(s) from %s",
        len(filter_config["filters"]),
        filter_type,
        Path(path).resolve(),
    )
    return filter_config


def validate_filters(config):
    """Validate YAML filter configuration if content is defined."""

    # Empty YAML content is valid
    if config is None:
        return True

    operators = {
        "equals",
        "contains",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
        "exists",
        "is_null",
        "is_empty",
    }

    operators_without_value = {"exists", "is_null", "is_empty"}

    numeric_operators = {
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
    }

    def check_keys(data, required_keys, optional_keys, context):
        if not isinstance(data, dict):
            raise ValueError(f"{context} must be a mapping")

        missing = required_keys - data.keys()
        unexpected = data.keys() - (required_keys | optional_keys)

        if missing:
            raise ValueError(f"{context}: missing keys {sorted(missing)}")

        if unexpected:
            raise ValueError(f"{context}: unexpected keys {sorted(unexpected)}")

    def is_number(value):
        # bool is a subclass of int in Python, so explicitly exclude it.
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    check_keys(config, {"filters"}, set(), "Root")

    if not isinstance(config["filters"], list):
        raise ValueError("'filters' must be a list")

    for i, item in enumerate(config["filters"]):
        context = f"filters[{i}]"

        check_keys(
            item,
            {"query_id", "mode", "rules"},
            set(),
            context,
        )

        if not isinstance(item["query_id"], str) or not item["query_id"]:
            raise ValueError(f"{context}.query_id must be a non-empty string")

        if item["mode"] not in {"include", "exclude"}:
            raise ValueError(
                f"{context}.mode must be 'include' or 'exclude'"
            )

        if not isinstance(item["rules"], list) or not item["rules"]:
            raise ValueError(f"{context}.rules must be a non-empty list")

        for j, rule in enumerate(item["rules"]):
            rule_context = f"{context}.rules[{j}]"

            # Determine whether value is required based on the operator.
            if not isinstance(rule, dict):
                raise ValueError(f"{rule_context} must be a mapping")

            operator = rule.get("operator")

            if not isinstance(operator, str) or operator not in operators:
                raise ValueError(
                    f"{rule_context}.operator must be one of: "
                    f"{sorted(operators)}"
                )

            required_keys = {"key", "operator"}

            if operator not in operators_without_value:
                required_keys.add("value")

            check_keys(
                rule,
                required_keys,
                set(),
                rule_context,
            )

            if not isinstance(rule["key"], str) or not rule["key"]:
                raise ValueError(
                    f"{rule_context}.key must be a non-empty string"
                )

            # Validate numeric operators.
            if operator in numeric_operators:
                value = rule["value"]

                if operator == "between":
                    if not isinstance(value, dict):
                        raise ValueError(
                            f"{rule_context}.value must be a mapping "
                            "with 'min' and 'max' for operator 'between'"
                        )

                    check_keys(
                        value,
                        {"min", "max"},
                        set(),
                        f"{rule_context}.value",
                    )

                    if not is_number(value["min"]) or not is_number(value["max"]):
                        raise ValueError(
                            f"{rule_context}.value.min and max must be numeric"
                        )

                    if value["min"] > value["max"]:
                        raise ValueError(
                            f"{rule_context}.value.min cannot exceed max"
                        )

                elif not is_number(value):
                    raise ValueError(
                        f"{rule_context}.value must be numeric "
                        f"for operator '{operator}'"
                    )

            # Validate string operators (including CSV values).
            elif operator in {"equals", "contains"}:
                value = rule["value"]

                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"{rule_context}.value must be a non-empty string "
                        f"for operator '{operator}'"
                    )

                # Validate comma-separated values.
                expected_values = [v.strip() for v in value.split(",")]

                if any(not v for v in expected_values):
                    raise ValueError(
                        f"{rule_context}.value contains an empty CSV value"
                    )

    return True


def filter_item(item_id, data_to_filter: dict, query_id: str, filters: dict, filter_type, args) -> bool:

    filter_label = {"item": "item", "seller": "seller"}.get(filter_type, "item")

    matching_queries = [
        query
        for query in filters.get("filters", [])
        if query.get("query_id") == query_id
    ]

    if not matching_queries:
        if args.log_excluded:
            logger.info(f"Item [{item_id}] in scope for {len(matching_queries)} [{filter_label}] filter(s)")

        return True

    if args.log_excluded:
        logger.info(f"Item [{item_id}] in scope for {len(matching_queries)} [{filter_label}] filter(s)")

    for query in matching_queries:
        mode = query.get("mode", "exclude")
        rules = query.get("rules", [])

        if mode == "include":
            # All rules must match.
            for rule in rules:
                if args.log_excluded:
                    logger.info(
                        f"Checking item [{item_id}] against [{filter_label}] filter rule [{query_id}][{rule['key']}][{rule['value']}] in [{mode}] mode")

                if not item_matches_rule(data_to_filter, rule):
                    if args.log_excluded:
                        logger.info(f"[ FAIL ✗ ] excluded item [{item_id}] for not matching [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")
                    return False
                else:
                    if args.log_excluded:
                        logger.info(f"[ PASS ✓ ] item [{item_id}] not excluded for current rule. Checking next rule if any")

        elif mode == "exclude":
            # Any matching rule excludes the item.
            for rule in rules:
                if args.log_excluded:
                    logger.info(
                        f"Checking item [{item_id}] against [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")

                if item_matches_rule(data_to_filter, rule):
                    if args.log_excluded:
                        logger.info(f"[ FAIL ✗ ] excluded item [{item_id}] for matching [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")
                    return False
                else:
                    if args.log_excluded:
                        logger.info(f"[ PASS ✓ ] item [{item_id}] not excluded for current rule. Checking next rule if any")

        else:
            raise ValueError(f"Invalid filter mode: {mode}")

    return True


def item_matches_rule(item: dict, rule: dict) -> bool:
    """Match an item's value against a rule, supporting nested keys."""
    key = rule["key"]
    operator = rule["operator"]

    exists, actual = get_nested_value(item, key)

    if operator == "exists":
        return exists

    if not exists:
        logger.info(f"Key [{key}] not found in item [{item.get('id')}]")
        return False

    if operator == "is_null":
        return actual is None

    if operator == "is_empty":
        return isinstance(actual, (str, list, dict)) and len(actual) == 0

    rule_value = rule["value"]

    logger.info(
        f"Rule value(s): [{rule_value}], actual value: [{actual}], operator: [{operator}]")

    return values_match(actual, rule_value, operator)


def values_match(actual, rule_value, operator="equals"):
    """Compare two values using the specified operator."""

    valid_operators = (
        "equals",
        "contains",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
    )

    if operator not in valid_operators:
        raise ValueError(f"Invalid operator: {operator}")

    # String operators
    if operator in ("equals", "contains"):

        if not isinstance(actual, str) or not isinstance(rule_value, str):
            raise ValueError(
                f"Operator '{operator}' requires string values"
            )

        # Support comma-separated rule values.
        # Any one of the values matching is sufficient.
        rule_values = [
            value.strip()
            for value in rule_value.split(",")
            if value.strip()
        ]

        if operator == "equals":
            return any(
                text_utils.normalise(value) == text_utils.normalise(actual)
                for value in rule_values
            )

        if operator == "contains":
            return any(
                re.search(
                    r"\b" + re.escape(text_utils.normalise(value)) + r"\b",
                    text_utils.normalise(actual)
                )
                for value in rule_values
            )

    # Numeric operators
    if operator in (
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
    ):
        # bool is a subclass of int in Python, so explicitly exclude it.
        if (
            isinstance(actual, bool)
            or isinstance(rule_value, bool)
            or not isinstance(actual, (int, float))
        ):
            raise ValueError(f"Operator '{operator}' requires numeric values")

        if operator == "between":
            if not isinstance(rule_value, dict) or set(rule_value.keys()) != {"min", "max"}:
                raise ValueError(
                    "Operator 'between' requires a value with 'min' and 'max' keys"
                )

            minimum = rule_value["min"]
            maximum = rule_value["max"]

            if (
                isinstance(minimum, bool)
                or isinstance(maximum, bool)
                or not isinstance(minimum, (int, float))
                or not isinstance(maximum, (int, float))
            ):
                raise ValueError("'between' min and max must be numeric")

            if minimum > maximum:
                raise ValueError("'between' minimum cannot exceed maximum")

            return minimum <= actual <= maximum

        if (
            isinstance(rule_value, bool)
            or not isinstance(rule_value, (int, float))
        ):
            raise ValueError(f"Operator '{operator}' requires numeric values")

        if operator == "greater_than":
            return actual > rule_value

        if operator == "greater_than_or_equal":
            return actual >= rule_value

        if operator == "less_than":
            return actual < rule_value

        if operator == "less_than_or_equal":
            return actual <= rule_value

    # Equality operators
    if isinstance(actual, str) and isinstance(rule_value, str):
        return text_utils.normalise(actual) == text_utils.normalise(rule_value)

    # Preserve type distinctions: True must not equal 1.
    return type(actual) is type(rule_value) and actual == rule_value


def get_nested_value(data, key):
    """Return (exists, value) for a dot-separated nested key."""
    current = data

    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None

        current = current[part]

    return True, current
