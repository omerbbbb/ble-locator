#!/bin/bash
# Run the BLE Indoor Positioning System
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "First run — setting up virtual environment…"
    make setup
fi

.venv/bin/python main.py "$@"
