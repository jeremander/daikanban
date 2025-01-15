# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project attempts to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--
Types of changes:
    - Added
    - Changed
    - Deprecated
    - Removed
    - Fixed
    - Security
-->

## [Unreleased]

## [0.2.1]

2025-01-15

### Added

- Github Actions workflow, more lint checking.

### Changed

- Set minimum Python version to 3.10.

### Fixed

- Allow relative times in fractional units (e.g. "in 0.5 hours," "4.5 days ago").

## [0.2.0]

2024-10-05

### Added

- `config` subcommand
  - `new`: create TOML configuration file
  - `path`: show path to the config file
  - `show`: print out config file
  - Can configure directory containing "default" boards.
- `list` subcommand: lists all boards installed in configured board directory.
- Data model updates
  - `Log` attributes:
    - `type` (string): type of the log
  - `Task` and `Project` attributes:
    - `uuid` (UUID4): unique identifier
    - `modified_time` (datetime): time last modified
    - `notes` (list of strings): notes about the task
    - `relations` (list of `Relation`s): arbitrary relations with other projects/tasks
    - `extra` (dict): any extra data associated with the task/project
- Import/export API
  - `import` subcommand: import board from file
  - `export` subcommand: export board to file
  - `daikanban` JSON import/export (standard board format)
  - [taskwarrior](https://taskwarrior.org) JSON import/export
- Environment variable `DKB_DEBUG` (debug mode), if set, will have exceptions emit their full traceback.

### Changed

- More flexible datetime parsing. Now accepts things like "yesterday at 8", "2 days from now at 5 PM", and "last Tuesday".
- Group tasks by status within each column in board view.
- Projects/tasks can now have duplicate names.
- Project/task names cannot be all digits.
- `=` can be used as a field/value delimiter in `project set` and `task set`.
- `board new [NAME_OR_PATH]` fills in the board name or path without prompting.

### Fixed

- Do not allow user to update project/task IDs.

## [0.1.2]

2024-05-31

### Added

- More flexible input:
  - Can provide project/task name directly when creating a new one, skipping prompt for the name.
    - E.g. `project new my-project`, `task new my-task`
  - Can set task start time before creation time (will reset creation time to match start time).
  - Can set null values via `project set [FIELD]` and `task set [FIELD]` with no argument.
  - Can provide comma-separated strings for set inputs, e.g. task `links` and `tags`.
    - Whitespace is stripped off.
- Board display:
  - Can limit completed tasks via `since` keyword.
    - E.g. `board show limit=10 since="1 week ago"`
  - Number of tasks is shown for each task status column.
  - `completed` tasks column shows completion date rather than score.
- `--version` option to display current `daikanban` version.
- Various `pre-commit` hooks.
- Unit tests for prompts, shell, CLI.

### Fixed

- Better error messages for invalid prompt input.
- Return to main shell when keyboard-interrupting prompt loop.

## [0.1.1]

2024-03-27

### Added

- Shell:
  - Include `project` column in task view
  - Include links in default new task prompt
- Basic unit tests for shell interface.

## [0.1.0]

2024-03-17

### Added

- CLI application:
  - `new`: create new board
  - `schema`: display JSON schema
  - `shell`: enter interactive shell
- Shell functionality:
  - Create/load boards
  - Create/delete/read/update board/projects/tasks
  - Change task status
  - Help menu
- [README](README.md) and [CHANGELOG](#changelog).

[unreleased]: https://github.com/jeremander/daikanban/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/jeremander/daikanban/releases/tag/v0.2.1
[0.2.0]: https://github.com/jeremander/daikanban/releases/tag/v0.2.0
[0.1.2]: https://github.com/jeremander/daikanban/releases/tag/v0.1.2
[0.1.1]: https://github.com/jeremander/daikanban/releases/tag/v0.1.1
[0.1.0]: https://github.com/jeremander/daikanban/releases/tag/v0.1.0
