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
2. **Callback NITA non signe** : GET `/payment/nita/webhook?status=1&transaction_id=<codeAchat>`
   (ou POST JSON `{"status","transaction_id"}`), sans signature, toujours
   reponse 200 `{"result":"received"}`. Le callback n'est qu'un declencheur : le
   statut reel est relu via checkAchatStatus (jamais cru sur `status`).
   Code inconnu -> `ignored` au journal ; rappel dans les 15 s -> `throttled` au journal ; statut
   reel injoignable (E2E sans sandbox) -> transaction jamais `done`.
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

## 2. `payment.method` NITA — corrige

**Mise a jour (2026-10-01) : corrige.** `payment_nita/data/payment_method_data.xml`
cree desormais un `payment.method` (`code='nita'`, icone minimale
`static/img/nita.png`), lie au provider via `payment_method_ids` dans
`data/payment_provider_data.xml` — sur le modele exact de
`payment_demo`/`payment_custom` (verifie contre le source officiel
`addons/payment/models/payment_method.py::_get_compatible_payment_methods`,
qui filtre sur `provider_ids` + `is_primary=True`).

Reverifie dans le conteneur apres correctif :
- `odoo -u payment_nita -d test --stop-after-init` -> 0 erreur.
- `provider.payment_method_ids` -> non vide (`['nita']`).
- `env['payment.method']._get_compatible_payment_methods(provider_ids=[provider.id], ...)`
  renvoie bien la methode NITA.
- `e2e/run.sh` rejoue : toujours 6/6 PASS (ce correctif ne touche pas le
  chemin callback).

Le checkout n'est donc plus bloque par ce manque.

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
`nita_phone='0022700000001'`, le wallet de test de la sandbox) et appelle
`tx._get_specific_rendering_values({})` directement (contourne l'IHM —
le point 2 ci-dessus l'empeche de toute facon pour l'instant). Verifiez dans
`e2e/.out/live_achat.log` que `api_url` est bien une URL de paiement NITA, et
que `nita_code_achat` est renseigne. **Ne validez jamais le paiement sur la
page NITA** : l'objectif est seulement de verifier que `createAchat`
reussit et renvoie un lien ; laissez la transaction en `draft`/`pending`.

## 4. Checkout bout-en-bout dans l'IHM — a faire par vous

Le `payment.method` est desormais cable (point 2) ; reste a verifier a la
main dans un vrai navigateur (l'E2E automatise ne clique jamais l'IHM) :

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
   le statut reel NITA (relu a la reception du callback ou par le cron) est la
   seule source de verite pour l'etat de la transaction, jamais le retour
   navigateur ni le contenu du callback.

## 5. Retour navigateur apres paiement — a faire par vous

Depuis l'ajout de `urlRetour` (envoye a `createAchat`) et du controleur
`/payment/nita/return` (verification du jeton signe + re-check live via
`checkAchatStatus`), le navigateur peut confirmer le paiement immediatement
au retour, sans attendre le cron de reconciliation. A verifier a la main
(hors de portee de l'E2E Docker, qui ne clique jamais l'IHM) :

1. **Installer le SDK avec `urlRetour`** : `pip install -e
   <chemin>/nita-sdks/sdks/python` dans le conteneur Odoo. Sans cette
   version a jour du SDK, le champ `urlRetour` est ignore par `AchatEnLigneModel`
   et le retour signe ne se declenche jamais (NITA ne redirige alors nulle
   part de particulier apres paiement).
2. **Payer un achat en sandbox** et verifier que le navigateur est bien
   redirige de la page de paiement NITA vers
   `/payment/nita/return?codeAchat=...&requestId=...&ts=...&sig=...`, puis
   immediatement vers `/payment/status`. La commande doit passer a `done`
   des ce retour (visible dans l'IHM ou via `env['payment.transaction']...state`),
   **sans attendre** le prochain passage du cron `_nita_cron_reconcile_pending`.
3. **Falsifier `sig`** dans l'URL de retour (changer un caractere) et
   rejouer la requete : la commande ne doit **pas** etre confirmee par ce
   chemin (`verify_return_token` rejette, un warning est journalise) — seul
   le callback ou le cron peuvent encore la faire passer a `done`. Le
   navigateur doit malgre tout atterrir sur `/payment/status` (jamais
   d'erreur visible pour l'utilisateur sur un jeton invalide/perime).

## 6. Dependance SDK — rappel

`e2e/Dockerfile` installe `nita-transfert-sdk==0.1.0b2` depuis PyPI (premiere
version publiee avec `NitaClient` et `url_retour`). Aucun correctif local du SDK
n'est necessaire : le webhook n'importe plus `nita_sdk.client.callback`.
