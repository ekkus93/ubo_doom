"""Unit tests for the pure-Python Ubo v2 Doom control mapper."""

from __future__ import annotations

import pytest

from doom_controller import (
    GS_DEMOSCREEN,
    GS_FINALE,
    GS_INTERMISSION,
    GS_LEVEL,
    DoomController,
    DownMode,
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

    def test_up_always_moves_forward_regardless_of_mode(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        for _ in range(len(DownMode)):
            ctrl.go_up()
            assert rec.last_key is UboKey.UP
            ctrl.cycle_mode()

    def test_down_is_back_only_in_back_mode(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        # Default is FIRE, so DOWN fires, not moves back.
        ctrl.go_down()
        assert rec.last_key is UboKey.FIRE
        while ctrl.down_mode is not DownMode.BACK:
            ctrl.cycle_mode()
        ctrl.go_down()
        assert rec.calls[-1] == (UboKey.DOWN, 8)


class TestL1:
    def test_cycles_mode_during_gameplay(self, ctrl: DoomController) -> None:
        set_level(ctrl)
        assert ctrl.down_mode is DownMode.FIRE
        assert ctrl.btn_l1() is True
        assert ctrl.down_mode is DownMode.USE

    def test_closes_menu_with_escape_when_menu_open(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_menu(ctrl)
        assert ctrl.btn_l1() is False
        assert rec.last_key is UboKey.ESCAPE

    def test_does_not_cycle_mode_while_menu_open(self, ctrl: DoomController) -> None:
        set_menu(ctrl)
        before = ctrl.down_mode
        ctrl.btn_l1()
        assert ctrl.down_mode is before  # sent ESC to close, did not cycle


class TestL2:
    def test_turns_left(self, ctrl: DoomController, rec: Recorder) -> None:
        set_level(ctrl)
        ctrl.btn_l2()
        assert rec.last_key is UboKey.LEFT
        assert rec.last_hold > 10

    def test_turns_left_in_every_mode(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        for _ in range(len(DownMode)):
            ctrl.btn_l2()
            assert rec.last_key is UboKey.LEFT
            ctrl.cycle_mode()


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

    def test_turns_right_in_every_mode(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        for _ in range(len(DownMode)):
            ctrl.btn_l3()
            assert rec.last_key is UboKey.RIGHT
            ctrl.cycle_mode()

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

    def test_attract_demo_opens_menu_not_turn(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        # Attract-loop demos run at GS_LEVEL but usergame=False. Pressing L3 must
        # open the menu (ESCAPE) so a game can be started, not turn right.
        ctrl.update_game_state(
            alive=True, gamestate=GS_LEVEL, menuactive=False, usergame=False
        )
        assert ctrl.in_level is False
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


class TestDownButton:
    def test_down_navigates_menus_outside_gameplay(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        # On the title/menu screens DOWN is always the menu-cursor down-arrow.
        ctrl.update_game_state(alive=True, gamestate=GS_DEMOSCREEN, menuactive=False)
        ctrl.go_down()
        assert rec.calls[-1] == (UboKey.DOWN, 8)

    def test_down_follows_mode_in_gameplay(
        self,
        ctrl: DoomController,
        rec: Recorder,
    ) -> None:
        set_level(ctrl)
        expected = {
            DownMode.FIRE: UboKey.FIRE,
            DownMode.USE: UboKey.USE,
            DownMode.BACK: UboKey.DOWN,
            DownMode.WEAPON: UboKey.WEAPON_NEXT,
            DownMode.MENU: UboKey.ESCAPE,
        }
        seen: dict[DownMode, UboKey] = {}
        for _ in range(len(DownMode)):
            mode = ctrl.down_mode
            ctrl.go_down()
            seen[mode] = rec.last_key
            ctrl.cycle_mode()
        assert seen == expected


class TestModeLifecycle:
    def test_mode_cycles_fire_use_back_weapon_menu(self, ctrl: DoomController) -> None:
        set_level(ctrl)
        assert ctrl.down_mode is DownMode.FIRE
        order = [
            DownMode.USE,
            DownMode.BACK,
            DownMode.WEAPON,
            DownMode.MENU,
            DownMode.FIRE,
        ]
        for expected in order:
            assert ctrl.cycle_mode() is True
            assert ctrl.down_mode is expected

    def test_mode_only_cycles_in_active_level(self, ctrl: DoomController) -> None:
        assert ctrl.cycle_mode() is False
        set_menu(ctrl)
        assert ctrl.cycle_mode() is False
        ctrl.update_game_state(
            alive=True,
            gamestate=GS_INTERMISSION,
            menuactive=False,
        )
        assert ctrl.cycle_mode() is False

        set_level(ctrl)
        assert ctrl.cycle_mode() is True
        assert ctrl.down_mode is DownMode.USE

    def test_mode_resets_to_fire_after_level_exit(self, ctrl: DoomController) -> None:
        set_level(ctrl)
        ctrl.cycle_mode()
        assert ctrl.down_mode is not DownMode.FIRE
        just_left = ctrl.update_game_state(
            alive=True,
            gamestate=GS_INTERMISSION,
            menuactive=False,
        )
        assert just_left is True
        assert ctrl.exit_level() is True
        assert ctrl.down_mode is DownMode.FIRE

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
