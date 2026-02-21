# Building libubodoom.so

Assumes Doom source under:
- `third_party/DOOM-master/linuxdoom-1.10`

## Build natively on the device (recommended)

This syncs the sources to the Pi, compiles there, and installs everything in
one step — no local compiler or cross-toolchain needed.

**Prerequisites on the device (once):**
```bash
sudo apt install build-essential libasound2-dev
```

**Run:**
```bash
./native/scripts/build_on_device.sh <user@host> [remote_base]
# e.g.
./native/scripts/build_on_device.sh debian@ubo-rd
```

This will:
1. Rsync `third_party/DOOM-master/linuxdoom-1.10` to `~/doom-build/` on the device.
2. Run `make libubodoom.so` natively on the device.
3. Copy the resulting `.so` to `<remote_base>/doom/libubodoom.so`.
4. Rsync `ubo_service/070-doom` to `<remote_base>/ubo_services/070-doom`.

## Build locally (alternative)

If you have a Linux machine with a compatible toolchain:

```bash
sudo apt install build-essential libasound2-dev
./native/scripts/build_libubodoom.sh
```

Output: `native/out/libubodoom.so`

Then deploy with:
```bash
./native/scripts/install_to_device.sh <user@host>
```

If you move the third-party source, edit `native/scripts/build_libubodoom.sh`.
