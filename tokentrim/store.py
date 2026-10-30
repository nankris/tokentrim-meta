"""Original-content store: every lossy transform keeps the exact original, addressable by a reference id."""
import hashlib
import json
from pathlib import Path
import threading


class OriginalStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else None
        self._values: dict[str, str] = {}
        self._lock = threading.Lock()
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)

    def put(self, text: str, prefix: str = "ref") -> str:
        ref = f"{prefix}_{hashlib.sha256(text.encode()).hexdigest()[:10]}"
        with self._lock:
            self._values[ref] = text
        if self.directory:
            (self.directory / ref).write_text(text, encoding="utf-8")
        return ref

    def put_json(self, value, prefix: str = "ref") -> str:
        return self.put(json.dumps(value, sort_keys=True, ensure_ascii=False), prefix)

    def get(self, ref: str) -> str:
        ref = str(ref).strip()
        with self._lock:
            if ref in self._values:
                return self._values[ref]
        if self.directory and "/" not in ref and (self.directory / ref).exists():
            return (self.directory / ref).read_text(encoding="utf-8")
        raise KeyError(ref)

    def __contains__(self, ref):
        try:
            self.get(ref)
            return True
        except KeyError:
            return False
