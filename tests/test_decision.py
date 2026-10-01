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
