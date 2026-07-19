---
name: deploy-device
description: Build libubodoom.so and install it plus the Python service onto an Ubo v2 device over SSH. User-triggered only; requires a target user@host.
disable-model-invocation: true
---

Deploy Doom to an Ubo v2 device. Target passed as `$ARGUMENTS` (e.g. `pi@ubo.local`).

1. If `$ARGUMENTS` is empty, ask the user for the target `user@host`.
2. Build the native lib first: `./native/scripts/build_libubodoom.sh` (see the build-doom skill; fix any GNU89 errors before deploying).
3. Install to the device: `native/scripts/install_to_device.sh $ARGUMENTS` — this scp's the prebuilt `.so` and rsyncs the service directory.
4. Restart the service on the device so changes take effect: `ssh $ARGUMENTS 'systemctl --user restart ubo-app'`.
5. Confirm with the user before restarting if they're actively using the device. Report success and remind them logs are at `journalctl --user -u ubo-app` on the device.

Note: the Python service is symlinked on-device so Python-only edits may already be live; a native `.so` change always requires this deploy.
