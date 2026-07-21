import json, os, hashlib
from datetime import datetime, timedelta
from pathlib import Path

class QueryCache:
    def __init__(self, cache_dir="cache", ttl_seconds=86400):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl = timedelta(seconds=ttl_seconds)

    def _key(self, query):
        return hashlib.md5(query.encode()).hexdigest()

    def get(self, query):
        key = self._key(query)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        entry = json.loads(open(path, encoding="utf-8").read())
        cached_at = datetime.fromisoformat(entry["cached_at"])
        if datetime.now() - cached_at > self.ttl:
            path.unlink()
            return None
        return entry["answer"]

    def set(self, query, answer, metadata=None):
        key = self._key(query)
        entry = {"answer": answer, "cached_at": datetime.now().isoformat(), "metadata": metadata or {}}
        with open(self.cache_dir / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)

    def clear(self):
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
