"""Root conftest: blocks all network access in every test.

AF_INET/AF_INET6 connections and DNS lookups of real host names raise
RuntimeError. AF_UNIX sockets and socket.socketpair stay allowed, because
multiprocessing and asyncio (used by e.g. ocrmypdf) depend on them.
"""

import socket

import pytest

NETWORK_ERROR = "Nettkall er ikke tillatt i journalistverktøy"
_INET_FAMILIES = {socket.AF_INET, socket.AF_INET6}


def _raise(*_args, **_kwargs):
    raise RuntimeError(NETWORK_ERROR)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        if self.family in _INET_FAMILIES:
            _raise()
        return original_connect(self, address)

    def guarded_connect_ex(self, address):
        if self.family in _INET_FAMILIES:
            _raise()
        return original_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in (None, "", b""):
            _raise()
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _raise)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield
