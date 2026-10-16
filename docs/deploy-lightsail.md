# Deploy to AWS Lightsail (~$7/month)

Live demo: **https://100-52-175-44.sslip.io** (deployed 3 Oct 2026).

Server: Lightsail **WordPress 7.1** blueprint ("Lightsail" packaging, not Bitnami) — Debian 12, Apache 2.4, MariaDB 10.11, PHP 8.2. WordPress in `/var/www/html`, config in `/var/www/wp-config.php`, SSH user `admin`, WP-CLI at `/usr/local/bin/wp`.

## 1. Create the instance (AWS console)
1. Lightsail → **Create instance** → region **Virginia (us-east-1)** → **Linux apps → WordPress** (not OpenClaw, which is pre-selected).
2. Plan **$7 / 1 GB** (the $5 / 512 MB plan is too tight for WordPress + MariaDB). Name `allsaints`.
3. **Networking → Firewall**: edit the SSH rule → **Update rule** with your IP or *Anywhere IPv4* (by default it only allows Lightsail browser SSH). Keep the Lightsail browser/Setup boxes ticked.
4. **Account → SSH keys**: download the us-east-1 default key → `C:\Users\<you>\.ssh\LightsailDefaultKey-us-east-1.pem` →
   `icacls <key> /inheritance:r /grant:r "$($env:USERNAME):R"`
5. Optional: attach a **static IP** (the address otherwise changes if the instance is stopped/started).

## 2. Domain
No registration needed for a demo: `https://<ip-with-dashes>.sslip.io` resolves to the server (e.g. `100-52-175-44.sslip.io`). For a real domain, point an A record at the IP and use that instead.

## 3. Package, upload, import (PowerShell, project root)
```powershell
$env:PATH = "$env:USERPROFILE\.local\ddev;$env:PATH"
ddev exec bash scripts/deploy/export.sh                     # → tmp\deploy\asc-deploy.tar.gz
$KEY = "$env:USERPROFILE\.ssh\LightsailDefaultKey-us-east-1.pem"; $IP = "100.52.175.44"
scp -i $KEY tmp\deploy\asc-deploy.tar.gz admin@${IP}:~/
ssh -i $KEY admin@$IP "rm -rf ~/asc; mkdir ~/asc; tar xzf ~/asc-deploy.tar.gz -C ~/asc; bash ~/asc/import.sh https://100-52-175-44.sslip.io"
```
`import.sh` backs up the DB to `~/backups/`, installs plugin/theme/uploads, imports the DB, rewrites URLs, pins `WP_HOME`/`WP_SITEURL` (the blueprint hard-codes `http://<host>`), enables `.htaccess` + writes WordPress rewrite rules (pretty URLs), raises PHP upload limits to 64 MB (sermon MP3s), rotates the admin password and the `sermon-worker` Application Password (printed once), and reindexes Church Knowledge.

## 4. HTTPS (first time only)
```bash
D=100-52-175-44.sslip.io
sudo sed -i "s|^\s*#ServerName www.example.com|\tServerName $D|" /etc/apache2/sites-available/000-default.conf && sudo systemctl reload apache2
sudo apt-get update && sudo apt-get install -y certbot python3-certbot-apache
sudo certbot --apache -d $D --agree-tos --register-unsafely-without-email --redirect
```
Renewal is automatic (`certbot.timer`).

## 5. Point the sermon worker at production
Worker `.env` (gitignored): `WP_BASE_URL=https://100-52-175-44.sslip.io`, `WP_USERNAME=sermon-worker`, `WP_APPLICATION_PASSWORD=<printed by import.sh>` → `python -m sermon_worker.cli check`.

## 6. Optional: OpenAI key on the server
```bash
sudo chmod 640 /var/www/wp-config.php
wp --path=/var/www/html config set OPENAI_API_KEY 'sk-…' --quiet
sudo chmod 440 /var/www/wp-config.php
wp --path=/var/www/html asc kb reindex --force
```

## Verified after deploy
All pages 200 at ~0.4 s TTFB; HTTP→HTTPS 301; chatbot grounded answer + sources; sermon MP3 served from the Media Library; worker auth + idempotent skip over HTTPS; chat widget browser check (phone + desktop).

## Updating / stopping
Re-run step 3 to redeploy (step 4 is one-time). To stop billing: delete the instance (and static IP, if created) in Lightsail.
