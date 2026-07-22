# OT-2 Scripts

Everything here does one of three things: **set up Tailscale**, **install the connector**,
or **verify the robot is up**. Every script is meant to be run from the repo root
(`sh scripts/<name>.sh <host>`), never inlined by hand on the robot — see AGENTS.md's
"Hardware Driver Rules" / canonical-scripts convention.

## The 3-step flow

### 1. Set up Tailscale — `setup_tailscale.sh` (one-time, per physical robot)

```sh
TS_AUTHKEY=tskey-auth-... sh scripts/setup_tailscale.sh <host>
```

Only needed once, when a robot has never had Tailscale on it (or a reflash wiped `/data`).
Uploads the Tailscale binary, writes the auth key, then calls `install_tailscale_service.sh`.
Skip this step for a robot that's already reachable over Tailscale.

### 2. Install the connector — `setup_ot2.sh` (every deploy)

```sh
sh scripts/setup_ot2.sh <host>
```

This is the script you run to ship the latest `main` to a robot. It:

1. Checks the robot's architecture and Python version over SSH first, and refuses to
   continue if there's no matching wheel build — so an incompatible wheel set is never
   pushed.
2. Downloads the matching wheels from the latest successful "Build OT-2 ARM Wheels" run
   on `main`.
3. Calls `deploy.sh` (installs the wheels + config into `/var/sila2_ot2`) and
   `install_connector_service.sh` (writes/enables/restarts the `sila2-connector`
   systemd service).
4. Calls `verify_ot2.sh`.

### 3. Verify everything is up — `verify_ot2.sh`

```sh
sh scripts/verify_ot2.sh <host>
```

Checks both services: `start-tailscale` (+ `tailscale status`) and `sila2-connector`
(+ its last 20 log lines). Run standalone any time you just want a health check.

## Everything else in this directory

These are internals called by the three scripts above — you shouldn't normally need to
run them directly:

| Script | Called by | Purpose |
|--------|-----------|---------|
| `install_tailscale_service.sh` | `setup_tailscale.sh` | Write/enable/restart the `start-tailscale` systemd unit |
| `start_tailscale.sh` | the `start-tailscale` systemd unit | Actually starts `tailscaled` and runs `tailscale up` |
| `install_connector_service.sh` | `setup_ot2.sh` | Write/enable/restart the `sila2-connector` systemd unit; disables the stock Opentrons services that would otherwise hold the GPIO lines |
| `install.sh` | `deploy.sh` (via `deploy.sh` → robot) | Runs *on* the robot: `pip install`s the wheels into the venv |
| `start_connector.sh` | manual, on the robot | `ssh root@<host> "sh /data/start_connector.sh [start\|stop\|restart\|status]"` — manual service management, e.g. after a crash |

## Not part of the 3-step flow (dev shortcuts)

| Script | Purpose |
|--------|---------|
| `deploy_python_changes.sh` | Sync raw `src/` changes straight into the venv, skipping a full wheel rebuild. For fast local iteration only — the real deploy path is `setup_ot2.sh`. |
| `switch_mode.sh` | Toggle the robot between the stock Opentrons app mode and the SiLA2 connector mode; persists across reboot. |

`../deploy.sh` (repo root, not in `scripts/`) is the lower-level wheel installer that
`setup_ot2.sh` calls into. `../deploy_executable.sh` is a separate, alternative
distribution path — a self-contained PyInstaller binary that needs no pip/venv/Python on
the robot at all — not part of the wheel-based flow above; see its own header for details.
