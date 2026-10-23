#!/usr/bin/env bash
# Run as innovagro. Backups remain on this VPS; keep external copies separately.
set -euo pipefail
umask 077

backup_dir=/opt/innovagro/backups/techa
mkdir -p "$backup_dir"
exec 9>"$backup_dir/.backup.lock"
flock -n 9 || exit 0
stamp=$(date -u +%Y%m%dT%H%M%SZ)

case "${1:-database}" in
  database)
    target="$backup_dir/database-$stamp.dump"
    temporary="$target.partial"
    trap 'rm -f "$temporary"' EXIT
    docker exec techa-db-1 pg_dump -U techa_user -d techa_db -Fc > "$temporary"
    test -s "$temporary"
    docker exec -i techa-db-1 pg_restore --list < "$temporary" > /dev/null
    mv "$temporary" "$target"
    find "$backup_dir" -maxdepth 1 -type f -name 'database-*.dump' -mtime +13 -delete
    ;;
  files)
    target="$backup_dir/files-$stamp.tar.gz"
    temporary="$target.partial"
    trap 'rm -f "$temporary"' EXIT
    docker exec techa-api-1 nice -n 19 tar -C /data -czf - . > "$temporary"
    gzip -t "$temporary"
    mv "$temporary" "$target"
    find "$backup_dir" -maxdepth 1 -type f -name 'files-*.tar.gz' -mtime +13 -delete
    ;;
  *) echo 'Usage: backup-hostinger.sh [database|files]' >&2; exit 2 ;;
esac
echo "$(date -u +%FT%TZ) Backup completed: $(basename "$target")"
