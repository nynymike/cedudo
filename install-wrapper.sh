#!/bin/bash
# Install the cedudo C wrapper for setuid support
#
# Most modern Linux systems don't allow setuid on interpreted scripts.
# This script compiles and installs the C wrapper that enables setuid.

set -e

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
echo "  cedudo view-logs"
