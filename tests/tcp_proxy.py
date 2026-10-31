"""A tiny TCP proxy for failure injection: put it between a service and MySQL or the broker, then
cut() the connection and restore() it. Works the same on every OS and in CI, with no control over
Docker needed -- from the client's side an outage is an outage."""

import socket
import threading


class TcpProxy:
    def __init__(self, target_host: str, target_port: int):
        self.target = (target_host, target_port)
        self.port = None
        self._listener = None
        self._connections: list[socket.socket] = []
        self._lock = threading.Lock()

    def __enter__(self):
        self.restore()
        return self

    def __exit__(self, *exc):
        self.cut()

    def restore(self):
        """Accept connections again (on the same port)."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port or 0))
        listener.listen(64)
        self.port = listener.getsockname()[1]
        self._listener = listener
        threading.Thread(target=self._accept, args=(listener,), daemon=True).start()

    def cut(self):
        """Drop every open connection and refuse new ones, like the server's host going away."""
        listener, self._listener = self._listener, None
        if listener:
            listener.close()
        with self._lock:
            connections, self._connections = self._connections, []
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

    def _accept(self, listener):
        while True:
            try:
                client, _ = listener.accept()
            except OSError:
                return  # cut()
            try:
                upstream = socket.create_connection(self.target, timeout=5)
                upstream.settimeout(None)
            except OSError:
                client.close()
                continue
            with self._lock:
                if self._listener is not listener:  # cut() raced with this accept
                    client.close()
                    upstream.close()
                    return
                self._connections += [client, upstream]
            for src, dst in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pipe, args=(src, dst), daemon=True).start()

    @staticmethod
    def _pipe(src, dst):
        try:
            while data := src.recv(65536):
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
