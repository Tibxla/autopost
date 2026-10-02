"""Essai de bout en bout le plus court : tunnel, image développeur, WebDriverAgent lancé, une capture et un tap.

    .venv/bin/python scripts/essai.py            # arrête WDA et les relais à la fin
    .venv/bin/python scripts/essai.py --garder   # les laisse tourner (Ctrl+C pour tout arrêter)

Prérequis (voir le README) : Mode développeur actif, WebDriverAgent signé par scripts/signer-wda.sh et son
certificat approuvé dans Réglages, `tunneld` lancé en root. Le tap vise le haut de l'écran, au milieu (l'encoche
sur un iPhone XS) : il ne déclenche rien. Aucune app n'est ouverte, rien n'est publié.
Avant le tap, le pont d'Autocalled est interrogé : s'il y a un appel en cours, ou si son état est illisible,
l'essai s'arrête sans toucher l'écran. Il est lu avant de lancer WDA, puis de nouveau juste avant le tap.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
PMD3 = str(RACINE / ".venv" / "bin" / "pymobiledevice3")
SORTIES = RACINE / "donnees" / "essai"


def lire_env() -> dict[str, str]:
    valeurs: dict[str, str] = {}
    fichier = RACINE / ".env"
    if fichier.exists():
        for ligne in fichier.read_text().splitlines():
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                cle, _, valeur = ligne.partition("=")
                valeurs[cle.strip()] = valeur.strip().strip('"')
    return {**valeurs, **{k: v for k, v in os.environ.items() if k in valeurs or k.startswith(("WDA_", "AUTOCALLED_"))}}


def etape(texte: str) -> None:
    print(f"\n== {texte}", flush=True)


def arret(texte: str) -> None:
    print(f"\nArrêt : {texte}", file=sys.stderr)
    sys.exit(1)


def pmd3(*args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run([PMD3, *args], capture_output=True, text=True, timeout=timeout)


def secret_du_pont(env: dict[str, str]) -> str | None:
    if env.get("AUTOCALLED_PONT_SECRET"):
        return env["AUTOCALLED_PONT_SECRET"]
    chemin = env.get("AUTOCALLED_ENV")
    if chemin and Path(chemin).exists():
        for ligne in Path(chemin).read_text().splitlines():
            if ligne.startswith("PONT_SECRET="):
                return ligne.split("=", 1)[1].strip().strip('"')
    return None


def telephone_libre(env: dict[str, str]) -> tuple[bool, str]:
    """Libre seulement si le pont répond 200 avec appelEnCours faux et appelId nul. Tout le reste bloque."""
    url = env.get("AUTOCALLED_PONT_URL", "http://127.0.0.1:3021").rstrip("/") + "/etat"
    secret = secret_du_pont(env)
    if not secret:
        return False, "secret du pont d'Autocalled introuvable (AUTOCALLED_PONT_SECRET ou AUTOCALLED_ENV)"
    try:
        r = requests.get(url, headers={"authorization": f"Bearer {secret}"}, timeout=5)
    except requests.RequestException as e:
        return False, f"pont d'Autocalled injoignable ({e.__class__.__name__})"
    if r.status_code != 200:
        return False, f"pont d'Autocalled : réponse {r.status_code}"
    etat = r.json()
    if etat.get("appelEnCours") is not False or etat.get("appelId") is not None:
        return False, "appel en cours sur la ligne d'Autocalled"
    return True, "aucun appel en cours"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--garder", action="store_true", help="laisser WDA et les relais tourner après l'essai")
    garder = parser.parse_args().garder
    env = lire_env()
    bundle = env.get("WDA_BUNDLE_ID") or arret("WDA_BUNDLE_ID absent du .env : lancer d'abord scripts/signer-wda.sh")
    port_wda = int(env.get("WDA_PORT_LOCAL", "8100"))
    port_mjpeg = int(env.get("MJPEG_PORT_LOCAL", "9110"))
    SORTIES.mkdir(parents=True, exist_ok=True)

    etape("Mode développeur")
    sortie = pmd3("amfi", "developer-mode-status").stdout.strip().lower()
    if sortie != "true":
        arret("Mode développeur inactif : Réglages > Confidentialité et sécurité > Mode développeur (voir README)")
    print("actif")

    etape("Tunnel (tunneld)")
    try:
        tunnels = requests.get("http://127.0.0.1:49151/", timeout=3).json()
    except requests.RequestException:
        arret("tunneld ne répond pas : sudo .venv/bin/pymobiledevice3 remote tunneld --host 127.0.0.1")
    if not tunnels:
        arret("tunneld tourne mais ne voit aucun iPhone")
    print("tunnel ouvert")

    etape("Image développeur")
    r = pmd3("mounter", "auto-mount", "--tunnel", "", timeout=300)
    if r.returncode != 0 and "already mounted" not in (r.stdout + r.stderr).lower():
        arret("montage refusé :\n" + (r.stderr or r.stdout)[-800:])
    print("montée")

    # Lancer WDA est déjà un geste (le runner passe au premier plan) : le pont est lu avant, puis avant le tap.
    etape("Téléphone libre ?")
    libre, raison = telephone_libre(env)
    print(raison)
    if not libre:
        arret("WDA non lancé : " + raison)

    etape(f"WebDriverAgent ({bundle})")
    journal_wda = open(SORTIES / "wda.log", "w")
    processus = [
        subprocess.Popen([PMD3, "developer", "dvt", "xcuitest", bundle, "--tunnel", ""], stdout=journal_wda, stderr=subprocess.STDOUT),
        subprocess.Popen([PMD3, "usbmux", "forward", str(port_wda), "8100"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([PMD3, "usbmux", "forward", str(port_mjpeg), "9100"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    wda = f"http://127.0.0.1:{port_wda}"
    try:
        for _ in range(60):
            if processus[0].poll() is not None:
                journal = (SORTIES / "wda.log").read_text(errors="replace")
                if "failed to launch process" in journal.lower():
                    arret("l'iPhone refuse de lancer WDA. Cause la plus fréquente : certificat pas encore approuvé "
                          "(Réglages > Général > VPN et gestion de l'appareil > Faire confiance), ou signature expirée "
                          "(relancer scripts/signer-wda.sh). Le détail est dans le journal système de l'iPhone : "
                          ".venv/bin/pymobiledevice3 syslog live | grep -i trust")
                arret(f"le lanceur XCUITest s'est arrêté, voir {SORTIES / 'wda.log'}")
            try:
                statut = requests.get(f"{wda}/status", timeout=2).json()
                break
            except requests.RequestException:
                time.sleep(1)
        else:
            arret(f"WDA ne répond pas sur {wda} après 60 s, voir {SORTIES / 'wda.log'}")
        print("WDA prêt :", json.dumps(statut.get("value", {}).get("build", {}), ensure_ascii=False))

        etape("Capture d'écran")
        png = base64.b64decode(requests.get(f"{wda}/screenshot", timeout=20).json()["value"])
        (SORTIES / "avant.png").write_bytes(png)
        print(f"{len(png)} octets -> {SORTIES / 'avant.png'}")

        etape("Flux MJPEG")
        with requests.get(f"http://127.0.0.1:{port_mjpeg}/", stream=True, timeout=5) as flux:
            debut = next(flux.iter_content(4096))
        if b"\xff\xd8" not in debut and b"image/jpeg" not in debut.lower():
            arret("le flux MJPEG ne renvoie pas d'image")
        print("images reçues")

        etape("Téléphone libre ?")
        libre, raison = telephone_libre(env)
        print(raison)
        if not libre:
            arret("tap annulé : " + raison)

        etape("Tap")
        session = requests.post(f"{wda}/session", json={"capabilities": {}}, timeout=30).json()["sessionId"]
        taille = requests.get(f"{wda}/session/{session}/window/size", timeout=10).json()["value"]
        x, y = int(taille["width"] / 2), 6
        actions = {"actions": [{"type": "pointer", "id": "doigt", "parameters": {"pointerType": "touch"}, "actions": [
            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
            {"type": "pointerDown", "button": 0},
            {"type": "pause", "duration": 80},
            {"type": "pointerUp", "button": 0},
        ]}]}
        r = requests.post(f"{wda}/session/{session}/actions", json=actions, timeout=20)
        r.raise_for_status()
        print(f"tap en ({x}, {y}) points sur un écran de {taille['width']}x{taille['height']} points : accepté")
        png = base64.b64decode(requests.get(f"{wda}/screenshot", timeout=20).json()["value"])
        (SORTIES / "apres.png").write_bytes(png)

        print("\nEssai réussi : tunnel, image développeur, WDA, capture, MJPEG et tap.")
        if garder:
            print(f"WDA sur {wda}, MJPEG sur http://127.0.0.1:{port_mjpeg}/ ; Ctrl+C pour arrêter.")
            processus[0].wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in processus:
            p.terminate()


if __name__ == "__main__":
    main()
