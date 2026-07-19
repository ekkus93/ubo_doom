"""Pure-Python Doom input routing for the Ubo v2 keypad model."""

from __future__ import annotations

from collections.abc import Callable

from native.doom_lib import UboKey

GS_LEVEL = 0
GS_INTERMISSION = 1
GS_FINALE = 2
GS_DEMOSCREEN = 3


class DoomController:
    """Map Ubo's five gameplay buttons to Doom's keyboard interface.

    BACK and HOME are intentionally not handled here. Ubo v2 owns those buttons:
    BACK closes the current render view and HOME returns to Ubo's home screen.
    """

    def __init__(self, tap_fn: Callable[[UboKey, int], None]) -> None:
        self._tap_fn = tap_fn
        self._alive = False
        self._gamestate = GS_DEMOSCREEN
        self._in_level = False
        self._menu_active = False
        self._alt_mode = False

    @property
    def in_level(self) -> bool:
        return self._in_level

    @property
    def menu_active(self) -> bool:
        return self._menu_active

    @property
    def alt_mode(self) -> bool:
        return self._alt_mode

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
        self._tap(UboKey.UP, hold_ticks=8)

    def go_down(self) -> None:
        self._tap(UboKey.DOWN, hold_ticks=8)

    def btn_l2(self) -> None:
        """Normal mode turns left; alternate mode uses doors and switches."""
        if self._alt_mode and self._in_level:
            self._tap(UboKey.USE)
        else:
            self._tap(UboKey.LEFT, hold_ticks=12)

    def btn_l3(self) -> None:
        """Context-sensitive right/select/open-menu/fire action.

        Normal mode:
        - gameplay: turn right
        - Doom menu: select
        - intermission/finale: continue
        - title/demo: open the Doom menu

        Alternate mode during gameplay: fire.
        """
        if self._alt_mode and self._in_level:
            self._tap(UboKey.FIRE)
        elif self._menu_active:
            self._tap(UboKey.MENU_SELECT)
        elif self._in_level:
            self._tap(UboKey.RIGHT, hold_ticks=12)
        elif self._gamestate in (GS_INTERMISSION, GS_FINALE):
            self._tap(UboKey.MENU_SELECT)
        else:
            self._tap(UboKey.ESCAPE)

    def toggle_mode(self) -> bool:
        """Toggle alternate controls while actively playing a level."""
        if not self._in_level:
            return False
        self._alt_mode = not self._alt_mode
        return True

    def exit_level(self) -> bool:
        """Reset alternate mode after leaving active gameplay."""
        if not self._alt_mode:
            return False
        self._alt_mode = False
        return True

    def _tap(self, key: UboKey, hold_ticks: int = 2) -> None:
        self._tap_fn(key, hold_ticks)
