#!/usr/bin/env bash
# Bootstrap the local All Saints' WordPress site. Idempotent: safe to re-run.
#
# Run from the project root (PowerShell or bash):
#   ddev exec bash scripts/bootstrap.sh
#
# Creates (only if missing): WordPress core, admin user, the sermon-worker
# integration user + Application Password, and writes local-only credentials to
# tmp/local-credentials.env (gitignored). No production credentials are used.
set -euo pipefail

cd /var/www/html
WP="wp --path=wordpress"
SITE_URL="${DDEV_PRIMARY_URL:-http://allsaints.ddev.site}"
CREDS="tmp/local-credentials.env"
mkdir -p tmp

# Docker creates wordpress/wp-content as root when it sets up the plugin bind mount.
if [ -d wordpress/wp-content ] && [ ! -w wordpress/wp-content ]; then
  echo "wordpress/wp-content is not writable. Run once from the project root:" >&2
  echo "  ddev exec -u root chown 1000:1000 /var/www/html/wordpress/wp-content /var/www/html/wordpress/wp-content/plugins" >&2
  exit 1
fi

if [ ! -f wordpress/wp-includes/version.php ]; then
  echo "==> Downloading WordPress core"
  $WP core download --skip-content --force
fi
mkdir -p wordpress/wp-content/themes wordpress/wp-content/uploads

# Application Passwords over plain HTTP require a 'local' environment type.
$WP config set WP_ENVIRONMENT_TYPE local --type=constant --quiet || true

if ! $WP core is-installed 2>/dev/null; then
  echo "==> Installing WordPress"
  ADMIN_PASS="$(openssl rand -base64 18 | tr -d '/+=')"
  $WP core install --url="$SITE_URL" --title="All Saints' Church" \
    --admin_user=admin --admin_password="$ADMIN_PASS" \
    --admin_email=admin@allsaints.ddev.site --skip-email
  {
    echo "# Local DDEV credentials only. Never use in production. (gitignored)"
    echo "WP_ADMIN_USER=admin"
    echo "WP_ADMIN_PASSWORD=$ADMIN_PASS"
  } > "$CREDS"
fi

echo "==> Site settings"
$WP option update blogname "All Saints' Church" --quiet
$WP option update blogdescription "An Anglican church in Woodbridge, Virginia" --quiet
$WP option update timezone_string "America/New_York" --quiet
$WP option update date_format "F j, Y" --quiet
$WP rewrite structure '/%postname%/' --quiet
$WP rewrite flush --quiet

echo "==> Theme"
# Avada is the target theme. If an authorized Avada package has been installed
# (see README "Avada installation"), activate it; otherwise use the temporary
# core block theme so the site remains testable.
if $WP theme is-installed Avada 2>/dev/null; then
  $WP theme activate Avada
else
  $WP theme is-installed twentytwentyfive || $WP theme install twentytwentyfive
  $WP theme activate twentytwentyfive
  echo "    Avada installation pending authorized theme package/license; using twentytwentyfive."
fi

echo "==> Plugin"
$WP plugin activate asc-digital-ministry

echo "==> Integration user for the sermon worker"
if ! $WP user get sermon-worker --field=ID >/dev/null 2>&1; then
  $WP user create sermon-worker sermon-worker@allsaints.ddev.site --role=editor \
    --display_name="Sermon Worker" --user_pass="$(openssl rand -base64 24)" --quiet
fi
if ! grep -q '^WP_APPLICATION_PASSWORD=' "$CREDS" 2>/dev/null; then
  APP_PASS="$($WP user application-password create sermon-worker sermon-flywheel-local --porcelain)"
  {
    echo "WP_BASE_URL=$SITE_URL"
    echo "WP_USERNAME=sermon-worker"
    echo "WP_APPLICATION_PASSWORD=$APP_PASS"
  } >> "$CREDS"
fi

echo "==> Done. Site: $SITE_URL  (local credentials in $CREDS)"
