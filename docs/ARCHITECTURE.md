# Architecture

## Overview
- Doom engine compiled as `libubodoom.so` (headless video + ALSA audio).
- ubo external service (`ubo_service/070-doom`) loads the shared library via `ctypes`,
  ticks the engine, then pushes frames to the ST7789 display.

## Video pipeline
- Doom renders 320×200 paletted.
- Service scales to 240×150, letterboxes to 240×240 (45px top/bottom), converts to RGB565,
  then blits to LCD with `bypass_pause=True`.

## Input pipeline
- Service observes `state.keypad.pressed_keys` via `store.autorun` and emits Doom key down/up events.

## Audio pipeline
- Doom outputs directly to ALSA (Option A). ubo output is muted while Doom runs.
