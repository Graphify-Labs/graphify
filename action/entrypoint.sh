#!/bin/sh
set -e

# GitHub Actions maps the repository to /github/workspace
cd "$GITHUB_WORKSPACE"

# Evaluate the command with options correctly splitting spaces
eval "python -m graphify $1 $2"
