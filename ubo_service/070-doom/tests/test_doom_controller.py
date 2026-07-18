"""Unit tests for the pure-Python Ubo v2 Doom control mapper."""

from __future__ import annotations

import pytest

from doom_controller import (
    DoomController,
    GS_DEMOSCREEN,
    GS_FINALE,
    GS_INTERMISSION,
    GS_LEVEL,
)
from native.doom_lib import UboKey


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[UboKey, int]] = []

    def tap(self, key: UboKey, hold_ticks: int) -> None:
        self.calls.append((key, hold_ticks))

    @property
    def last_key(self) -> UboKey:
        assert self.calls
        return self.calls[-1][0]

    @property
    def last_hold(self) -> int:
        assert self.calls
        return self.calls[-1][1]


@pytest.fixture()
def rec() -> Recorder:
    return Recorder()


@pytest.fixture()
def ctrl(rec: Recorder) -> DoomController:
    return DoomController(rec.tap)


def set_level(ctrl: DoomController) -> None:
    ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=False)


def set_menu(ctrl: DoomController) -> None:
    ctrl.update_game_state(alive=True, gamestate=GS_LEVEL, menuactive=True)


class TestMovement:
    def test_up_moves_forward_for_eight_ticks(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        ctrl.go_up()
        assert rec.calls[-1] == (UboKey.UP, 8)

    def test_down_moves_backward_for_eight_ticks(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        ctrl.go_down()
        assert rec.calls[-1] == (UboKey.DOWN, 8)

    def test_movement_is_unchanged_in_alt_mode(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        ctrl.toggle_mode()
        ctrl.go_up()
        ctrl.go_down()
        assert [key for key, _ in rec.calls[-2:]] == [UboKey.UP, UboKey.DOWN]


class TestL2:
    def test_normal_mode_turns_left(self, ctrl: DoomController, rec: Recorder) -> None:
        set_level(ctrl)
        ctrl.btn_l2()
        assert rec.last_key is UboKey.LEFT
        assert rec.last_hold > 10

    def test_alt_mode_uses(self, ctrl: DoomController, rec: Recorder) -> None:
        set_level(ctrl)
        ctrl.toggle_mode()
        ctrl.btn_l2()
        assert rec.last_key is UboKey.USE


class TestL3:
    def test_normal_gameplay_turns_right(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.RIGHT
        assert rec.last_hold > 10

    def test_alt_gameplay_fires(self, ctrl: DoomController, rec: Recorder) -> None:
        set_level(ctrl)
        ctrl.toggle_mode()
        ctrl.btn_l3()
        assert rec.last_key is UboKey.FIRE

    def test_open_menu_selects(self, ctrl: DoomController, rec: Recorder) -> None:
        set_menu(ctrl)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.MENU_SELECT

    @pytest.mark.parametrize("gamestate", [GS_INTERMISSION, GS_FINALE])
    def test_intermission_and_finale_continue(
        self,
        ctrl: DoomController,
        rec: Recorder,
        gamestate: int,
    ) -> None:
        ctrl.update_game_state(alive=True, gamestate=gamestate, menuactive=False)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.MENU_SELECT

    def test_title_or_demo_opens_menu(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_DEMOSCREEN, menuactive=False)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.ESCAPE

    def test_title_then_menu_does_not_escape_select_ping_pong(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        ctrl.update_game_state(alive=True, gamestate=GS_DEMOSCREEN, menuactive=False)
        ctrl.btn_l3()
        assert rec.last_key is UboKey.ESCAPE

        set_menu(ctrl)
        ctrl.btn_l3()
        ctrl.btn_l3()
        assert [key for key, _ in rec.calls[-2:]] == [
            UboKey.MENU_SELECT,
            UboKey.MENU_SELECT,
        ]


class TestModeLifecycle:
    def test_mode_only_toggles_in_active_level(self, ctrl: DoomController) -> None:
        assert ctrl.toggle_mode() is False
        set_menu(ctrl)
        assert ctrl.toggle_mode() is False
        ctrl.update_game_state(
            alive=True,
            gamestate=GS_INTERMISSION,
            menuactive=False,
        )
        assert ctrl.toggle_mode() is False

        set_level(ctrl)
        assert ctrl.toggle_mode() is True
        assert ctrl.alt_mode is True

    def test_mode_resets_after_level_exit(self, ctrl: DoomController) -> None:
        set_level(ctrl)
        ctrl.toggle_mode()
        just_left = ctrl.update_game_state(
            alive=True,
            gamestate=GS_INTERMISSION,
            menuactive=False,
        )
        assert just_left is True
        assert ctrl.exit_level() is True
        assert ctrl.alt_mode is False

    def test_no_false_level_exit(self, ctrl: DoomController) -> None:
        assert (
            ctrl.update_game_state(
                alive=True,
                gamestate=GS_INTERMISSION,
                menuactive=False,
            )
            is False
        )
        set_level(ctrl)
        assert (
            ctrl.update_game_state(
                alive=True,
                gamestate=GS_LEVEL,
                menuactive=False,
            )
            is False
        )

    def test_engine_death_clears_cached_state(self, ctrl: DoomController) -> None:
        set_level(ctrl)
        assert (
            ctrl.update_game_state(alive=False, gamestate=-1, menuactive=True) is True
        )
        assert ctrl.in_level is False
        assert ctrl.menu_active is False
        assert ctrl.gamestate == -1
