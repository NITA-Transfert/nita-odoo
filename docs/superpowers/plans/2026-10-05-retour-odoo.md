# Retour navigateur signé — Plugin Odoo — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal :** Le plugin Odoo `payment_nita` transmet son URL de retour à la création de l'achat, et son contrôleur `/payment/nita/return` vérifie le jeton signé, re-vérifie le statut réel via `checkAchatStatus`, confirme la commande, puis renvoie le client vers l'écran de statut Odoo.

**Architecture :** Trois couches qui se renforcent (callback S2S = source de vérité ; retour navigateur + re-check synchrone = confirmation immédiate ; cron = filet). Ce plan ajoute la 2ᵉ. On réutilise la couche de décision existante (`reconcile_action`) et on factorise la réconciliation « live » (déjà dans le cron) en une méthode partagée appelée AUSSI par le contrôleur de retour. Le jeton ne vaut jamais preuve : on re-interroge toujours l'API.

**Tech Stack :** Odoo 17 (payment framework), Python 3, SDK pip `nita_sdk`, pytest (lib pure), E2E Docker (contrôleur/modèle).

**Spec :** `C:\Users\NGM929\Documents\apps\Nita_developer_portal\docs\superpowers\specs\2026-10-02-url-retour-jeton-signe-design.md` (D5). Contrat repris inline ci-dessous.

## Global Constraints

- **Le plugin ne paie JAMAIS via l'API** — uniquement create / checkAchatStatus / mise à jour locale.
- **Le jeton seul n'est jamais une preuve de paiement** : après vérif de signature, on re-vérifie TOUJOURS le statut réel via `checkAchatStatus` (D3).
- **Signature du jeton** : `sig = hex(HMAC-SHA256(secret, codeAchat + "\n" + requestId + "\n" + ts))`, hex minuscule, comparaison à temps constant ; `secret` = `provider.nita_hmac_secret` (= le `hmac_secret` que le partenaire configure, en Test = le secret partagé sandbox). Même famille que les callbacks.
- **Fraîcheur** : rejeter un `ts` plus vieux que 15 min (900 s) — anti-rejeu léger.
- **Rétrocompatible / non bloquant** : signature invalide/périmée ou params manquants → PAS de confirmation, mais on redirige quand même vers `/payment/status` (le callback + le cron restent la vérité ; ne jamais planter le navigateur).
- **Idempotent** : une transaction déjà `done` n'est jamais retouchée.
- **Dépendance SDK** : l'envoi de `urlRetour` suppose un `nita_sdk` qui porte le champ (fait : NITA-SDK PR #23). La version PyPI installée est périmée → pour le test live, `pip install -e <nita-sdks>/sdks/python` dans le conteneur. Avec un SDK périmé, `url_retour` est silencieusement ignoré (pydantic `extra='ignore'`) → changement **forward-compatible**, pas de casse.
- Suivre le style du dépôt : lib pure testée en pytest (`tests/`) ; contrôleur/modèle vérifiés via `e2e/` + `docs/QA-manuelle.md`.

## Review Focus

- **Signature forgée / absente** → aucune confirmation, simple redirection (jamais confiance au jeton). Couvert Task 2 (verifier) + Task 3 (contrôleur).
- **`ts` périmé (rejeu)** → rejeté. Couvert Task 2.
- **Params de query manquants/partiels** (`codeAchat`/`requestId`/`ts`/`sig`) → redirection gracieuse, pas d'exception. Couvert Task 3.
- **Transaction déjà `done`** → idempotent, pas de double-confirmation. Couvert Task 3 (`_nita_reconcile_live` garde `state == 'done'`).
- **`checkAchatStatus` en erreur réseau au retour** → log + redirection ; le callback/cron rattrapent. Couvert Task 3 (try/except au call-site).

---

### Task 1 : Transmettre `urlRetour` à la création de l'achat

**Files :**
- Modify : `payment_nita/lib/mapping.py` (`build_achat_args`)
- Modify : `payment_nita/models/payment_transaction.py` (`_get_specific_rendering_values`, appel à `build_achat_args`)
- Test : `tests/test_mapping.py`

**Interfaces :**
- Produces : `build_achat_args(..., return_url='')` → dict avec clé `'url_retour'`.

- [ ] **Step 1 : Test (échec attendu)**

Dans `tests/test_mapping.py`, ajouter :
```python
def test_build_achat_args_url_retour():
    a = build_achat_args(**_base(), return_url='https://shop/odoo/return')
    assert a['url_retour'] == 'https://shop/odoo/return'

def test_build_achat_args_url_retour_absent_par_defaut():
    a = build_achat_args(**_base())
    assert a['url_retour'] == ''
```

- [ ] **Step 2 : Lancer → échec** — `cd <repo> && python -m pytest tests/test_mapping.py -q` (FAIL : `url_retour` absent / TypeError sur `return_url`).

- [ ] **Step 3 : Implémenter**

Dans `lib/mapping.py`, `build_achat_args` : ajouter `return_url=''` comme dernier paramètre keyword-only, et ajouter au dict retourné (juste après `url_callback`) :
```python
        'url_retour': str(return_url or ''),
```
Signature : `def build_achat_args(*, reference, total, currency, items, callback_url, phone, ip='', return_url=''):`

Dans `models/payment_transaction.py`, `_get_specific_rendering_values`, l'appel `build_achat_args(...)` : ajouter l'argument
```python
                return_url=self.provider_id.get_base_url() + '/payment/nita/return',
```
(juste après `callback_url=callback_url,` / `phone=self.nita_phone,` — même bloc).

- [ ] **Step 4 : Lancer → vert** — `python -m pytest tests/test_mapping.py -q`.

- [ ] **Step 5 : Commit**

```bash
git add payment_nita/lib/mapping.py payment_nita/models/payment_transaction.py tests/test_mapping.py
git commit -m "feat(odoo): transmettre urlRetour (endpoint de retour) a la creation de l'achat"
```

---

### Task 2 : Vérificateur de jeton de retour (lib pure, TDD)

**Files :**
- Create : `payment_nita/lib/return_token.py`
- Test : `tests/test_return_token.py`

**Interfaces :**
- Produces : `verify_return_token(secret, code_achat, request_id, ts, sig, *, max_age_s=900, now=None) -> bool`.

- [ ] **Step 1 : Tests (échec attendu)**

`tests/test_return_token.py` :
```python
import hmac, hashlib
from payment_nita.lib.return_token import verify_return_token

SECRET = "sandbox_test_signing_secret"

def _sig(code, rid, ts, secret=SECRET):
    msg = f"{code}\n{rid}\n{ts}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def test_valide():
    ts = "1000000000"
    sig = _sig("ACH1", "REQ1", ts)
    assert verify_return_token(SECRET, "ACH1", "REQ1", ts, sig, now=lambda: 1000000100) is True

def test_signature_fausse():
    assert verify_return_token(SECRET, "ACH1", "REQ1", "1000000000", "deadbeef", now=lambda: 1000000100) is False

def test_ts_perime():
    ts = "1000000000"
    sig = _sig("ACH1", "REQ1", ts)
    # 1000 s plus tard > 900 s de tolérance
    assert verify_return_token(SECRET, "ACH1", "REQ1", ts, sig, now=lambda: 1000001000) is False

def test_code_falsifie():
    ts = "1000000000"
    sig = _sig("ACH1", "REQ1", ts)
    assert verify_return_token(SECRET, "AUTRE", "REQ1", ts, sig, now=lambda: 1000000100) is False

def test_request_id_falsifie():
    ts = "1000000000"
    sig = _sig("ACH1", "REQ1", ts)
    assert verify_return_token(SECRET, "ACH1", "AUTRE", ts, sig, now=lambda: 1000000100) is False

def test_secret_ou_sig_manquant():
    assert verify_return_token("", "ACH1", "REQ1", "1000000000", "x", now=lambda: 1000000100) is False
    assert verify_return_token(SECRET, "ACH1", "REQ1", "1000000000", "", now=lambda: 1000000100) is False

def test_ts_non_numerique():
    assert verify_return_token(SECRET, "ACH1", "REQ1", "pasunnombre", "x", now=lambda: 1000000100) is False
```

- [ ] **Step 2 : Lancer → échec** — `python -m pytest tests/test_return_token.py -q` (module absent).

- [ ] **Step 3 : Implémenter**

`payment_nita/lib/return_token.py` :
```python
import hashlib
import hmac
import time


def verify_return_token(secret, code_achat, request_id, ts, sig, *, max_age_s=900, now=None):
    """Vrai si `sig` est un HMAC-SHA256 valide de `code_achat + "\\n" + request_id + "\\n" + ts`
    avec `secret`, ET que `ts` (epoch s) n'est pas plus vieux que `max_age_s`.

    Même famille de signature que les callbacks NITA. Comparaison à temps constant.
    Le jeton prouve l'authenticité de la redirection ; il ne prouve PAS le paiement
    (l'appelant re-vérifie via checkAchatStatus). `ts` est utilisé BRUT dans le message
    (tel que signé par NITA), et parsé séparément pour la fraîcheur."""
    if not secret or not sig:
        return False
    try:
        ts_i = int(ts)
    except (TypeError, ValueError):
        return False
    current = now() if now is not None else time.time()
    if abs(current - ts_i) > max_age_s:
        return False
    msg = f"{code_achat}\n{request_id}\n{ts}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(sig))
```

- [ ] **Step 4 : Lancer → vert** — `python -m pytest tests/test_return_token.py -q`.

- [ ] **Step 5 : Commit**

```bash
git add payment_nita/lib/return_token.py tests/test_return_token.py
git commit -m "feat(odoo): verificateur de jeton de retour signe (HMAC + fraicheur), lib pure"
```

---

### Task 3 : Contrôleur de retour (vérif + re-check live + redirection) + factorisation de la réconciliation

**Files :**
- Modify : `payment_nita/models/payment_transaction.py` (factoriser `_nita_reconcile_live`, appelé par le cron)
- Modify : `payment_nita/controllers/main.py` (`nita_return`)
- Modify : `docs/QA-manuelle.md` (scénario de vérification du retour)

**Interfaces :**
- Consumes : `verify_return_token` (Task 2), `urlRetour` envoyé (Task 1), `_nita_status` / `reconcile_action` / `_nita_amount_matches` (existants).
- Produces : `PaymentTransaction._nita_reconcile_live()` (per-record).

- [ ] **Step 1 : Factoriser la réconciliation « live » (per-record)**

Dans `models/payment_transaction.py`, ajouter une méthode (au-dessus de `_nita_cron_reconcile_pending`) :
```python
    def _nita_reconcile_live(self):
        """Re-interroge le STATUT RÉEL côté NITA (checkAchatStatus) et confirme/annule/échoue
        en conséquence. Partagée par le cron de réconciliation ET le contrôleur de retour.
        Idempotente ; le plugin ne paie jamais (lecture du statut + MAJ locale). Lève en cas
        d'erreur réseau (l'appelant décide quoi en faire)."""
        self.ensure_one()
        if self.provider_code != 'nita':
            return
        if self.state == 'done':
            return  # idempotent
        status = self._nita_status(self.nita_request_id)
        action = reconcile_action(status, self._nita_amount_matches({}))
        if action == 'done':
            self._set_done()
            try:
                self._finalize_post_processing()
            except Exception:
                _logger.exception("NITA: finalisation de %s a échoué (retentée par Odoo)", self.reference)
        elif action == 'cancel':
            self._set_canceled()
        elif action == 'error':
            self._set_error(_("Paiement NITA non abouti."))
        # 'review' / 'none' -> laisser en attente
```

Remplacer le corps de la boucle de `_nita_cron_reconcile_pending` par un appel à cette méthode (conserver la capture d'erreur par-tx) :
```python
        for tx in txs:
            try:
                tx._nita_reconcile_live()
            except Exception:
                _logger.exception("NITA cron: reconcile live indisponible pour %s", tx.reference)
                continue
        return True
```
(La recherche des `txs` en attente reste inchangée.)

- [ ] **Step 2 : Enrichir le contrôleur de retour**

Dans `controllers/main.py`, remplacer le corps du stub `nita_return` par :
```python
    @http.route('/payment/nita/return', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def nita_return(self, **kwargs):
        """Retour navigateur signé après la page de paiement NITA. On vérifie la signature
        (authenticité + fraîcheur) PUIS on re-vérifie le statut réel via checkAchatStatus
        (le jeton seul ne vaut jamais preuve de paiement), on confirme/annule, et on renvoie
        le client vers l'écran de statut Odoo. Le callback reste la source de vérité ; ce
        retour n'est qu'une confirmation immédiate pour l'UX. Jamais de paiement via l'API."""
        code = kwargs.get('codeAchat')
        rid = kwargs.get('requestId')
        ts = kwargs.get('ts')
        sig = kwargs.get('sig')
        provider = request.env['payment.provider'].sudo().search([('code', '=', 'nita')], limit=1)
        if provider and provider.nita_hmac_secret and code and rid and ts and sig:
            from ..lib.return_token import verify_return_token
            if verify_return_token(provider.nita_hmac_secret, code, rid, ts, sig):
                tx = request.env['payment.transaction'].sudo().search(
                    [('nita_code_achat', '=', code), ('provider_code', '=', 'nita')], limit=1)
                if tx:
                    try:
                        tx._nita_reconcile_live()
                    except Exception:
                        _logger.exception("NITA return: reconcile live a échoué pour %s", code)
            else:
                _logger.warning("NITA return: jeton invalide/périmé (codeAchat=%s)", code)
        return request.redirect('/payment/status')
```

- [ ] **Step 3 : Vérifier que la lib pure reste verte + le module s'importe**

```bash
cd <repo> && python -m pytest tests/ -q
python -c "import ast; ast.parse(open('payment_nita/controllers/main.py').read()); ast.parse(open('payment_nita/models/payment_transaction.py').read()); print('syntaxe OK')"
```
(Les tests pytest couvrent la lib pure ; le contrôleur/modèle Odoo se vérifient en E2E — Step 5.)

- [ ] **Step 4 : Documenter la vérification manuelle**

Dans `docs/QA-manuelle.md`, ajouter une section « Retour navigateur après paiement » :
- Installer le SDK avec `urlRetour` : `pip install -e <chemin>/nita-sdks/sdks/python` dans le conteneur Odoo (sinon le champ est ignoré, le retour ne se déclenche pas).
- Payer un achat en sandbox ; vérifier que le navigateur est redirigé de la page NITA vers `/payment/nita/return?...&sig=...` puis vers `/payment/status` ; la commande passe `done` immédiatement (sans attendre le cron).
- Falsifier `sig` dans l'URL de retour → la commande n'est PAS confirmée par ce chemin (seulement par callback/cron) ; le navigateur atterrit quand même sur `/payment/status`.

- [ ] **Step 5 : Vérification E2E (si l'environnement Docker est disponible)**

Lancer le kit `e2e/` (`bash e2e/run.sh` ou équivalent documenté) OU la QA manuelle ci-dessus contre la sandbox :8190 (recompilée pour PR #62). Noter le résultat dans le rapport. Si Docker/sandbox indisponible dans cet environnement, marquer la vérification live comme à faire par l'utilisateur et s'appuyer sur la revue de code + les tests lib.

- [ ] **Step 6 : Commit**

```bash
git add payment_nita/models/payment_transaction.py payment_nita/controllers/main.py docs/QA-manuelle.md
git commit -m "feat(odoo): retour navigateur signe (verif jeton + re-check live + redirection), reconcile factorise"
```
