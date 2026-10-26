from unittest.mock import Mock

import idradar.__main__ as entry


def test_entry_local_host_and_browser_thread(monkeypatch):
    # 使用简单的假 socket，不绑定真实端口。
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            assert address == ("127.0.0.1", 8765)

    monkeypatch.setattr(entry.socket, "socket", FakeSocket)
    thread = Mock()
    thread_factory = Mock(return_value=thread)
    run = Mock()
    monkeypatch.setattr(entry.threading, "Thread", thread_factory)
    monkeypatch.setattr(entry.uvicorn, "run", run)
    entry.main([])
    assert thread_factory.call_args.kwargs["target"] == entry.open_when_ready
    thread.start.assert_called_once()
    assert run.call_args.args == ("idradar.server:app",)
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8765
    assert run.call_args.kwargs["access_log"] is False


def test_ready_opens_local_url(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    connect = Mock(return_value=Connection())
    open_browser = Mock()
    monkeypatch.setattr(entry.socket, "create_connection", connect)
    monkeypatch.setattr(entry.webbrowser, "open", open_browser)
    entry.open_when_ready()
    open_browser.assert_called_once_with("http://127.0.0.1:8765")
