# Vinted Scanner Plus

**Vinted Scanner Plus** is a lightweight Python scanner that polls any **Vinted** marketplace for newly listed items matching your search queries and sends **Telegram** notifications on each run, compensating for Vinted's lack of real-time alerts.

It introduces a flexible and powerful rules engine to alert only on listings that match your criteria, while keeping a record of previously seen items to avoid duplicates. This enhanced functionality, over Vinted's default search, ensures you csnap a bargain as soon as an item is listed!

This project is a fork of Vinted Scanner, but not part of the fork network. All credit goes to the respective authors. See [Why another Vinted Scanner?](#why-another-vinted-scanner) and [credits ](#credits-and-licence) for details.

![Python](https://img.shields.io/badge/python-3.14-blue?style=flat-square&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/notifications-Telegram-26A5E4?style=flat-square&logo=telegram&logoColor=white)
![License](https://img.shields.io/badge/license-GPL--3.0-green?style=flat-square)

---

## Table of contents

- [Disclaimer](#disclaimer)
- [Why another Vinted Scanner?](#why-another-vinted-scanner)
- [How it works](#how-it-works)
- [Structure](#structure)
- [Quick start](#quick-start)
- [Configuration](#configuration)
  - [CLI arguments](#cli-arguments)
  - [Building queries](#building-queries)
  - [Rules engine](#rules-engine)
  - [Finding available attributes](#finding-available-attributes)
- [Notifications](#notifications)
  - [Telegram](#telegram)
  - [Message options](#message-options)
  - [State file](#state-file)
- [Running on a schedule](#running-on-a-schedule)
  - [GitHub Actions](#github-actions)
- [Known quirks and limitations](#known-quirks-and-limitations)
- [Troubleshooting](#troubleshooting)
- [Credits and licence](#credits-and-licence)

---

## Disclaimer

> [!WARNING]
> Vinted may employ legitimate traffic management strategies if you're querying the Vinted API too frequently. It is possible to be flagged by any of these strategies and potentially be banned. Use your judgement to configure the scanner so you do not breach any limits in place. The same may hold for Telegram and other platforms used.

> [!NOTE]
> This independent project is not affiliated with or endorsed by Vinted. It uses undocumented internal API endpoints that may change without notice. Use the scanner responsibly and comply with the rules applicable to your Vinted marketplace. Contributors to this project take no liability, under any circumstances, implied or otherwise, for consequences of its use.

## Why another Vinted Scanner?

**TODO:** expand, and add future scope

- Full refactor for future extensibility
- No hardcoded values
- All config in YAML
- Exposing all item and seller attributes from Vinted API response
- Flexible and powerful rules engine, with inclusive/exclusive filters
- Full logging, including for the rules engine
- Naive rate limiting strategy
- User isolation*
- Config validation*
- Free and reliable job scheduling

\* Work-In-Progress (see [Known quirks and limitations ](#known-quirks-and-limitations))

## How it works

On run, `vinted_scanner_plus.py` does the following:

1. Loads a config file `configs.yaml`, which in turn points to all other files required
2. Loads platform config, search queries, item and seller filter rules, and a CSV state file that contains previously seen items
3. Opens a session to your chosen Vinted url (with the appropriate headers) to search for items
4. For every query entry in `search_config.yaml`, requests available items using `{vinted.vinted_api_url}/svc-catalogue/items`
5. For each item returned up to a maximum N, where N = `search.max_items`:
   - Skips it if the item has already been seen/notified according to the state file
   - Parses the HTML from the item page at `{vinted_url.vinted_url}/items/`, and retrieves the full description and upload time of the item
   - Looks-up the seller information using `{vinted.vinted_api_url}/api/v2/users/`
   - Checks the item against the 'Items' rule engine; keeping it a candidate or excluding it (see [Rules engine](#rules-engine))
   - Checks the item against the 'Seller' rule engine; keeping it a candidate or excluding it (see [Rules engine](#rules-engine))
   - In both instances, it logs which exact rules in config the item matched, and why the item was included or excluded
   - If the item has not been excluded at the end, then:
     - If notifications are enabled, it sends a Telegram message with optional long description
     - If the state file is enabled, it records the item in the csv file as previously seen
6. Logs a summary of stats for the query e.g. items found, items excluded, etc.

Logging goes to **stdout** and file with timestamps.

## Structure

```text
VintedScannerPlus/
├── .github/
│   ├── workflows/
│   │   ├── _vinted-scanner-plus-call-template.yaml : GitHub Actions workflow template that accepts inputs, setups an env, loads the config (from Actions secrets and variables), runs the scanner, and merges files back to the repo
│   │   └── vinted-scanner-plus-dispatch-sample.yam : Sample GitHub Actions template to run the 'call-template' on a schedule
├── configs/
│   ├── configs.yaml : List of config file paths to be loaded into the scanner 
│   ├── notification_config.yaml : Set message options and Telegram token. Only store on disk for local use or with a test token; never commit to Git. For production runs on GitHub, store in an Actions secret
│   └── search_config.yaml : Vinted platform parameters, and queries to search
├── filters/
│   ├── item_filters.yaml : Optional filters on item attributes for each Vinted query. Used to include or exclude items from the final result set
│   └── seller_filters.yaml : Optional filters on seller attributes for each Vinted query. Used to include or exclude items from the final result set
├── managers/
│   ├── config_manager.py : Load all config files
│   ├── filter_manager.py : Load and validate yaml item and seller filters, and process items in the rule engine 
│   ├── logging_manager.py : Logging setup and helper functions to log the run, including detailed processing by the rule engine
│   ├── notification_manager.py : Send notifications to defined connectors e.g. Telegram
│   ├── query_manager.py : Main entry point to process each query
│   ├── state_manager.py : Load a CSV of previously seen/notified items, and append new items to it
│   └── vinted_api_manager.py : Initialise a Vinted session, run a search query, and retrieve item and seller details
├── state/
│   └── already_notified_items.csv : Previously seen/notified items stored as CSV
├── utils/
│   ├── file_utils.py : Yaml load function, and other file handling operations
│   └── text_utils.py : Text handling functions
├── README.md : this read me
├── vinted_scanner_plus.log : log file
└── vinted_scanner_plus.py : Main entry point for the app. Accepts following CLI args: --log-path --log-filtering --enable-notifications --disable-state-file
```

## Quick start

**Requirements**

- Python 3.14 or newer
- A Telegram bot token and a chat ID (see [Telegram](#telegram))
- Dependencies from `requirements.txt`:
  - `beautifulsoup4`
  - `currency-symbols`
  - `pyyaml`
  - `pycountry`
  - `requests`

1. To get started, clone the repo and install required packages:
```bash
git clone https://github.com/alan-s/vinted-scanner-plus.git
cd vinted-scanner-plus

pip3 install -r requirements.txt
```
Configure all settings (see [Configuration](#configuration)), but at a minimum, you'll need to set the marketplace and define a search query (see [Marketplace and Search settings](#marketplace-and-search-settings)).

Run Vinted Scanner Plus, with optional command line args.
```bash
python3 vinted_scanner_plus.py [--log-path --log-filtering --enable-notifications --disable-state-file]
```
Recommendation is to always run with `--log-filtering`, and for the first run, set `--disable-state-file` but not `--enable-notifications`. Once all config has been confirmed, then enable notifications.

Add a `.gitignore` if you plan to push your own fork:

```gitignore
configs/
filters/
state/
__pycache__/
```

## Configuration

- All config files use standard YAML format with a `.yaml` extension. While the YAML load function validates syntax, it doesn't validate content
- The state file used to store previous items is CSV format with a `.csv` extension
- Each config file has guidance for further details and what each of the parameters achieve

1. edit `search_config.yaml`. Add Vinted urls, locale (if required), and define search queries 
2. add Telegram token and chat id to `notification_config.yaml` (do not commit tokens to git. Use Actions for GitHub hosting)
3. (optional) add item filter rules to `item_filters.yaml` (see [Rules engine](#rules-engine))
4. (optional) add seller filter rules to `seller_filters.yaml` (see [Rules engine](#rules-engine))
5. (optional) edit configs.yaml to point at all other files

### CLI arguments

Optional args:

- `--log-path` : Set the desired log path to use. By default, a log named `vinted_scanner_plus.log` is created in the current working directory
- `--log-filtering` : Enable logging when filtering items. By default, logging of filters is off
- `--enable-notifications` : Enable notifications to external connectors e.g. Telegram. By default, no notifications are sent
- `--disable-state-file` : Disable storing previously notified items in a state file. By default, notified items are stored

### Marketplace and Search Settings

Target a specific marketplace by entering its urls in `search_config.yaml`:

| Key              | Use                                                    | Options  | 
|------------------|--------------------------------------------------------|----------|
| `vinted_url`     | Set to your country's url (e.g. co.uk, .fr, .es, etc.) |          |
| `vinted_api_url` | Url of the api for the same marketplace                |          |
| `locale`         | Marketplace locale value e.g. en-GB, it-IT, etc.       | Optional |

Configure the search parameters, in the same file, for optimal search strategy:

| Key                                     | Use                                                                                                                | Options  | 
|-----------------------------------------|--------------------------------------------------------------------------------------------------------------------|----------|
| `pages`                                 | Number of pages to scan for each search query                                                                      |          |
| `per_page`                              | Number of items per page to return. 24 with 'order' by 'relevance' appears to be a good combination                |          |
| `max_items`                             | Maximum number of items to process (and potentially notify) for each search query. Useful to ensure an upper bound | Optional |
| `min_delay_seconds` `max_delay_seconds` | Optional random delay (between min and max seconds) to reduce likelihood of rate-limiting by the Vinted API        | Optional |

### Building queries

Each key of a `queries` entry in `search_config.yaml` maps to a query-string parameter sent to the Vinted API. Any combination can be valid, supplied in any order, and keys can support multiple values e.g. `attribute_ids[catalog]`.

| Key                      | Use                                                                          | Options                                                                                 | 
|--------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| `{query_id}`             | Set a unique identifier. Linked to seller and item filters                   |                                                                                         |
| `search_text`            | Free-text keywords. Leave empty to match everything within the other filters |                                                                                         |
| `attribute_ids[filter]`* | Set of dynamic Vinted filters to use                                         |                                                                                         |
| `order`                  | How to order the results                                                     | `newest_first`, `relevance`, `price_high_to_low` or `price_low_to_high`. `newest_first` |
\* multiple entries supported

**Notes on search queries**

- All query attributes are optional. However, this will return a random set of items (as decided by the Vinted API)
- Any key can be sent to the API, even non-existent keys — the dict is forwarded verbatim
- The Vinted API uses dynamic filters for `attribute_ids[filter]` i.e. based on category and currently listed products, so the applicable filters depend on the items, which either apply and will filter the set, or will exclude results where the filter is not applicable e.g. `size` for category `board games`

Examples:
```yaml
queries:
# Free-text search for "Monopoly" in ALL categories, where price (excluding any fees) is between 4 and 16 inclusive; ordered by most recently listed
  - query_id: monopoly_board_game
    search_text: Monopoly
    price_from: 4
    price_to: 16    
    order: newest_first
    
# Free-text search for "Monopoly" where price (excluding any fees) is between 4 and 16 inclusive AND in category 4881 (board games); ordered by most recently listed
  - query_id: monopoly_board_game
    search_text: Monopoly
    attribute_ids[catalog]: 4881
    price_from: 4
    price_to: 16
    order: newest_first
    
# Free-text search for "Monopoly" where price (excluding any fees) is between 4 and 16 inclusive, in category 4881 (board games) AND with brand id 1317890 (C'Mon); ordered by most recently listed
  - query_id: monopoly_board_game
    search_text: Monopoly
    attribute_ids[catalog]: 4881
    attribute_ids[brand]: 1317890
    price_from: 4
    price_to: 16
    order: newest_first
    
# Free-text search for "Monopoly" where price (excluding any fees) is between 4 and 16 inclusive, in category 4881 (board games), with brand id 1317890 (C'Mon) OR 114196 (Hasbro); ordered by most recently listed    
  - query_id: monopoly_board_game
    search_text: Monopoly
    attribute_ids[catalog]: 4881
    attribute_ids[brand]: 1317890,114196
    price_from: 4
    price_to: 16
    order: newest_first
]
```

### Rules engine

The core features of Vinted Scanner Plus is a flexible and powerful rule engine that provides the ability to filter results, even more than what the Vinted API provides. For example, a common complaint from users is the inability to filter by country on the Vinted UI or the API.

The rules engine provides an additional level of filtering on both item and seller details, defined in `item_filters.yaml` and `seller_filters.yaml`. So in the example above, a rule can be set to include or exclude items/sellers from the United States using `country_iso_code`.

| Key                     | Use                                                                                                             | Options                                                                                                                                                          | 
|-------------------------|-----------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `query_id`              | Same as your query_id in `search_config.yaml`                                                                   |                                                                                                                                                                  |
| `mode`                  | include or exclude the item if the rules evaluate to `True`                                                     | `include`, `exclude` <br>**include**: all rules must match for the item to be included <br>**exclude**: a match against any rule excludes the item               |
| `rules.key`*            | Key name for the attribute to filter (additionally accepts nested keys using "." e.g. item.title)               |                                                                                                                                                                  |
| `rules.operator`        | Available operators for the comparison                                                                          |                                                                                                                                                                  |
| - `string operators`    | Normalised case-insensitive exact match, or substring match (partial or full word matching. Default is partial) | `equals`, `contains` <br>**equals**: exact match <br>**contains**: substring match (default is partial matching. Add optional `word_match: false` for full word) |
| - `numeric operators`   | Must be a numeric type                                                                                          | `equals`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `between`                                                                  |
| - `'nothing' operators` | Whether the key exists, or explictly equals NULL, or whether it is empty                                        | `exists`, `is_null`, `is_empty`                                                                                                                                  |
| `rules.value`           | The value to use in the comparison operator (additionally accepts csv list for keys with string value)          |                                                                                                                                                                  |
\* multiple entries supported

> [!TIP]
> Utilise query filters, to narrow the search results returned by the Vinted API (see [Building queries](#building-queries)), prior to utilising custom filters. This will reduce the number of lookups against the Vinted API and the likelihood of being rate limited.

Examples:
```yaml
# Exclude any items where the item title contains "2nd edition"
- query_id: monopoly_board_game
  mode: exclude
  rules:
    - key: title
      operator: contains
      value: 2nd edition
      #word_match: false (add for full word matching)
    
# Exclude any items where the seller country is "US" or "AU"
- query_id: monopoly_board_game
  mode: exclude
  rules:
    - key: country_iso_code
      operator: equals
      value: US,AU

# You can define multiple rules in a single rule set
# Include only items where seller country is "US", and seller feedback is between 75 and 100 inclusive
- query_id: monopoly_board_game
  mode: include
  rules:
    - key: country_iso_code
      operator: equals
      value: US
    - key: positive_feedback_count
      operator: between        
      value:
        min: 75
        max: 100
        
# You can even define multiple rule sets for a single query, even with different modes
# Include any items where the title contains "2nd edition" or "Second Edition", but exclude anywhere more than 30 users have it as a favourite
- query_id: monopoly_board_game
  mode: include
  rules:
  - key: title
    operator: contains
    value: 2nd edition,Second Edition
- query_id: monopoly_board_game
  mode: exclude
  rules:
  - key: favourite_count
    operator: greater_than
    value: 30
```

**Notes on rules**

- Ensure item and seller filters are in `item_filters.yaml` and `seller_filters.yaml` respectively. You cannot mix item and seller filters in the same config file
- String operators are normalised and case-insensitive
- `Contains` is partial substring matching by default i.e. for a rule value *"dice"*, item title *"game with dice"* will be a match and *"game with dices"*. Use optional key `word_match: false` per rule for full word
- Any type mismatch, between API value and config will cause a `ValueError`
- Accepted boolean types are `true` or `false` only. 1 and 0 are not treated as equivalent

#### Logging

As the rules engine is very flexible and many combinations of item and seller rules can be defined, it's recommended `--log-filtering` is set on the command line at all times. This logs useful information that can help test and troubleshoot how each rule defined is impacting the end results and thus notifications.

Example logging:
```log
2026-11-16 17:16:03.668 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:03.668 INFO Started processing item [10563369430]
2026-11-16 17:16:03.669 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:03.669 INFO Checking item [10563369430] against [item] filters
2026-11-16 17:16:03.669 INFO Item [10563369430] in scope for 1 item filter(s) - [monopoly_stranger_things]
2026-11-16 17:16:03.669 INFO Checking item [10563369430] against rule: [monopoly_stranger_things] on key: [title] in mode: [exclude]
2026-11-16 17:16:03.669 INFO Rule value(s): [cluedo], actual value: [Stranger Things Cluedo board game Netflix edition sealed], operator: [contains], word_match: [True]
2026-11-16 17:16:03.669 INFO [ FAIL ✗ ] excluded item [10563369430] for matching [item] filter rule [monopoly_stranger_things, title, cluedo] in [exclude] mode
2026-11-16 17:16:03.669 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:03.669 INFO Completed processing item [10563369430]
2026-11-16 17:16:03.670 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:03.670 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:03.670 INFO Started processing item [10192559570]
2026-11-16 17:16:03.670 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:03.670 INFO Checking item [10192559570] against [item] filters
2026-11-16 17:16:03.670 INFO Item [10192559570] in scope for 1 item filter(s) - [monopoly_stranger_things]
2026-11-16 17:16:03.670 INFO Checking item [10192559570] against rule: [monopoly_stranger_things] on key: [title] in mode: [exclude]
2026-11-16 17:16:03.670 INFO Rule value(s): [cluedo], actual value: [Monopoly stranger things], operator: [contains], word_match: [True]
2026-11-16 17:16:03.670 INFO [ PASS ✓ ] item [10192559570] not excluded for rule. Checking next rule if any
2026-11-16 17:16:03.670 INFO Getting seller details for item [10192559570]
2026-11-16 17:16:03.794 INFO Vinted seller API called: https://www.vinted.co.uk/api/v2/users/309714452
2026-11-16 17:16:03.794 INFO Checking item [10192559570] against [seller] filters
2026-11-16 17:16:03.795 INFO Item [10192559570] in scope for 1 seller filter(s) - [monopoly_stranger_things]
2026-11-16 17:16:03.795 INFO Checking item [10192559570] against rule: [monopoly_stranger_things] on key: [country_iso_code] in mode: [exclude]
2026-11-16 17:16:03.795 INFO Rule value(s): [US,AU], actual value: [GB], operator: [equals]
2026-11-16 17:16:03.795 INFO [ PASS ✓ ] item [10192559570] not excluded for rule. Checking next rule if any
2026-11-16 17:16:03.795 INFO Item [10192559570] meets all selection filters and no exclusions apply
2026-11-16 17:16:03.795 INFO Getting additional item details from Vinted
2026-11-16 17:16:04.259 INFO Vinted item endpoint called: https://www.vinted.co.uk/items/10192559570-monopoly-stranger-things
2026-11-16 17:16:04.370 ERROR Missing 'bot_token' or 'chat_id' in notification config at 'F:\GitHub\vinted-scanner-plus\configs\notification_config.yaml'
2026-11-16 17:16:04.370 ERROR Failed to send notification for item [10192559570]
2026-11-16 17:16:04.370 INFO --------------------------------------------------------------------------------
2026-11-16 17:16:04.370 INFO Completed processing item [10192559570]
2026-11-16 17:16:04.370 INFO --------------------------------------------------------------------------------
```


### Finding available attributes

To understand the available search and filter attributes, you can inspect the various Vinted API endpoint responses, and update the config accordingly.

The logs include the url calls made to the search API, for example [this](https://api.vinted.co.uk/svc-catalogue/items?search_text=Monopoly&attribute_ids%5Bcatalog%5D=4881&price_from=5&price_to=20&order=newest_first). You can enter this url into a browser and then copy-and-paste the entire JSON into something like [Online JSON Viewer
](https://jsonformatter.org/json-viewer). Inspect all the available fields - which will include categories, brands, or filters which you can then use in the search query.

The same approach can be used for the items ( `{vinted_url.vinted_url}/items/`) and user (`{vinted.vinted_api_url}/api/v2/users/`) endpoints, and the fields filtered using the rules engine.

### Notifications

#### Telegram

> [!WARNING]
> Never commit production tokens to Git. For production runs on GitHub, store tokens in an Actions secret (see [Running on a schedule](#running-on-a-schedule))

1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token into `telegram_bot_token`.
2. Get your chat ID:
   - **Direct messages:** send any message to your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `message.chat.id`.
   - **Groups:** add the bot to the group, post a message, and use the same endpoint. Group IDs are negative.
   - **Channels:** add the bot as an administrator and use the `@channelname` or the numeric `-100…` ID.
3. Put the value in `telegram_chat_id`.

#### Message options

- Messages are sent as HTML. When the listing has a photo the script uses `sendPhoto` with the caption below; otherwise it falls back to `sendMessage`
- If set to `true`, `message.include_description` in `notification_config.yaml` will add the full item description to the message body in the notification

#### State file

`already_notified_items.csv` (the value of `configs.yaml` -> `config.file_name`) is a CSV of items previously seen/notified. It appends each new item to the file, recording ID, title, and price, one per line. 
- Delete entries or the file to reset the scanner — the next run will treat everything it finds as new.

## Running on a schedule

You can schedule Vinted Scanner Plus like any other script on your local host, supplying the desired CLI arguments. Take note of the [disclaimer](#disclaimer) with regards hitting APIs too frequently. However, you can also utilise GitHub workflows to schedule and run the scanner for free.

### GitHub Actions

Probably one of the better approaches is to run the scanner directly in GitHub, using GitHub Actions, if you do not have access to your own server. Crucially, we need to ensure the state file (and the log) is committed back to `main`. We need two workflow files; the first defines the scan job, and the second the user and schedule. 

**Job**

**`_vinted-scanner-plus-job-template.yaml`** is a reusable workflow (`workflow_call`) taking as input several repo variables and one secret to define the required job steps. It:

1. Checks out the repo and sets up Python 3.14
2. Installs `requirements.txt`
3. If not present, creates `configs`, `filters` and `state` directories 
4. Writes the contents of `CONFIGS`, `SEARCH_CONFIG`, `ITEM_FILTERS` and `SELLER_FILTERS` repo variables to respective YAML files in `configs/` and `filters/`. Also writes `NOTIFICATION_CONFIG` secret verbatim into `notification_config.yaml`
5. Runs `python3 vinted_scanner_plus.py` after injecting any command line args from calling workflows
6. Merges the run's state file (default `already_notified_items.csv)`) with the copy on `origin/main`. Commits as `github-actions[bot]` and pushes
7. Does the same for `vinted_scanner_plus.log`

It declares `permissions: contents: write` so the default `GITHUB_TOKEN` can push, and a `concurrency` group of `vinted-scanner-plus-main` with `cancel-in-progress: false`, so runs from different profiles queue up instead of racing each other to push.

With the job template configured, schedule it using a profile workflow.

**User Profile**

**`vinted-scanner-plus-user-template.yaml`** is a workflow (`workflow_dispatch`) that can be used to schedule the job template above. Every additional template file (and set of repo config variables) can be used to run/schedule a different user. For example:

| Workflow File                     | Schedule (UTC)        | Actions variables and secrets                                                                                                                                                                    |
|-----------------------------------|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `vinted-scanner-plus-user01.yaml` | `7,22,37,52 * * * *`  | **variables:** <br> `VSP_USER01_CONFIGS `<br> `VSP_USER01_SEARCH_CONFIG` <br> `VSP_USER01_ITEM_FILTERS` <br> `VSP_USER01_SELLER_FILTERS` <br> **secrets:** <br> `VSP_USER01_NOTIFICATION_CONFIG` |
| `vinted-scanner-plus-user02.yaml` | '12,27,42,57 * * * *' | `_USER02_` variables                                                                                                                                                                             |


Both are every 15 minutes, offset by 5 minutes so the two jobs don't collide on the shared state file. Both also expose `workflow_dispatch` for manual runs from the Actions tab.

**Adding a profile:**

1. Create the listed repo variables and secret in your repo, and paste the *entire contents* of that user's configs into each respective variable
2. Copy one of the user template files, rename it, pick cron minutes that don't clash with the existing ones, and point `[CONFIGS, SEARCH_CONFIG, ITEM_FILTERS, SELLER_FILTERS]`, `[NOTIFICATION_CONFIG]` at the repo variables/secrets
3. Add `--enable-notifications` to the `args` when ready to enable notifications

```yaml
name: Vinted Scanner Plus User Template

on:
  workflow_dispatch:
  schedule:
    - cron: "7,22,37,52 * * * *" # remove this schedule if using 'workflow_dispatch' with external schedule

permissions:
  contents: write

jobs:
  scan:
    uses: ./.github/workflows/_vinted-scanner-plus-job-template.yaml

    with:
      args: "--log-filtering" #--enable-notifications when ready to send notifications
      log_path: "vinted_scanner_plus.log" # leave as file name to output to app root

      CONFIGS: ${{ vars.VSP_USER01_CONFIGS }}
      SEARCH_CONFIG: ${{ vars.VSP_USER01_SEARCH_CONFIG }}
      ITEM_FILTERS: ${{ vars.VSP_USER01_ITEM_FILTERS }}
      SELLER_FILTERS: ${{ vars.VSP_USER01_SELLER_FILTERS }}

    secrets:
      NOTIFICATION_CONFIG: ${{ secrets.VSP_USER01_NOTIFICATION_CONFIG }}  
```

Notes on the CI setup:

- Cron in GitHub Actions is **UTC**, and scheduled runs are best-effort, not guaranteed, on a free tier — they are frequently delayed or dropped. The recommended approach is to schedule using an external source (see [Scheduling with 'workflow_dispatch'](#scheduling-with-workflow_dispatch))
- Since each run loads configs from dynamic paths, there is full user isolation for queries, state, filters and log file
- Scheduled workflows are disabled automatically after 60 days without repository activity. The state-file commits count as activity, so this normally takes care of itself.
- Under Settings → Actions → General, workflow permissions must allow read *and* write for the push step to succeed.

### Scheduling with `workflow_dispatch`

Any runs scheduled through GitHub using the `schedule` trigger are frequently delayed or dropped on the free tier, making it less-than-ideal for reliable monitoring; it isn't recommended.

Instead, define a schedule externally, and use it to call the GitHub API. GitHub almost always run the workflow when the `workflow_dispatch` trigger is called, making it a reliable and free method for monitoring. 

To configure:
1. Ensure `workflow_dispatch` is defined in the `vinted-scanner-plus-user-template.yaml` (and remove or comment out the `schedule` block)
2. Set up an access token on your repo, for example, `Settings > Developer Settings > Personal access tokens > Fine-grained token`
   1. Enter a token name, select your repo under `Repository access` and ensure the read/write permission is granted for `Actions`. Copy the `github_pat_` token
3. Configure an external scheduler to call the GitHub API. Something simple, free, and reliable, such as [cron-job.org](https://cron-job.org/) is ideal
   1. Assuming you've created a free account with [cron-job.org](https://cron-job.org/), add a new cronjob with a title
   2. Set `URL`: `https://api.github.com/repos/{your_username}/{repo_name}/actions/workflows/vinted-scanner-plus-user-template.yaml/dispatches` 
   3. Define the desired schedule e.g. `7,22,37,52 * * * *`
   4. Under `Advanced`, add the following `Header` key:value pairs
   ```
    Accept : application/vnd.github+json
    Authorization : Bearer {your_token}
    Content-Type : application/json
    User-Agent : CronJob-Trigger
    ```
   5. `Request method`: `POST`
   6. `Request body`: `{"ref": "main"}`
4. Save and test

This job will now run on the defined schedule, use your access token to call the GitHub API, and then so a workflow run scheduled (with high likelihood!).

## Known quirks and limitations

Things the code does today that are worth being aware of before you rely on it:

- **Config validation needs improvement.** Currently, it's limited and some assumptions are assumed on user entry
- **Single notification token and state file used.** Currently, all query notifications are sent to a single Telegram account and state is saved in a single file
- **State file and logs are visible on a public repo,** so everyone can see the IDs of the listings you have been tracking. Make your repo private if that is a concern
- **Uses an unofficial API.** Vinted publishes no documented public API. Endpoint paths, parameter names and response shapes can change without notice
- **Two requests are made per new item.** Item and seller details are fetched individually, so a run that discovers many new items makes many calls in quick succession. Aggressive polling can get you rate-limited or blocked. Keep the interval reasonable and check the platform's terms before running this at scale (see [Disclaimer](#disclaimer))
- **Vinted `svc-catalogue/items` endpoint when used with `order : relevance` is non-deterministic**, so do not be confused if the same query returns different, but tangential results on each run, even in short succession
- **A small number of Telegram notifications fail**, and further investigation is required. Possible issue with the image content sent to the Telegram sendPhoto API

## Troubleshooting


## Credits and licence

This project is a fork of [michelepinto/VintedScanner](https://github.com/michelepinto/VintedScanner) by Michele Pinto, which itself is a fork of [drego85/VintedScanner](https://github.com/drego85/VintedScanner) by Andrea Draghetti. All credit goes to the respective authors.

While derived from those projects, this repository is detached from the GitHub fork network because it has been substantially refactored, its scope differs from other forks, and it is unlikely to push changes back upstream.

Released under the **GNU General Public License v3.0**.
