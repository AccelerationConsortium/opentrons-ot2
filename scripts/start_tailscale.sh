#!/bin/sh

if ! ps | grep '[t]ailscaled' > /dev/null; then
    echo "Starting tailscaled..." >> /tmp/tailscale-watch.log
    nohup /data/tailscale_1.82.0_arm/tailscaled --tun=userspace-networking > /tmp/tailscaled.log 2>&1 &
    sleep 5
    /data/tailscale_1.82.0_arm/tailscale up --ssh --authkey $(cat /data/tskey.txt) >> /tmp/tailscale-up.log 2>&1
else
    echo "tailscaled already running" >> /tmp/tailscale-watch.log
fi
