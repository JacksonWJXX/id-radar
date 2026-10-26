"""逐行保存完整的一次查询，不保存自我介绍或 API 配置。"""

import json
from pathlib import Path


class HistoryStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / ".idradar" / "history.jsonl"

    def append(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list(self):
        if not self.path.exists():
            return []
        records = []
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                    if (isinstance(record, dict) and isinstance(record.get("id"), str)
                            and isinstance(record.get("created_at"), str)
                            and all(isinstance(record.get(key), list) for key in ("candidates", "platforms", "results"))):
                        records.append(record)
                except ValueError:
                    continue
        return records[::-1]
