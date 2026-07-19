"""Pure-Python Doom input routing for the Ubo v2 keypad model."""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum

from native.doom_lib import UboKey

GS_LEVEL = 0
GS_INTERMISSION = 1
GS_FINALE = 2
GS_DEMOSCREEN = 3


class DownMode(IntEnum):
    """What the DOWN button does during active gameplay.

    Turning (L2/L3) and moving forward (UP) are always live; the DOWN button is
    multiplexed through these functions, cycled by the MODE button (L1). Values
    are in cycle order, so advancing is ``(mode + 1) % len(DownMode)``.
    """

    FIRE = 0
    USE = 1
    BACK = 2
    WEAPON = 3


class DoomController:
    """Map Ubo's five inputs (UP, DOWN, L1, L2, L3) to Doom's keyboard interface.

    Turning is always available: L2 turns left and L3 turns right during
    gameplay. Forward is always UP. The DOWN button is multiplexed through
    :class:`DownMode` (fire / use / back / next-weapon), cycled by L1 (MODE), so
    the player can turn and shoot at once without giving up turning.

    BACK and HOME are intentionally not handled here — Ubo v2 owns those.
    """

    def __init__(self, tap_fn: Callable[[UboKey, int], None]) -> None:
        self._tap_fn = tap_fn
        self._alive = False
        self._gamestate = GS_DEMOSCREEN
        self._in_level = False
        self._menu_active = False
        self._down_mode = DownMode.FIRE

    @property
    def in_level(self) -> bool:
        return self._in_level

    @property
    def menu_active(self) -> bool:
        return self._menu_active

    @property
    def down_mode(self) -> DownMode:
        return self._down_mode

    @property
    def gamestate(self) -> int:
        return self._gamestate

    def update_game_state(
        self,
        *,
        alive: bool,
        gamestate: int,
        menuactive: bool,
        usergame: bool = True,
    ) -> bool:
        """Refresh cached engine state and report a transition out of gameplay.

        ``usergame`` distinguishes a real game from the attract-loop demos, which
        also run at ``GS_LEVEL``. Without it, a playing demo counts as being
        in a level, so buttons that should open the menu (to start a game) turn
        the player instead. Defaults to True for callers that cannot supply it.
        """
        menu_active = bool(menuactive) if alive else False
        in_level = bool(alive and usergame and gamestate == GS_LEVEL and not menu_active)
        was_in_level = self._in_level

        self._alive = alive
        self._gamestate = gamestate if alive else -1
        self._menu_active = menu_active
        self._in_level = in_level
        return was_in_level and not in_level

    def go_up(self) -> None:
        """UP always moves forward."""
        self._tap(UboKey.UP, hold_ticks=8)

    def go_down(self) -> None:
        """DOWN moves the menu cursor outside gameplay; in a level it follows the
        current :class:`DownMode` (fire / use / back / next-weapon)."""
        if not self._in_level:
            self._tap(UboKey.DOWN, hold_ticks=8)
        elif self._down_mode is DownMode.BACK:
            self._tap(UboKey.DOWN, hold_ticks=8)
        elif self._down_mode is DownMode.USE:
            self._tap(UboKey.USE)
        elif self._down_mode is DownMode.WEAPON:
            self._tap(UboKey.WEAPON_NEXT)
        else:  # DownMode.FIRE
            self._tap(UboKey.FIRE)

    def btn_l2(self) -> None:
        """L2 always turns left."""
        self._tap(UboKey.LEFT, hold_ticks=12)

    def btn_l3(self) -> None:
        """L3 turns right during gameplay; otherwise it drives the menus.

        - Doom menu open: select
        - gameplay: turn right
        - intermission/finale: continue
        - title/demo: open the Doom menu
        """
        if self._menu_active:
            self._tap(UboKey.MENU_SELECT)
        elif self._in_level:
            self._tap(UboKey.RIGHT, hold_ticks=12)
        elif self._gamestate in (GS_INTERMISSION, GS_FINALE):
            self._tap(UboKey.MENU_SELECT)
        else:
            self._tap(UboKey.ESCAPE)

    def cycle_mode(self) -> bool:
        """Advance the DOWN button's function; only while actively in a level.

        Returns True if the mode changed (so the caller can update the display).
        """
        if not self._in_level:
            return False
        self._down_mode = DownMode((self._down_mode + 1) % len(DownMode))
        return True

    def exit_level(self) -> bool:
        """Reset the DOWN button to FIRE after leaving active gameplay.

        Returns True if the mode actually changed.
        """
        if self._down_mode is DownMode.FIRE:
            return False
        self._down_mode = DownMode.FIRE
        return True

    def _tap(self, key: UboKey, hold_ticks: int = 2) -> None:
        self._tap_fn(key, hold_ticks)
