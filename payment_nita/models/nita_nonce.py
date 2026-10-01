import time

from odoo import fields, models


class NitaCallbackNonce(models.Model):
    _name = 'nita.callback.nonce'
    _description = "Nonces anti-rejeu des callbacks NITA"

    nonce = fields.Char(required=True, index=True)
    expiry = fields.Integer(required=True)
    _sql_constraints = [('nonce_uniq', 'unique(nonce)', "Nonce déjà vu")]

    def _remember(self, nonce, ttl):
        """True si le nonce est nouveau (ou expiré, redevenu réutilisable). Atomique via la
        contrainte unique : une insertion en doublon lève, interceptée -> rejeu refusé."""
        now = int(time.time())
        self.sudo().search([('expiry', '<', now)]).unlink()  # purge
        existing = self.sudo().search([('nonce', '=', nonce)], limit=1)
        if existing:
            if existing.expiry < now:
                existing.expiry = now + ttl
                return True
            return False
        try:
            with self.env.cr.savepoint():
                self.sudo().create({'nonce': nonce, 'expiry': now + ttl})
            return True
        except Exception:
            return False  # inséré en concurrence -> rejeu
