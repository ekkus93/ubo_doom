# Troubleshooting

## Doom does not start / missing IWAD
- Ensure `UBO_DOOM_IWAD` points to a valid `.wad` file on device.
- Ensure `UBO_DOOM_LIB` points to a valid `libubodoom.so` path.

## No audio
- Ensure ALSA device is available and not held by another process.
- Set `UBO_DOOM_ALSA_DEVICE` to a working playback device in your env/systemd override.
- Example values: `default`, `sysdefault:CARD=wm8960soundcard`, `plughw:CARD=wm8960soundcard,DEV=0`.

## Blank screen
- Verify `UBO_DOOM_LIB` points to `libubodoom.so`.
- Check service logs for ctypes load errors.

## Wrong config file / inconsistent defaults
- Set `UBO_DOOM_CWD` to a stable working directory (typically `$HOME/doom`).
- Set `UBO_DOOM_CONFIG` (for example `$HOME/doom/doomrc.cfg`) to avoid picking up stale `$HOME/.doomrc` behavior.

## Performance
- Start with `UBO_DOOM_FPS=20` and increase.
- Consider moving scaling/color conversion into C if needed.

## CI/CD status
- Check workflow runs in GitHub Actions: `.github/workflows/ci-release.yml`.
- `master`/PR runs perform CI checks; tag runs also publish release artifacts.
