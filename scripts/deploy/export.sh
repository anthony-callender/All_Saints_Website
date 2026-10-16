#!/usr/bin/env bash
# Package the local site for deployment: database + plugin + theme + uploads + import script.
#
#   ddev exec bash scripts/deploy/export.sh
#
# Output: tmp/deploy/asc-deploy.tar.gz  (gitignored; contains the DB, treat as private)
set -euo pipefail
cd /var/www/html
STAGE=tmp/deploy/stage
rm -rf "$STAGE" && mkdir -p "$STAGE"

wp --path=wordpress transient delete --all --quiet
wp --path=wordpress db export "$STAGE/db.sql" --quiet
cp scripts/deploy/import.sh "$STAGE/import.sh"
cp -r wordpress/wp-content "$STAGE/wp-content-full"
mkdir -p "$STAGE/wp-content/plugins" "$STAGE/wp-content/themes"
cp -r "$STAGE/wp-content-full/plugins/asc-digital-ministry" "$STAGE/wp-content/plugins/"
cp -r "$STAGE/wp-content-full/themes/twentytwentyfive" "$STAGE/wp-content/themes/"
cp -r "$STAGE/wp-content-full/uploads" "$STAGE/wp-content/"
rm -rf "$STAGE/wp-content-full"

tar czf tmp/deploy/asc-deploy.tar.gz -C "$STAGE" .
rm -rf "$STAGE"
echo "==> tmp/deploy/asc-deploy.tar.gz ($(du -h tmp/deploy/asc-deploy.tar.gz | cut -f1))"
