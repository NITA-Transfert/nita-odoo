import json
import re

_CODE_RE = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
_MAX_BODY = 65536


def _clean(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if _CODE_RE.match(value) else None


def extract_code_achat(query_value, raw_body):
    """codeAchat d'un callback NITA, ou None.

    Le callback n'est qu'un declencheur non signe : seul l'identifiant compte.
    Source : parametre `transaction_id` (GET `?status=1&transaction_id=...` ou POST),
    sinon corps JSON `{"transaction_id": ...}`. Un parametre present mais invalide
    donne None (jamais de repli sur le corps). JSON invalide -> None. Format :
    1 a 100 caracteres [A-Za-z0-9_-] apres strip.
    """
    if isinstance(query_value, str) and query_value.strip():
        return _clean(query_value)
    if not raw_body or len(raw_body) > _MAX_BODY:
        return None
    try:
        data = json.loads(raw_body)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return _clean(data.get('transaction_id'))
