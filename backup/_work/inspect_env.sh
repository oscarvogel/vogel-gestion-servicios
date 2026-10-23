#!/bin/bash
echo "=== OS ==="
cat /etc/os-release | head -3
echo "=== python ==="
python3 --version 2>&1
pip3 --version 2>&1 | head -1
echo "=== docker ==="
docker --version 2>&1 | head -1
echo "=== docker running? ==="
docker ps 2>&1 | head -3
echo "=== sqlcmd ==="
which sqlcmd 2>&1
ls /opt/mssql-tools*/bin/ 2>&1 | head -5
echo "=== disk ==="
df -h / /mnt/c 2>&1 | head -6
echo "=== mem ==="
free -h | head -2
echo "=== mysql/mariadb ==="
which mysql mariadb mysqld 2>&1
echo "=== bak file visible from WSL? ==="
ls -la "/mnt/c/Programacion/vogel-gestion/backup/" 2>&1 | head -5
