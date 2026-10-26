import json
from unittest.mock import Mock

import httpx
import pytest

from idradar import __main__ as entry
from idradar import server
from idradar.demo import SAMPLES
from idradar.parse_names import parse_names


@pytest.mark.parametrize("lang,platforms", [("zh", ["bilibili", "github", "x"]), ("en", ["github", "x"])])
async def test_demo_isolated_and_triggers_recommendations(monkeypatch, tmp_path, lang, platforms):
    def forbidden(*args, **kwargs):
        raise AssertionError("演示模式不能访问真实服务或历史")
    for name in ("BrowserManager", "HistoryStore", "CustomPlatformStore", "BilibiliChecker", "GitHubChecker", "DouyinChecker", "XiaohongshuChecker", "XChecker"):
        monkeypatch.setattr(server, name, forbidden)
    app = server.create_app(demo=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        prompt = (await client.get("/api/prompt?lang=" + lang)).json()
        assert prompt["demo"] and prompt["sample"] == SAMPLES[lang]
        candidates = [{key: item[key] for key in ("name", "handle")} for item in parse_names(prompt["sample"])]
        response = await client.post("/api/check?lang=" + lang, json={"candidates": candidates, "platforms": platforms})
        cells = [json.loads(chunk.split("data: ")[1]) for chunk in response.text.split("\n\n") if chunk.startswith("event: result")]
        assert {"available", "taken", "similar"} <= {cell["result"]["status"] for cell in cells}
        assert "event: recommendation" in response.text
        assert (await client.get("/api/history?lang=" + lang)).json() == {"history": []}
        assert (await client.post("/api/login/douyin?lang=" + lang, json={})).status_code == 400
        assert (await client.post("/api/probe/bilibili?lang=" + lang, json={"name": "Name"})).status_code == 400
        site = (await client.post("/api/custom-platforms?lang=" + lang, json={"label": "Example", "kind": "profile", "url_template": "https://example.test/{handle}"})).json()["site"]
        assert (await client.post("/api/check?lang=" + lang, json={"candidates": candidates[:1], "platforms": [site["id"]]})).status_code == 200


def test_demo_entry_does_not_open_browser(monkeypatch):
    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): pass
    monkeypatch.setattr(entry.socket, "socket", FakeSocket)
    thread = Mock(side_effect=AssertionError("演示模式不打开浏览器"))
    monkeypatch.setattr(entry.threading, "Thread", thread)
    run = Mock()
    monkeypatch.setattr(entry.uvicorn, "run", run)
    entry.main(["--demo"])
    assert run.call_args.args[0].state.demo
