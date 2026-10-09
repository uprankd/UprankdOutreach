"""Read settings from a .env file next to app.py (KEY=value per line).

Real environment variables win, so Supervisor/systemd settings still override
the file. Lines starting with # are ignored; quotes around values are removed.
"""

import os


def load(folder):
    path = os.path.join(folder, ".env")
    if not os.path.isfile(path):
        return []
    loaded = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            if key and key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    return loaded
