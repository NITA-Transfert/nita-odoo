# nita-odoo

Plugin de paiement NITA pour Odoo 17 (module `payment_nita`).
Voir la spec et le plan dans le dépôt Nita_developer_portal (docs/superpowers) :
[spec de conception](../Nita_developer_portal/docs/superpowers/specs/2026-10-01-nita-odoo-plugin-design.md).

Le module encaisse une commande e-commerce (`website_sale`) ou une facture au
portail client via NITA : le client est redirigé vers la page de paiement
NITA, et la commande/facture est validée à la réception du **callback NITA**, qui déclenche la relecture
du statut réel (jamais sur la foi du callback lui-même ni du retour navigateur).

## ⚠️ Avertissement bloquant — paquet PyPI en retard

La version actuellement publiée sur PyPI, **`nita-transfert-sdk==0.1.0b1`**
(seule version disponible à ce jour), **ne contient pas** le module
`nita_sdk.client.callback` (`verify_callback`, `NitaCallbackError`) que le
controller webhook de ce module importe
(`payment_nita/controllers/main.py`). Un `pip install nita-transfert-sdk`
« à la lettre » installe donc un SDK qui **plante à l'import** dès la
première notification NITA :

```
ImportError: cannot import name 'NitaCallbackError' from 'nita_sdk.client'
```

(reproduit en conteneur Odoo 17 réel — voir
`.superpowers/sdd/odoo/e2e-report.md`, Finding 1.)

**Ce module importe correctement l'API publique documentée du SDK** — ce
n'est pas un défaut de `payment_nita`, c'est le paquet PyPI qui est en retard
sur le monorepo `nita-sdks` (le module `callback.py` y a été ajouté par le
commit `ec20fd5`, **après** la publication `0.1.0b1`, jamais republiée
depuis).

**Prérequis bloquant avant toute installation réelle** : tant que
`nita-transfert-sdk` n'est pas republié sur PyPI avec `nita_sdk.client.callback`
inclus, installez le SDK depuis la **source du monorepo `nita-sdks`**
(branche `main`) plutôt que depuis PyPI, par exemple :

```bash
pip install "git+https://github.com/NITA-Transfert/nita-sdks.git#subdirectory=sdks/python"
# ou, en clone local :
pip install -e /chemin/vers/nita-sdks/sdks/python
```

Adaptez le sous-répertoire à la structure réelle du monorepo au moment de
l'installation. Une fois `nita-transfert-sdk` republié sur PyPI avec
`callback.py` inclus, le `pip install nita-transfert-sdk` standard
ci-dessous redevient suffisant — vérifiez `pip index versions
nita-transfert-sdk` avant de décider.

## Prérequis

- **Odoo 17.0**, self-hosted ou Odoo.sh. **Odoo Online (SaaS) n'est pas
  supporté** : ce module dépend d'un paquet pip (`nita_sdk`) et d'addons
  custom, deux choses interdites sur Odoo Online.
- Le paquet Python `nita_sdk` installé **dans l'environnement Python
  qu'Odoo utilise réellement** (le virtualenv/l'image du serveur Odoo, pas
  un venv de développement local) :
  ```bash
  pip install nita-transfert-sdk
  ```
  — en tenant compte de l'avertissement ci-dessus tant que la republication
  PyPI n'est pas faite.
- Un compte partenaire NITA (login, clé API, mot de passe, secret HMAC) et
  l'URL de base de l'API (sandbox ou production).

## Installation du module

1. Copiez (ou liez) le dossier `payment_nita/` dans le répertoire
   `addons`/`extra-addons` de votre instance Odoo 17 — voir
   [Packaging](#packaging--zip-installable) pour produire un zip prêt à
   déposer.
2. Redémarrez le serveur Odoo (ou laissez-le recharger s'il surveille déjà
   ce répertoire).
3. En mode développeur, **Apps > Mettre à jour la liste des Apps**.
4. Recherchez « NITA », ouvrez **NITA - Paiement en ligne**, cliquez
   **Activer**.

## Configuration du provider

**Comptabilité/Site Web > Configuration > Fournisseurs de paiement**, ouvrez
**NITA** et renseignez :

| Champ | Description |
|---|---|
| URL de l'API NITA | URL de base de l'environnement NITA ciblé (sandbox ou production) |
| Login | identifiant partenaire NITA |
| Clé API | clé API partenaire |
| Mot de passe | mot de passe partenaire |
| Secret HMAC | secret utilisé pour signer/vérifier le jeton de retour navigateur (plus exigé pour le callback) |

Puis :

- Vérifiez que la devise de la société/du site est bien **XOF** — le
  provider se déclare indisponible pour toute autre devise
  (`_get_supported_currencies`), par défense en profondeur côté module.
- Passez l'**État** de « Désactivé » à **Test** ou **Activé** selon
  l'environnement visé (le provider est livré désactivé par défaut).

## Note sécurité

- Les 4 champs d'identifiants (login, clé API, mot de passe, secret HMAC)
  sont `groups='base.group_system'` : réservés aux administrateurs système,
  jamais réaffichés en clair aux autres profils.
- Le callback NITA (`/payment/nita/webhook`, **GET non signé** `?status=1&transaction_id=<codeAchat>`
  en production, POST JSON accepté aussi) n'est qu'un **déclencheur** : ni le
  `status` reçu ni une signature ne sont utilisés. Le module retrouve la
  transaction par `codeAchat`, relit le **statut réel** via `checkAchatStatus`
  puis confirme/annule. Code inconnu ou transaction déjà finale : aucun appel
  API. Une relecture par `codeAchat` au plus toutes les 15 s (table
  `nita.callback.nonce`). Réponse toujours HTTP 200 `{"result": ...}`
  (`paid`/`pending`/`failed`/`ignored`/`throttled`/`unavailable`) ; en cas
  d'échec le cron de réconciliation rattrape.
- **Réconciliation du montant** : si le montant engagé auprès de NITA ne correspond
  plus à la transaction (commande modifiée entre-temps), la transaction
  n'est **jamais** validée automatiquement — elle reste en attente de
  vérification manuelle.
- Le module **ne paie jamais via l'API** : seuls `createAchat`,
  `check_achat_status` (et `annuler_achat` si besoin) sont appelés ; aucun
  appel ne débite directement.

## Fonctionnement (redirect + callback)

1. Au checkout, le client choisit NITA et saisit son **numéro MyNITA**.
2. Odoo crée la transaction et appelle `createAchat` (SDK) avec le montant
   en XOF, le numéro MyNITA, et l'URL de callback du module ; il reçoit
   `codeAchat` + `urlPaiement`, puis redirige le client vers `urlPaiement`.
3. Le client paie sur la page NITA.
4. NITA notifie `/payment/nita/webhook` (GET non signé) → le module relit le
   statut réel (`checkAchatStatus`) → la transaction passe `done` (ou
   `cancel`/`error` selon le statut NITA). Le cron rattrape un callback perdu.
5. Le client est ramené sur la page de confirmation Odoo
   (`/payment/nita/return` → `/payment/status`).

## Limites (v1)

**Dans ce v1 :**
- Odoo **17.0** uniquement.
- Devise **XOF** uniquement.
- Flux de paiement **par redirection** uniquement (page NITA hébergée).
- E-commerce (`website_sale`) et paiement de facture au portail (même
  provider).

**Hors v1 (non couvert, suivis séparés) :**
- Portage vers les branches Odoo **16.0** / **18.0**.
- **Odoo Online (SaaS)** / Odoo Apps Store.
- **Remboursements** via l'API.
- **Tokenisation** / paiement enregistré (S2S).
- Autres devises que le XOF.

## Packaging — zip installable

```bash
bash bin/build.sh
```

Produit `payment_nita-17.0.zip` à la racine du repo : le dossier
`payment_nita/` seul (élagué de `tests/`, `e2e/`, `.git`, `.superpowers`,
`__pycache__`). Ce zip s'installe via **Apps > Mettre à jour la liste des
Apps** (ou en le décompressant directement dans `extra-addons`). Le script
est robuste au répertoire d'appel (chemins relatifs à son propre
emplacement) et ne requiert pas l'utilitaire `zip` (repli automatique sur
`python`/`python3` si absent).

## Pour aller plus loin

- Spec de conception complète :
  `Nita_developer_portal/docs/superpowers/specs/2026-10-01-nita-odoo-plugin-design.md`
- QA manuelle détaillée (checkout réel, créneaux à vérifier à la main) :
  `docs/QA-manuelle.md`
- Rapport E2E (install réelle, callback signé, limites constatées) :
  `.superpowers/sdd/odoo/e2e-report.md`
