# Deploy OT-2

Deploy updated Python code to the OT-2 robot.

**Usage:** `/deploy-ot2 [host]`

The host is the robot's Tailscale IP or hostname. Check the user's memory or ask if unknown.

---

Run the canonical script — do not run robot operations outside it:

```sh
sh scripts/setup_ot2.sh $HOST
```

This checks the robot's architecture/Python version, downloads the matching self-contained
connector binary from the rolling `ot2-latest` GitHub Release (published by the latest
successful "Build OT-2 ARM Wheels" run on `main`), deploys it, installs the
`sila2-connector` systemd service, and verifies both it and Tailscale are up. No venv, no
Python required on the robot. See `scripts/README.md` for what each step calls internally.

If the latest commit on `main` has no completed build yet, wait for it first:

```sh
gh run list --limit 5
gh run watch <run-id> --exit-status
```

If the script reports the service failed, show the full error and stop — do not attempt
workarounds outside the scripts.
