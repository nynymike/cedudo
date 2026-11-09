#!/bin/bash
# Install the cedudo C wrapper for setuid support
#
# Most modern Linux systems don't allow setuid on interpreted scripts.
# This script compiles and installs the C wrapper that enables setuid.

# Run as your ordinary administrator account WITHOUT sudo. The compiler runs as
# you; only the install steps below call sudo.
set -e
[ "$(id -u)" -ne 0 ] || echo "note: running as root; run as an administrator account without sudo instead" >&2

echo "Building cedudo wrapper..."
gcc -o cedudo-wrapper cedudo-wrapper.c

echo "Installing wrapper to /opt/cedudo/cedudo..."
sudo cp cedudo-wrapper /opt/cedudo/cedudo
sudo chown root:root /opt/cedudo/cedudo
sudo chmod 4755 /opt/cedudo/cedudo

echo "Creating symlink..."
sudo ln -sf /opt/cedudo/cedudo /usr/local/bin/cedudo

echo "Cleaning up build artifacts..."
rm cedudo-wrapper

echo ""
echo "Installation complete!"
echo ""
echo "Verify with:"
echo "  ls -l /opt/cedudo/cedudo"
echo "  # Should show: -rwsr-xr-x 1 root root ... /opt/cedudo/cedudo"
echo ""
echo "Test as a regular user:"
echo "  cedudo read-logs"
