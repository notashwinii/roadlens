#!/usr/bin/env bash
set -e

ruff check . --fix --unsafe-fixes
black .