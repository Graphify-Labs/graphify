#!/usr/bin/env zsh
set -euo pipefail

greet() {
    print "Hello, $1"
}

deploy() {
    local env_name="${1:-production}"
    greet "$env_name"
    print "Deploying to $env_name"
}

deploy staging
