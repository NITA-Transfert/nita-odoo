import time

from odoo import fields, models


class NitaCallbackNonce(models.Model):
    _name = 'nita.callback.nonce'
    _description = "Nonces anti-rejeu des callbacks NITA"

    nonce = fields.Char(required=True, index=True)
    expiry = fields.Integer(required=True)
    _sql_constraints = [('nonce_uniq', 'unique(nonce)', "Nonce déjà vu")]

    def _remember(self, nonce, ttl):
        """True si le nonce est nouveau. Les nonces expirés sont purgés avant la recherche
        (donc un nonce encore trouvé est forcément non expiré -> rejeu). Atomique via la
        contrainte unique : une insertion en doublon lève, interceptée -> rejeu refusé."""
        now = int(time.time())
        self.sudo().search([('expiry', '<', now)]).unlink()  # purge (rend réutilisable)
        if self.sudo().search_count([('nonce', '=', nonce)]):
            return False  # déjà vu (et pas expiré, sinon purgé ci-dessus) -> rejeu
        try:
            with self.env.cr.savepoint():
                self.sudo().create({'nonce': nonce, 'expiry': now + ttl})
            return True
        except Exception:
            return False  # inséré en concurrence -> rejeu
