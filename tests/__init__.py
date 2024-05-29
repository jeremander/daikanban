from io import StringIO
import re


def patch_stdin(monkeypatch, content):
    """Patches stdin with the given input."""
    monkeypatch.setattr('sys.stdin', StringIO(content))

def match_patterns(patterns, string, exact=False):
    """Matches one or more regexes on a string."""
    if not isinstance(patterns, (list, tuple)):
        patterns = [patterns]
    for pattern in patterns:
        if exact:  # exact match
            if isinstance(pattern, str):
                assert pattern == string
            else:
                assert re.compile(pattern).fullmatch(string)
        else:
            if isinstance(pattern, str):
                pattern = re.compile(pattern)
            assert isinstance(pattern, re.Pattern)
            assert pattern.search(string)
