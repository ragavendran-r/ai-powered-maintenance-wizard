from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


@lru_cache
def load_sample_data() -> dict[str, Any]:
    data_dir = get_settings().data_dir
    with Path(data_dir, "steel_plant_demo.json").open(encoding="utf-8") as handle:
        return json.load(handle)
