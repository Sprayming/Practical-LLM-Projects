import json, os, threading
from datetime import datetime
from loguru import logger

class ProfileStore:
    """User entity profile store, separate from ChromaDB memory."""
    def __init__(self, path="./user_profiles.json"):
        self.path = path
        self._lock = threading.Lock()
        self._data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.warning("Profile load failed: {}", e)
                self._data = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Profile save failed: {}", e)

    def get_profile(self, tenant_id):
        with self._lock:
            return dict(self._data.get(tenant_id, {}))

    def to_prompt_text(self, tenant_id):
        profile = self.get_profile(tenant_id)
        if not profile:
            return ""
        items = sorted(profile.items())
        parts = [k + ": " + v["value"] for k, v in items]
        return "[User Profile]\n" + "\n".join(parts)

    def merge_entities(self, tenant_id, entities):
        if not entities:
            return
        with self._lock:
            if tenant_id not in self._data:
                self._data[tenant_id] = {}
            profile = self._data[tenant_id]
            for ent in entities:
                key = (ent.get("key") or "").strip()
                value = (ent.get("value") or "").strip()
                confidence = min(float(ent.get("confidence") or 0.5), 1.0)
                if not key or not value:
                    continue
                now = datetime.now().isoformat()
                if key in profile:
                    ex = profile[key]
                    if confidence > (ex.get("confidence") or 0):
                        profile[key] = {
                            "value": value,
                            "confidence": confidence,
                            "source": "llm",
                            "timestamp": now,
                            "access_count": (ex.get("access_count") or 0) + 1,
                        }
                    else:
                        profile[key]["access_count"] = profile[key].get("access_count", 0) + 1
                else:
                    profile[key] = {
                        "value": value,
                        "confidence": confidence,
                        "source": "llm",
                        "timestamp": now,
                        "access_count": 1,
                    }
            self._save()

    def clear(self, tenant_id):
        with self._lock:
            self._data.pop(tenant_id, None)
            self._save()
