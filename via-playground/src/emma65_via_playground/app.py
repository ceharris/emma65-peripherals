"""VIA GPIO playground: a panel for observing and driving every pin of a via/6522 device.

Connects to a `via/6522` device's `unix:` transport and speaks the VIA peer
protocol's ASCII encoding via `emma65_via`. This unit renders a static
placeholder Port A row (see `cells.py`) on top of the connection plumbing --
no live VIA data or interactivity yet, that lands in later units.
"""

from __future__ import annotations

import argparse
import sys

import pygame

from emma65_via import ViaAsciiClient

from . import cells

DEFAULT_SOCKET = "~/.emma/sock/via6522"
RECONNECT_INTERVAL_MS = 1000

FOOTER_H = cells.sc(24)
CONNECTED_COLOR = (120, 200, 140)
DISCONNECTED_COLOR = (210, 100, 100)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--socket", default=DEFAULT_SOCKET,
        help=f"Unix-domain socket path for the VIA transport (default: {DEFAULT_SOCKET})",
    )
    return parser.parse_args(argv)


class Peripheral:
    """Owns the VIA connection. Drives no pins yet -- read/write pin state lands in later units."""

    def __init__(self, args: argparse.Namespace):
        self._client = ViaAsciiClient(args.socket)
        self._next_connect_attempt = 0

    @property
    def connected(self) -> bool:
        return self._client.connected

    def connect_if_needed(self, now_ms: int) -> None:
        if self._client.connected or now_ms < self._next_connect_attempt:
            return
        if not self._client.connect():
            self._next_connect_attempt = now_ms + RECONNECT_INTERVAL_MS

    def poll(self) -> None:
        if not self._client.connected:
            return
        try:
            self._client.poll()
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry

    def close(self) -> None:
        self._client.close()


def run(args: argparse.Namespace) -> None:
    pygame.init()
    pygame.display.set_caption("emma65 VIA GPIO playground")

    port_a = cells.build_port_a()
    content_right = cells.layout_row(port_a, 0)
    window_size = (
        cells.LEFT_MARGIN + content_right + cells.LEFT_MARGIN,
        cells.CONTENT_HEIGHT + FOOTER_H,
    )
    screen = pygame.display.set_mode(window_size)
    cells.layout_row(port_a, cells.LEFT_MARGIN)

    clock = pygame.time.Clock()
    fonts = cells.Fonts()
    status_font = pygame.font.SysFont("Consolas,Menlo,monospace", cells.sc(12))

    peripheral = Peripheral(args)

    running = True
    while running:
        now_ms = pygame.time.get_ticks()
        peripheral.connect_if_needed(now_ms)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        peripheral.poll()

        screen.fill(cells.BG)
        cells.draw_status_bar(screen, fonts, "PORT A", window_size[0])
        for cell in port_a:
            cell.draw(screen, fonts)

        status = "connected" if peripheral.connected else "connecting..."
        color = CONNECTED_COLOR if peripheral.connected else DISCONNECTED_COLOR
        cells.draw_text(
            screen, status_font, f"{status}  ({args.socket})", color,
            topleft=(cells.LEFT_MARGIN, cells.CONTENT_HEIGHT + cells.sc(4)),
        )

        pygame.display.flip()
        clock.tick(60)

    peripheral.close()
    pygame.quit()


def main(argv: list[str] | None = None) -> None:
    run(parse_args(sys.argv[1:] if argv is None else argv))
