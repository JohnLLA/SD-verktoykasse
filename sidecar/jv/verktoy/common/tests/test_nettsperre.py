"""Checks that the root conftest blocks the network but not local IPC."""

import asyncio
import multiprocessing
import socket
import tempfile
from pathlib import Path

import pytest

MSG = "Nettkall er ikke tillatt"


def test_create_connection_blocked():
    with pytest.raises(RuntimeError, match=MSG):
        socket.create_connection(("example.com", 443), timeout=1)


def test_getaddrinfo_blocked():
    with pytest.raises(RuntimeError, match=MSG):
        socket.getaddrinfo("example.com", 443)


def test_getaddrinfo_localhost_blocked():
    with pytest.raises(RuntimeError, match=MSG):
        socket.getaddrinfo("localhost", 80)


@pytest.mark.parametrize(
    "family,addr",
    [(socket.AF_INET, ("127.0.0.1", 9)), (socket.AF_INET6, ("::1", 9))],
)
def test_inet_connect_blocked(family, addr):
    try:
        s = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        pytest.skip("adressefamilien finnes ikke her")
    with s:
        with pytest.raises(RuntimeError, match=MSG):
            s.connect(addr)
        with pytest.raises(RuntimeError, match=MSG):
            s.connect_ex(addr)


def test_udp_connect_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(RuntimeError, match=MSG):
            s.connect(("8.8.8.8", 53))


def test_getaddrinfo_empty_host_allowed():
    assert socket.getaddrinfo(None, 80)


def test_socketpair_allowed():
    a, b = socket.socketpair()
    with a, b:
        a.sendall(b"hei")
        assert b.recv(3) == b"hei"


def test_af_unix_allowed():
    with tempfile.TemporaryDirectory(prefix="jv") as d:
        path = str(Path(d) / "s")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen(1)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(path)
                conn, _ = server.accept()
                with conn:
                    client.sendall(b"ok")
                    assert conn.recv(2) == b"ok"


def test_asyncio_allowed():
    async def work():
        await asyncio.sleep(0)
        return 42

    assert asyncio.run(work()) == 42


def test_multiprocessing_allowed():
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(1) as pool:
        assert pool.map(abs, [-2, 3]) == [2, 3]
    with ctx.Manager() as manager:  # Manager talks over AF_UNIX
        shared = manager.list([1])
        shared.append(2)
        assert list(shared) == [1, 2]
