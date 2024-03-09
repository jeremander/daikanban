# TODO list

## `v0.1.0`

- Icon for paused/due/overdue tasks in board view
  - Include paused task in test file
- Implement arguments for 'board show'
- Test appearance on both light and dark terminals
- Shell features
  - Advance task status
    - If task progresses todo->complete/paused or paused->complete, prompt for what time it was started, *ex post facto*.
- Create a README and CHANGELOG
- Bugfixes
  - For never-paused task, no need to store both first and last started timestamps
  - Name uniqueness on projects/tasks
    - Completed projects maybe should be allowed to have duplicate names? Esp. if tasks can recur.
- Small QoL improvements
  - Catch Ctrl-C within sequential prompts to go back to main loop
  - Set widths for each help menu separately
  - Accept today/tomorrow/yesterday as valid due dates
  - Relax URL parsing to infer scheme if missing (default https?)
  - Fuzzy matching of names in prompts

## Future

- Settings
  - `settings` subcommand of main CLI to interact with settings
    - Also an option within the shell
  - Global config file?
  - Which items to include when making new tasks (priority/difficulty/duration can be omitted, with default)
  - Priority/difficulty upper bounds
  - Store board-specific settings in file itself?
    - To avoid circularity, may have to move BoradSettings class into model.py
  - Size limit, set of statuses to show
  - Float format for things like scores (rounding, precision)
  - Date format in tables
  - Show dates as timestamps or human-readable relative times
  - XDG directory?
  - Make colors configurable?
- Allow custom task status labels?
  - todo/active/paused/complete are still the primary ones; extras would presumably be "sub-statuses" of active
  - What should be the name of this field? "status" would conflict with the existing one. Options:
        1) Use "status", rename the old one to "stage"
        2) Use "active_status", keep the old one the same
- Write more tests
  - Want high coverage of data model, board manipulations
  - Use hypothesis to generate random data?
  - Some UI tests (input command -> terminal output), though these can be brittle if output format changes
- Recurring tasks? A la Pianote.
  - Library of recurring tasks, with simple command to queue them into backlog
- Github/Gitlab/Jira integration
  - Query APIs
  - Interface to map between external task metadata and DaiKanban Tasks
- Analytics
  - Kanban metrics
    - Lead time (todo to complete) & cycle time (active to complete)
      - Per task, and averaged across tasks historically
      - Distributional estimates of these quantities, for forecasting purposes
  - Various throughput metrics
    - number of tasks per time
    - total priority, priority\*difficulty, priority\*duration, per time
- Task blocking (tasks require other tasks to be finished)
  - Prevent cyclic blocking?
  - Prevent completion of a blocked task without its precursors
    - Prompt user to complete all of them at once
- Web app (streamlit? FastUI?)
  - `web` subcommand of main CLI
- I/O
  - Export pretty output
    - markdown checklist/table
    - HTML static site (maybe unecessary if web app covers it)
  - "Scanner"
    - Input a task list (e.g. markdown checklist, e.g. Python files with lines matching regex "#\s*TODO")
    - See kanban-python library for example of this:

    ```lang=python
            config["settings.scanner"] = {
                "Files": ".py .md",
                "Patterns": "# TODO,#TODO,# BUG",
            }
    ```

- Notifications
  - Could be *chosen tasks for today*, *tasks due soon*, etc.
  - Send reminders via e-mail (smtplib) or text (twilio/pushover/etc.)
    - The latter may cost money