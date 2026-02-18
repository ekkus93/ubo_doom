# ubo_app setup

1) Ensure external services are enabled:
- Set `UBO_SERVICES_PATH=$HOME/ubo_services`

2) Deploy the Doom service:
- Copy `ubo_service/070-doom` to `~/ubo_services/070-doom` on the device.

3) Set Doom env vars:
- `UBO_DOOM_LIB`, `UBO_DOOM_IWAD`, `UBO_DOOM_FPS`

See `system/env/ubo_app.env.example` and `ubo_service/070-doom/config/doom.env.example`.
