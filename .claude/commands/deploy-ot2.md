# Deploy OT-2

Deploy updated Python code to the OT-2 robot.

**Usage:** `/deploy-ot2 [host]`

The host is the robot's Tailscale IP or hostname. Check the user's memory or ask if unknown.

---

Follow these steps in order. Do not skip steps or run robot operations outside the canonical scripts.

## Step 1 — wait for ARM wheel build

Check if the latest commit on `main` has a completed "Build OT-2 ARM Wheels" run:

```sh
gh run list --limit 5
```

If a build is `in_progress`, watch it:

```sh
gh run watch <run-id> --exit-status
```

If the latest commit has no wheel build (e.g. docs-only change), find the most recent successful one:

```sh
gh run list --workflow build-ot2-arm-wheels.yml --status success --limit 1
```

## Step 2 — download wheels

Download the py312 artifact from the completed build:

```sh
rm -rf dist_arm
gh run download <run-id> --name ot2-arm-wheels-py312 --dir dist_arm
ls dist_arm/unitelabs_opentrons_ot2*.whl
```

Confirm the wheel version matches the current `pyproject.toml` version before continuing.

## Step 3 — deploy

```sh
sh deploy.sh $HOST dist_arm
```

This installs all wheels into `/var/sila2_ot2`, copies `config/ot2_config.json`, and precompiles `.pyc` bytecode into `/var/cache/sila2-pycache`.

## Step 4 — install and restart service

```sh
sh scripts/install_connector_service.sh $HOST
```

This writes the systemd unit (with `PYTHONPYCACHEPREFIX` env var), enables the service, and restarts it.

## Step 5 — verify

Check the service started cleanly:

```sh
ssh root@$HOST "journalctl -u sila2-connector -n 20 --no-pager"
```

Confirm you see:

- `SiLA server listening on 0.0.0.0:50051`
- `Server bound to '0.0.0.0:50051'`
- No `ModuleNotFoundError` or `Failed` lines

If the service failed, show the full error and stop — do not attempt workarounds outside the scripts.
