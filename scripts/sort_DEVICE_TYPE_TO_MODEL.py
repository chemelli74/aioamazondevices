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
    hw_ver = f'"{value["hw_version"]}"' if value["hw_version"] else None
    vendor = value.get("manufacturer")
    file.write(f'  "{key}": {{\n')
    if vendor:
        file.write(f'    "manufacturer": "{vendor}",\n')
    file.write(f'    "model": "{value["model"]}",\n')
    file.write(f'    "hw_version": {hw_ver},\n')
    file.write("},\n")

file.close()
