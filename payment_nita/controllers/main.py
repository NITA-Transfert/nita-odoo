import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class NitaController(http.Controller):

    @http.route('/payment/nita/webhook', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def nita_webhook(self, **kwargs):
        """Callback v2 NITA (POST JSON signé HMAC X-NT-*).

        La signature porte sur les octets BRUTS du corps : on ne lit JAMAIS
        `request.get_json_data()` (qui re-sérialiserait). Le secret HMAC vient
        du provider `code='nita'` actif (jamais d'un secret global). Anti-rejeu
        persistant via `nita.callback.nonce._remember`. Ne paie jamais via
        l'API : ne fait que vérifier + déléguer au framework `payment`.
        """
        from nita_sdk.client import NitaCallbackError, verify_callback

        raw = request.httprequest.get_data()  # octets bruts (ne pas re-sérialiser)
        headers = dict(request.httprequest.headers)

        provider = request.env['payment.provider'].sudo().search(
            [('code', '=', 'nita')], limit=1)
        if not provider or not provider.nita_hmac_secret:
            _logger.warning("NITA webhook: aucun provider NITA actif avec secret HMAC")
            return request.make_response('', status=401)

        nonce_model = request.env['nita.callback.nonce'].sudo()
        try:
            data = verify_callback(
                raw, headers, provider.nita_hmac_secret,
                is_new_nonce=lambda n, ttl: nonce_model._remember(n, ttl))
        except NitaCallbackError:
            _logger.warning("NITA webhook: signature/callback refusé")
            return request.make_response('', status=401)
        except Exception:
            _logger.exception("NITA webhook: échec inattendu de la vérification")
            return request.make_response('', status=401)

        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('nita', data)
        except Exception:
            _logger.exception("NITA webhook: traitement de la notification a échoué")
            return request.make_response('', status=500)
        return request.make_response('', status=200)

    @http.route('/payment/nita/return', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def nita_return(self, **kwargs):
        """Retour navigateur après la page de paiement NITA : l'état réel de la
        transaction est déterminé par le callback (source de vérité), pas par ce
        retour. On renvoie simplement le client vers l'écran de statut de paiement."""
        return request.redirect('/payment/status')
