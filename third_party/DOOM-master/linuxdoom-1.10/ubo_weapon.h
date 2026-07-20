// Ubo Doom: weapon-cycle selection logic.
//
// Split out of doom_api.c's ubo_weapon_next() so the (off-by-one prone) cyclic
// scan can be unit-tested without the engine. Pulls in NO engine state -- it
// works on plain ints, so the test does not link players[]/consoleplayer or run
// doom_init().
#ifndef UBO_WEAPON_H
#define UBO_WEAPON_H

// Given the currently selected weapon index `cur`, return the index of the next
// owned weapon, scanning cyclically over `n` slots (owned[i] != 0 == owned).
// Skips the current slot unless it is the only weapon owned; returns `cur`
// unchanged when nothing (not even `cur`) is owned. Pure function.
int ubo_next_owned_weapon(int cur, int n, const int* owned);

#endif // UBO_WEAPON_H
