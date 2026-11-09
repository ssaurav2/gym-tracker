"""A deliberately small local .env reader; never runs shell code or prints values."""
import os
import re
from pathlib import Path


def load_local_env(path=None):
    path = Path(path) if path is not None else Path(__file__).resolve().parent / '.env'
    if not path.exists():
        return
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name):
            raise ValueError(f'Invalid .env format on line {number}; expected NAME=value.')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'Invalid .env quoting on line {number}.')
            value = value[1:-1]
        os.environ.setdefault(name, value)
