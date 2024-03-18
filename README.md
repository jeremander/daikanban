# DaiKanban <br/> 大看板

A command-line Kanban board application that helps you prioritize and organize your projects.

## Screenshot

![Screenshot](doc/screenshot_v0_1_0.png)

(*screenshot from `v0.1.0`*)

Inspired by prior projects like the excellent [clikan] and [kanban-python], I've made yet another terminal kanban board in Python. My long-term goals with it are:

1. High degree of customization (display settings, scoring/prioritizing tasks)
2. Syncing with external platforms (Github/Jira Issues)
3. Productivity metrics and completion forecasting

⚠️ DaiKanban is currently in its very early stages and should *not* be considered stable.

## Concepts

A DaiKanban **board** displays your **tasks**, organized into three status groups:

- `todo` (AKA *backlog*)
- `active` (AKA *in-progress*)
- `completed`

Tasks advance from one status to the next. You can rank tasks in your backlog by various criteria such as priority, expected time to completion, etc.

You may have more than one board (e.g. to separate personal and business tasks), and tasks in each board may be associated with **projects** to categorize them further.

## Installation

```shell
pip install daikanban
```

## Usage

View help menu:

```shell
daikanban -h
```

Launch interactive shell:

```shell
daikanban shell
```

### Common shell commands

| Long | Short | Description |
| --- | --- | --- |
| `help` | `h` | Show help menu |
| `quit` | `q` | Quit |
| `board load` | `b l` | Load a board |
| `board show` | `b s` | Show current board |
| `project new` | `p n` | Create new project |
| `project show [PROJECT]` | `p s [PROJECT]` | Show project info |
| `task new` | `t n` | Create new task |
| `task show [TASK]` | `t s [TASK]` | Show task info |

Projects and tasks can be referred to either by their ID (a unique number assigned at creation) or their name. For ease of use, it is recommended to avoid whitespace characters in names:

- ❌ `Do the thing`
- ✅ `do-the-thing`

### Shell commands to advance tasks

| Long | Short | Description |
| --- | --- | --- |
| `task begin [TASK]` | `t b [TASK]` | Start a task in the backlog |
| `task complete [TASK]` | `t c [TASK]` | Complete an active task |
| `task pause [TASK]` | `t p [TASK]` | Pause an active task |
| `task resume [TASK]` | `t r [TASK]` | Resume a paused or completed task back to active |
| `task todo [TASK]` | `t t [TASK]` | Revert a task to the backlog |

### Board files

For now, DaiKanban boards are saved as local JSON files that you need to load explicitly, either by running `board load [FILENAME]` within the shell, or launching the program like `daikanban shell --board [FILENAME]`.

🚧 In the near future, multiple boards will be stored inside a canonical directory, along with a global configuration file in which you can set up a default board.

### Flexible dates & times

One nice feature of DaiKanban is its flexible datetime parsing. For example, when creating a new task, it will prompt you for a due date. All of the following responses are valid:

- `2024-03-19`
- `3/19/24`
- `march 19th`
- `in 2 days`
- `in two days`
- `48 hours from now`

This makes it easy to enter these kinds of fields naturally as a human, without having to memorize a specific date format. 😃

## 🚧 Future Work

- Configurable settings
- Syncing with external platforms (Github, Jira)
- Custom task statuses
- Blocking tasks
- Recurring tasks
- Standard markdown format for storing readable task lists
- Productivity analytics
- Web-based alternative to CLI
- And more...

## Support and feedback

🛠️ Feel free to submit pull requests, ask questions, or make bugfix/feature requests on [Github Issues](https://github.com/jeremander/daikanban/issues).

✨ This library is built on [pydantic], [typer], and [rich]. Check them out!

[clikan]: https://github.com/kitplummer/clikan
[kanban-python]: https://github.com/Zaloog/kanban-python
[pydantic]: https://github.com/pydantic/pydantic
[rich]: https://github.com/Textualize/rich
[typer]: https://github.com/tiangolo/typer
