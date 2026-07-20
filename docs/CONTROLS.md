# Controls

On Ubo v2, Doom renders through the `frame_stream` view with five usable inputs:
**UP/DOWN** and the three footer buttons **L1/L2/L3** (labelled `MODE`, `◄`, `►`).

**BACK and HOME are owned by Ubo, not Doom.** BACK closes the Doom view and HOME
returns to the Ubo home screen; the service deliberately does not handle them.

The design keeps **turning always live** so you can turn side-to-side and shoot at
the same time. Forward is always UP. The **DOWN button is multiplexed** through
several actions, and **MODE (L1) cycles which one** — the current mode is shown as
a small color-coded tag in the **top-left of the Doom image** (e.g. `FIRE`).
(It is drawn into the frame rather than the view title, which would force a
full-screen refresh on every change.)

## Gameplay

| Input | Action |
|-------|--------|
| UP | move forward |
| L2 (◄) | turn left |
| L3 (►) | turn right |
| L1 (MODE) | cycle what DOWN does: **FIRE → USE → BACK → WEAPON → MENU** (wraps) |
| DOWN | performs the current mode's action (see below) |

DOWN by mode (the HUD tag shows which is active):

| Mode | DOWN does |
|------|-----------|
| FIRE (default) | fire |
| USE | use — open doors / flip switches |
| BACK | move backward |
| WEAPON | switch to your next owned weapon |
| MENU | open Doom's own (ESC) menu — New Game, Options, Quit |

So to fight: leave DOWN in FIRE, and turn (L2/L3) + advance (UP) + shoot (DOWN)
together. Tap MODE to flip DOWN to USE for a door, to WEAPON to change guns, to
BACK to reposition, or to MENU to open Doom's menu. The mode resets to FIRE
whenever you leave a level.

**Trade-off:** while DOWN is set to USE / FIRE / WEAPON / MENU you cannot move
backward — turn 180° and walk forward instead. This is the cost of never tying up
the turn keys, which keeps turn-and-shoot possible on only five buttons.

**Reaching Doom's own menu:** the Ubo **BACK** button leaves the Doom app (Ubo v2
owns BACK/HOME for navigation), so it can't open Doom's in-game menu. Cycle L1 to
**MENU** and press DOWN to open it; once open, UP/DOWN move the cursor, L3 selects,
and **L1 backs out / closes the menu** — so you can peek and resume without leaving
the app. (L1 is context-sensitive: it cycles the DOWN-mode during play and acts as
"back" whenever a menu is open, including the title-screen menu.)

## Respawning after death

When you die, the camera sinks to the floor. After roughly a second, press
**DOWN** (FIRE, the default mode) or **USE** to respawn — this reloads the current
level from the start. Since FIRE is the default DOWN action, a plain DOWN press is
enough; you don't have to cycle to USE. The ~1 s delay is intentional: it keeps
the death view from being skipped if the fire button is still held when you die.

Vanilla Doom respawns on USE only; this port also accepts FIRE so the natural
action button works when you're dead.

## Menus (title screen, Doom menu, intermission)

Outside active gameplay the buttons drive the menus:

| Input | Action |
|-------|--------|
| UP / DOWN | move the menu cursor |
| L3 (►) | title/demo: open the Doom menu (ESC); menu: select; intermission/finale: continue |

To start a game from the title screen: press **L3** to open the menu, **UP/DOWN**
to choose, **L3** to select.
