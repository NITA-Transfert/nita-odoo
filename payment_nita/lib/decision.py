PAID = 'paid'
PENDING = 'pending'
FAILED = 'failed'
CANCELLED = 'cancelled'

# StatutAchat NITA : 0=NON_PAYER, 1=PAYER, 2=ANNULE, 3=BLOQUER (clé ou libellé).
_BY_KEY = {'0': PENDING, '1': PAID, '2': CANCELLED, '3': FAILED}
_BY_LABEL = {'non_payer': PENDING, 'payer': PAID, 'annule': CANCELLED, 'bloquer': FAILED}

def map_nita_status(raw):
    """Normalise un statut NITA (clé '0'..'3' OU libellé) vers un statut interne.
    Défaut CONSERVATEUR = PENDING (on ne valide jamais sur un statut inconnu)."""
    if raw is None:
        return PENDING
    s = str(raw).strip()
    if s in _BY_KEY:
        return _BY_KEY[s]
    return _BY_LABEL.get(s.lower().replace(' ', '_'), PENDING)

def reconcile_action(status, amount_matches):
    """Décide quoi faire d'une transaction selon le statut NITA et la cohérence du montant.
    - payé + montant cohérent -> valider ('done')
    - payé + montant incohérent -> vérification manuelle ('review'), jamais validé auto
    - annulé -> 'cancel' ; échec/bloqué -> 'error' ; sinon -> 'none'."""
    if status == PAID:
        return 'done' if amount_matches else 'review'
    if status == CANCELLED:
        return 'cancel'
    if status == FAILED:
        return 'error'
    return 'none'
