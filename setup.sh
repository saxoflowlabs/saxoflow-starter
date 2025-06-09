#!/bin/bash
set -e

# -------------------------------------
# SaxoFlow Setup Bootstrap (setup.sh)
# -------------------------------------
# Purpose: User runs ONLY this once after cloning
# It makes CLI scripts executable and runs launch_saxoflow

# Mark CLI scripts as executable
chmod +x bin/saxoflow
chmod +x bin/launch_saxoflow

# Run main launch script
./bin/launch_saxoflow