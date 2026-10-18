#!/bin/bash
if [ -f /etc/lgtvcontrol/disabled ]; then
    echo "LG TV control is deactivated — skipping on"
    exit 0
fi
python3 /etc/lgtvcontrol/lgtv.py on --auto
