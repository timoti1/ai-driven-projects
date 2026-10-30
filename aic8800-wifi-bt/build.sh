#!/bin/bash
# =============================================================================
# AIC8800 WiFi+BT Driver Builder
#
# Builds aic_load_fw.ko + aic8800_fdrv.ko + aic_zlp_quirk.ko for the CURRENT
# running kernel. Run after a kernel update:
#
#   sudo ./build.sh
#
# Requirements:
#   - linux-headers-$(uname -r) installed
#   - build-essential (gcc, make)
#
# After building, run install.sh to install and load the modules.
# =============================================================================

set -euo pipefail

KVER=$(uname -r)
KDIR=/lib/modules/${KVER}/build
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_DIR="${SCRIPT_DIR}/driver"
ZLP_DIR="${SCRIPT_DIR}/zlp-quirk"
FW_DIR="${SCRIPT_DIR}/firmware/aic8800D80"

echo "================================================="
echo " AIC8800 WiFi+BT Driver Builder"
echo " Kernel: ${KVER}"
echo "================================================="

# --- Check prerequisites ---
if [[ ! -d "${KDIR}" ]]; then
    echo "ERROR: kernel headers not found at ${KDIR}"
    echo "Install: sudo apt install linux-headers-${KVER}"
    exit 1
fi

if ! command -v gcc &>/dev/null; then
    echo "ERROR: gcc not found. Install: sudo apt install build-essential"
    exit 1
fi

# --- Clean stale build artifacts ---
echo "[1/3] Cleaning build artifacts..."
find "${DRIVER_DIR}" -name "*.o" -delete 2>/dev/null || true
find "${DRIVER_DIR}" -name "*.ko" -delete 2>/dev/null || true
find "${DRIVER_DIR}" -name "*.mod" -delete 2>/dev/null || true
find "${DRIVER_DIR}" -name ".*.cmd" -delete 2>/dev/null || true
find "${DRIVER_DIR}" -name ".*.d" -delete 2>/dev/null || true
find "${DRIVER_DIR}" -name "modules.order" -delete 2>/dev/null || true
find "${DRIVER_DIR}" -name "Module.symvers" -delete 2>/dev/null || true
find "${ZLP_DIR}" -name "*.o" -delete 2>/dev/null || true
find "${ZLP_DIR}" -name "*.ko" -delete 2>/dev/null || true
find "${ZLP_DIR}" -name "*.mod" -delete 2>/dev/null || true
find "${ZLP_DIR}" -name ".*.cmd" -delete 2>/dev/null || true
find "${ZLP_DIR}" -name ".*.d" -delete 2>/dev/null || true

# --- Build main driver (aic_load_fw + aic8800_fdrv) ---
echo "[2/3] Building aic_load_fw + aic8800_fdrv..."
make -C "${KDIR}" M="${DRIVER_DIR}" ARCH=x86_64 modules 2>&1 | grep -vE "^\s*(CC|LD|MODPOST|BTF|make\[)" || true

# Verify
if [[ ! -f "${DRIVER_DIR}/aic_load_fw/aic_load_fw.ko" ]]; then
    echo "ERROR: aic_load_fw.ko not built"
    exit 1
fi
if [[ ! -f "${DRIVER_DIR}/aic8800_fdrv/aic8800_fdrv.ko" ]]; then
    echo "ERROR: aic8800_fdrv.ko not built"
    exit 1
fi
echo "      aic_load_fw.ko: $(du -h "${DRIVER_DIR}/aic_load_fw/aic_load_fw.ko" | cut -f1)"
echo "      aic8800_fdrv.ko: $(du -h "${DRIVER_DIR}/aic8800_fdrv/aic8800_fdrv.ko" | cut -f1)"

# --- Build ZLP quirk ---
echo "[3/3] Building aic_zlp_quirk..."
make -C "${KDIR}" M="${ZLP_DIR}" ARCH=x86_64 modules 2>&1 | grep -vE "^\s*(CC|LD|MODPOST|BTF|make\[)" || true

if [[ ! -f "${ZLP_DIR}/aic_zlp_quirk.ko" ]]; then
    echo "ERROR: aic_zlp_quirk.ko not built"
    exit 1
fi
echo "      aic_zlp_quirk.ko: $(du -h "${ZLP_DIR}/aic_zlp_quirk.ko" | cut -f1)"

# --- Verify vermagic ---
echo ""
echo "=== Verificating vermagic ==="
for ko in \
    "${DRIVER_DIR}/aic_load_fw/aic_load_fw.ko" \
    "${DRIVER_DIR}/aic8800_fdrv/aic8800_fdrv.ko" \
    "${ZLP_DIR}/aic_zlp_quirk.ko"; do
    vm=$(modinfo "${ko}" 2>/dev/null | grep vermagic | awk '{print $2}')
    if [[ "${vm}" == "${KVER}"* ]]; then
        echo "  OK: $(basename "${ko}") -> ${vm}"
    else
        echo "  MISMATCH: $(basename "${ko}") -> ${vm} (expected ${KVER})"
    fi
done

echo ""
echo "================================================="
echo " Build complete! Run ./install.sh to install."
echo "================================================="
