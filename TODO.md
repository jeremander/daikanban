# TODO list

## `v0.1.2`

- Bugs
  - Allow user to set start time before creation time
  - Be able to set null value in `task set`?
- Age-off for completed tasks to prevent displaying too many in board
  - `archived` status? Like `kanban-python`
  - Or set `limit=none` to view these in `completed` column

## `v0.2.0`

- Show number of tasks in each board column
- Settings customization
  - Use `fancy_dataclass`
  - Generic pydantic->TOML serialization (rudimentary)
  - Use system default directory for app-specific configs? XDG?
  - Global config file stored in app folder
  - `settings` subcommand of main CLI to interact with settings
    - Also an option within the shell
  - Updates global `Settings` object whenever it is loaded/updated
  - Which items to include when making new tasks (priority/difficulty/duration can be omitted, with default)
  - Priority/difficulty upper bounds?
  - Default size limit, set of statuses to show
  - Show dates as timestamps or human-readable relative times
  - More flexible datetime parsing
    - E.g. "tomorrow at 3 PM", "yesterday 18:00", "1800 yesterday"
    - Allow things like "next Tuesday"?
- Set up Github Actions, test coverage

## `v0.3.0`

- Default for dark terminal? (E.g. task IDs are too dark)
- Use different scorer for completed tasks?
  - E.g. `priority-rate` would use actual duration rather than expected duration
  - Could actually be the same `TaskScorer` object, but it chooses a different field if completed
  - But then it's less flexible (e.g. might want `completed` board to be chronological)
  - Best solution is to allow different scorers, keyed by `TaskStatus`
  - Short-term: don't display the score by default?
- Error handling
  - Debug mode: env variable to drop into pdb on unhandled exception
- Shell features
  - Simple option for JSON output in `project/task show`
  - Don't show `total_time_worked` in table if the task has never been started
  - Scrollable TUI-type thing for editing project/task fields
    - `proj/task edit [ID]`
    - Opening up terminal editor would work reasonably well, see: [https://github.com/fmoo/python-editor/blob/master/editor.py](python-editor)
  - For advancing status, currently prompts user for time(s)
    - If just a single time, could take it as an optional final argument?
  - Upon task completion, inform user how off their time estimate was.
- Github Actions for automated code-checking

## Future

- Shell features
  - ASCII billboard art is hot garbage
  - Consider having a yes/no user prompt before resetting/deleting a task?
  - Filtering
    - Consider boolean complement operator (`~` or `!`), implicitly ANDed with other constraints?
      - This may be too complicated
  - `task split`: split up a task into multiple tasks
    - Presumably walks through interactive prompts to populate new descriptions for subtasks
      - Keep it as simple as possible (only prompt for description/priority/difficulty/duration, or less)
      - Ask "Add another subtask?" at the end of each one
    - Should formalize "hierarchical names" (e.g. if no spaces are present, just separate with dots?)
    - Could also formalize the parent/child relation, if so desired
  - `board merge` (or direct CLI subcommand): merge two or more boards together
    - Can avoid name collisions by once again assuming a "name hierarchy" convention
    - Could warn about exact duplicates in case both name & description are the same
- Settings
  - Store board-specific settings in file itself?
    - Overrides the global settings
  - Float format for things like scores (rounding, precision)
  - Make colors configurable?
  - Accept "work days," "work weeks," etc. as relative times (not just durations)
    - Would require settings to specify exactly which hours/days are working times
    - (This may be more effort than it's worth)
    - But currently comparisons are kind of wrong: true durations will be in actual time while expected durations may be in *worked* time
- Migrate from `pydantic` to `fancy_dataclass` for simplicity?
- [prompt_toolkit](https://python-prompt-toolkit.readthedocs.io) for better prompt auto-completion, etc.
- Allow custom task status labels?
  - todo/active/paused/complete are still the primary ones; extras would presumably be "sub-statuses" of active
  - What should be the name of this field? "status" would conflict with the existing one. Options:
        1) Use "status", rename the old one to "stage"
        2) Use "active_status", keep the old one the same
- External integrations
  - Query APIs
  - Bidirectional syncing
  - Interface to map between external task metadata and DaiKanban Tasks
  - Need to handle issue assignment (i.e. only pull tasks assigned to you)
  - Platforms
    - Github
    - Gitlab
    - Jira
    - ICS calendar
    - Thunderbird sqlite
- Write more tests
  - Want high coverage of data model, board manipulations
  - Use `hypothesis` to generate random data?
  - Some UI tests (input command -> terminal output), though these can be brittle if output format changes
- Better schema documentation
  - Go into more detail about the meaning(s) of priority/difficulty/duration
- Support task logs
- Analytics
  - Kanban metrics
    - Lead time (todo to complete) & cycle time (active to complete)
      - Per task, and averaged across tasks historically
      - Distributional estimates of these quantities, for forecasting purposes
  - Various throughput metrics
    - number of tasks per time
    - total priority, priority\*difficulty, priority\*duration, per time
- Recurring tasks? A la Pianote.
  - Library of recurring tasks, with simple command to queue them into backlog
- Task depencency
  - Task blocking relation (task requires another tasks to be completed)
  - Prevent cyclic blocking?
  - Prevent completion of a blocked task without its precursors
    - Prompt user to complete all of them at once
  - Score calculation of blocked tasks can be complex
    - Can try to ensure it is less than any of its blockers (but that's hard if score is arbitrary, e.g. =priority)
    - Or just ensure it comes later in the ordering, even if its score is higher
  - Might be overly complicated, but a related concept would be *subtasks*
    - New task field, `parent_task_id` (needs to be updated when task is deleted)
    - All subtasks block their parent task
    - Optionally, the parent task can be automatically completed once the subtasks are
- Import/Export
  - Import
    - Input a task list (e.g. markdown checklist, e.g. Python files with lines matching regex "#\s*TODO")
    - More full-fledged idea would be custom [markdown format](doc/dkmarkdown.md)
    - See kanban-python library for example of this:

    ```lang=python
            config["settings.scanner"] = {
                "Files": ".py .md",
                "Patterns": "# TODO,#TODO,# BUG",
            }
    ```

  - Export pretty output
    - markdown checklist/table
    - HTML static site (maybe unecessary if web app covers it)
- Backup/restore
- Web app
  - `web` subcommand of main CLI
  - `streamlit`? `fastui`?
  - Some cloud solution for syncing your board file
- Notifications
  - Could be *chosen tasks for today*, *tasks due soon*, etc.
  - Send reminders via e-mail (smtplib) or text (twilio/pushover/etc.)
    - The latter may cost money
- NLP to predict difficulty/duration based on name/description/project/tags
