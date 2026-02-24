# Troubleshooting

## Doom does not start / missing IWAD
- Ensure `UBO_DOOM_IWAD` points to a valid `.wad` file on device.

## No audio
- Ensure ALSA device is available and not held by another process.
- Set `UBO_DOOM_ALSA_DEVICE` to a working playback device in your env/systemd override.
- Example values: `default`, `sysdefault:CARD=wm8960soundcard`, `plughw:CARD=wm8960soundcard,DEV=0`.

## Blank screen
- Verify `UBO_DOOM_LIB` points to `libubodoom.so`.
- Check service logs for ctypes load errors.

## Performance
- Start with `UBO_DOOM_FPS=20` and increase.
- Consider moving scaling/color conversion into C if needed.
