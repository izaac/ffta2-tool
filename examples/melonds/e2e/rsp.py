"""Minimal GDB remote serial protocol client for the melonDS ARM9 stub.

melonDS accepts one client per emulator start: after a detach the stub keeps the dead
connection and never accepts another, so peeks and pokes must share a single long-lived
connection. Keep it open for the whole session and use halt()/resume() around reads.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager, suppress

CHUNK = 512


class Rsp:
    def __init__(self, port: int, host: str = "127.0.0.1", timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""
        self.running = False
        # the stub waits up to 1 s for this initial ack and answers with its own
        self.sock.sendall(b"+")
        self._take_ack()

    def _fill(self) -> None:
        data = self.sock.recv(65536)
        if not data:
            raise ConnectionError("melonDS gdb stub closed the connection")
        self.buf += data

    def _take_ack(self) -> None:
        while not self.buf:
            self._fill()
        if self.buf[:1] in (b"+", b"-"):
            self.buf = self.buf[1:]

    def _send(self, payload: bytes) -> None:
        self.sock.sendall(b"$" + payload + b"#" + b"%02x" % (sum(payload) & 0xFF))

    def _packet(self) -> bytes:
        while True:
            start = self.buf.find(b"$")
            if start >= 0:
                end = self.buf.find(b"#", start)
                if end >= 0 and len(self.buf) >= end + 3:
                    payload = self.buf[start + 1 : end]
                    self.buf = self.buf[end + 3 :]
                    self.sock.sendall(b"+")
                    return payload
            self._fill()

    def request(self, payload: bytes) -> bytes:
        self._send(payload)
        self._take_ack()
        return self._packet()

    def halt(self, timeout: float = 5.0) -> None:
        """Interrupt a running target and wait for the stop reply."""
        if not self.running:
            return
        self.sock.sendall(b"\x03")
        self.sock.settimeout(timeout)
        self._packet()
        self.running = False

    def resume(self) -> None:
        if self.running:
            return
        self._send(b"c")
        self._take_ack()
        self.running = True

    def read(self, addr: int, length: int) -> bytes:
        out = b""
        while length > 0:
            n = min(CHUNK, length)
            reply = self.request(b"m%x,%x" % (addr, n))
            if reply.startswith(b"E"):
                raise OSError(f"read {addr:#x}+{n:#x} failed: {reply!r}")
            out += bytes.fromhex(reply.decode())
            addr += n
            length -= n
        return out

    def write(self, addr: int, data: bytes) -> None:
        if addr % 4 or len(data) % 4:
            raise ValueError("melonDS stub needs aligned word writes")
        reply = self.request(b"M%x,%x:%s" % (addr, len(data), data.hex().encode()))
        if reply != b"OK":
            raise OSError(f"write {addr:#x} failed: {reply!r}")

    @contextmanager
    def paused(self):
        """Halt for a consistent multi-read, resume afterwards even on errors."""
        self.halt()
        try:
            yield self
        finally:
            self.resume()

    def snapshot(self, addr: int, length: int) -> bytes:
        """Halt, read a region, resume."""
        self.halt()
        try:
            return self.read(addr, length)
        finally:
            self.resume()

    def close(self) -> None:
        self.sock.close()


def serve(gdb_port: int, sock_path: str) -> None:
    """Hold the single stub connection and serve peeks/pokes on a unix socket.

    Line protocol, one request per connection: "read <addr> <len>" -> hex,
    "dump <path> <addr> <len>" -> "ok", "write <addr> <hex>" -> "ok", "quit".
    """
    import os

    rsp = Rsp(gdb_port)
    rsp.resume()
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(4)
    while True:
        conn, _ = srv.accept()
        with conn:
            line = conn.makefile().readline().split()
            try:
                if not line:
                    continue
                op = line[0]
                if op == "quit":
                    conn.sendall(b"ok\n")
                    break
                rsp.halt()
                try:
                    if op == "read":
                        conn.sendall(rsp.read(int(line[1], 16), int(line[2], 16)).hex().encode() + b"\n")
                    elif op == "dump":
                        with open(line[1], "wb") as fh:
                            fh.write(rsp.read(int(line[2], 16), int(line[3], 16)))
                        conn.sendall(b"ok\n")
                    elif op == "write":
                        rsp.write(int(line[1], 16), bytes.fromhex(line[2]))
                        conn.sendall(b"ok\n")
                    else:
                        conn.sendall(b"err unknown op\n")
                finally:
                    rsp.resume()
            except Exception as exc:  # keep serving; report to the caller
                with suppress(OSError):
                    conn.sendall(f"err {exc}\n".encode())
    rsp.close()


def ask(sock_path: str, request: str, timeout: float = 30.0) -> str:
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.settimeout(timeout)
    c.connect(sock_path)
    c.sendall(request.encode() + b"\n")
    out = b""
    while not out.endswith(b"\n"):
        chunk = c.recv(1 << 20)
        if not chunk:
            break
        out += chunk
    c.close()
    return out.decode().strip()


if __name__ == "__main__":
    import sys

    serve(int(sys.argv[1]), sys.argv[2])
