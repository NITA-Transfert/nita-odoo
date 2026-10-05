import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..lib.mapping import build_achat_args, request_id_for_order
from ..lib.decision import map_nita_status, reconcile_action, PAID, PENDING

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    nita_code_achat = fields.Char(readonly=True)
    nita_url_paiement = fields.Char(readonly=True)
    nita_request_id = fields.Char(readonly=True)
    nita_montant_achat = fields.Integer(readonly=True)
    nita_phone = fields.Char("Numéro MyNITA")

    def _nita_source_reference(self):
        """Référence du document SOURCE (= requestId, option a), PAS la référence de la
        transaction Odoo (qui change à chaque tentative). Commande e-commerce puis facture,
        repli sur la référence de transaction."""
        self.ensure_one()
        order = self.sale_order_ids[:1]
        if order:
            return order.name
        inv = self.invoice_ids[:1]
        if inv:
            return inv.name
        return self.reference

    def _nita_status(self, request_id, ip='0.0.0.0'):
        """Statut réel côté NITA pour ce requestId (normalisé)."""
        from nita_sdk.models import CheckAchatStatusModel
        from nita_sdk.client import unwrap
        r = unwrap(self.provider_id._nita_client().achat.check_achat_status(
            CheckAchatStatusModel(request_id=request_id, adresse_ip=ip)))
        return map_nita_status(getattr(r, 'code', None))

    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'nita':
            return res
        from nita_sdk.models import AchatEnLigneModel
        from nita_sdk.client import unwrap
        # Cette transaction a déjà son lien -> le réutiliser (double-clic).
        if self.nita_url_paiement:
            return {'api_url': self.nita_url_paiement}
        request_id = request_id_for_order(self._nita_source_reference())
        # requestId = réf de la commande source : partagé entre les tentatives (payment.transaction)
        # d'une même commande. Avant de recréer, regarder une tentative antérieure et interroger le
        # STATUT RÉEL côté NITA (le callback a pu ne pas passer) -> réutiliser / enregistrer / recréer.
        prior = self.sudo().search([
            ('provider_code', '=', 'nita'), ('nita_request_id', '=', request_id),
            ('nita_code_achat', '!=', False), ('id', '!=', self.id),
        ], order='id desc', limit=1)
        if prior:
            try:
                live = self._nita_status(request_id)
            except Exception:
                live = PENDING  # erreur réseau : défaut prudent (réutiliser)
            if live == PAID:
                # Payé côté NITA mais Odoo pas à jour (callback manqué) : enregistrer, ne pas recréer.
                self.write({'nita_request_id': request_id, 'nita_code_achat': prior.nita_code_achat,
                            'nita_montant_achat': prior.nita_montant_achat})
                # Même garde-fou que le chemin callback : ne jamais valider si le montant
                # réellement engagé ne correspond plus à la commande courante (ex. commande
                # modifiée entre deux tentatives).
                if self._nita_amount_matches({}):
                    self._set_done()
                else:
                    self._set_pending()
                    self._log_message_on_linked_documents(_(
                        "Paiement NITA %s reçu mais le montant ne correspond plus à la commande. "
                        "Vérification manuelle requise.") % prior.nita_code_achat)
                return {'api_url': prior.nita_url_paiement or self.provider_id.get_base_url()}
            if live == PENDING and prior.nita_url_paiement:
                self.write({'nita_request_id': request_id, 'nita_code_achat': prior.nita_code_achat,
                            'nita_url_paiement': prior.nita_url_paiement,
                            'nita_montant_achat': prior.nita_montant_achat})
                return {'api_url': prior.nita_url_paiement}  # même lien, pas de 2e achat
            # annulé / échec (ou pending sans URL) -> recréer ci-dessous (NITA autorise la réutilisation après annulation).
        callback_url = self.provider_id.get_base_url() + '/payment/nita/webhook'
        try:
            args = build_achat_args(
                reference=self._nita_source_reference(),
                total=self.amount,
                currency=self.currency_id.name,
                items=[self._nita_source_reference()],
                callback_url=callback_url,
                phone=self.nita_phone,
                ip='',  # IP client indisponible côté serveur ici -> repli '0.0.0.0' dans la lib
                return_url=self.provider_id.get_base_url() + '/payment/nita/return',
            )
            result = unwrap(self.provider_id._nita_client().achat.add_achat_enligne(
                AchatEnLigneModel(**args)))
        except Exception as e:
            _logger.exception("NITA createAchat a échoué")
            raise ValidationError(_("Le paiement NITA n'a pas pu démarrer : %s") % e)
        self.write({
            'nita_request_id': args['request_id'],
            'nita_code_achat': result.code_achat,
            'nita_url_paiement': result.url_paiement or '',
            'nita_montant_achat': args['montant_transaction'],
        })
        if not result.url_paiement:
            raise ValidationError(_("NITA : page de paiement indisponible."))
        return {'api_url': result.url_paiement}

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'nita':
            return tx
        code_achat = notification_data.get('transaction_id')
        tx = self.search([('nita_code_achat', '=', code_achat), ('provider_code', '=', 'nita')], limit=1)
        if not tx:
            raise ValidationError(_("NITA : transaction introuvable pour %s") % code_achat)
        return tx

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'nita':
            return
        if self.state == 'done':
            return  # idempotent
        status = map_nita_status(notification_data.get('status'))
        amount_matches = self._nita_amount_matches(notification_data)
        action = reconcile_action(status, amount_matches)
        if action == 'done':
            self._set_done()
        elif action == 'review':
            self._set_pending()
            self._log_message_on_linked_documents(_(
                "Paiement NITA %s reçu mais le montant ne correspond plus à la commande. "
                "Vérification manuelle requise.") % self.nita_code_achat)
        elif action == 'cancel':
            self._set_canceled()
        elif action == 'error':
            self._set_error(_("Paiement NITA non abouti."))
        # 'none' -> rien (reste pending)

    def _nita_amount_matches(self, notification_data):
        """Le callback v2 réel ne transporte PAS de montant ({status, transaction_id}
        seulement) : on compare donc le montant réellement engagé auprès de NITA
        (nita_montant_achat, fixé à la création/réutilisation de l'achat) au montant
        courant de la transaction. Incohérent si l'achat réutilisé a été créé pour un
        autre montant que la commande actuelle -> jamais validé automatiquement."""
        from ..lib.mapping import amount_xof
        if not self.nita_montant_achat:
            return True  # pas de montant engagé connu : on s'en remet au statut signé
        return self.nita_montant_achat == amount_xof(self.amount)

    @api.model
    def _nita_cron_reconcile_pending(self, limit=80):
        """Tâche planifiée : rattrape les paiements dont le callback n'est jamais arrivé.
        Le paiement NITA se fait sur une page externe et le callback peut ne pas parvenir
        (le sandbox n'en émet pas ; en prod un webhook peut se perdre). Sans ce rattrapage,
        une commande payée resterait « en attente » et re-proposerait le paiement.
        Pour chaque transaction NITA encore en attente, on interroge le STATUT RÉEL côté
        NITA et on confirme/annule en conséquence. Le plugin ne paie JAMAIS : lecture du
        statut + mise à jour locale uniquement."""
        txs = self.search([
            ('provider_code', '=', 'nita'),
            ('state', 'in', ('draft', 'pending')),
            ('nita_request_id', '!=', False),
        ], limit=limit)
        for tx in txs:
            try:
                status = tx._nita_status(tx.nita_request_id)
            except Exception:
                _logger.exception("NITA cron: statut indisponible pour %s", tx.reference)
                continue  # erreur réseau/API : on retentera au prochain passage
            action = reconcile_action(status, tx._nita_amount_matches({}))
            if action == 'done':
                tx._set_done()
                # Confirme la commande/facture liée immédiatement. En cas d'échec (ex. config
                # comptable incomplète), le cron intégré d'Odoo `_cron_finalize_post_processing`
                # retentera (la tx reste `done` avec is_post_processed=False).
                try:
                    tx._finalize_post_processing()
                except Exception:
                    _logger.exception("NITA cron: finalisation de %s a échoué (retentée par Odoo)", tx.reference)
            elif action == 'cancel':
                tx._set_canceled()
            elif action == 'error':
                tx._set_error(_("Paiement NITA non abouti."))
            # 'review' / 'none' : on laisse en attente (vérification manuelle / pas encore payé)
        return True
