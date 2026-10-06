from payment_nita.lib.decision import map_nita_status, reconcile_action, PAID, PENDING, FAILED, CANCELLED

def test_map_nita_status_keys():
    assert map_nita_status('1') == PAID
    assert map_nita_status('0') == PENDING
    assert map_nita_status('2') == CANCELLED
    assert map_nita_status('3') == FAILED

def test_map_nita_status_labels_caseinsensitive():
    assert map_nita_status('PAYER') == PAID
    assert map_nita_status('payer') == PAID
    assert map_nita_status('Annule') == CANCELLED
    assert map_nita_status('NON_PAYER') == PENDING

def test_map_nita_status_unknown_defaults_pending():
    assert map_nita_status(None) == PENDING
    assert map_nita_status('n-importe-quoi') == PENDING

def test_reconcile_action():
    assert reconcile_action(PAID, True) == 'done'
    assert reconcile_action(PAID, False) == 'review'   # montant incohérent -> vérif manuelle
    assert reconcile_action(CANCELLED, True) == 'cancel'
    assert reconcile_action(FAILED, True) == 'error'
    assert reconcile_action(PENDING, True) == 'none'


from payment_nita.lib.decision import prior_attempt_action

def test_prior_attempt_paid_never_reuses_the_paid_link():
    # Payé côté NITA : enregistrer, jamais renvoyer le client sur le lien déjà réglé.
    assert prior_attempt_action(PAID, amount_matches=True, has_url=True) == 'paid'
    assert prior_attempt_action(PAID, amount_matches=False, has_url=True) == 'paid'

def test_prior_attempt_pending_same_amount_reuses_link():
    assert prior_attempt_action(PENDING, amount_matches=True, has_url=True) == 'reuse'

def test_prior_attempt_pending_amount_changed_cancels_then_recreates():
    # Panier modifié depuis la 1re tentative : l'ancien lien demanderait le mauvais montant.
    assert prior_attempt_action(PENDING, amount_matches=False, has_url=True) == 'cancel_and_create'

def test_prior_attempt_pending_without_url_cancels_then_recreates():
    # NITA refuse un requestId encore 'non payé' : il faut annuler avant de recréer.
    assert prior_attempt_action(PENDING, amount_matches=True, has_url=False) == 'cancel_and_create'

def test_prior_attempt_cancelled_or_failed_recreates():
    assert prior_attempt_action(CANCELLED, amount_matches=True, has_url=True) == 'create'
    assert prior_attempt_action(FAILED, amount_matches=False, has_url=True) == 'create'
