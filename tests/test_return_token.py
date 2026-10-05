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
