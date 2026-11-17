import socket


def resolve_host(host: str) -> list[str]:
    """Every address a host name resolves to, or an empty list when it does not resolve."""
    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)})
    except socket.gaierror:
        return []
