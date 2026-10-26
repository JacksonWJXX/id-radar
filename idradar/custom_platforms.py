"""本机自定义网站，只保存名称、网址模板和判断方式。"""

import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .i18n import t

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "custom_platforms.json"


def validate_site(label: str, url_template: str, kind: str) -> dict:
    label, url_template = label.strip(), url_template.strip()
    if not 1 <= len(label) <= 12:
        raise ValueError(t('site.label'))
    if kind not in ("profile", "search"):
        raise ValueError(t('site.kind'))
    if not any(token in url_template for token in ("{name}", "{handle}")):
        raise ValueError(t('site.placeholder'))
    remaining = url_template.replace("{name}", "").replace("{handle}", "")
    if "{" in remaining or "}" in remaining or any(char.isspace() for char in url_template):
        raise ValueError(t('site.template'))
    try:
        parsed = urlsplit(url_template)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError
        parsed.port
    except ValueError:
        raise ValueError(t('site.url')) from None
    return {"label": label, "url_template": url_template, "kind": kind}


class CustomPlatformStore:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)

    def list(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(records, list) or len(records) > 10:
                raise ValueError
            result, seen = [], set()
            for record in records:
                id = record["id"]
                if not isinstance(id, str) or not id.startswith("custom_") or id in seen:
                    raise ValueError
                result.append({"id": id, **validate_site(record["label"], record["url_template"], record["kind"])})
                seen.add(id)
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise ValueError(t('site.file')) from None

    def _save(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def add(self, label, url_template, kind):
        site = validate_site(label, url_template, kind)
        records = self.list()
        if len(records) >= 10:
            raise ValueError(t('site.limit'))
        site = {"id": "custom_" + uuid4().hex, **site}
        self._save([*records, site])
        return site

    def delete(self, id):
        records = self.list()
        remaining = [record for record in records if record["id"] != id]
        if len(remaining) == len(records):
            raise ValueError(t('site.missing'))
        self._save(remaining)
