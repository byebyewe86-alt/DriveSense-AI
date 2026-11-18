"""
car_link.py - the laptop <-> ESP32 link for DriveSense AI.

Keeps a background thread that connects to the ESP32's TCP server, stays
connected, and forwards only the freshest command. If the link drops it keeps
retrying quietly, so the gesture script never freezes and the car (which has
its own watchdog) stops on its own.

    link = CarLink("192.168.4.1")
    link.start()
    link.send(steer=-30, throttle=60, brake=0)   # -100..100 / 0..100 / 0..100
    link.stop()
"""

import socket
import threading
import time

DEFAULT_HOST = "192.168.4.1"     # AP mode address of the ESP32
DEFAULT_PORT = 5005

CONNECT_TIMEOUT = 2.0            # seconds to wait for the TCP handshake
RETRY_INTERVAL = 1.0             # seconds between reconnect attempts


def _clamp(value, low, high):
    return max(low, min(high, value))


class CarLink:
    """Non-blocking-ish TCP client that always sends the latest command."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, verbose=True):
        self.host = host
        self.port = port
        self.verbose = verbose

        self.connected = False
        self.status = "idle"
        self.last_error = None
        self.packets_sent = 0

        self._sock = None
        self._packet = b"0,0,0\n"
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    # ------------------------------------------------------------------ API

    def start(self):
        """Start the background connection/writer thread."""
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def send(self, steer, throttle, brake):
        """Queue the newest command. Replaces any command not yet sent."""
        packet = "%d,%d,%d\n" % (
            int(_clamp(round(steer), -100, 100)),
            int(_clamp(round(throttle), 0, 100)),
            int(_clamp(round(brake), 0, 100)),
        )
        with self._lock:
            self._packet = packet.encode("ascii")

    def stop(self, timeout=0.5):
        """Send a neutral command, give it a moment to leave, then close."""
        self.send(0, 0, 0)

        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                flushed = self._packet is None
            if flushed:
                break
            time.sleep(0.02)

        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

        self._close_socket()
        self.connected = False
        self.status = "closed"

    # ------------------------------------------------------------- internals

    def _log(self, message):
        if self.verbose:
            print(message, flush=True)

    def _close_socket(self):
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _connect(self):
        sock = socket.create_connection((self.host, self.port), CONNECT_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.settimeout(1.0)
        self._sock = sock
        self.connected = True
        self.status = "connected"
        self._log("[car] connected to %s:%d" % (self.host, self.port))

    def _worker(self):
        while self._running:
            if self._sock is None:
                try:
                    self._connect()
                except OSError as error:
                    self.connected = False
                    self.status = "no link"
                    self.last_error = error
                    time.sleep(RETRY_INTERVAL)
                    continue

            with self._lock:
                packet, self._packet = self._packet, None

            if packet is None:
                time.sleep(0.004)
                continue

            try:
                self._sock.sendall(packet)
                self.packets_sent += 1
            except OSError as error:
                self.last_error = error
                self.connected = False
                self.status = "dropped"
                self._log("[car] link lost (%s), reconnecting..." % error)
                self._close_socket()
                time.sleep(0.3)


if __name__ == "__main__":
    # Tiny smoke test: drive forward-left, then stop.
    link = CarLink()
    link.start()
    print("Waiting for the car (Ctrl+C to abort)...")
    for _ in range(120):
        if link.connected:
            break
        time.sleep(0.1)

    if not link.connected:
        print("Never connected. Is the laptop on the 'DriveSense-Car' WiFi?")
        link.stop()
        raise SystemExit(1)

    try:
        for _ in range(60):
            link.send(steer=-40, throttle=45, brake=0)
            time.sleep(0.033)
        link.send(steer=0, throttle=0, brake=0)
        time.sleep(0.5)
        print("Sent %d packets." % link.packets_sent)
    finally:
        link.stop()
