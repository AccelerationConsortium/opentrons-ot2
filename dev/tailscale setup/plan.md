# Tailscale Setup Plan

Reproduce the existing OT-2 tailscale installation on a new machine via SSH.

## Existing setup (reference)

| Item | Value |
|------|-------|
| Binary | `tailscale_1.82.0_arm` |
| Install path | `/data/tailscale_1.82.0_arm/` |
| Start script | `/data/start_tailscale.sh` |
| Auth key | `/data/tskey.txt` |
| Daemon flags | `--tun=userspace-networking` |
| Persistence | systemd one-shot `start-tailscale.service` |

## Script steps

1. `mount -o remount,rw /` — unlock read-only root filesystem
2. `scp` tailscale tarball → `/data/`, extract in place
3. Write auth key to `/data/tskey.txt` (chmod 600)
4. `scp` `scripts/start_tailscale.sh` → `/data/start_tailscale.sh`
5. Write and enable `/etc/systemd/system/start-tailscale.service`
6. `systemctl start start-tailscale` and verify with `tailscale status`

## Inputs

| Arg | Description |
|-----|-------------|
| `<host>` | IP of target machine (SSH as root) |
| `TS_AUTHKEY` env var | Tailscale auth key — env var keeps it out of shell history |

## Files needed locally

- `tailscale_1.82.0_arm.tgz` — ARM binary tarball (fetch from pkgs.tailscale.com if absent)
- `scripts/start_tailscale.sh` — already in this repo
