"""Script to sort DEVICE_TYPE_TO_MODEL."""

import sys
from pathlib import Path
from typing import Any

sys.path.append("/workspaces/aioamazondevices/src/aioamazondevices")
from const import DEVICE_TYPE_TO_MODEL

sorted_dict: dict[str, dict[str, Any]] = dict(sorted(DEVICE_TYPE_TO_MODEL.items()))
destination_file = "scripts/sorted_device_model.json"

file = Path.open(Path(destination_file), mode="w", encoding="utf-8")

for key, value in sorted_dict.items():
    file.write(f'  "{key}": {{\n')
    file.write(f'    "model": "{value["model"]}",\n')
    file.write(f'    "hw_version": "{value["hw_version"]}",\n')
    file.write("},\n")

file.close()
