#!/usr/bin/env bash
# Signe WebDriverAgent avec un identifiant Apple gratuit et l'installe sur l'iPhone branché en USB.
#
# À lancer soi-même, dans un terminal (identifiant, mot de passe et code à deux facteurs sont demandés ici,
# jamais écrits dans un fichier du dépôt) :
#     scripts/signer-wda.sh
# Une signature gratuite dure 7 jours : relancer ce script chaque semaine. Garder le même WDA_BUNDLE_ID
# d'une semaine à l'autre (un compte gratuit n'a droit qu'à 10 identifiants d'app neufs par semaine).
#
# Outils, épinglés et vérifiés par empreinte :
#   - plumesign (projet claration/impactor, licence MIT) : connexion Apple, certificat, profil, signature, installation ;
#   - WebDriverAgentRunner-Runner.zip (projet appium/WebDriverAgent) : la version appareil réel, non signée.
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
OUTILS="$RACINE/wda"
PMD3="$RACINE/.venv/bin/pymobiledevice3"

PLUMESIGN_VERSION="v2.6.5"
PLUMESIGN_URL="https://github.com/claration/impactor/releases/download/$PLUMESIGN_VERSION/plumesign-linux-x86_64"
PLUMESIGN_SHA256="c076524c48074fb6a8d1acb4944078b52cffc70b3875970e66494e3655c67279"

WDA_VERSION="v16.13.6"
WDA_URL="https://github.com/appium/WebDriverAgent/releases/download/$WDA_VERSION/WebDriverAgentRunner-Runner.zip"
WDA_SHA256="152fb7feedaa2b33a9fd9717d8ad62cfebfde820cc391f378e200e9e77361c6f"

dire() { printf '\n== %s\n' "$*"; }
echec() { printf '\nÉchec : %s\n' "$*" >&2; exit 1; }

telecharger() { # url fichier empreinte
  local url="$1" fichier="$2" attendu="$3"
  if [[ ! -f "$fichier" ]] || [[ "$(sha256sum "$fichier" | cut -d' ' -f1)" != "$attendu" ]]; then
    curl -fsSL -o "$fichier.part" "$url"
    mv "$fichier.part" "$fichier"
  fi
  [[ "$(sha256sum "$fichier" | cut -d' ' -f1)" == "$attendu" ]] || echec "empreinte inattendue pour $fichier"
}

# Lit une clé du .env sans exécuter le fichier.
lire_env() {
  [[ -f "$RACINE/.env" ]] || return 0
  sed -n "s/^$1=//p" "$RACINE/.env" | tail -1 | sed -e 's/^"//' -e 's/"$//'
}

[[ -x "$PMD3" ]] || echec "environnement Python absent ($PMD3) : voir l'installation dans le README"
mkdir -p "$OUTILS"

dire "Outils : plumesign $PLUMESIGN_VERSION et WebDriverAgent $WDA_VERSION"
telecharger "$PLUMESIGN_URL" "$OUTILS/plumesign" "$PLUMESIGN_SHA256"
chmod +x "$OUTILS/plumesign"
telecharger "$WDA_URL" "$OUTILS/WebDriverAgentRunner-Runner.zip" "$WDA_SHA256"

dire "iPhone branché"
# plumesign 2.6.5 compare la valeur de --udid au numéro que usbmuxd donne à l'appareil (DeviceID : 1, 2…),
# pas à son UDID (crates/plume_utils/src/device.rs, get_device_for_id) ; il lit ensuite l'UDID lui-même
# par lockdown pour enregistrer l'appareil dans le compte. On lui passe donc ce numéro.
NUMERO_USBMUX="$("$RACINE/.venv/bin/python" -c '
import asyncio, inspect
from pymobiledevice3 import usbmux
appareils = usbmux.list_devices()
if inspect.isawaitable(appareils):
    appareils = asyncio.run(appareils)
usb = [a for a in appareils if a.connection_type == "USB"]
print(usb[0].devid if len(usb) == 1 else "")
' 2>/dev/null)"
[[ -n "$NUMERO_USBMUX" ]] || echec "il faut exactement un iPhone branché en USB et déverrouillé (« Faire confiance » accepté)"
echo "un iPhone vu en USB (numéro usbmuxd $NUMERO_USBMUX)"

# Identifiant du runner : choisi une fois, gardé dans .env (non suivi par git), réutilisé chaque semaine.
BUNDLE="${WDA_BUNDLE_ID:-$(lire_env WDA_BUNDLE_ID)}"
if [[ -z "$BUNDLE" ]]; then
  BUNDLE="autopost.wda.$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  if grep -q '^WDA_BUNDLE_ID=$' "$RACINE/.env" 2>/dev/null; then
    sed -i "s/^WDA_BUNDLE_ID=\$/WDA_BUNDLE_ID=$BUNDLE/" "$RACINE/.env"
  else
    printf 'WDA_BUNDLE_ID=%s\n' "$BUNDLE" >> "$RACINE/.env"
  fi
  echo "identifiant du runner créé et gardé dans .env : $BUNDLE"
fi

dire "Compte Apple"
if "$OUTILS/plumesign" account list 2>&1 | grep -q "(selected)"; then
  echo "session plumesign déjà ouverte (plumesign account list pour la voir)"
else
  APPLE_ID="${APPLE_ID:-$(lire_env APPLE_ID)}"
  if [[ -z "$APPLE_ID" ]]; then
    read -r -p "Identifiant Apple (adresse e-mail) : " APPLE_ID
  fi
  # Sans -p : le mot de passe est demandé par plumesign, il n'apparaît ni dans l'historique ni dans `ps`.
  "$OUTILS/plumesign" account login -u "$APPLE_ID"
fi

dire "Signature et installation de WebDriverAgent ($BUNDLE)"
TRAVAIL="$(mktemp -d "$OUTILS/signature.XXXXXX")"
trap 'rm -rf "$TRAVAIL"' EXIT
unzip -q "$OUTILS/WebDriverAgentRunner-Runner.zip" -d "$TRAVAIL"
rm -rf "$TRAVAIL"/WebDriverAgentRunner-Runner.app/PlugIns/*.dSYM
"$OUTILS/plumesign" sign \
  -p "$TRAVAIL/WebDriverAgentRunner-Runner.app" \
  --apple-id \
  --custom-identifier "$BUNDLE" \
  --register-and-install \
  --udid "$NUMERO_USBMUX"

dire "Vérification sur l'iPhone"
"$PMD3" apps list 2>/dev/null | "$RACINE/.venv/bin/python" -c '
import json, sys
apps = json.load(sys.stdin)
trouves = {k: v for k, v in apps.items() if "WebDriverAgent" in v.get("CFBundleExecutable", "") or k.startswith(sys.argv[1])}
if not trouves:
    sys.exit("WebDriverAgent introuvable sur l’iPhone après installation")
for ident, info in trouves.items():
    executable = info.get("CFBundleExecutable")
    print(f"installé : {ident} (exécutable {executable})")
' "$BUNDLE"

"$PMD3" provision list 2>/dev/null | "$RACINE/.venv/bin/python" -c '
import json, sys
profils = json.load(sys.stdin)
for p in profils:
    ident = p.get("Entitlements", {}).get("application-identifier", "")
    if sys.argv[1] in ident:
        fin = p.get("ExpirationDate")
        print(f"profil valable jusqu’au {fin} (à re-signer avant)")
' "$BUNDLE" || true

cat <<'FIN'

Signature faite. Si c'est la première fois sur cet iPhone :
  Réglages > Général > VPN et gestion de l'appareil > [ton identifiant Apple] > Faire confiance.
Ensuite : scripts/essai.sh (capture d'écran et tap depuis le serveur).
FIN
