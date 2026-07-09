import socket

import main


def test_resolve_bind_addresses_retries_transient_dns(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port, type):
        calls.append((host, port, type))
        if len(calls) == 1:
            raise socket.gaierror("temporary failure")
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("100.64.0.1", port))]

    monkeypatch.setattr(main.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(main.time, "sleep", lambda _delay: None)

    addresses = main._resolve_bind_addresses("example.test", 7999, attempts=2, delay_seconds=0)

    assert addresses == [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("100.64.0.1", 7999))]
    assert len(calls) == 2


def test_resolve_bind_addresses_gives_up_after_attempts(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port, type):
        calls.append((host, port, type))
        raise socket.gaierror("still unavailable")

    monkeypatch.setattr(main.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(main.time, "sleep", lambda _delay: None)

    addresses = main._resolve_bind_addresses("example.test", 7999, attempts=2, delay_seconds=0)

    assert addresses == []
    assert len(calls) == 2
