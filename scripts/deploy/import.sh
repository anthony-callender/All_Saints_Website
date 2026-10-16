#!/usr/bin/env bash
# Import the All Saints' bundle into a Lightsail "WordPress" instance
# (Debian 12 + Apache + MariaDB; WordPress in /var/www/html, config in /var/www/wp-config.php).
#
# Run ON THE SERVER as the `admin` user, from the folder containing this script:
#
#   bash import.sh https://your-site.duckdns.org
#
# Then enable HTTPS (see docs/deploy-lightsail.md, step 5).
# Safe to re-run: backs up the current database to ~/backups first.
set -euo pipefail

NEW_URL="${1:?Usage: bash import.sh https://your-domain}"
NEW_URL="${NEW_URL%/}"
OLD_URL="http://allsaints.ddev.site"
WPDIR="/var/www/html"
CONFIG="/var/www/wp-config.php"
HERE="$(cd "$(dirname "$0")" && pwd)"
WP="wp --path=$WPDIR"
[ -f "$CONFIG" ] || { echo "Expected $CONFIG (Lightsail WordPress blueprint)."; exit 1; }

echo "==> Backing up current database"
mkdir -p ~/backups
$WP db export ~/backups/pre-import-$(date +%Y%m%d%H%M).sql --quiet

echo "==> Copying plugin, theme and uploads"
for dir in plugins/asc-digital-ministry themes/twentytwentyfive; do
  rm -rf "$WPDIR/wp-content/$dir"
  cp -r "$HERE/wp-content/$dir" "$WPDIR/wp-content/$dir"
done
cp -r "$HERE/wp-content/uploads/." "$WPDIR/wp-content/uploads/"
sudo chown -R admin:www-data "$WPDIR/wp-content"
sudo find "$WPDIR/wp-content/uploads" "$WPDIR/wp-content/plugins/asc-digital-ministry" "$WPDIR/wp-content/themes/twentytwentyfive" -type d -exec chmod 2775 {} \;
sudo find "$WPDIR/wp-content/uploads" "$WPDIR/wp-content/plugins/asc-digital-ministry" "$WPDIR/wp-content/themes/twentytwentyfive" -type f -exec chmod 664 {} \;

echo "==> Importing database"
$WP db import "$HERE/db.sql" --quiet

echo "==> Rewriting URLs $OLD_URL -> $NEW_URL"
$WP search-replace "$OLD_URL" "$NEW_URL" --all-tables --skip-columns=guid --quiet
$WP search-replace "https://allsaints.ddev.site" "$NEW_URL" --all-tables --skip-columns=guid --quiet
$WP option update home "$NEW_URL" --quiet 2>/dev/null || true   # already set by search-replace
$WP option update siteurl "$NEW_URL" --quiet 2>/dev/null || true

echo "==> wp-config.php: fixed site URL (the blueprint hard-codes http://<host>)"
sudo chmod 640 "$CONFIG"
$WP config set WP_HOME "$NEW_URL" --type=constant --quiet
$WP config set WP_SITEURL "$NEW_URL" --type=constant --quiet
case "$NEW_URL" in https://*) $WP config set FORCE_SSL_ADMIN true --raw --type=constant --quiet ;; esac
sudo chmod 440 "$CONFIG"

echo "==> Apache: allow WordPress .htaccess (pretty URLs) + larger uploads (sermon MP3s)"
sudo tee /etc/apache2/conf-available/asc-wordpress.conf >/dev/null <<'CONF'
# All Saints': let WordPress manage rewrites for pretty permalinks.
<Directory /var/www/html>
    AllowOverride All
</Directory>
CONF
sudo a2enconf -q asc-wordpress
sudo tee /etc/php/8.2/apache2/conf.d/99-asc-uploads.ini >/dev/null <<'INI'
; All Saints': sermon MP3s are ~25 MB
upload_max_filesize = 64M
post_max_size = 64M
INI
sudo apache2ctl configtest
sudo systemctl reload apache2

echo "==> WordPress settings"
$WP rewrite structure '/%postname%/' --quiet
# WP-CLI can't detect mod_rewrite from the command line, so write the standard rules explicitly.
cat > "$WPDIR/.htaccess" <<'HTACCESS'
# BEGIN WordPress
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]
RewriteBase /
RewriteRule ^index\.php$ - [L]
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule . /index.php [L]
</IfModule>
# END WordPress
HTACCESS
chmod 664 "$WPDIR/.htaccess"
$WP rewrite flush --quiet
$WP theme activate twentytwentyfive --quiet
$WP plugin activate asc-digital-ministry --quiet

echo "==> Rotating credentials (local ones are no longer valid)"
ADMIN_PASS="$(openssl rand -base64 18 | tr -d '/+=')"
$WP user update admin --user_pass="$ADMIN_PASS" --skip-email --quiet
for uuid in $($WP user application-password list sermon-worker --field=uuid 2>/dev/null); do
  $WP user application-password delete sermon-worker "$uuid" --quiet
done
APP_PASS="$($WP user application-password create sermon-worker sermon-flywheel-production --porcelain)"

$WP transient delete --all --quiet
$WP cache flush --quiet || true
$WP asc kb reindex

cat <<EOF

==================================================================
 Imported. Site: $NEW_URL   Admin: $NEW_URL/wp-admin/
 Save these now (shown once; not stored anywhere else):
   WordPress admin user:      admin
   WordPress admin password:  $ADMIN_PASS
   WP_USERNAME=sermon-worker
   WP_APPLICATION_PASSWORD=$APP_PASS
==================================================================
EOF
