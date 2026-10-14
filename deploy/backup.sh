#!/usr/bin/env bash
# Run as root; backups include plaintext mailbox and AI credentials.
set -euo pipefail
umask 077
backup_dir=/var/backups/uprankd-outreach
install -d -m 700 "$backup_dir"
exec 9>"$backup_dir/.backup.lock"
flock -n 9 || exit 0
stamp=$(date +%Y%m%dT%H%M%S)
dump_path="$backup_dir/$stamp.dump"
tar_path="$backup_dir/$stamp-files.tar.gz"
trap 'rm -f "$dump_path.partial" "$tar_path.partial"' EXIT
runuser -u postgres -- pg_dump -Fc uprankd_outreach > "$dump_path.partial"
tar -C /home/outreach -czf "$tar_path.partial" outreach-data webapps/uprankd-outreach/.env
pg_restore --list "$dump_path.partial" >/dev/null
mv "$dump_path.partial" "$dump_path"
mv "$tar_path.partial" "$tar_path"
find "$backup_dir" -maxdepth 1 -type f \( -name '*.dump' -o -name '*-files.tar.gz' \) -mtime +14 -delete
