"""A push button and a toggle button wired to two VIA GPIO pins.

Connects to a `via/6522` device's `unix:` transport and drives two bits of
one port: the push button asserts its bit while held and releases it on
mouse-up; the toggle button flips its bit each time it's clicked. Nothing
else about the port is touched, so it can share a port with other
peripherals driving other bits.
"""

from __future__ import annotations

import argparse
import sys

import pygame

from .via_transport import ViaAsciiClient

DEFAULT_SOCKET = "~/.emma/sock/via6522"
RECONNECT_INTERVAL_MS = 1000

WINDOW_SIZE = (360, 240)
BG_COLOR = (24, 24, 28)
IDLE_COLOR = (70, 70, 80)
ACTIVE_COLOR = (90, 200, 120)
TEXT_COLOR = (230, 230, 230)
CONNECTED_COLOR = (120, 200, 140)
DISCONNECTED_COLOR = (210, 100, 100)

PUSH_RECT = pygame.Rect(30, 55, 140, 120)
TOGGLE_RECT = pygame.Rect(190, 55, 140, 120)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--socket", default=DEFAULT_SOCKET,
        help=f"Unix-domain socket path for the VIA transport (default: {DEFAULT_SOCKET})",
    )
    parser.add_argument(
        "--via-port", choices=("A", "B"), default="A",
        help="VIA port the buttons are wired to (default: A)",
    )
    parser.add_argument(
        "--push-bit", type=int, choices=range(8), default=0, metavar="0-7",
        help="Port bit driven by the push button (default: 0)",
    )
    parser.add_argument(
        "--toggle-bit", type=int, choices=range(8), default=1, metavar="0-7",
        help="Port bit driven by the toggle button (default: 1)",
    )
    args = parser.parse_args(argv)
    if args.push_bit == args.toggle_bit:
        parser.error("--push-bit and --toggle-bit must be different")
    return args


class ButtonPeripheral:
    """Owns the VIA connection and the two bits this peripheral drives."""

    def __init__(self, args: argparse.Namespace):
        self._client = ViaAsciiClient(args.socket)
        self._via_port = args.via_port
        self._push_mask = 1 << args.push_bit
        self._toggle_mask = 1 << args.toggle_bit
        self.push_active = False
        self.toggle_active = False
        self._next_connect_attempt = 0

    @property
    def connected(self) -> bool:
        return self._client.connected

    def connect_if_needed(self, now_ms: int) -> None:
        if self._client.connected or now_ms < self._next_connect_attempt:
            return
        if self._client.connect():
            # Re-assert both bits so a mid-press/toggle state survives a reconnect.
            self._send_bit(self._push_mask, self.push_active)
            self._send_bit(self._toggle_mask, self.toggle_active)
        else:
            self._next_connect_attempt = now_ms + RECONNECT_INTERVAL_MS

    def poll(self) -> None:
        if not self._client.connected:
            return
        try:
            self._client.drain()
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry

    def set_push(self, active: bool) -> None:
        if active == self.push_active:
            return
        self.push_active = active
        self._send_bit(self._push_mask, active)

    def toggle(self) -> None:
        self.toggle_active = not self.toggle_active
        self._send_bit(self._toggle_mask, self.toggle_active)

    def close(self) -> None:
        self._client.close()

    def _send_bit(self, mask: int, active: bool) -> None:
        if not self._client.connected:
            return
        try:
            if active:
                self._client.set_bits(self._via_port, mask)
            else:
                self._client.reset_bits(self._via_port, mask)
        except ConnectionError:
            pass  # connect_if_needed() will notice and retry


def _draw_button(screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect, label: str, active: bool) -> None:
    pygame.draw.rect(screen, ACTIVE_COLOR if active else IDLE_COLOR, rect, border_radius=10)
    text = font.render(label, True, TEXT_COLOR)
    screen.blit(text, text.get_rect(center=rect.center))


def run(args: argparse.Namespace) -> None:
    pygame.init()
    pygame.display.set_caption("emma65 buttons")
    screen = pygame.display.set_mode(WINDOW_SIZE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    status_font = pygame.font.SysFont(None, 20)

    peripheral = ButtonPeripheral(args)

    running = True
    while running:
        now_ms = pygame.time.get_ticks()
        peripheral.connect_if_needed(now_ms)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if PUSH_RECT.collidepoint(event.pos):
                    peripheral.set_push(True)
                elif TOGGLE_RECT.collidepoint(event.pos):
                    peripheral.toggle()
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                peripheral.set_push(False)

        peripheral.poll()

        screen.fill(BG_COLOR)
        _draw_button(screen, font, PUSH_RECT, "PUSH", peripheral.push_active)
        _draw_button(screen, font, TOGGLE_RECT, "TOGGLE", peripheral.toggle_active)

        status = "connected" if peripheral.connected else "connecting..."
        color = CONNECTED_COLOR if peripheral.connected else DISCONNECTED_COLOR
        status_text = status_font.render(
            f"{status}  (port {args.via_port}, bits {args.push_bit}/{args.toggle_bit})", True, color,
        )
        screen.blit(status_text, status_text.get_rect(midtop=(WINDOW_SIZE[0] // 2, 195)))

        pygame.display.flip()
        clock.tick(60)

    peripheral.close()
    pygame.quit()


def main(argv: list[str] | None = None) -> None:
    run(parse_args(sys.argv[1:] if argv is None else argv))
