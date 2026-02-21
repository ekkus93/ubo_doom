# ubo_doom_port

A non-fork “Doom on ubo_app” port implemented as an **external ubo service** (no changes to the `ubo_app` repo).
Video is rendered **240×240 letterboxed** to preserve Doom’s aspect ratio; audio outputs directly to **ALSA** (Option A).

## What this repo contains

- `third_party/DOOM-master/linuxdoom-1.10/`  
  The classic `linuxdoom-1.10` source, pre-modified to build an embeddable shared library (`libubodoom.so`) with:
  - headless video backend (palette capture + framebuffer export)
  - ALSA audio backend (replaces OSS `/dev/dsp`)
  - minimal C API for embedding: init/tick/framebuffer/input
  - 64-bit (aarch64) portability fixes

- `ubo_service/070-doom/`  
  The ubo external service that:
  - pauses normal UI LCD rendering
  - drives the LCD by pushing RGB565 frames to the ST7789 (bypass pause)
  - maps ubo keypad state to Doom key events
  - restores ubo audio/UI state when exiting

- `native/scripts/`  
  Build + install helpers (safe defaults; tweak for your environment).

## Requirements

### Build machine
- `gcc`, `make`
- ALSA dev headers: `libasound2-dev`

### Target device (ubo)
- `ubo_app` installed and runnable
- External services enabled via `UBO_SERVICES_PATH`
- A legally obtained IWAD (e.g. `doom.wad`, `doom2.wad`, `doom1.wad`)

## Quick start (recommended workflow)

### 1) Build the shared library
From repo root:

```bash
./native/scripts/build_libubodoom.sh
```

Outputs:
- `native/out/libubodoom.so`

### 2) Copy artifacts to the ubo device
On the ubo device, create:

```bash
mkdir -p ~/doom
```

Copy:
- `native/out/libubodoom.so` → `~/doom/libubodoom.so`
- your legally obtained IWAD → `~/doom/doom2.wad` (or similar)

This repo does **not** include an IWAD.

You can use:

```bash
./native/scripts/install_to_device.sh <user@host>
```

### 3) Deploy the ubo service
Copy the service directory to the device:

```bash
rsync -av ubo_service/070-doom/ <user@host>:~/ubo_services/070-doom/
```

### 4) Configure environment variables on the device
Example environment:

- `UBO_SERVICES_PATH=$HOME/ubo_services`
- `UBO_DOOM_LIB=$HOME/doom/libubodoom.so`
- `UBO_DOOM_IWAD=$HOME/doom/doom2.wad`
- `UBO_DOOM_FPS=30`

See:
- `ubo_service/070-doom/config/doom.env.example`
- `system/env/ubo_app.env.example`

### 5) Run ubo_app
However you normally start it (systemd or manual). The Doom launcher will appear once the service is enabled.

## Controls (default mapping)

See `docs/CONTROLS.md`.

## Notes / legal

- This repo does **not** distribute IWADs.
- You are responsible for ensuring you have the legal right to use the IWAD you provide.

## Troubleshooting

See `docs/TROUBLESHOOTING.md`.
