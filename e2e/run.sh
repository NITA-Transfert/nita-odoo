#!/usr/bin/env bash
# E2E payment_nita : installe le module dans un vrai Odoo 17, puis valide le
# callback v2 signe (sans dependre d'un sandbox NITA vivant).
#
# Objectifs couverts (voir plan Task 10) :
#   1. Install propre du module payment_nita dans Odoo 17 (LE check cle).
#   2. Callback signe -> transaction `done` ; rejeu refuse ; signature
#      invalide -> 401 ; montant incoherent -> jamais valide automatiquement.
#   3. createAchat live (sandbox NITA reel) : OPTIONNEL, gardee par variables
#      d'env (voir section en bas). Sans elles : documentee, non executee,
#      non bloquante.
#
# Usage :
#   bash e2e/run.sh
#   TEARDOWN=1 bash e2e/run.sh      # arrete et supprime la stack a la fin
#
# Windows/Git Bash : ce script ne passe JAMAIS de chemin absolu "/..." en
# argument direct a `docker` (uniquement des noms de service/flags), donc le
# piege MSYS_NO_PATHCONV ne s'applique pas ici. Si vous ajoutez un appel
# `docker exec ... /chemin/absolu`, prefixez-le par MSYS_NO_PATHCONV=1.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="docker compose"
DB_NAME="test"
HTTP_PORT="${ODOO_HTTP_PORT:-8169}"
BASE_URL="http://localhost:${HTTP_PORT}"
OUT_DIR="$SCRIPT_DIR/.out"
mkdir -p "$OUT_DIR"

PASS=0
FAIL=0
declare -a RESULTS=()

pass() { RESULTS+=("PASS - $1"); PASS=$((PASS+1)); echo "[PASS] $1"; }
fail() { RESULTS+=("FAIL - $1"); FAIL=$((FAIL+1)); echo "[FAIL] $1"; }
info() { echo "[....] $1"; }

# --- Helper : calcule timestamp/nonce/signature HMAC pour un corps JSON, et
#     imprime 4 lignes (ts, nonce, sig, body) a capturer via command
#     substitution. NE JAMAIS `source` du JSON brut (les guillemets internes
#     seraient avales par le shell) : toujours capturer via $() + sed -n Np,
#     comme fait ci-dessous.
sign_callback() {
    local status="$1" transaction_id="$2" secret="$3"
    python3 - "$status" "$transaction_id" "$secret" <<'EOF'
import hmac, hashlib, time, uuid, json, sys
status, transaction_id, secret = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({"status": status, "transaction_id": transaction_id}, separators=(",", ":"))
ts = str(int(time.time()))
nonce = uuid.uuid4().hex
msg = (ts + "\n" + nonce + "\n" + body).encode("utf-8")
sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
print(ts); print(nonce); print(sig); print(body)
EOF
}

# POST un callback signe (ou volontairement mal signe) et renvoie le code HTTP.
post_callback() {
    local ts="$1" nonce="$2" sig="$3" body="$4"
    curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/payment/nita/webhook" \
        -H "Content-Type: application/json" \
        -H "X-NT-TIMESTAMP: $ts" -H "X-NT-NONCE: $nonce" -H "X-NT-SIGNATURE: $sig" \
        --data-raw "$body"
}

echo "=== 1. Stack Docker (build + up) ==="
$COMPOSE build || { echo "docker compose build a echoue"; exit 1; }
$COMPOSE up -d || { echo "docker compose up a echoue"; exit 1; }

info "attente Postgres..."
for i in $(seq 1 30); do
    $COMPOSE exec -T db pg_isready -U odoo >/dev/null 2>&1 && break
    sleep 2
done

echo
echo "=== 2. Objectif 1 : install propre de payment_nita dans Odoo 17 ==="
info "purge de la base '${DB_NAME}' (install a froid, idempotent)"
$COMPOSE exec -T db dropdb -U odoo --if-exists "$DB_NAME" >/dev/null 2>&1

INSTALL_LOG="$OUT_DIR/install.log"
$COMPOSE exec -T odoo odoo -i payment_nita -d "$DB_NAME" \
    --db_host=db --db_user=odoo --db_password=odoo \
    --stop-after-init --without-demo=all > "$INSTALL_LOG" 2>&1
INSTALL_RC=$?

# Un vrai echec Odoo : "Traceback (most recent call last):" (python) ou une
# ligne de log au niveau ERROR/CRITICAL emise par le logger odoo (format
# horodate "... ERROR <db> <logger>: ..."). On ignore sciemment les notes
# docutils ("<string>:NN: (ERROR/3) ...") emises par des docstrings de modules
# CORE Odoo sans rapport avec payment_nita (bruit connu, non bloquant).
if [ $INSTALL_RC -ne 0 ] || grep -qE "Traceback \(most recent call last\):" "$INSTALL_LOG" \
   || grep -qE "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+ [0-9]+ (ERROR|CRITICAL) " "$INSTALL_LOG"; then
    fail "Objectif 1 : install payment_nita (voir $INSTALL_LOG)"
    echo "----- extrait du log d'install -----"
    grep -nE "Traceback|ERROR|CRITICAL" "$INSTALL_LOG" | head -40
    echo "-------------------------------------"
else
    LOADED_LINE=$(grep -E "Module payment_nita loaded" "$INSTALL_LOG" || true)
    if [ -n "$LOADED_LINE" ]; then
        pass "Objectif 1 : install payment_nita ($LOADED_LINE)"
    else
        fail "Objectif 1 : 'Module payment_nita loaded' absent du log (voir $INSTALL_LOG)"
    fi
fi

echo
echo "=== 3. Demarrage du serveur Odoo (pour les tests HTTP du callback) ==="
$COMPOSE exec -T odoo sh -c "pkill -9 -f '/usr/bin/odoo -d ${DB_NAME}'" >/dev/null 2>&1
sleep 1
MSYS_NO_PATHCONV=1 $COMPOSE exec -d odoo odoo -d "$DB_NAME" \
    --db_host=db --db_user=odoo --db_password=odoo \
    --http-port=8069 --without-demo=all \
    --logfile=/var/lib/odoo/server.log --log-level=info

info "attente HTTP sur ${BASE_URL}..."
UP=0
for i in $(seq 1 30); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/web/login" 2>/dev/null)
    if [ "$CODE" = "200" ]; then UP=1; break; fi
    sleep 2
done
if [ "$UP" != "1" ]; then
    echo "Le serveur Odoo n'a pas repondu a temps sur ${BASE_URL}/web/login — abandon des tests callback."
    $COMPOSE exec -T odoo sh -c "tail -n 80 /var/lib/odoo/server.log" 2>&1
    echo
    echo "=== Resume ==="
    printf '%s\n' "${RESULTS[@]}"
    echo "PASS=$PASS FAIL=$FAIL"
    exit 1
fi

echo
echo "=== 4. Configuration provider NITA + transactions de test (odoo shell) ==="
SETUP_LOG="$OUT_DIR/setup.log"
$COMPOSE exec -T odoo odoo shell -d "$DB_NAME" --db_host=db --db_user=odoo --db_password=odoo --no-http > "$SETUP_LOG" 2>&1 <<'PYEOF'
xof = env['res.currency'].with_context(active_test=False).search([('name', '=', 'XOF')], limit=1)
xof.write({'active': True})

provider = env['payment.provider'].search([('code', '=', 'nita')], limit=1)
provider.write({
    'nita_base_url': 'http://sandbox.invalid',
    'nita_login': 'e2e-login',
    'nita_api_key': 'e2e-api-key',
    'nita_password': 'e2e-password',
    'nita_hmac_secret': 'testsecret',
    'state': 'test',
})

pm = env.ref('payment.payment_method_unknown')
partner = env.ref('base.main_partner')

# TX1 : montant engage == montant transaction -> callback valide doit faire 'done'.
env['payment.transaction'].search([('reference', '=', 'E2E-TX-DONE')]).unlink()
tx1 = env['payment.transaction'].create({
    'provider_id': provider.id, 'payment_method_id': pm.id,
    'reference': 'E2E-TX-DONE', 'amount': 15000, 'currency_id': xof.id,
    'partner_id': partner.id, 'nita_code_achat': 'E2E-CODE-DONE',
    'nita_montant_achat': 15000, 'nita_request_id': 'E2E-TX-DONE',
    'nita_phone': '0022790000000',
})

# TX2 : montant engage (15000) != montant courant de la commande (20000)
# -> callback 'paye' valide mais ne doit JAMAIS passer 'done' automatiquement.
env['payment.transaction'].search([('reference', '=', 'E2E-TX-MISMATCH')]).unlink()
tx2 = env['payment.transaction'].create({
    'provider_id': provider.id, 'payment_method_id': pm.id,
    'reference': 'E2E-TX-MISMATCH', 'amount': 20000, 'currency_id': xof.id,
    'partner_id': partner.id, 'nita_code_achat': 'E2E-CODE-MISMATCH',
    'nita_montant_achat': 15000, 'nita_request_id': 'E2E-TX-MISMATCH',
    'nita_phone': '0022790000000',
})

env.cr.commit()
print("SETUP_OK tx1=%s(%s) tx2=%s(%s)" % (tx1.id, tx1.state, tx2.id, tx2.state))
PYEOF

if grep -q "SETUP_OK" "$SETUP_LOG"; then
    pass "Setup : provider NITA + 2 transactions de test crees (voir $SETUP_LOG)"
else
    fail "Setup : echec de la configuration (voir $SETUP_LOG)"
    tail -n 60 "$SETUP_LOG"
    echo "Impossible de poursuivre les tests de callback."
    echo "=== Resume ==="
    printf '%s\n' "${RESULTS[@]}"
    echo "PASS=$PASS FAIL=$FAIL"
    exit 1
fi

read_tx_state() {
    local ref="$1"
    $COMPOSE exec -T odoo odoo shell -d "$DB_NAME" --db_host=db --db_user=odoo --db_password=odoo --no-http 2>/dev/null <<PYEOF
tx = env['payment.transaction'].search([('reference', '=', '$ref')])
print("STATE=" + (tx.state or ''))
PYEOF
}

echo
echo "=== 5. Objectif 2 : callback signe -> transaction 'done' ==="
OUT=$(sign_callback "1" "E2E-CODE-DONE" "testsecret")
TS=$(printf '%s\n' "$OUT" | sed -n '1p'); NONCE=$(printf '%s\n' "$OUT" | sed -n '2p')
SIG=$(printf '%s\n' "$OUT" | sed -n '3p'); BODY=$(printf '%s\n' "$OUT" | sed -n '4p')

CODE=$(post_callback "$TS" "$NONCE" "$SIG" "$BODY")
STATE=$(read_tx_state "E2E-TX-DONE" | grep "^STATE=" | cut -d= -f2)
if [ "$CODE" = "200" ] && [ "$STATE" = "done" ]; then
    pass "Callback signe valide -> HTTP $CODE, transaction state=$STATE"
else
    fail "Callback signe valide -> HTTP $CODE, transaction state=$STATE (attendu 200/done)"
fi

echo
echo "=== 6. Rejeu du meme nonce -> refuse (401), idempotent ==="
REPLAY_CODE=$(post_callback "$TS" "$NONCE" "$SIG" "$BODY")
STATE_AFTER_REPLAY=$(read_tx_state "E2E-TX-DONE" | grep "^STATE=" | cut -d= -f2)
if [ "$REPLAY_CODE" = "401" ] && [ "$STATE_AFTER_REPLAY" = "done" ]; then
    pass "Rejeu du nonce -> HTTP $REPLAY_CODE, etat inchange ($STATE_AFTER_REPLAY)"
else
    fail "Rejeu du nonce -> HTTP $REPLAY_CODE, etat=$STATE_AFTER_REPLAY (attendu 401/done)"
fi

echo
echo "=== 7. Signature invalide -> 401 ==="
BAD_SIG="${SIG:0:-4}dead"
BAD_CODE=$(post_callback "$TS" "deadbeefdeadbeefdeadbeefdeadbeef" "$BAD_SIG" "$BODY")
if [ "$BAD_CODE" = "401" ]; then
    pass "Signature invalide -> HTTP $BAD_CODE"
else
    fail "Signature invalide -> HTTP $BAD_CODE (attendu 401)"
fi

echo
echo "=== 8. Montant incoherent -> jamais valide automatiquement ==="
OUT2=$(sign_callback "1" "E2E-CODE-MISMATCH" "testsecret")
TS2=$(printf '%s\n' "$OUT2" | sed -n '1p'); NONCE2=$(printf '%s\n' "$OUT2" | sed -n '2p')
SIG2=$(printf '%s\n' "$OUT2" | sed -n '3p'); BODY2=$(printf '%s\n' "$OUT2" | sed -n '4p')
CODE2=$(post_callback "$TS2" "$NONCE2" "$SIG2" "$BODY2")
STATE2=$(read_tx_state "E2E-TX-MISMATCH" | grep "^STATE=" | cut -d= -f2)
if [ "$CODE2" = "200" ] && [ "$STATE2" != "done" ]; then
    pass "Montant incoherent -> HTTP $CODE2, transaction state=$STATE2 (pas 'done')"
else
    fail "Montant incoherent -> HTTP $CODE2, transaction state=$STATE2 (ne doit jamais etre 'done')"
fi

echo
echo "=== 9. Objectif 3 (optionnel) : createAchat live contre un sandbox NITA reel ==="
if [ -n "${NITA_E2E_SANDBOX_URL:-}" ] && [ -n "${NITA_E2E_SANDBOX_LOGIN:-}" ] \
   && [ -n "${NITA_E2E_SANDBOX_API_KEY:-}" ] && [ -n "${NITA_E2E_SANDBOX_PASSWORD:-}" ] \
   && [ -n "${NITA_E2E_SANDBOX_HMAC_SECRET:-}" ]; then
    info "Variables NITA_E2E_SANDBOX_* detectees : execution de createAchat contre $NITA_E2E_SANDBOX_URL"
    LIVE_LOG="$OUT_DIR/live_achat.log"
    $COMPOSE exec -T odoo odoo shell -d "$DB_NAME" --db_host=db --db_user=odoo --db_password=odoo --no-http \
        > "$LIVE_LOG" 2>&1 <<PYEOF
provider = env['payment.provider'].search([('code', '=', 'nita')], limit=1)
provider.write({
    'nita_base_url': '$NITA_E2E_SANDBOX_URL',
    'nita_login': '$NITA_E2E_SANDBOX_LOGIN',
    'nita_api_key': '$NITA_E2E_SANDBOX_API_KEY',
    'nita_password': '$NITA_E2E_SANDBOX_PASSWORD',
    'nita_hmac_secret': '$NITA_E2E_SANDBOX_HMAC_SECRET',
    'state': 'test',
})
xof = env['res.currency'].search([('name', '=', 'XOF')], limit=1)
pm = env.ref('payment.payment_method_unknown')
partner = env.ref('base.main_partner')
env['payment.transaction'].search([('reference', '=', 'E2E-TX-LIVE')]).unlink()
tx = env['payment.transaction'].create({
    'provider_id': provider.id, 'payment_method_id': pm.id,
    'reference': 'E2E-TX-LIVE', 'amount': 1000, 'currency_id': xof.id,
    'partner_id': partner.id, 'nita_phone': '0022700000001',
})
env.cr.commit()
try:
    values = tx._get_specific_rendering_values({})
    print("LIVE_OK api_url=%s code_achat=%s" % (values.get('api_url'), tx.nita_code_achat))
except Exception as e:
    print("LIVE_FAIL %r" % (e,))
PYEOF
    if grep -q "LIVE_OK" "$LIVE_LOG"; then
        pass "Objectif 3 : createAchat live (voir $LIVE_LOG)"
    else
        fail "Objectif 3 : createAchat live a echoue (voir $LIVE_LOG)"
    fi
else
    info "Objectif 3 ignore (pas de sandbox NITA vivant disponible dans cet environnement)."
    info "Pour l'executer : exporter NITA_E2E_SANDBOX_URL, NITA_E2E_SANDBOX_LOGIN,"
    info "NITA_E2E_SANDBOX_API_KEY, NITA_E2E_SANDBOX_PASSWORD, NITA_E2E_SANDBOX_HMAC_SECRET"
    info "puis relancer ce script. Voir docs/QA-manuelle.md."
fi

echo
echo "=== Resume ==="
printf '%s\n' "${RESULTS[@]}"
echo "PASS=$PASS FAIL=$FAIL"

if [ "${TEARDOWN:-0}" = "1" ]; then
    info "TEARDOWN=1 : arret et suppression de la stack"
    $COMPOSE down -v
fi

[ "$FAIL" -eq 0 ]
