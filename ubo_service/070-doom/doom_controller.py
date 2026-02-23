"""
ubo_service/070-doom/doom_controller.py

Pure-Python state machine for Doom input routing.

No Kivy, DoomLib, or ubo_app dependencies — fully unit-testable.

DoomPage owns one instance and:
  - calls update_game_state() from the tick thread after each doom.tick()
  - calls go_up/go_down/go_back/btn_l2/btn_l3/toggle_mode from the Kivy main thread
  - provides a tap_fn that enqueues key events for the tick thread

The state machine rules are:

  Normal mode (default):
    go_up      → forward  (hold=8 ticks), always
    go_down    → backward (hold=8 ticks), always
    go_back    → FIRE (in-level), MENU_SELECT/confirm (menu open), ESCAPE (title/demo)
    btn_l2     → turn LEFT with hold=12  (>SLOWTURNTICS=10 for full speed)
    btn_l3     → turn RIGHT with hold=12 (in-level), MENU_SELECT/ENTER (in menu)
    toggle_mode→ switch to ALT mode (only when in-level; no-op otherwise)

  ALT mode (in-game only; auto-resets when leaving a level):
    go_up/down → unchanged (forward/backward)
    go_back    → FIRE (always)
    btn_l2     → USE (open doors/push switches)
    btn_l3     → ESCAPE (open/close menu)
    toggle_mode→ switch back to Normal mode

  Menu / demo / intermission:
    toggle_mode→ no-op  (ALT mode has no meaning outside a level)

  go_back return value is always True so callers can use it as a Kivy handler
  that absorbs the BACK event (prevents ubo from treating BACK as "exit page").
"""

from __future__ import annotations

from typing import Callable

# Import only the enum — no .so is loaded at import time; see native/doom_lib.py.
from native.doom_lib import UboKey

# GS_LEVEL constant — keep in sync with doomstat.h
GS_LEVEL: int = 0


class DoomController:
    """
    Input routing and mode state for the Doom service page.

    All public methods are thread-safe under CPython's GIL:
      - update_game_state() is called from the tick thread
      - all other methods are called from the Kivy main thread
      - state reads/writes are single bool assignments (GIL-atomic in CPython)

    Args:
        tap_fn: called to emit a key event; signature is (key: UboKey, hold_ticks: int)
    """

    def __init__(self, tap_fn: Callable[[UboKey, int], None]) -> None:
        self._tap_fn = tap_fn
        # These bools are written by tick thread, read by main thread.
        # Single-assignment reads/writes are atomic under CPython's GIL.
        self._in_level: bool = False
        self._menu_active: bool = False
        # This bool is written and read only on the Kivy main thread.
        self._alt_mode: bool = False

    # ------------------------------------------------------------------ #
    # Properties — read-only views for DoomPage (footer items, etc.)
    # ------------------------------------------------------------------ #

    @property
    def in_level(self) -> bool:
        return self._in_level

    @property
    def menu_active(self) -> bool:
        return self._menu_active

    @property
    def alt_mode(self) -> bool:
        return self._alt_mode

    # ------------------------------------------------------------------ #
    # Tick-thread state update
    # ------------------------------------------------------------------ #

    def update_game_state(
        self,
        *,
        alive: bool,
        gamestate: int,
        menuactive: bool,
    ) -> bool:
        """
        Refresh cached state from a completed doom.tick().

        Called from the tick thread immediately after doom.tick() returns so
        the values are consistent with the just-completed game frame.

        Returns True if the game *just left* a level (was in-level, now not).
        DoomPage uses this signal to call exit_level() on the main thread.
        """
        menu_active = menuactive if alive else False
        in_level = alive and gamestate == GS_LEVEL and not menu_active
        was_in_level = self._in_level
        # Write both together — in_level was derived from menu_active,
        # so they are always mutually consistent.
        self._menu_active = menu_active
        self._in_level = in_level
        return was_in_level and not in_level

    # ------------------------------------------------------------------ #
    # Main-thread input handlers
    # ------------------------------------------------------------------ #

    def go_up(self) -> None:
        """Always forward, regardless of ALT mode."""
        self._tap(UboKey.UP, hold_ticks=8)

    def go_down(self) -> None:
        """Always backward, regardless of ALT mode."""
        self._tap(UboKey.DOWN, hold_ticks=8)

    def go_back(self) -> bool:
        """
        Absorb the BACK hardware button — never propagate to ubo (which would
        close the Doom service page).

        Routing:
          in-level (no menu)        → FIRE (shoot weapon)
          menu visible              → MENU_SELECT (confirm/navigate forward)
          title screen / demo       → ESCAPE (opens the Doom main menu)

        This allows the common workflow: BACK × N to start a game from the title
        screen — first BACK opens the menu, subsequent BACKs confirm each menu
        selection (New Game → episode → skill → game starts).

        No ping-pong risk: title sends ESCAPE (menu_active=False→True), then
        menu sends MENU_SELECT (menu_active=True) which either enters a sub-menu
        or starts a level, never toggling back to False until a level is loaded.

        Returns True always (Kivy handler return value meaning "event handled").
        """
        if self._in_level:
            self._tap(UboKey.FIRE)
        elif self._menu_active:
            self._tap(UboKey.MENU_SELECT)
        else:
            self._tap(UboKey.ESCAPE)
        return True

    def btn_l2(self) -> None:
        """Normal: turn left.  ALT: use door/switch."""
        if self._alt_mode:
            self._tap(UboKey.USE)
        else:
            self._tap(UboKey.LEFT, hold_ticks=12)

    def btn_l3(self) -> None:
        """
        Normal: turn right (in-level) or confirm/select (in menu).
        ALT: open/close menu via ESCAPE.
        """
        if self._alt_mode:
            self._tap(UboKey.ESCAPE)
        elif self._menu_active:
            self._tap(UboKey.MENU_SELECT)
        else:
            self._tap(UboKey.RIGHT, hold_ticks=12)

    def toggle_mode(self) -> bool:
        """
        Toggle between Normal and ALT mode.

        Only meaningful during active gameplay; ignored in menus, intermissions,
        demos, and finales so the mode footprint doesn't get into a weird state.

        Returns True if the mode actually changed (DoomPage uses this to refresh
        the footer ActionItems).
        """
        if not self._in_level:
            return False
        self._alt_mode = not self._alt_mode
        return True

    def exit_level(self) -> bool:
        """
        Called on the Kivy main thread when update_game_state() signals a
        level exit (True return).

        Resets ALT mode to Normal. Returns True if the footer needs to be
        refreshed (i.e. alt_mode was active and got cleared).
        """
        if self._alt_mode:
            self._alt_mode = False
            return True
        return False

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _tap(self, key: UboKey, hold_ticks: int = 2) -> None:
        self._tap_fn(key, hold_ticks)
