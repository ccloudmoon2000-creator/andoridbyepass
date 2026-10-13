#!/usr/bin/env bash
set -Eeuo pipefail

# Run from the root of an Android source checkout. The script is kept in the
# browser-lab repository, while AOSP_SRC_DIR points to the separate AOSP tree.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
AOSP_SRC_DIR="$(cd -- "${AOSP_SRC_DIR:-$PWD}" && pwd)"
DEPLOY_IMAGE_DIR="${DEPLOY_IMAGE_DIR:-$PROJECT_DIR/aosp-image}"
JOBS="${JOBS:-$(nproc)}"
REPO_JOBS="${REPO_JOBS:-8}"
AOSP_TAG="android-platform-12.0.0_r40"

if [[ ! -x "$AOSP_SRC_DIR/build/envsetup.sh" ]]; then
  echo "ERRO: AOSP_SRC_DIR não contém build/envsetup.sh: $AOSP_SRC_DIR" >&2
  echo "Execute o script a partir da raiz de uma checkout AOSP ou defina AOSP_SRC_DIR." >&2
  exit 2
fi
if ! command -v repo >/dev/null 2>&1; then
  echo "ERRO: o comando repo não está instalado no host de compilação." >&2
  exit 2
fi

cd "$AOSP_SRC_DIR"
echo "Fixar checkout na tag oficial $AOSP_TAG…"
repo init -u https://android.googlesource.com/platform/manifest -b "$AOSP_TAG"

echo "Sincronizar código-fonte AOSP…"
repo sync -c -j"$REPO_JOBS"

echo "Compilar alvo AVD x86-64 para Android 12…"
# shellcheck disable=SC1091
source build/envsetup.sh
lunch sdk_phone_x86_64-userdebug
make -j"$JOBS"

PRODUCT_DIR="$AOSP_SRC_DIR/out/target/product/sdk_phone_x86_64"
if [[ ! -f "$PRODUCT_DIR/system.img" ]]; then
  echo "ERRO: não foi encontrado $PRODUCT_DIR/system.img." >&2
  echo "Confirme o alvo lunch e consulte os artefactos produzidos pela compilação." >&2
  exit 3
fi
if [[ ! -f "$PRODUCT_DIR/ramdisk.img" ]]; then
  echo "ERRO: não foi encontrado $PRODUCT_DIR/ramdisk.img." >&2
  exit 3
fi
if [[ ! -f "$PRODUCT_DIR/kernel-ranchu" && ! -f "$PRODUCT_DIR/kernel" ]]; then
  echo "ERRO: não foi encontrado kernel-ranchu nem kernel em $PRODUCT_DIR." >&2
  exit 3
fi

mkdir -p "$DEPLOY_IMAGE_DIR"
# Copy all device output images, not a web representation or modified Android UI.
cp -a "$PRODUCT_DIR/." "$DEPLOY_IMAGE_DIR/"
if [[ ! -f "$DEPLOY_IMAGE_DIR/kernel-ranchu" && -f "$DEPLOY_IMAGE_DIR/kernel" ]]; then
  ln -s kernel "$DEPLOY_IMAGE_DIR/kernel-ranchu"
fi

printf '\nImagem AOSP copiada para: %s\n' "$DEPLOY_IMAGE_DIR"
printf 'Artefactos-chave:\n'
ls -lh "$DEPLOY_IMAGE_DIR/system.img" "$DEPLOY_IMAGE_DIR/ramdisk.img" "$DEPLOY_IMAGE_DIR/kernel-ranchu"
printf '\nPróximo passo: no diretório do projeto, configure .env e execute docker compose up --build -d.\n'
printf 'Nota: esta etapa não declara sucesso de arranque; confirme /api/status e Settings > About phone após iniciar.\n'
