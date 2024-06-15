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

### Changed

- More flexible datetime parsing. Now accepts things like "yesterday at 8", "2 days from now at 5 PM", and "last Tuesday".

## [0.1.2]

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

### Added

- Shell:
  - Include `project` column in task view
  - Include links in default new task prompt
- Basic unit tests for shell interface.

## [0.1.0]

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

[unreleased]: https://github.com/jeremander/daikanban/compare/v0.1.0...HEAD
[0.1.1]: https://github.com/jeremander/daikanban/releases/tag/v0.1.1
[0.1.0]: https://github.com/jeremander/daikanban/releases/tag/v0.1.0
