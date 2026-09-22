#!/bin/sh
# Run with sudo on a fresh Ubuntu 22.04 or 24.04 LTS VPS.
set -eu
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo." >&2; exit 1; fi
. /etc/os-release
if [ "$ID" != ubuntu ] || { [ "$VERSION_ID" != 24.04 ] && [ "$VERSION_ID" != 22.04 ]; }; then
    echo "This installer targets Ubuntu 22.04/24.04 LTS. See Docker's official instructions for other systems." >&2
    exit 1
fi
apt-get update
apt-get install -y ca-certificates curl python3 unzip restic
if command -v docker >/dev/null 2>&1; then
    docker compose version
else
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    arch="$(dpkg --print-architecture)"
    cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${VERSION_CODENAME}
Components: stable
Architectures: $arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
docker compose version
echo "Docker and backup tools installed. No firewall settings were changed."
