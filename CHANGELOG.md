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

## [0.1.2]

### Added

- Various `pre-commit` hooks.
- Unit tests for prompts, shell, CLI

### Fixed

- Better error messages for invalid prompt input
- Return to main shell when keyboard-interrupting prompt loop

## [0.1.1]

### Added

- Shell:
  - Include `project` column in task view
  - Include links in default new task prompt
- Basic unit tests for shell interface

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
- [README](README.md) and [CHANGELOG](#changelog)

[unreleased]: https://github.com/jeremander/daikanban/compare/v0.1.0...HEAD
[0.1.1]: https://github.com/jeremander/daikanban/releases/tag/v0.1.1
[0.1.0]: https://github.com/jeremander/daikanban/releases/tag/v0.1.0
