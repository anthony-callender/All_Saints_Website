#!/usr/bin/env bash
# Push the asc-digital-ministry plugin to the live server: lint every PHP file on the
# server first, keep a timestamped backup of the live copy, then swap it in.
#
#   bash scripts/deploy/push-plugin.sh            (needs SSH access; see docs/deploy-lightsail.md)
#   ASC_SSH="admin@1.2.3.4" ASC_SSH_KEY=~/.ssh/key.pem bash scripts/deploy/push-plugin.sh
#
# Roll back: sudo rsync -a --delete ~/plugin-backup-<stamp>/ /var/www/html/wp-content/plugins/asc-digital-ministry/
set -euo pipefail
cd "$(dirname "$0")/../.."
host="${ASC_SSH:-admin@100.52.175.44}"
key="${ASC_SSH_KEY:-$HOME/.ssh/LightsailDefaultKey-us-east-1.pem}"
mkdir -p tmp/deploy
tar -czf tmp/deploy/plugin.tgz -C wp-content/plugins asc-digital-ministry
scp -q -i "$key" tmp/deploy/plugin.tgz "$host:/tmp/plugin.tgz"
ssh -i "$key" "$host" 'set -e
rm -rf /tmp/stage && mkdir /tmp/stage && tar -xzf /tmp/plugin.tgz -C /tmp/stage
for f in $(find /tmp/stage -name "*.php"); do php -l "$f" >/dev/null || { echo "PHP lint failed: $f"; exit 1; }; done
P=/var/www/html/wp-content/plugins/asc-digital-ministry
B=~/plugin-backup-$(date +%Y%m%d-%H%M%S); cp -a "$P" "$B"
sudo rsync -a --delete /tmp/stage/asc-digital-ministry/ "$P/"
sudo chown -R admin:www-data "$P"
sudo find "$P" -type d -exec chmod 2775 {} +
sudo find "$P" -type f -exec chmod 664 {} +
ls -dt ~/plugin-backup-* | tail -n +6 | xargs -r rm -rf   # keep the 5 newest backups
echo "deployed (backup: $B)"'
