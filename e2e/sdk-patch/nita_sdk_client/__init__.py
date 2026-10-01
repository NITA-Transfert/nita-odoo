"""Couche mince ergonomique au-dessus du SDK Python généré.

Écrite à la main (protégée de la régénération via .openapi-generator-ignore).
Fournit `NitaClient` : login → JWT, rafraîchissement automatique du token,
signature HMAC anti-rejeu, APIs typées par domaine, et `unwrap`/`NitaError`
pour décoder l'enveloppe `{status, code, message, data}`, et `verify_callback`
pour vérifier un callback v2 signé reçu de NITA.

    from nita_sdk.client import NitaClient, unwrap, NitaError, new_request_id

    nita = NitaClient.connect(base_url=URL, api_key=KEY, login=LOGIN,
                              password=PASSWORD, hmac_secret=SECRET)
    solde = unwrap(nita.compte.consulter_solde_compte())
"""
from .callback import NitaCallbackError, verify_callback
from .errors import NitaError, unwrap
from .hmac import signature_headers
from .nita_client import NITA_ENVIRONMENTS, NitaClient
from .photos import encode_photos, to_base64
from .request_id import new_request_id

__all__ = [
    "NitaClient",
    "NITA_ENVIRONMENTS",
    "unwrap",
    "NitaError",
    "new_request_id",
    "encode_photos",
    "to_base64",
    "signature_headers",
    "verify_callback",
    "NitaCallbackError",
]
