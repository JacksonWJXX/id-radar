"""测试只使用本地样本和假实现，禁止真实 socket 连接。"""

import socket
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ARTIFACTS = Path(__file__).resolve().parents[1] / ".test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
(ARTIFACTS / "cache").mkdir(exist_ok=True)


@pytest.fixture
def tmp_path():
    # Python 3.13 在 Windows 对 0700 目录施加 ACL，沙盒进程无法再次读取。
    # 使用默认目录权限，并把测试文件限制在仓库内，避免触碰用户配置。
    path = ARTIFACTS / ("case-" + uuid4().hex)
    path.mkdir()
    return path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("pytest 不允许访问真实网络")

    original_connect = socket.socket.connect
    original_pair = socket.socketpair

    def internal_socketpair(*args, **kwargs):
        # Windows 的事件循环通过 socketpair 自唤醒，这不是对外请求。
        with monkeypatch.context() as local:
            local.setattr(socket.socket, "connect", original_connect)
            return original_pair(*args, **kwargs)

    monkeypatch.setattr(socket, "socketpair", internal_socketpair)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.fixture
def fake_browser():
    async def close():
        pass

    return SimpleNamespace(login_status={"douyin": False, "xiaohongshu": False}, is_open=False, close=close)
