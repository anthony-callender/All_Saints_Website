#!/usr/bin/env bash
# Seed migrated content. Idempotent.  Usage: ddev exec bash scripts/seed.sh
set -euo pipefail
cd /var/www/html
wp --path=wordpress eval-file scripts/seed.php
