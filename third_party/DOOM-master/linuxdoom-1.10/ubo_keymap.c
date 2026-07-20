// Ubo Doom: stable-key-enum -> linuxdoom-keycode mapping. See ubo_keymap.h.
#include "ubo_keymap.h"
#include "doomkeys.h"

int ubo_map_key(ubo_key_t key)
{
    switch (key)
    {
        case UBO_KEY_UP: return KEY_UPARROW;
        case UBO_KEY_DOWN: return KEY_DOWNARROW;
        case UBO_KEY_LEFT: return KEY_LEFTARROW;
        case UBO_KEY_RIGHT: return KEY_RIGHTARROW;
        case UBO_KEY_FIRE: return KEY_RCTRL;   /* NOT KEY_ENTER: stolen by HU_MSGREFRESH */
        case UBO_KEY_USE: return ' ';          /* Space -> BT_USE (doors, switches, respawn) */
        case UBO_KEY_ESCAPE: return KEY_ESCAPE;
        case UBO_KEY_MENU_SELECT: return KEY_ENTER;   /* menus only, not in-game */
        default: return 0;
    }
}
