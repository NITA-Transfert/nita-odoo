from odoo import fields, models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('nita', 'NITA')], ondelete={'nita': 'set default'})
    nita_base_url = fields.Char("URL de l'API NITA", required_if_provider='nita')
    nita_login = fields.Char("Login", required_if_provider='nita', groups='base.group_system')
    nita_api_key = fields.Char("Clé API", required_if_provider='nita', groups='base.group_system')
    nita_password = fields.Char("Mot de passe", required_if_provider='nita', groups='base.group_system')
    nita_hmac_secret = fields.Char("Secret HMAC", required_if_provider='nita', groups='base.group_system')

    def _get_supported_currencies(self):
        """NITA encaisse uniquement en francs CFA (XOF)."""
        currencies = super()._get_supported_currencies()
        if self.code == 'nita':
            currencies = currencies.filtered(lambda c: c.name == 'XOF')
        return currencies

    def _nita_client(self):
        """Couche cliente du SDK (login JWT + HMAC)."""
        self.ensure_one()
        from nita_sdk.client import NitaClient
        return NitaClient.connect(
            base_url=self.nita_base_url,
            api_key=self.nita_api_key,
            login=self.nita_login,
            password=self.nita_password,
            hmac_secret=self.nita_hmac_secret,
        )
