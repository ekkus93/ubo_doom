"""
tests/test_doom_controller.py

Unit tests for DoomController — the pure-Python input-routing state machine.

Run from the ubo_service/070-doom/ directory:
    pytest

Or from the workspace root:
    pytest ubo_service/070-doom/

No Kivy, no .so, no ubo_app imports required.  Every test constructs a
DoomController with a recording tap_fn and then asserts on the emitted keys.
"""

from __future__ import annotations

import pytest

from doom_controller import DoomController, GS_LEVEL
from native.doom_lib import UboKey

# ------------------------------------------------------------------ #
# Helper / fixtures
# ------------------------------------------------------------------ #

GS_INTERMISSION = 1
GS_FINALE = 2
GS_DEMOSCREEN = 3


class Recorder:
    """Records (key, hold_ticks) tuples emitted by the controller."""

    def __init__(self) -> None:
        self.calls: list[tuple[UboKey, int]] = []

    def tap(self, key: UboKey, hold_ticks: int) -> None:
        self.calls.append((key, hold_ticks))

    @property
    def last(self) -> tuple[UboKey, int]:
        assert self.calls, "no tap was emitted"
        return self.calls[-1]

    @property
    def last_key(self) -> UboKey:
        return self.last[0]

    @property
    def last_hold(self) -> int:
        return self.last[1]

    def clear(self) -> None:
        self.calls.clear()


@pytest.fixture()
def rec() -> Recorder:
    return Recorder()


@pytest.fixture()
def ctrl(rec: Recorder) -> DoomController:
    return DoomController(tap_fn=rec.tap)


def _set_in_level(ctrl: DoomController) -> None:
    """Drive the controller into the in-level state."""
    ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)


def _set_menu_open(ctrl: DoomController) -> None:
    """Drive the controller into the menu-active state (not in-level)."""
    ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=True)


def _set_intermission(ctrl: DoomController) -> None:
    ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)


# ------------------------------------------------------------------ #
# go_up / go_down — always forward/backward, no state dependency
# ------------------------------------------------------------------ #

class TestMovement:
    def test_go_up_always_sends_up(self, ctrl: DoomController, rec: Recorder) -> None:
        ctrl.go_up()
        assert rec.last_key is UboKey.UP

    def test_go_up_hold_is_8_ticks(self, ctrl: DoomController, rec: Recorder) -> None:
        ctrl.go_up()
        assert rec.last_hold == 8

    def test_go_down_always_sends_down(self, ctrl: DoomController, rec: Recorder) -> None:
        ctrl.go_down()
        assert rec.last_key is UboKey.DOWN

    def test_go_down_hold_is_8_ticks(self, ctrl: DoomController, rec: Recorder) -> None:
        ctrl.go_down()
        assert rec.last_hold == 8

    def test_go_up_ignores_alt_mode(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()  # enable ALT
        ctrl.go_up()
        assert rec.last_key is UboKey.UP

    def test_go_down_ignores_alt_mode(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        ctrl.go_down()
        assert rec.last_key is UboKey.DOWN

    def test_go_up_ignores_menu_state(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_menu_open(ctrl)
        ctrl.go_up()
        assert rec.last_key is UboKey.UP

    def test_go_down_ignores_menu_state(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_menu_open(ctrl)
        ctrl.go_down()
        assert rec.last_key is UboKey.DOWN


# ------------------------------------------------------------------ #
# go_back routing
# ------------------------------------------------------------------ #

class TestGoBack:
    def test_in_level_sends_fire(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.go_back()
        assert rec.last_key is UboKey.FIRE

    def test_in_level_absorbs_event(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        assert ctrl.go_back() is True

    def test_menu_active_sends_escape(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_menu_open(ctrl)
        ctrl.go_back()
        assert rec.last_key is UboKey.ESCAPE

    def test_menu_active_absorbs_event(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_menu_open(ctrl)
        assert ctrl.go_back() is True

    def test_other_state_sends_menu_select(self, ctrl: DoomController, rec: Recorder) -> None:
        # Default state: not alive, not in level, no menu
        ctrl.go_back()
        assert rec.last_key is UboKey.MENU_SELECT

    def test_intermission_sends_menu_select(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_intermission(ctrl)
        ctrl.go_back()
        assert rec.last_key is UboKey.MENU_SELECT

    def test_always_returns_true(self, ctrl: DoomController, rec: Recorder) -> None:
        """go_back must return True in every state so ubo doesn't close the page."""
        for setup in [
            lambda: None,
            lambda: _set_in_level(ctrl),
            lambda: _set_menu_open(ctrl),
            lambda: _set_intermission(ctrl),
        ]:
            setup()
            assert ctrl.go_back() is True, f"go_back() returned False in state: in_level={ctrl.in_level} menu={ctrl.menu_active}"

    def test_in_level_fire_not_escape(self, ctrl: DoomController, rec: Recorder) -> None:
        """Regression: in-level go_back must NOT send ESCAPE (would open menu mid-game)."""
        _set_in_level(ctrl)
        ctrl.go_back()
        assert rec.last_key is not UboKey.ESCAPE

    def test_menu_escape_not_menu_select(self, ctrl: DoomController, rec: Recorder) -> None:
        """Regression: menu go_back must NOT send ENTER (would select INTO menus)."""
        _set_menu_open(ctrl)
        ctrl.go_back()
        assert rec.last_key is not UboKey.MENU_SELECT


# ------------------------------------------------------------------ #
# btn_l2 routing
# ------------------------------------------------------------------ #

class TestBtnL2:
    def test_normal_mode_turns_left(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.btn_l2()
        assert rec.last_key is UboKey.LEFT

    def test_normal_mode_hold_exceeds_slowturntics(self, ctrl: DoomController, rec: Recorder) -> None:
        # SLOWTURNTICS = 10; hold must be > 10 for full-speed turning.
        ctrl.btn_l2()
        assert rec.last_hold > 10

    def test_alt_mode_sends_use(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        ctrl.btn_l2()
        assert rec.last_key is UboKey.USE

    def test_alt_mode_not_left(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        ctrl.btn_l2()
        assert rec.last_key is not UboKey.LEFT


# ------------------------------------------------------------------ #
# btn_l3 routing
# ------------------------------------------------------------------ #

class TestBtnL3:
    def test_normal_in_level_turns_right(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.RIGHT

    def test_normal_in_level_hold_exceeds_slowturntics(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.btn_l3()
        assert rec.last_hold > 10

    def test_normal_menu_active_sends_menu_select(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_menu_open(ctrl)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.MENU_SELECT

    def test_alt_mode_sends_escape(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        ctrl.btn_l3()
        assert rec.last_key is UboKey.ESCAPE

    def test_alt_mode_ignores_menu_active(self, ctrl: DoomController, rec: Recorder) -> None:
        """
        Regression: in ALT mode, btn_l3 must send ESCAPE even if menu is active.
        The alt_mode branch must short-circuit before the menu_active branch.
        """
        # Force alt_mode=True while menu is active:
        # ALT mode can only be set in-level, so: enter level → toggle → open menu
        _set_in_level(ctrl)
        ctrl.toggle_mode()          # now alt_mode=True
        _set_menu_open(ctrl)        # now menu_active=True, but alt_mode stays True
        ctrl.btn_l3()
        assert rec.last_key is UboKey.ESCAPE

    def test_default_state_sends_right(self, ctrl: DoomController, rec: Recorder) -> None:
        # No state updates: not alive, not in level, no menu
        ctrl.btn_l3()
        assert rec.last_key is UboKey.RIGHT


# ------------------------------------------------------------------ #
# toggle_mode
# ------------------------------------------------------------------ #

class TestToggleMode:
    def test_no_op_when_not_in_level(self, ctrl: DoomController) -> None:
        result = ctrl.toggle_mode()
        assert result is False
        assert ctrl.alt_mode is False

    def test_no_op_during_menu(self, ctrl: DoomController) -> None:
        _set_menu_open(ctrl)
        result = ctrl.toggle_mode()
        assert result is False
        assert ctrl.alt_mode is False

    def test_no_op_during_intermission(self, ctrl: DoomController) -> None:
        _set_intermission(ctrl)
        result = ctrl.toggle_mode()
        assert result is False
        assert ctrl.alt_mode is False

    def test_enables_alt_mode_in_level(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        result = ctrl.toggle_mode()
        assert result is True
        assert ctrl.alt_mode is True

    def test_disables_alt_mode_in_level(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()  # on
        result = ctrl.toggle_mode()  # off
        assert result is True
        assert ctrl.alt_mode is False

    def test_does_not_emit_key(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        assert rec.calls == []


# ------------------------------------------------------------------ #
# exit_level
# ------------------------------------------------------------------ #

class TestExitLevel:
    def test_no_op_when_alt_mode_false(self, ctrl: DoomController) -> None:
        result = ctrl.exit_level()
        assert result is False
        assert ctrl.alt_mode is False

    def test_resets_alt_mode_when_active(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        assert ctrl.alt_mode is True
        result = ctrl.exit_level()
        assert result is True
        assert ctrl.alt_mode is False

    def test_does_not_emit_key(self, ctrl: DoomController, rec: Recorder) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        rec.clear()
        ctrl.exit_level()
        assert rec.calls == []


# ------------------------------------------------------------------ #
# update_game_state — cached state
# ------------------------------------------------------------------ #

class TestUpdateGameState:
    def test_dead_engine_clears_everything(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=False, gamestate=GS_LEVEL, menuactive=True)
        assert ctrl.in_level is False
        assert ctrl.menu_active is False

    def test_alive_in_level_no_menu(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        assert ctrl.in_level is True
        assert ctrl.menu_active is False

    def test_alive_in_level_menu_open(self, ctrl: DoomController) -> None:
        """Menu overlay on GS_LEVEL: in_level must be False (menu takes priority)."""
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=True)
        assert ctrl.in_level is False
        assert ctrl.menu_active is True

    def test_alive_in_level_menu_mutually_exclusive(self, ctrl: DoomController) -> None:
        """in_level and menu_active can never both be True simultaneously."""
        for alive in (True, False):
            for gs in (GS_LEVEL, GS_INTERMISSION, GS_FINALE, GS_DEMOSCREEN):
                for menu in (True, False):
                    ctrl.update_game_state(alive=alive, gamestate=gs, menuactive=menu)
                    assert not (ctrl.in_level and ctrl.menu_active), (
                        f"Both True: alive={alive} gs={gs} menu={menu}"
                    )

    def test_intermission_not_in_level(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        assert ctrl.in_level is False

    def test_demoscreen_not_in_level(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_DEMOSCREEN, menuactive=False)
        assert ctrl.in_level is False

    # -- just-left-level return value --

    def test_returns_false_when_never_in_level(self, ctrl: DoomController) -> None:
        result = ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        assert result is False

    def test_returns_false_when_entering_level(self, ctrl: DoomController) -> None:
        # Transition: not-in-level → in-level
        result = ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        assert result is False

    def test_returns_false_when_staying_in_level(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        result = ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        assert result is False

    def test_returns_true_when_leaving_level_to_intermission(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        result = ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        assert result is True

    def test_returns_true_when_leaving_level_to_menu(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        result = ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=True)
        assert result is True

    def test_returns_true_when_engine_dies_mid_level(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        result = ctrl.update_game_state(alive=False, gamestate=GS_LEVEL, menuactive=False)
        assert result is True

    def test_returns_false_after_already_left(self, ctrl: DoomController) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)
        ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        result = ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        assert result is False


# ------------------------------------------------------------------ #
# Integration: the ENTER/ESCAPE ping-pong regression
# ------------------------------------------------------------------ #

class TestPingPongRegression:
    """
    Regression test for the race condition that caused go_back() to alternate
    between ESCAPE and ENTER when opening New Game.

    Root cause: go_back() was calling doom.menuactive() directly from the Kivy
    main thread, which races with the tick thread.  The fix caches the state in
    update_game_state() (tick thread only) and go_back() reads only the cached value.

    This test simulates the exact scenario from the logs:
      - Doom is on the main menu (menu_active=True, in_level=False)
      - User presses BACK repeatedly
      - Each call should emit ESCAPE, never ENTER
    """

    def test_repeated_go_back_in_menu_always_escapes(
        self, ctrl: DoomController, rec: Recorder
    ) -> None:
        _set_menu_open(ctrl)
        for _ in range(10):
            rec.clear()
            ctrl.go_back()
            assert rec.last_key is UboKey.ESCAPE, "Expected ESCAPE, got ENTER (ping-pong bug)"

    def test_repeated_go_back_in_level_always_fires(
        self, ctrl: DoomController, rec: Recorder
    ) -> None:
        _set_in_level(ctrl)
        for _ in range(10):
            rec.clear()
            ctrl.go_back()
            assert rec.last_key is UboKey.FIRE


# ------------------------------------------------------------------ #
# Integration: ALT mode lifecycle
# ------------------------------------------------------------------ #

class TestAltModeLifecycle:
    def test_alt_mode_set_only_in_level(self, ctrl: DoomController) -> None:
        """ALT mode must be off outside of active gameplay."""
        for setup in [
            lambda: ctrl.update_game_state(alive=False, gamestate=-1, menuactive=False),
            lambda: _set_menu_open(ctrl),
            lambda: _set_intermission(ctrl),
        ]:
            setup()
            ctrl.toggle_mode()
            assert ctrl.alt_mode is False, "ALT mode enabled outside in-level state"

    def test_alt_mode_persists_within_level(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        assert ctrl.alt_mode is True
        # Another tick in-level: state unchanged
        _set_in_level(ctrl)
        assert ctrl.alt_mode is True

    def test_alt_mode_cleared_on_level_exit(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        assert ctrl.alt_mode is True
        # Simulate leaving level
        just_left = ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        assert just_left is True
        ctrl.exit_level()   # DoomPage calls this on the main thread
        assert ctrl.alt_mode is False

    def test_alt_mode_not_reopenable_during_intermission(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        ctrl.update_game_state(alive=True, gamestate=GS_INTERMISSION, menuactive=False)
        ctrl.exit_level()
        ctrl.toggle_mode()   # should be a no-op
        assert ctrl.alt_mode is False

    def test_alt_mode_cleared_on_engine_death(self, ctrl: DoomController) -> None:
        _set_in_level(ctrl)
        ctrl.toggle_mode()
        just_left = ctrl.update_game_state(alive=False, gamestate=-1, menuactive=False)
        assert just_left is True
        ctrl.exit_level()
        assert ctrl.alt_mode is False
