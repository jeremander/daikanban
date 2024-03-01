#!/usr/bin/env python3
"""Export the DaiKanban JSON schema."""

import json

from daikanban.model import DaiKanban


if __name__ == '__main__':
    print(json.dumps(DaiKanban.model_json_schema(mode='serialization'), indent=2))
