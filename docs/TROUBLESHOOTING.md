# Troubleshooting

## Doom does not start / missing IWAD
- Ensure `UBO_DOOM_IWAD` points to a valid `.wad` file on device.

## No audio
- Ensure ALSA device is available and not held by another process.
- Try changing device string in the Doom ALSA backend (e.g., `default` -> `plughw:0,0`).

## Blank screen
- Verify `UBO_DOOM_LIB` points to `libubodoom.so`.
- Check service logs for ctypes load errors.

## Performance
- Start with `UBO_DOOM_FPS=20` and increase.
- Consider moving scaling/color conversion into C if needed.
