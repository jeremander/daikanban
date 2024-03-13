# Custom DaiKanban Markdown format

## Purpose

- Useful for creating simple task lists in plaintext
- Can include in a Github project so it's casually readable, and can sync with your local (or remote) workflows

## Format

- Hierarchical bullets indicate projects/tasks
- Unclear for now how to interpret different levels (e.g. nested bullets could be markdown lists, or "subtasks")
- Use markers for each bullet to indicate status; two ideas:
  1. Idea 1
     - No checkbox: `todo`
     - Empty checkbox: `active`
     - Filled checkbox: `complete`
  2. Idea 2
     - Empty or no checkbox: `todo`
     - Partial checkbox (`[.]` or `[o]` or `[-]`): `active`
       - Note this is not standard, but there are proposals to make it so
     - Filled checkbox: `complete`
- Some convention for adding metadata
  - Tags: `^mytag` or `#mytag`
  - Links: just pick up usual markdown links
  - Priority/difficulty: numbers in parentheses / square brackets?
  - Timestamps could be tricky since they add clutter, but simple date-only ones might be OK (`3/12/24`)
- Might need some (optional) canonical header to configure how items are interpreted

## Goals

- Standardize file format
- Someday: VSCode/Obsidian plugins to parse/style the format
- Conform to DaiKanban import/export protocol
- Have round-trip fidelity as much as possible:
  - DB -> MD -> DB should be faithful
  - MD -> DB -> MD should be nondestructive, and enrich the original MD with reasonable defaults
