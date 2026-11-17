import logging
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from utils.file_utils import load_yaml
from utils.text_utils import normalise

logger = logging.getLogger(__name__)


def load_filters(filter_type, path):
    try:
        filter_config = load_yaml(path)
        validate_filters(filter_config)

    except ValueError as e:
        logger.error("Invalid filter configuration in %s. Error: %s", path, e)
        sys.exit(1)

    # No YAML content means no filters
    filter_config = filter_config or {"filters": []}

    logger.info(
        "Loaded %s [%s] filter(s) from '%s'",
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

    string_operators = {"equals", "contains"}

    def check_keys(data_arg, required_keys_arg, optional_keys, context_arg):
        if not isinstance(data_arg, dict):
            raise ValueError(f"{context_arg} must be a mapping")

        missing = required_keys_arg - data_arg.keys()
        unexpected = data_arg.keys() - (required_keys_arg | optional_keys)

        if missing:
            raise ValueError(f"{context_arg}: missing keys {sorted(missing)}")

        if unexpected:
            raise ValueError(f"{context_arg}: unexpected keys {sorted(unexpected)}")

    def is_number(value_arg):
        # bool is a subclass of int in Python, so explicitly exclude it.
        return isinstance(value_arg, (int, float)) and not isinstance(value_arg, bool)

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
                {"word_match"},
                rule_context,
            )

            # Exception if 'word_match' is defined for anything but 'contains' operator
            if "word_match" in rule:
                if rule["operator"] != "contains":
                    raise ValueError(
                        f"{rule_context}.word_match is only valid with the 'contains' operator"
                    )

                if not isinstance(rule["word_match"], bool):
                    raise ValueError(
                        f"{rule_context}.word_match must be a boolean"
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

            # Validate string/equality operators.
            elif operator in string_operators:
                value = rule["value"]

                if (
                        not isinstance(value, (str, int, float))
                        or isinstance(value, bool)
                ):
                    raise ValueError(
                        f"{rule_context}.value must be a string or number "
                        f"for operator '{operator}'"
                    )

                value = str(value)

                if not value.strip():
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


def filter_item(item_id, data_to_filter: dict, query_id: str, filters: list, filter_type, args) -> bool:
    filter_label = {"item": "item", "seller": "seller"}.get(filter_type, "item")

    matching_queries = [
        query
        for query in filters
        if query.get("query_id") == query_id
    ]

    if args.log_filtering:
        logger.info(
            f"Item [{item_id}] in scope for {len(matching_queries)} {filter_label} filter(s) - "
            f"[{', '.join(query['query_id'] for query in matching_queries)}]"
        )

    if not matching_queries:
        return True

    for query in matching_queries:
        mode = query.get("mode", "exclude")
        rules = query.get("rules", [])

        if mode == "include":
            # All rules must match.
            for rule in rules:
                if args.log_filtering:
                    logger.info("Checking item [%s] against rule: [%s] on key: [%s] in mode: [%s]", item_id,
                                query_id,
                                rule["key"], mode)

                if not item_matches_rule(data_to_filter, rule, word_match=rule.get("word_match", False)):
                    if args.log_filtering:
                        logger.info(
                            "[ FAIL ✗ ] excluded item [%s] for not matching [%s] filter rule [%s, %s, %s] in [%s] mode",
                            item_id, filter_label, query_id, rule["key"], rule.get("value", "<not required>"), mode)

                    return False

                elif args.log_filtering:
                    logger.info("[ PASS ✓ ] item [%s] not excluded for rule. Checking next rule if any",
                                item_id)

        elif mode == "exclude":
            # Any matching rule excludes the item.
            for rule in rules:
                if args.log_filtering:
                    logger.info("Checking item [%s] against rule: [%s] on key: [%s] in mode: [%s]", item_id,
                                query_id,
                                rule["key"], mode)

                if item_matches_rule(data_to_filter, rule, word_match=rule.get("word_match", False)):
                    if args.log_filtering:
                        logger.info(
                            "[ FAIL ✗ ] excluded item [%s] for matching [%s] filter rule [%s, %s, %s] in [%s] mode",
                            item_id, filter_label, query_id, rule["key"], rule.get("value", "<not required>"), mode)

                    return False

                elif args.log_filtering:
                    logger.info("[ PASS ✓ ] item [%s] not excluded for rule. Checking next rule if any",
                                item_id)

        else:
            raise ValueError(f"Invalid filter mode: {mode}")

    return True


def item_matches_rule(item: dict, rule: dict, word_match=False) -> bool:
    """Match an item's value against a rule, supporting nested keys."""

    key = rule["key"]
    operator = rule["operator"]

    exists, actual = get_nested_value(item, key)

    if operator == "exists":
        return exists

    if not exists:
        logger.info(
            "Key [%s] not found in item [%s]",
            key,
            item.get("id"),
        )
        return False

    if operator == "is_null":
        return actual is None

    if operator == "is_empty":
        return isinstance(actual, (str, list, dict)) and len(actual) == 0

    rule_value = rule["value"]

    logger.info(
        "Rule value(s): [%s], actual value: [%s], operator: [%s]%s",
        rule_value,
        actual,
        operator,
        f", word_match: [{word_match}]" if operator == "contains" else "",
    )

    return values_match(actual, rule_value, operator, word_match)


def values_match(actual, rule_value, operator="equals", word_match=False):
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

    def is_number(value):
        # bool is a subclass of int in Python, so explicitly exclude it.
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def numeric_string_equal(number, string):
        """Compare a numeric value with a numeric string."""

        try:
            return Decimal(str(number)) == Decimal(string.strip())
        except (InvalidOperation, ValueError):
            return False

    # Equality operator.
    if operator == "equals":

        # Do not allow booleans to be treated as numbers.
        if isinstance(actual, bool) or isinstance(rule_value, bool):
            return type(actual) is type(rule_value) and actual == rule_value

        # Numeric equality.
        if is_number(actual) and is_number(rule_value):
            return actual == rule_value

        # String equality.
        if isinstance(actual, str) and isinstance(rule_value, str):
            return any(
                normalise(value.strip())
                == normalise(actual)
                for value in rule_value.split(",")
                if value.strip()
            )

        # Support numeric API values against quoted numeric YAML values,
        # and vice versa.
        if is_number(actual) and isinstance(rule_value, str):
            return any(
                numeric_string_equal(actual, value)
                for value in rule_value.split(",")
                if value.strip()
            )

        if isinstance(actual, str) and is_number(rule_value):
            return numeric_string_equal(rule_value, actual)

        return False

    # Contains operator.
    if operator == "contains":

        if (
                isinstance(actual, bool)
                or isinstance(rule_value, bool)
                or not isinstance(actual, (str, int, float))
                or not isinstance(rule_value, (str, int, float))
        ):
            raise ValueError(
                f"Operator '{operator}' requires string or numeric values. "
                "Check values from Vinted API and in rule config"
            )

        actual = normalise(str(actual))
        rule_value = str(rule_value)

        # Support comma-separated rule values.
        # Any one of the values matching is sufficient.
        rule_values = [
            normalise(value.strip())
            for value in rule_value.split(",")
            if value.strip()
        ]

        if word_match:
            return any(
                re.search(
                    r"\b" + re.escape(value) + r"\b",
                    actual,
                )
                for value in rule_values
            )

        # Substring matching.
        return any(
            value in actual
            for value in rule_values
        )

    # Numeric comparison operators.
    # "equals" is also an operator (see above)
    if operator in (
            "greater_than",
            "greater_than_or_equal",
            "less_than",
            "less_than_or_equal",
            "between",
    ):

        if not is_number(actual):
            raise ValueError(
                f"Operator '{operator}' requires numeric actual values. "
                "Check values from Vinted API"
            )

        if operator == "between":
            if (
                    not isinstance(rule_value, dict)
                    or set(rule_value.keys()) != {"min", "max"}
            ):
                raise ValueError(
                    "Operator 'between' requires a value with "
                    "'min' and 'max' keys"
                )

            minimum = rule_value["min"]
            maximum = rule_value["max"]

            if not is_number(minimum) or not is_number(maximum):
                raise ValueError("'between' min and max must be numeric")

            if minimum > maximum:
                raise ValueError("'between' minimum cannot exceed maximum")

            return minimum <= actual <= maximum

        if not is_number(rule_value):
            raise ValueError(
                f"Operator '{operator}' requires numeric values. "
                "Check values in rule config"
            )

        if operator == "greater_than":
            return actual > rule_value

        if operator == "greater_than_or_equal":
            return actual >= rule_value

        if operator == "less_than":
            return actual < rule_value

        if operator == "less_than_or_equal":
            return actual <= rule_value

    return False


def get_nested_value(data, key):
    """Return (exists, value) for a dot-separated nested key."""

    current = data

    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None

        current = current[part]

    return True, current
