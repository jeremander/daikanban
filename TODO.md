# TODO list

## `v0.1.0`

- Small QoL improvements
  - Set widths for each help menu separately
  - Accept now/today/tomorrow/yesterday as valid dates, also month/year durations
  - Relax URL parsing to infer scheme if missing (default https?)
  - Fuzzy matching of names in prompts, and as filter keys
- Create a `README` and `CHANGELOG`
- Upload to PyPI

## Future

- Github Actions for automated code-checking
- Shell features
  - Filtering
    - `task show` list view should also allow filtering by status/project/tag, and limit number
    - Consider boolean complement operator (`~` or `!`), implicitly ANDed with other constraints?
      - This may be too complicated
    - Consider having a yes/no user prompt before resetting/deleting a task?
  - Simple option for JSON output in `project/task show`
  - `task split`: split up a task into multiple tasks
    - Presumably walks through interactive prompts to populate new descriptions for subtasks
      - Keep it as simple as possible (only prompt for description/priority/difficulty/duration, or less)
      - Ask "Add another subtask?" at the end of each one
    - Should formalize "hierarchical names" (e.g. if no spaces are present, just separate with dots?)
    - Could also formalize the parent/child relation, if so desired
  - `board merge` (or direct CLI subcommand): merge two or more boards together
    - Can avoid name collisions by once again assuming a "name hierarchy" convention
    - Could warn about exact duplicates in case both name & description are the same
  - Scrollable TUI-type thing for editing project/task fields
    - `proj/task edit [ID]`
    - Opening up terminal editor would work reasonably well, see: [https://github.com/fmoo/python-editor/blob/master/editor.py](python-editor)
  - ASCII billboard art is hot garbage
  - For advancing status, currently prompts user for time(s)
    - If just a single time, could take it as an optional final argument?
- Settings
  - `settings` subcommand of main CLI to interact with settings
    - Also an option within the shell
  - Global config file?
  - Which items to include when making new tasks (priority/difficulty/duration can be omitted, with default)
  - Priority/difficulty upper bounds
  - Age-off for completed tasks to prevent displaying too many in board
    - `archived` status? Like `kanban-python`
    - Or set `limit=none` to view these in `completed` column
  - Store board-specific settings in file itself?
    - To avoid circularity, may have to move BoradSettings class into model.py
  - Size limit, set of statuses to show
  - Float format for things like scores (rounding, precision)
  - Date format in tables
  - Show dates as timestamps or human-readable relative times
  - Use system default directory for app-specific configs? XDG?
  - Make colors configurable?
  - Advanced: Set time ranges which will be excluded from duration measurements (e.g. work only counts during work hours)
- Allow custom task status labels?
  - todo/active/paused/complete are still the primary ones; extras would presumably be "sub-statuses" of active
  - What should be the name of this field? "status" would conflict with the existing one. Options:
        1) Use "status", rename the old one to "stage"
        2) Use "active_status", keep the old one the same
- Write more tests
  - Want high coverage of data model, board manipulations
  - Use `hypothesis` to generate random data?
  - Some UI tests (input command -> terminal output), though these can be brittle if output format changes
- Better schema documentation
  - Go into more detail about the meaning(s) of priority/difficulty/duration
- Support task logs
- Github/Gitlab/Jira integration
  - Query APIs
  - Bidirectional syncing
  - Interface to map between external task metadata and DaiKanban Tasks
  - Need to handle issue assignment (i.e. only pull tasks assigned to you)
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
- Task blocking (tasks require other tasks to be finished)
  - Prevent cyclic blocking?
  - Prevent completion of a blocked task without its precursors
    - Prompt user to complete all of them at once
  - Score calculation of blocked tasks can be complex
    - Can try to ensure it is less than any of its blockers (but that's hard if score is arbitrary, e.g. =priority)
    - Or just ensure it comes later in the ordering, even if its score is higher
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
- Web app
  - `web` subcommand of main CLI
  - `streamlit`? `fastui`?
  - Some cloud solution for syncing your board file
- Notifications
  - Could be *chosen tasks for today*, *tasks due soon*, etc.
  - Send reminders via e-mail (smtplib) or text (twilio/pushover/etc.)
    - The latter may cost money
- NLP to predict difficulty/duration based on name/description/project/tags
