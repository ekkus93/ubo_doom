# Controls

On Ubo v2, Doom renders through the `frame_stream` view. Input comes from the
**UP/DOWN** scroll and the **three footer buttons** — labelled on screen as
**MODE**, **LEFT/USE**, and **RIGHT/FIRE** (L1/L2/L3).

**BACK and HOME are owned by Ubo, not Doom.** BACK closes the Doom view and HOME
returns to the Ubo home screen; the service deliberately does not handle them, so
they can't be used for in-game actions. There are no dedicated LEFT/RIGHT or FIRE
buttons — turning is on the footer, and firing lives in ALT mode.

## Normal mode (default)

| Input | Action |
|-------|--------|
| UP | move forward |
| DOWN | move backward |
| MODE (L1) | toggle ALT mode — only while actively in a level |
| LEFT/USE (L2) | turn left (◄) |
| RIGHT/FIRE (L3) | context-sensitive: in a level → turn right (►); menu open → confirm/select; intermission/finale → continue; title/demo → open the Doom menu (ESC) |

## ALT mode (press MODE to activate)

| Input | Action |
|-------|--------|
| UP | move forward |
| DOWN | move backward |
| MODE (L1) | toggle back to normal mode |
| LEFT/USE (L2) | use (open doors / switches) |
| RIGHT/FIRE (L3) | fire |

## Starting a game

From the title/attract screen, press **RIGHT/FIRE (L3)** to open the Doom menu,
use **UP/DOWN** to move the cursor, and press **RIGHT/FIRE (L3)** again to select.
The attract-loop demo runs at the same gamestate as live play, so the service
uses the engine's `usergame` flag to keep L3 opening the menu during demos (rather
than turning) — without it, you can't reach the menu to start a game.

## Notes

- ALT mode can only be toggled while actively in a real level (not during a demo).
- ALT mode is automatically cleared when leaving a level (menu / intermission /
  finale / demo).
- RIGHT/FIRE only fires in ALT mode; in normal mode it turns right. Press MODE
  first to fire.
