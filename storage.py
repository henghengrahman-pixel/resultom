import json
import os
import tempfile
import threading
from copy import deepcopy

_LOCK = threading.RLock()


def _ensure_parent(path: str):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


def load_json(path: str, default):
    with _LOCK:
        if not os.path.exists(path):
            return deepcopy(default)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return deepcopy(default)


def save_json(path: str, data):
    with _LOCK:
        _ensure_parent(path)
        parent = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(prefix=".tmp-resultom-", dir=parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
