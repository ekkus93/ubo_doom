# Controls

On Ubo v2, Doom renders through the `frame_stream` view with five usable inputs:
**UP/DOWN** and the three footer buttons **L1/L2/L3** (labelled `MODE`, `◄`, `►`).

**BACK and HOME are owned by Ubo, not Doom.** BACK closes the Doom view and HOME
returns to the Ubo home screen; the service deliberately does not handle them.

The design keeps **turning always live** so you can turn side-to-side and shoot at
the same time. Forward is always UP. The **DOWN button is multiplexed** through
several actions, and **MODE (L1) cycles which one** — the current mode is shown in
the **title bar** (e.g. `Doom · FIRE`).

## Gameplay

| Input | Action |
|-------|--------|
| UP | move forward |
| L2 (◄) | turn left |
| L3 (►) | turn right |
| L1 (MODE) | cycle what DOWN does: **FIRE → USE → BACK → WEAPON** (wraps) |
| DOWN | performs the current mode's action (see below) |

DOWN by mode (title bar shows which is active):

| Mode | DOWN does |
|------|-----------|
| FIRE (default) | fire |
| USE | use — open doors / flip switches |
| BACK | move backward |
| WEAPON | switch to your next owned weapon |

So to fight: leave DOWN in FIRE, and turn (L2/L3) + advance (UP) + shoot (DOWN)
together. Tap MODE to flip DOWN to USE for a door, to WEAPON to change guns, or to
BACK to reposition. The mode resets to FIRE whenever you leave a level.

**Trade-off:** while DOWN is set to USE / FIRE / WEAPON you cannot move backward —
turn 180° and walk forward instead. This is the cost of never tying up the turn
keys, which keeps turn-and-shoot possible on only five buttons.

## Menus (title screen, Doom menu, intermission)

Outside active gameplay the buttons drive the menus:

| Input | Action |
|-------|--------|
| UP / DOWN | move the menu cursor |
| L3 (►) | title/demo: open the Doom menu (ESC); menu: select; intermission/finale: continue |

To start a game from the title screen: press **L3** to open the menu, **UP/DOWN**
to choose, **L3** to select.
