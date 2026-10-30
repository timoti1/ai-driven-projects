#!/bin/bash
# =============================================================================
# AIC8800 WiFi+BT Driver Installer
#
# Installs built modules into /lib/modules/$(uname -r)/kernel/drivers/net/wireless/aic8800/
# and loads them in the correct order.
#
# Usage:
#   sudo ./install.sh          # install + load
#   sudo ./install.sh --load   # load only (modules already installed)
#   sudo ./install.sh --unload # unload all AIC modules
# =============================================================================

set -euo pipefail

KVER=$(uname -r)
DEST=/lib/modules/${KVER}/kernel/drivers/net/wireless/aic8800
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_LOAD_FW="${SCRIPT_DIR}/driver/aic_load_fw/aic_load_fw.ko"
SRC_FDRV="${SCRIPT_DIR}/driver/aic8800_fdrv/aic8800_fdrv.ko"
SRC_ZLP="${SCRIPT_DIR}/zlp-quirk/aic_zlp_quirk.ko"
FW_SRC="${SCRIPT_DIR}/firmware/aic8800D80"
FW_DST=/lib/firmware/aic8800D80

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run as root (sudo)."
    exit 1
fi

MODE="${1:-install}"

# --- Unload ---
if [[ "${MODE}" == "--unload" ]]; then
    echo "Unloading AIC modules..."
    modprobe -r aic_zlp_quirk 2>/dev/null || true
    modprobe -r btusb 2>/dev/null || true
    modprobe -r aic8800_fdrv 2>/dev/null || true
    modprobe -r aic_load_fw 2>/dev/null || true
    echo "Done."
    exit 0
fi

# --- Load only ---
if [[ "${MODE}" == "--load" ]]; then
    echo "Loading AIC modules..."
    modprobe aic_load_fw
    sleep 4
    modprobe aic8800_fdrv
    sleep 2
    modprobe aic_zlp_quirk
    sleep 1
    modprobe btusb
    sleep 3
    hciconfig hci0 up 2>/dev/null || true
    echo "Loaded. Status:"
    lsmod | grep -E "aic|btusb"
    hciconfig -a 2>/dev/null || true
    exit 0
fi

# --- Full install ---
echo "================================================="
echo " AIC8800 WiFi+BT Driver Installer"
echo " Kernel: ${KVER}"
echo "================================================="

# Check built modules exist
for f in "${SRC_LOAD_FW}" "${SRC_FDRV}" "${SRC_ZLP}"; do
    if [[ ! -f "${f}" ]]; then
        echo "ERROR: ${f} not found. Run ./build.sh first."
        exit 1
    fi
done

# Install firmware
echo "[1/4] Installing firmware..."
mkdir -p "${FW_DST}"
cp -f "${FW_SRC}/"*.bin "${FW_DST}/" 2>/dev/null || true
cp -f "${FW_SRC}/"*.txt "${FW_DST}/" 2>/dev/null || true
echo "      Firmware -> ${FW_DST}/"

# Install kernel modules
echo "[2/4] Installing kernel modules..."
mkdir -p "${DEST}"
install -p -m 644 "${SRC_LOAD_FW}" "${DEST}/"
install -p -m 644 "${SRC_FDRV}" "${DEST}/"
install -p -m 644 "${SRC_ZLP}" "${DEST}/"
depmod -a "${KVER}"
echo "      Modules -> ${DEST}/"
ls -la "${DEST}/"

# Unload for clean state
echo "[3/4] Unloading existing modules..."
modprobe -r aic_zlp_quirk 2>/dev/null || true
modprobe -r btusb 2>/dev/null || true
modprobe -r aic8800_fdrv 2>/dev/null || true
modprobe -r aic_load_fw 2>/dev/null || true
sleep 2

# Load in correct order
echo "[4/4] Loading modules..."
echo "      aic_load_fw (firmware upload, device re-enumerates)..."
modprobe aic_load_fw
sleep 4
echo "      aic8800_fdrv (WiFi)..."
modprobe aic8800_fdrv
sleep 2
echo "      aic_zlp_quirk (BT ZLP quirk, BEFORE btusb)..."
modprobe aic_zlp_quirk
sleep 1
echo "      btusb (standard Bluetooth)..."
modprobe btusb
sleep 3
echo "      hciconfig hci0 up..."
hciconfig hci0 up 2>/dev/null || true
sleep 1

# Status
echo ""
echo "================================================="
echo " STATUS"
echo "================================================="
echo "--- Modules ---"
lsmod | grep -E "aic|btusb" || echo "(none)"
echo ""
echo "--- USB ---"
lsusb | grep -iE "a69c|368b|aic" || echo "(adapter not seen)"
echo ""
echo "--- Network ---"
ip -br link show
echo ""
echo "--- Bluetooth ---"
hciconfig -a 2>/dev/null || echo "(no hci)"
echo ""
echo "================================================="
echo " Done."
echo "================================================="
