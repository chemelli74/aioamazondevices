"""Script to sort DEVICE_TYPE_TO_MODEL."""

import sys
from typing import Any

import orjson

sys.path.append("/workspaces/aioamazondevices/src/aioamazondevices")
from const import DEVICE_TYPE_TO_MODEL

sorted_dict: dict[str, dict[str, Any]] = dict(sorted(DEVICE_TYPE_TO_MODEL.items()))

print(orjson.dumps(sorted_dict, option=orjson.OPT_INDENT_2))
