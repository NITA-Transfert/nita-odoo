"""Vérification d'un callback v2 signé envoyé par NITA au partenaire.

NITA poste un JSON avec les en-têtes X-NT-TIMESTAMP, X-NT-NONCE et
X-NT-SIGNATURE = hex(HMAC-SHA256(secret, timestamp + "\\n" + nonce + "\\n" + corps)).
La signature porte sur les octets BRUTS reçus : ne jamais re-sérialiser le JSON.

Anti-rejeu : sans `is_new_nonce`, un callback valide rejoué dans la fenêtre de
tolérance est accepté. En production, fournir `is_new_nonce` adossé à un stockage
partagé entre instances (base, Redis…) qui mémorise le nonce pendant `ttl` secondes.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import re
import time
from typing import Callable, Mapping, Optional, Sequence, Union

_TIMESTAMP = "x-nt-timestamp"
_NONCE = "x-nt-nonce"
_SIGNATURE = "x-nt-signature"


class NitaCallbackError(Exception):
    """Callback refusé : en-têtes, horodatage, signature, rejeu ou corps invalides."""


def _header(headers: Mapping[str, Union[str, Sequence[str]]], name: str) -> str:
    """Valeur d'un en-tête, nom insensible à la casse ; liste → premier élément."""
    for key, value in headers.items():
        if str(key).lower() == name:
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            return value if isinstance(value, str) else str(value)
    return ""


def verify_callback(
    raw_body: Union[bytes, str],
    headers: Mapping[str, Union[str, Sequence[str]]],
    secret: str,
    *,
    tolerance_seconds: int = 300,
    is_new_nonce: Optional[Callable[[str, int], bool]] = None,
    now: Optional[Callable[[], float]] = None,
) -> dict:
    """Vérifie un callback NITA et renvoie son corps JSON (`status`, `transaction_id`…).

    - `raw_body` : corps brut reçu (`str` encodé en UTF-8).
    - `is_new_nonce(nonce, ttl)` : renvoie vrai si le nonce n'a jamais été vu, et le
      mémorise `ttl` secondes (2 × tolérance). Appelé uniquement si la signature est valide.
    - `now` : horloge (epoch secondes), `time.time` par défaut.

    Lève `NitaCallbackError` si le callback est refusé.
    """
    if not secret:
        raise NitaCallbackError("Secret de signature manquant")
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else bytes(raw_body)

    timestamp = _header(headers, _TIMESTAMP)
    nonce = _header(headers, _NONCE)
    signature = _header(headers, _SIGNATURE)
    if not timestamp or not nonce or not signature:
        raise NitaCallbackError("En-tetes de signature manquants")

    if not re.fullmatch(r"-?[0-9]+", timestamp):
        raise NitaCallbackError("Horodatage hors tolerance")
    ts = int(timestamp)
    current = (now or time.time)()
    if abs(current - ts) > tolerance_seconds:
        raise NitaCallbackError("Horodatage hors tolerance")

    message = timestamp.encode("utf-8") + b"\n" + nonce.encode("utf-8") + b"\n" + body
    expected = _hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(expected.encode("ascii"), signature.encode("utf-8")):
        raise NitaCallbackError("Signature invalide")

    if is_new_nonce is not None and not is_new_nonce(nonce, 2 * tolerance_seconds):
        raise NitaCallbackError("Nonce deja utilise (rejeu)")

    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError:
        raise NitaCallbackError("Corps JSON invalide") from None
    if not isinstance(payload, dict):
        raise NitaCallbackError("Corps JSON invalide")
    return payload
