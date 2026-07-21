import json, os, uuid
from datetime import datetime
from pathlib import Path

class ConversationStore:
    def __init__(self, store_dir="conversations"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(exist_ok=True)

    def save(self, messages, conv_id=None):
        if conv_id is None:
            conv_id = str(uuid.uuid4())[:8]
        path = self.store_dir / f"{conv_id}.json"
        data = {"id": conv_id, "timestamp": datetime.now().isoformat(), "message_count": len(messages), "messages": messages[-20:]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return conv_id

    def load(self, conv_id):
        path = self.store_dir / f"{conv_id}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def list_all(self):
        result = []
        for f in sorted(self.store_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            data = json.load(open(f, encoding="utf-8"))
            result.append({"id": data["id"], "timestamp": data["timestamp"], "message_count": data["message_count"]})
        return result
