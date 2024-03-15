from dataclasses import dataclass
import re
from typing import Any, Callable, Generic, Optional, TextIO, TypeVar

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined
import rich
from rich.prompt import Prompt
from rich.text import TextType

from daikanban.utils import UserInputError, err_style


M = TypeVar('M', bound=BaseModel)
T = TypeVar('T')


class Console(rich.console.Console):
    """Subclass of rich's Console that fixes a terminal bug.
    See:
        - https://github.com/Textualize/rich/issues/2293
        - https://github.com/Textualize/rich/commit/568b9517b63282ac781a907d82b0c2965242be54"""

    def input(self, prompt: TextType = '', password: bool = False, stream: Optional[TextIO] = None) -> str:  # type: ignore  # noqa
        prompt_str = ''
        if prompt:
            with self.capture() as capture:
                self.print(prompt, markup=True, emoji=True, end='')
            prompt_str = capture.get()
        return input(prompt_str)


class PromptNoSuffix(Prompt):
    """Subclass of Prompt which suppresses the prompt suffix (colon)."""
    prompt_suffix = ''


def simple_input(prompt: str, default: Optional[str] = None, match: str = '.*') -> str:
    """Prompts the user with the given string until the user's response matches a certain regex."""
    regex = re.compile(match)
    while True:
        result = Prompt.ask(f'[bold]{prompt}[/]', default=default, console=Console()) or ''
        if regex.fullmatch(result):
            break
    return result

def validated_input(prompt: str, validator: Callable[[str], T], default: Any = None, use_prompt_suffix: bool = True, **kwargs: Any) -> T:
    """Prompts the user with the given string until the user's response passes a validator function with no error.
        prompt: prompt string
        validator: function to parse and validate the input
        default: default value
        use_prompt_suffix: display the default prompt suffix (colon) after the prompt and default
        kwargs: passed to the rich prompt"""
    if default not in (None, PydanticUndefined):
        if isinstance(default, float) and (int(default) == default):
            default = int(default)
        default = str(default)
    prompt_cls = Prompt if use_prompt_suffix else PromptNoSuffix
    while True:
        result = prompt_cls.ask(f'[bold]{prompt}[/]', default=default, console=Console(), **kwargs) or ''
        try:
            return validator(result)
        except Exception as e:
            rich.print(err_style(e))


@dataclass
class Prompter(Generic[T]):
    """Class which prompts a user for input, then parses and validates the response."""
    prompt: str  # prompt string
    parse: Optional[Callable[[str], T]] = None  # function to parse input
    validate: Optional[Callable[[T], None]] = None  # function to validate parsed input
    default: Optional[T | Callable[[], T]] = None  # default value or factory

    def parse_and_validate(self, s: str) -> T:
        """Parses the value from a string, validates it, then returns it."""
        val = s if (self.parse is None) else self.parse(s)
        if self.validate is not None:
            self.validate(val)  # type: ignore[arg-type]
        return val  # type: ignore[return-value]

    def loop_prompt(self, **kwargs: Any) -> T:
        """Prompts the user for the value until a valid one is entered.
        Additional keyword arguments are passed to the rich prompt."""
        default = self.default() if isinstance(self.default, Callable) else self.default  # type: ignore
        return validated_input(self.prompt, self.parse_and_validate, default=default, **kwargs)


@dataclass
class FieldPrompter(Generic[M, T]):
    """Class which prompts a user for input associated with a given BaseModel field, then parses and validates the response."""
    model_type: type[M]
    field: str
    prompter: Prompter[T]

    def __init__(self, model_type: type[M], field: str, prompt: Optional[str] = None, parse: Optional[Callable[[str], T]] = None) -> None:
        self.model_type = model_type
        self.field = field
        self.readable_name = self.field.replace('_', ' ').capitalize()
        prompt = prompt or self.readable_name
        info = model_type.model_fields[field]
        self.default = info.default if (info.default_factory is None) else info.default_factory
        self.prompter = Prompter(prompt, parse, self.validate, self.default)

    def validate(self, val: Any) -> None:
        """Validates the field value."""
        if val == PydanticUndefined:
            raise UserInputError('This field is required')
        try:
            self.model_type.__pydantic_validator__.validate_assignment(self.model_type.model_construct(), self.field, val)
        except ValidationError as e:
            msg = '\n'.join(d['msg'] for d in e.errors())
            raise UserInputError(msg) from None

    def prompt_field(self) -> T:
        """Prompts the user for the field until a valid one is entered."""
        return self.prompter.loop_prompt()


def model_from_prompt(model_type: type[M], prompters: dict[str, FieldPrompter] = {}) -> M:  # noqa: B006
    """Given a BaseModel type and collection of FieldPrompters, constructs an instance of the type from a sequence of user prompts."""
    kwargs: dict[str, Any] = {}
    for (field, prompter) in prompters.items():
        kwargs[field] = prompter.prompt_field()
    return model_type(**kwargs)
