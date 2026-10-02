# autopost

Publier ses propres vidéos sur TikTok et Instagram depuis son vrai iPhone, sans le tenir. L'iPhone reste branché en USB à un serveur Linux ; le serveur pilote l'écran par WebDriverAgent, à une heure tirée dans une fenêtre choisie, et une petite page web montre l'écran en direct pour reprendre la main à tout moment.

## Pourquoi

Publier depuis le téléphone, c'est publier comme un humain le fait : l'app officielle, le vrai compte, la vraie bibliothèque Photos. Pas d'API tierce, pas de cookies copiés dans un navigateur sans tête. Ce qu'on automatise, c'est seulement le moment où il faudrait sortir le téléphone pour appuyer sur « Publier ».

## Périmètre, volontairement étroit

autopost publie, et ne fait rien d'autre. Pas de défilement de fil, pas de like, pas d'abonnement, pas de commentaire, pas de geste « humanisé » ni de hasard dans les mouvements pour passer sous les radars des plateformes. Le seul hasard est l'heure de publication, tirée dans une fenêtre choisie à l'avance : c'est de la planification. Rien ne part sans une validation explicite dans l'interface.

## État

| Étape | État |
|---|---|
| iPhone vu par usbmuxd, tunnel iOS 17+ (`tunneld`) | vérifié |
| Mode développeur, image développeur montée | vérifié |
| WebDriverAgent signé sans Mac (plumesign) et installé | vérifié : installé, profil valable 7 jours |
| Capture d'écran, flux MJPEG et tap depuis le serveur | en attente : l'iPhone refuse de lancer WDA tant que le certificat n'est pas approuvé dans Réglages |
| Garde d'Autocalled (pas d'action pendant un appel) | vérifiée contre le pont réel |
| Raccourci iOS, parcours TikTok et Instagram, file, service, interface | pas commencé : on ne construit rien tant que l'essai de bout en bout ne passe pas |

## Les gestes à faire sur l'iPhone et au terminal, dans l'ordre

1. **Mode développeur.** Le serveur l'a déjà fait apparaître dans les Réglages (`pymobiledevice3 amfi reveal-developer-mode`). Sur l'iPhone : Réglages > Confidentialité et sécurité > Mode développeur > activer, puis « Redémarrer ». Après le redémarrage, déverrouiller et répondre « Activer » à la question, avec le code.
   Si l'iPhone sert aussi de passerelle à un autre service (Bluetooth, appels), le faire hors de tout usage de ce service : le redémarrage coupe la liaison, qu'il faudra peut-être relancer depuis ce service.
2. **Signer WebDriverAgent**, dans un terminal du serveur : `scripts/signer-wda.sh`. Le script demande l'identifiant Apple, puis plumesign demande le mot de passe et le code à deux facteurs. Ils ne sont écrits dans aucun fichier du dépôt ; plumesign garde sa session dans son propre dossier de configuration.
3. **Faire confiance au certificat** sur l'iPhone : Réglages > Général > VPN et gestion de l'appareil > l'identifiant Apple > Faire confiance.
4. **Lancer l'essai** : `.venv/bin/python scripts/essai.py`. Il monte l'image développeur, lance WebDriverAgent, enregistre une capture dans `donnees/essai/` (non suivi par git), vérifie le flux MJPEG et fait un tap inoffensif en haut de l'écran.
5. **Avant d'écrire les parcours** : installer TikTok et Instagram sur l'iPhone depuis l'App Store et s'y connecter (tous les comptes TikTok visés ajoutés dans l'app, pour la bascule de compte), puis créer le Raccourci d'import (ses étapes seront décrites ici avec le parcours).
6. **Chaque semaine** : relancer `scripts/signer-wda.sh`. La signature gratuite dure 7 jours ; le script affiche la date d'expiration lue sur le profil installé.

Accrocs possibles, non rencontrés à ce jour : un identifiant Apple jamais utilisé pour du développement peut demander d'accepter les conditions sur developer.apple.com avant que plumesign puisse créer le certificat ; un compte gratuit n'a droit qu'à 10 identifiants d'app neufs par semaine, d'où l'identifiant de WebDriverAgent tiré une seule fois et gardé dans `.env`.

## Installation

Python 3.12 dans un environnement virtuel (avec [uv](https://docs.astral.sh/uv/)) :

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env    # puis remplir
```

`usbmuxd` doit tourner (`systemctl status usbmuxd`) et l'iPhone avoir accepté « Faire confiance à cet ordinateur ».
Sur iOS 17 et plus, les services développeur passent par un tunnel. Pour l'instant il est ouvert en root :

```sh
sudo .venv/bin/pymobiledevice3 remote tunneld --host 127.0.0.1
```

Après un redémarrage de l'iPhone, `tunneld` peut rester sans tunnel (l'iPhone était verrouillé à sa reconnexion) : l'arrêter et le relancer une fois l'iPhone déverrouillé.

pymobiledevice3 propose aussi un tunnel sans root (`--userspace`, iOS 17.4 et plus) ; il sera essayé pour le service.

## Projets existants et choix

Relevé du 2026-10-02 (`gh api`, README, issues). L'idée était de reprendre ce qui existe plutôt que de le réécrire.

| Projet | Licence | Dernier push | iOS 17+ et Linux | Ce qu'on en fait |
|---|---|---|---|---|
| [doronz88/pymobiledevice3](https://github.com/doronz88/pymobiledevice3) | GPL-3.0 | 2026-09-30 | oui : tunnel RSD, image développeur personnalisée, lancement XCUITest, relais usbmux | **dépendance principale** : tunnel, montage, lancement de WebDriverAgent, relais de ports, lecture des profils |
| [appium/WebDriverAgent](https://github.com/appium/WebDriverAgent) | BSD | 2026-09-30 (v16.13.6) | le serveur qui tourne sur l'iPhone ; la release `WebDriverAgentRunner-Runner.zip` est une compilation arm64 pour appareil réel, non signée (vérifié) | **repris tel quel**, re-signé sous Linux. Les frameworks XCTest n'y sont pas : sur iOS 17+ ils viennent de l'image développeur |
| [claration/impactor](https://github.com/claration/impactor) (plumesign, ex PlumeImpactor) | MIT | 2026-09-30 (v2.6.5) | binaire Linux x86_64 statique, installation par usbmuxd | **retenu pour signer** (voir plus bas), pas encore éprouvé sur cet iPhone |
| [danielpaulus/go-ios](https://github.com/danielpaulus/go-ios) | MIT | 2026-09-29 | oui : `ios tunnel start`, `ios runwda` | plan B si le lancement de WDA par pymobiledevice3 lâche sur iOS 18.7 |
| [openatx/facebook-wda](https://github.com/openatx/facebook-wda) | MIT | 2026-07-01 (pas de release depuis 2025-09) | client HTTP, indépendant du système ; bogues ouverts sur iOS 17/18 | écarté : les quelques appels utiles (session, actions W3C, `/source`, capture) s'écrivent en quelques lignes avec `requests` |
| [go-ios, PR #834 « ios remote »](https://github.com/danielpaulus/go-ios/pull/834) | MIT | ouverte, non fusionnée | page web : écran en direct, tap, glisser, texte | référence pour l'interface (coordonnées en fraction de l'image ramenées en points, un seul diffuseur d'images qui saute les images pour un client lent), pas de code repris |
| [alibaba/tidevice](https://github.com/alibaba/tidevice) | MIT | 2025-11 | non : pas d'iOS 17+, le projet renvoie vers pymobiledevice3 | écarté |
| [SonicCloudOrg/sonic-agent](https://github.com/SonicCloudOrg/sonic-agent), [sonic-ios-bridge](https://github.com/SonicCloudOrg/sonic-ios-bridge) | AGPL-3.0 | archivés (2024, 2025) | non | écarté |
| [appium/appium-xcuitest-driver](https://github.com/appium/appium-xcuitest-driver) | Apache-2.0 | 2026-09-28 | le pilotage réel suppose Xcode | écarté : Node et Appium entiers pour quelques appels HTTP |
| [DeviceFarmer/stf](https://github.com/DeviceFarmer/stf) | Apache-2.0 | 2026-10 | Android seulement | écarté |
| Outils de publication automatique TikTok/Instagram (par ex. [wkaisertexas/tiktok-uploader](https://github.com/wkaisertexas/tiktok-uploader)) | MIT pour la plupart | divers | navigateur sans tête avec cookies, ou Android par ADB | écartés : ce n'est pas publier depuis le téléphone, et plusieurs embarquent des fonctions d'engagement hors périmètre |

Aucun projet public trouvé ne publie sur TikTok ou Instagram depuis un iPhone réel piloté par WebDriverAgent sous Linux : les parcours de publication sont à écrire.

### Signer WebDriverAgent sans Mac

| Outil | Licence | Dernière release | Pourquoi |
|---|---|---|---|
| **plumesign** ([claration/impactor](https://github.com/claration/impactor)) | MIT | v2.6.5, 2026-09-28 | **retenu** : un binaire Linux qui fait tout en une commande (connexion à l'identifiant Apple avec double facteur, certificat, enregistrement de l'appareil et des identifiants d'app, signature récursive des sous-bundles, installation par usbmuxd), session mémorisée, projet très actif |
| [Dadoum/Sideloader](https://github.com/Dadoum/Sideloader) | GPL-3.0 | 1.0-pre4, 2024-10 | plan B : CLI qui fait la même chose, mais les correctifs récents ne sont pas publiés en binaire (il faudrait compiler du D) |
| [NyaMisty/AltServer-Linux](https://github.com/NyaMisty/AltServer-Linux) | AGPL-3.0 | 0.0.5, 2022 | écarté : à l'abandon, pensé pour installer AltStore |
| [zhlynn/zsign](https://github.com/zhlynn/zsign) | MIT | v1.1.2, 2026-08 | écarté : signe avec un certificat et un profil qu'on lui donne, ne parle pas à Apple |

Piège de plumesign 2.6.5 : son option `--udid` attend en réalité le numéro que usbmuxd donne à l'appareil (1, 2…), pas l'UDID (« Device ID … not found » sinon) ; plumesign relit ensuite l'UDID lui-même pour enregistrer l'iPhone dans le compte. Le script lui passe ce numéro.

Le script épingle les versions de plumesign et de WebDriverAgent et vérifie leurs empreintes SHA-256 avant de s'en servir.

## Architecture (prévue)

```
navigateur (tailnet) ── tailscale serve ── interface autopost (127.0.0.1)
                                              │  file SQLite, journal, pause
                                              │
                                   automate (service systemd utilisateur)
                                     │ vérifie avant chaque geste : pause, pont d'Autocalled
                                     │
              pymobiledevice3 : tunnel, image développeur, XCUITest, relais usbmux
                                     │
                    iPhone ── WebDriverAgent :8100 (HTTP) et :9100 (MJPEG)
```

- **Entrée des vidéos** : le serveur sert la vidéo sur une adresse du tailnet, ouvre `shortcuts://run-shortcut?name=…&input=text&text=<url>`, un Raccourci iOS la télécharge et l'enregistre dans Photos. La légende reste côté serveur et se tape par WebDriverAgent.
- **Parcours** : éléments repérés par l'accessibilité (`/source`, prédicats), jamais par coordonnées en dur ; chaque étape vérifie l'élément attendu et garde une capture. Au moindre écart : arrêt, état « à reprendre à la main », rien n'est retenté à l'aveugle.
- **Garde d'appel** : un autre service peut utiliser le même iPhone comme ligne téléphonique. Avant chaque geste, autopost interroge son pont (`GET /etat`) et n'agit que sur une réponse 200 sans appel en cours ; une erreur, un refus de connexion ou un secret faux bloquent.
- **Interface** : servie sur 127.0.0.1, exposée sur le tailnet par `tailscale serve`, authentification par l'en-tête `Tailscale-User-Login`.

## Limites

- Les apps changent leurs écrans sans prévenir : un parcours qui marchait peut casser du jour au lendemain. autopost s'arrête alors et demande la main, il ne devine pas.
- Les conditions d'utilisation de TikTok et d'Instagram encadrent l'accès automatisé. autopost se limite à publier son propre contenu sur ses propres comptes, depuis l'app officielle ; à chacun de vérifier que cet usage lui convient.
- La signature gratuite expire tous les 7 jours : sans re-signature hebdomadaire, WebDriverAgent ne se lance plus.
- iPhone sous iOS 17 ou plus récent, serveur Linux ; testé sur un seul modèle.

## Licence

GPL-3.0-or-later, comme pymobiledevice3 dont autopost se sert comme bibliothèque.
