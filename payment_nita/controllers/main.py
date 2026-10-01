import logging

from odoo import http
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentPortal as _BasePaymentPortal

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


class PaymentPortal(_BasePaymentPortal):
    """Glue Task 9 (numéro MyNITA) côté serveur, PAS seulement côté JS.

    `static/src/js/payment_form.js` ajoute `nita_phone` aux paramètres envoyés à
    `/payment/transaction`, mais le contrôleur générique du framework `payment`
    17.0 (`PaymentPortal`) :
      - rejette toute clé non whitelistée via `_validate_transaction_kwargs`
        (sinon `ValidationError`) ;
      - ne reporte vers `payment.transaction.create()` QUE le contenu de
        `custom_create_values`, tout le reste de `**kwargs` est consommé puis
        jeté par `_create_transaction`.
    Sans cet override, `nita_phone` ne pourrait jamais atteindre la transaction
    (il serait soit rejeté, soit silencieusement ignoré).

    R1 — vérifié contre le source Odoo 17.0 officiel
    (addons/payment/controllers/portal.py) au moment de l'écriture : la classe
    s'appelle bien `PaymentPortal` dans `odoo.addons.payment.controllers.portal`,
    `_validate_transaction_kwargs` est `@staticmethod`, `_create_transaction` a la
    signature `(self, provider_id, payment_method_id, token_id, amount,
    currency_id, partner_id, flow, tokenization_requested, landing_route,
    reference_prefix=None, is_validation=False, custom_create_values=None,
    **kwargs)` et est appelée par la route `/payment/transaction` en keyword-only
    (`self._create_transaction(amount=amount, currency_id=currency_id,
    partner_id=partner_id, **kwargs)`). À reconfirmer contre le conteneur réel de
    la Task 10 (ces noms/signatures peuvent différer d'un correctif mineur 17.0
    à l'autre).
    """

    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        return _BasePaymentPortal._validate_transaction_kwargs(
            kwargs, additional_allowed_keys=(*additional_allowed_keys, 'nita_phone'))

    def _create_transaction(self, *args, custom_create_values=None, **kwargs):
        # *args préservé tel quel (positionnel ou vide) : ne jamais supposer que
        # cette méthode n'est appelée qu'en keyword (cf. docstring ci-dessus).
        nita_phone = kwargs.pop('nita_phone', None)
        if nita_phone:
            provider_id = kwargs.get('provider_id') or (args[0] if args else None)
            provider_sudo = request.env['payment.provider'].sudo().browse(provider_id)
            if provider_sudo.code == 'nita':
                custom_create_values = dict(custom_create_values or {},
                                             nita_phone=str(nita_phone).strip())
        return super()._create_transaction(*args, custom_create_values=custom_create_values, **kwargs)
