#!/usr/bin/env bash
# One-time setup of the team dashboard on the EC2 box (todo/09). Safe to run again.
#   sudo deploy/dash_setup.sh 13-210-120-238.sslip.io
# Before: attach the Elastic IP (the hostname is the IP with dashes), and open ports 80 and 443 in the security
# group. It asks you to type the dashboard password (user "swan"); the password is never echoed or stored in git.
set -euo pipefail
cd "$(dirname "$0")"
HOST=${1:?usage: sudo deploy/dash_setup.sh <ip-with-dashes>.sslip.io}
[[ $HOST =~ ^[a-z0-9.-]+$ ]] || { echo "bad hostname: $HOST"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

dnf install -y -q nginx httpd-tools dnf-automatic
install -d -o ec2-user -g ec2-user -m 755 /var/www/swan
install -d -m 755 /var/www/letsencrypt

if [ ! -s /etc/nginx/swan.htpasswd ]; then
  echo "Choose the dashboard password (20+ random characters; share it with the team privately):"
  htpasswd -c -B /etc/nginx/swan.htpasswd swan
fi
chown root:nginx /etc/nginx/swan.htpasswd
chmod 640 /etc/nginx/swan.htpasswd

# 1. HTTP only, so Let's Encrypt can check we own the name
if [ ! -d "/etc/letsencrypt/live/$HOST" ]; then
  sed "s/HOST/$HOST/g" nginx-swan.conf | awk '/^server \{/{n++} n<2' > /etc/nginx/conf.d/swan.conf
  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx
  command -v certbot >/dev/null || dnf install -y -q certbot \
    || { python3 -m venv /opt/certbot && /opt/certbot/bin/pip install -q certbot && ln -sf /opt/certbot/bin/certbot /usr/local/bin/certbot; }
  certbot certonly --webroot -w /var/www/letsencrypt -d "$HOST" --agree-tos --register-unsafely-without-email -n
fi

# 2. the real site: HTTPS + password
sed "s/HOST/$HOST/g" nginx-swan.conf > /etc/nginx/conf.d/swan.conf
nginx -t
systemctl enable --now nginx
systemctl reload nginx

# 3. the page builder (every minute) and certificate renewal
install -m 644 swan-dash.service swan-dash.timer swan-certbot.service swan-certbot.timer swan-portal.service swan-portal.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now swan-dash.timer swan-certbot.timer
[ -s /home/ec2-user/ctn/secrets/portal_cookie ] && systemctl enable --now swan-portal.timer   # needs the cookie (todo/09)
systemctl start swan-dash.service

# 4. security updates, applied automatically
sed -i 's/^upgrade_type *=.*/upgrade_type = security/; s/^apply_updates *=.*/apply_updates = yes/' /etc/dnf/automatic.conf
systemctl enable --now dnf-automatic.timer

echo "done: https://$HOST  (user swan). Check: systemctl status swan-dash; ls -l /var/www/swan"
