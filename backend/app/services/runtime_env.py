from pathlib import Path
from typing import Iterable

from dotenv import dotenv_values


def env_file_values_for(prefixes: Iterable[str], names: Iterable[str] = ()) -> dict[str, str]:
    """Return whitelisted .env values for subprocesses without mutating os.environ."""
    root_dir = Path(__file__).resolve().parents[3]
    env_files = (root_dir / ".env", Path.cwd() / ".env")
    prefixes_tuple = tuple(prefixes)
    names_set = set(names)
    values: dict[str, str] = {}
    seen: set[Path] = set()
    for env_file in env_files:
        env_path = env_file.resolve()
        if env_path in seen or not env_path.exists():
            continue
        seen.add(env_path)
        for key, value in dotenv_values(env_path).items():
            if value is None:
                continue
            if key in names_set or key.startswith(prefixes_tuple):
                values[key] = value
    return values
