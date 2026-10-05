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
