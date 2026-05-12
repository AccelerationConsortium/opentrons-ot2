# Plan: Single Self-Contained Executable for OT-2

## Goal

Replace the wheel-bundle-plus-venv deploy with a single `connector` binary.
No pip, no venv, no system packages required on the robot. The binary carries
every shared library it needs except glibc, which is the OS ABI boundary and
cannot be abstracted away.

**Truly unavoidable external dependencies (OS ABI):**

- `libc.so.6` / `libpthread.so.0` / `libm.so.6` — glibc 2.25 on OT-2; we
  build on Stretch (glibc 2.24) so forward-compatibility is guaranteed.

Everything else — including `libgpiod.so.2`, `libstdc++.so.6`, `libgcc_s.so.1`
— is bundled inside the binary.

---

## Tool: PyInstaller `--onefile`

`shiv`/`pex` cannot bundle C extensions — they still require Python on the
target and extract `.so` files to a temp dir without controlling `RPATH`.
Nuitka compiles Python to C but is significantly more complex and less tested
with gRPC. PyInstaller `--onefile` self-extracts to `/tmp` on startup,
sets `LD_LIBRARY_PATH` to the extraction directory so all bundled `.so`
files resolve, and executes. For a long-running systemd service the ~2s
extraction overhead on first start is negligible.

---

## Docker: New `pyinstaller-builder` Stage

Base: `FROM gpiod-builder` (inherits Stretch + Python 3.10 + OpenSSL 1.1.1 +
all compiled C extensions already in place).

### Step 1 — Install all wheels

Copy all output wheels from the existing build stages into the stage and
install them into the Stretch Python 3.10 environment:

```dockerfile
COPY --from=numpy-builder  /numpy-output/   /wheels/
COPY --from=grpc-builder   /grpc-output/    /wheels/
COPY --from=gpiod-builder  /gpiod-output/   /wheels/
COPY --from=builder        /output/         /wheels/
RUN /usr/local/bin/pip3 install --no-index --no-deps /wheels/*.whl
```

### Step 2 — Compile the PyInstaller bootloader for armv7l on Stretch

PyInstaller ships pre-built bootloaders for x86/x86_64/aarch64 but not
armv7l. The bootloader binary is injected into the output file and must be
compiled for the target glibc. Building on Stretch (glibc 2.24) guarantees
the result runs on the OT-2 (glibc 2.25).

```dockerfile
RUN /usr/local/bin/pip3 install pyinstaller-hooks-contrib && \
    wget -q https://github.com/pyinstaller/pyinstaller/archive/refs/tags/v5.13.2.tar.gz && \
    tar xzf v5.13.2.tar.gz && \
    cd pyinstaller-5.13.2/bootloader && \
    /usr/local/bin/python3 ./waf all && \
    cd ../.. && \
    /usr/local/bin/pip3 install --no-index pyinstaller-5.13.2/ && \
    rm -rf pyinstaller-5.13.2*
```

PyInstaller 5.x is used (not 6.x) because 6.x requires Python 3.8+ features
that conflict with the Stretch build environment's pkg-resources constraints.

### Step 3 — Write the entry point script

The installed `connector` bin script is a console_scripts shim. Extract its
body and write a clean `entry.py` that PyInstaller can use as its target:

```dockerfile
RUN python3 -c "
import importlib.metadata
ep = next(e for e in importlib.metadata.distribution('unitelabs-cdk').entry_points
          if e.name == 'connector')
mod, attr = ep.value.split(':')
with open('/build/entry.py', 'w') as f:
    f.write(f'from {mod} import {attr}\n{attr}()\n')
"
```

### Step 4 — Run PyInstaller

```dockerfile
RUN _PYTHON_HOST_PLATFORM=linux-armv7l \
    /usr/local/bin/pyinstaller \
        --onefile \
        --name connector \
        --collect-all opentrons \
        --collect-all opentrons_shared_data \
        --collect-all unitelabs \
        --hidden-import grpc._cython.cygrpc \
        --hidden-import grpc._channel \
        --add-binary '/usr/local/lib/libgpiod.so.2:.' \
        --distpath /exe-output/ \
        /build/entry.py
```

`--add-binary '/usr/local/lib/libgpiod.so.2:.'` — explicitly bundles the
libgpiod.so.2 we compiled from libgpiod-1.6.3 source. PyInstaller sets
`LD_LIBRARY_PATH` to the extraction directory at runtime so `gpiod.cpython-310.so`
resolves it from inside the bundle, not from the system.

`libstdc++.so.6` and `libgcc_s.so.1` — PyInstaller auto-collects these when
it runs `ldd` on `grpcio`'s `.so` files. No explicit flag needed; they will
appear in the bundle automatically.

### Step 5 — In-Docker smoke test

Run the binary inside the builder stage before CI uploads it. This catches
missing hidden imports and missing data files without deploying to the robot.
Since libgpiod.so.2 is bundled, the test covers the gpiod import path too:

```dockerfile
RUN /exe-output/connector --help && \
    /exe-output/connector -c \
        "import grpc; import gpiod; import opentrons; import numpy; print('OK')"
```

If any import fails, the Docker build fails and no artifact is uploaded.

### Final COPY

```dockerfile
COPY --from=pyinstaller-builder /exe-output/connector /output/connector
```

---

## CI Workflow Changes (`.github/workflows/build-ot2-arm-wheels.yml`)

1. Add the `pyinstaller-builder` target to the existing `docker buildx build`
   invocation (same multi-stage build, new `--target`).
2. Extract `/output/connector` alongside the existing wheels.
3. Upload a second artifact `ot2-connector-arm` containing:
   - `connector` (the binary)
   - `config/ot2_config.json`

Keep the existing `ot2-arm-wheels` artifact. It serves as a debugging tool
and as the fallback deploy path.

---

## Deploy Changes

### New `deploy_executable.sh`

```sh
#!/bin/sh
set -e
HOST="${1:?Usage: $0 <host> <connector-binary>}"
BINARY="${2:?Usage: $0 <host> <connector-binary>}"
echo "Copying connector to $HOST..."
scp -O "$BINARY" "root@$HOST:/var/sila2_ot2/connector"
scp -O config/ot2_config.json "root@$HOST:/var/sila2_ot2/config.json"
ssh "root@$HOST" "chmod +x /var/sila2_ot2/connector"
echo "Verifying..."
ssh "root@$HOST" "/var/sila2_ot2/connector --help"
echo "Done."
```

### Updated ExecStart in `scripts/install_connector_service.sh`

```sh
ExecStart=/var/sila2_ot2/connector start --app unitelabs.opentrons_ot2:create_app --config-path /var/sila2_ot2/config.json
```

No venv path, no `bin/` subdirectory. Everything else in the service file is
unchanged (GPIO service teardown, After/Wants ordering, Restart policy).

### What goes away on the robot

- `/var/sila2_ot2/bin/`, `/var/sila2_ot2/lib/` — no venv
- `scripts/install.sh` is not used in the executable deploy path
- `pip` is never invoked on the robot
- The `/etc/pip.conf --root /` workaround is irrelevant

---

## Verification Sequence

| Step | Command | What it confirms |
|------|---------|-----------------|
| 1. Docker build | `docker buildx build --target pyinstaller-builder` | PyInstaller packaging + all imports + libgpiod bundle |
| 2. Port listening | `ssh root@ot2... "ss -tlnp \| grep 50051"` | Service started, gRPC bound |
| 3. SiLA client connect | `grpcurl ot2cep20240218r04:50051 list` | gRPC handshake end-to-end |
| 4. Feature call | Issue a SiLA command (e.g. home axes) | opentrons + GPIO hardware path |

Step 1 runs in CI on every push. Steps 2–4 run manually after deploy.
The v0.0.1 tag (wheel-bundle deploy, confirmed working) is the baseline to
compare against.
