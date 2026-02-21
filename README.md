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

- `gcc`, `make`
- ALSA dev headers: `libasound2-dev`
- `ubo_app` installed and runnable
- External services enabled via `UBO_SERVICES_PATH`
- A legally obtained IWAD (e.g. `doom.wad`, `doom2.wad`, `doom1.wad`)

## Quick start

All steps are run on the ubo device.

### 1) Clone the repo

```bash
git clone https://github.com/ekkus93/ubo_doom.git ~/work/ubo_doom
cd ~/work/ubo_doom
```

### 2) Install build dependencies

```bash
sudo apt install gcc make libasound2-dev
```

### 3) Build the shared library

```bash
./native/scripts/build_libubodoom.sh
```

Outputs `native/out/libubodoom.so`.

### 4) Install the library and IWAD

```bash
mkdir -p ~/doom
cp native/out/libubodoom.so ~/doom/
cp /path/to/your/doom2.wad ~/doom/   # or doom.wad, doom1.wad, etc.
```

This repo does **not** include an IWAD. You are responsible for providing one legally.

### 5) Deploy the ubo service

```bash
mkdir -p ~/ubo_services
cp -r ubo_service/070-doom ~/ubo_services/
```

### 6) Configure environment variables

Add to your ubo_app environment (e.g. `~/.config/ubo_app/ubo_app.env` or wherever `UBO_SERVICES_PATH` is set):

```bash
UBO_SERVICES_PATH=$HOME/ubo_services
UBO_DOOM_LIB=$HOME/doom/libubodoom.so
UBO_DOOM_IWAD=$HOME/doom/doom2.wad
UBO_DOOM_FPS=30
```

See `ubo_service/070-doom/config/doom.env.example` and `system/env/ubo_app.env.example` for reference.

### 7) Run ubo_app

However you normally start it (systemd or manual). The Doom launcher will appear once the service is enabled.

## Controls (default mapping)

See `docs/CONTROLS.md`.

## Troubleshooting

See `docs/TROUBLESHOOTING.md`.
