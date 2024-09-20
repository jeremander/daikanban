# TODO list

## `v0.2.0`

- Config customization
  - Board management
    - If `board load` attempts to load nonexistent path, suggest the user create it with `board new [path]`.
      - Have `board new [name_or_path]` fill in the name/path without prompting.
      - Have `board new` do a `mkdir` with `parents=True`, if needed.
  - Particular configs:
    - [x] Which items to include when making new tasks (priority/difficulty/duration can be omitted, with default)
    - [x] Default size limit
    - [ ] Set of statuses to show
    - [ ] Show dates as timestamps or human-readable relative times
    - [ ] Default colors (E.g. project IDs are too dark on dark terminal)
      - Can we detect terminal color?

## `v0.2.1`

- Provide informative error/warning if loaded config file does not match latest schema
  - Ideally load what we can of the file and warn if there's an unknown field (no fields should be required).
    - Currently we probably just silently fail to notice unknown fields?
- Config customization
  - CLI command to reset configs to the basic defaults
  - Shell option to interact with configs
    - View/get/set
    - Setting TOML values can be tricky, but doable
      - Setting a value will persist until the config is changed, or shell is closed
      - Option to save current configs to the config file (after prompt confirmation)
  - Priority/difficulty upper bounds?
  - Logging level
- Time tracking via logs
  - Use `type` field to indicate type of status action.
    - Three types, `start`, `stop`, `done`. The latter two are essentially the same.
      - Might be simpler to exclude `done`, but then there's no way to distinguish "pause" from "false completion."
    - Status actions:
      - `start`: no log, since stored in `first_started_time`
      - `complete`: no log, since stored in `completed_time`
      - `pause`: set `last_paused_time`. If there is one already, push it onto log with type `stop`.
      - `resume`: set `last_started_time`. If there is one already, push it onto log with type `start`.
        - If status is completed, push the completion time onto log with type `stop` (or `done`).
    - Figure out what to do when backdating times.
  - Make `TaskHistory` object to help with calculations
  - Test for consistency with stored data
    - Start/stop must *strictly* alternate
    - First entry must be a stop
    - Times must be monotonic
    - Last start log must be <= `last_started_time`
    - First stop log must be >= `first_started_time`
    - Last stop log must be <= min(`completed_time`, `last_paused_time`)
- Add an icon indicating a note exists for a project or task
- `project set` or `task set` multiple values at once?
  - Likewise, set one or more values at creation time
- Change "updated field" text when setting project/field so that it shows the value too?
- Allow `task delete` to take multiple IDs
- Relation validation
  - Prevent parent/blocked_by relation (and possibly others in the future) from being reflexive
  - Check that IDs in `relations` are valid
- UUIDs
  - Match projects/tasks on UUID as alternative to ID.
  - Accept any unique prefix (of length >= 8).
- Board updates
  - Duplication:
    - For UUID match with differing data, do one of the following:
      1. Keep original
      2. Replace with import
      3. Use whichever has more recent modified time
      4. Prompt user for action
    - Currently we only do option (3), but the resolution mode should be configurable (and overridable via CLI flag)
    - Implement as a callback, via an enum ConflictResolutionMode

## `v0.3.0`

- Set up Github Actions, test coverage
- Encapsulate notion of a *filter*.
  - Create new library for boolean algebra of predicates? With `FieldPredicate` that checks existence of field at construction time.
- How to set lists like blocking tasks, relations?
  - Should probably be one at a time, might need special sub-subcommand like:
    - `task set [ID] blocker [BLOCKER_ID]`
    - `task set [ID] relation [TYPE] [DEST_ID]`
- Configurable time exclusion rules for time tracking
- Use different scorer for completed tasks?
  - E.g. `priority-rate` would use actual duration rather than expected duration
  - Could actually be the same `TaskScorer` object, but it chooses a different field if completed
  - But then it's less flexible (e.g. might want `completed` board to be chronological)
  - Best solution is to allow different scorers, keyed by `TaskStatus`
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

- Make it an error if relation has an unknown ID?
  - Error upon creation/update
- "Context" (i.e. persistent filter)
- (BREAKING) Should we store UUIDs instead of IDs for project/task relations?
  - Pros:
    - Don't need complicated logic to remap the IDs (but still need to deal with broken references)
  - Cons:
    - Take up more space in JSON
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
- Other features from [Taskwarrior](https://taskwarrior.org/docs/):
  - Statuses (not mutually exclusive with the "main" statuses):
    - Scheduled (when to start working on the task)
    - Waiting (todo status, but is "hidden" until this time)
    - Until (delete the task if not done by this time, perhaps call it "expire" instead)
    - Recurring (just a template for spawning other instance tasks)
      - See: [How Recurrence Works](https://taskwarrior.org/docs/recurrence/)
    - Assign UUID to every task at creation time that stays fixed.
    - More thorough filter system
    - "Contexts" for applying filters automatically
      - Since we're in a shell, we could just have a command to activate a filter and stay in it, in addition to named contexts.
    - +/- syntax for tags
    - Hooks
      - Would be cool to be language-agnostic, but will function better if it's just a Python API.
        - Find functions with a particular name, like `on_add`, in one or more Python modules in configured hooks directory.
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
