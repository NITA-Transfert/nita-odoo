# QA manuelle — `payment_nita`

Ce document couvre deux choses : comment lancer l'E2E automatise (`e2e/run.sh`),
et ce qui reste a verifier a la main (hors de portee de l'E2E, ou qui demande
des identifiants que vous seul possedez).

## 1. Lancer l'E2E automatise

Prerequis : Docker Desktop.

```bash
bash e2e/run.sh
```

Le script est idempotent (rejouable sans nettoyage prealable) et valide :

1. **Install propre du module dans Odoo 17** (`odoo:17.0` + `postgres:16`,
   module monte dans `/mnt/extra-addons`, `nita-transfert-sdk` installe dans
   le conteneur). C'est le check le plus important : il prouve que tous les
   modeles, vues, xpath, donnees et assets du module se chargent sans erreur
   dans un Odoo 17 reel.
2. **Callback v2 signe** : POST sur `/payment/nita/webhook` avec un corps JSON
   et les en-tetes `X-NT-TIMESTAMP`/`X-NT-NONCE`/`X-NT-SIGNATURE` calcules
   avec le secret HMAC du provider -> transaction passee a `done`. Puis :
   rejeu du meme nonce (refuse, 401, etat inchange), signature invalide
   (401), et montant incoherent entre l'achat NITA engage et la commande
   actuelle (callback accepte mais transaction JAMAIS validee automatiquement
   — reste `pending`, pour verification manuelle).
3. **`createAchat` live** (optionnel, voir section 3 ci-dessous) : nécessite
   un sandbox NITA joignable, gardé par variables d'environnement.

Les logs detailles de chaque etape sont ecrits dans `e2e/.out/` (ignore par
git) : `install.log`, `setup.log`, et `live_achat.log` si l'etape 3 est
executee.

Pour tout arreter et nettoyer les volumes a la fin : `TEARDOWN=1 bash e2e/run.sh`.

Pour inspecter l'instance a la main apres un run (`TEARDOWN` non positionne) :
Odoo tourne sur `http://localhost:8169` (ou le port de `$ODOO_HTTP_PORT`),
base `test`. Pas de mot de passe admin defini par ce script (l'E2E passe
uniquement par `odoo shell`/HTTP direct, jamais par l'IHM) — pour vous
connecter en admin, il faut d'abord en definir un (`odoo shell` ->
`env.ref('base.user_admin').write({'password': '...'})`) ou utiliser le
mode `--dev=reload` localement.

## 2. Point d'attention decouvert pendant l'E2E — a faire avant tout test de checkout reel

**Le provider `nita` n'a aucun `payment.method` associe.** En Odoo 17, un
provider de paiement n'apparait comme option de paiement au checkout QUE s'il
a au moins un `payment.method` compatible lie via `payment_method_ids`
(`payment.method._get_compatible_payment_methods`, verifie contre le source
officiel `addons/payment/models/payment_method.py`). Tous les providers de
premiere partie (`payment_demo`, `payment_custom`, etc.) expedient :
- un `data/payment_method_data.xml` creant un `payment.method` (`code='nita'`
  par exemple),
- le wiring `payment_method_ids` sur l'enregistrement provider dans
  `data/payment_provider_data.xml`.

`payment_nita` n'a ni l'un ni l'autre aujourd'hui. **Consequence concrete :
si vous testez le checkout a la main maintenant, NITA n'apparaitra dans
aucune liste de moyens de paiement**, meme avec le provider a l'etat
`enabled`/`test` et une devise XOF correcte. Ce n'est pas un bug de l'E2E :
reproduit et trace precisement (voir `.superpowers/sdd/odoo/e2e-report.md`,
section « Finding 2 »). A corriger (hors perimetre de cette tache 10) avant
tout essai de checkout reel ou toute demo.

## 3. `createAchat` live contre un sandbox NITA reel — a faire par vous

L'E2E ne declenche jamais de paiement reel et ne peut pas, sans vos
identifiants, verifier que `_get_specific_rendering_values` obtient bien une
`urlPaiement` valide d'un vrai sandbox NITA. Pour l'executer :

```bash
export NITA_E2E_SANDBOX_URL="https://<votre-sandbox>"
export NITA_E2E_SANDBOX_LOGIN="<login partenaire>"
export NITA_E2E_SANDBOX_API_KEY="<cle API>"
export NITA_E2E_SANDBOX_PASSWORD="<mot de passe>"
export NITA_E2E_SANDBOX_HMAC_SECRET="<secret HMAC>"
bash e2e/run.sh
```

Avec ces 5 variables definies, le script (etape 9) reconfigure le provider
avec vos vrais identifiants, cree une transaction de test (1000 XOF,
`nita_phone='0022700000001'`, cf. memory "wallet de test sandbox") et appelle
`tx._get_specific_rendering_values({})` directement (contourne l'IHM —
le point 2 ci-dessus l'empeche de toute facon pour l'instant). Verifiez dans
`e2e/.out/live_achat.log` que `api_url` est bien une URL de paiement NITA, et
que `nita_code_achat` est renseigne. **Ne validez jamais le paiement sur la
page NITA** : l'objectif est seulement de verifier que `createAchat`
reussit et renvoie un lien ; laissez la transaction en `draft`/`pending`.

## 4. Checkout bout-en-bout dans l'IHM — a faire par vous, apres avoir corrige le point 2

Une fois le `payment.method` cable (point 2) :

1. Installer `website_sale` + `payment_nita`, activer le provider NITA
   (devise XOF, secret HMAC, `state='test'` ou `enabled`).
2. Creer un produit et une commande en XOF.
3. Passer au paiement : verifier que NITA apparait, que le champ **Numero
   MyNITA** s'affiche (template `payment_nita.inline_form`), qu'il est
   pre-rempli si le partenaire a un telephone, et qu'il est bien transmis a
   `payment.transaction.nita_phone` apres soumission (point R1 du rapport
   Task 8/9 — verifie en E2E au niveau controller/ORM, jamais clique dans un
   vrai navigateur).
4. Verifier la redirection vers `urlPaiement` (template
   `payment_nita.redirect_form`).
5. **Ne payez jamais reellement.** Revenez en arriere ou laissez expirer :
   le callback (section 1) est la seule source de verite pour l'etat de la
   transaction, jamais le retour navigateur.

## 5. Dependance SDK — rappel

`e2e/Dockerfile` installe `nita-transfert-sdk==0.1.0b1` (PyPI) **puis**
ecrase `nita_sdk/client/callback.py` et `nita_sdk/client/__init__.py` par la
version a jour du monorepo `nita-sdks` (voir `e2e/sdk-patch/README.md`) : au
2026-10-01, le paquet PyPI publie ne contient pas encore
`verify_callback`/`NitaCallbackError`. **Ce correctif est uniquement dans ce
kit E2E, pas dans `payment_nita`.** Pour un deploiement reel aujourd'hui
(hors de ce kit Docker), le webhook `/payment/nita/webhook` plantera a
l'import tant que `nita-transfert-sdk` n'est pas republie sur PyPI avec ce
module inclus — a signaler/suivre separement (depot `nita-sdks`).
