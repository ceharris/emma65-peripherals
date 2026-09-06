"""Throwaway script: connects to a live VIA socket and prints decoded events.

Usage: uv run --package emma65-via python \
    gpio-playground/plan/uat/unit-1-via-read-side/watch_events.py [socket_path]
"""

from __future__ import annotations

import sys
import time

from emma65_via import ViaAsciiClient

socket_path = sys.argv[1] if len(sys.argv) > 1 else "~/.emma/sock/via6522"
client = ViaAsciiClient(socket_path)

print(f"connecting to {socket_path} ...")
while not client.connect():
    time.sleep(0.2)
print("connected")

try:
    while True:
        for event in client.poll():
            print(event)
        time.sleep(0.05)
except ConnectionError:
    print("connection closed")
except KeyboardInterrupt:
    pass
finally:
    client.close()
