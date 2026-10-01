# Correctif temporaire : `nita_sdk.client` (PyPI en retard sur le monorepo)

**Constat (E2E Task 10, 2026-10-01)** : le paquet publié `nita-transfert-sdk==0.1.0b1`
(seule version sur PyPI à ce jour) ne contient **pas** le module
`nita_sdk.client.callback` (`verify_callback`, `NitaCallbackError`), que le
controller webhook de `payment_nita` importe
(`payment_nita/controllers/main.py`). Installer uniquement depuis PyPI comme
documenté casse le webhook avec :

```
ImportError: cannot import name 'NitaCallbackError' from 'nita_sdk.client'
```

(reproduit en conteneur Odoo 17 réel, voir `.superpowers/sdd/odoo/e2e-report.md`).

**Cause** : `verify_callback`/`NitaCallbackError` ont été ajoutés au monorepo
`nita-sdks` par le commit `ec20fd5` (« feat(securite): verificateur de callback
et delais HTTP dans les 7 SDK, usage serveur »), **après** la publication PyPI
`0.1.0b1`. Le paquet PyPI n'a jamais été republié depuis. Aucune version plus
récente n'existe sur l'index (`pip index versions nita-transfert-sdk` ne
renvoie que `0.1.0b1`).

**Correctif ici** : `callback.py` et `__init__.py` de ce dossier sont une copie
figée de `nita-sdks` (dépôt `nita-sdks`, branche `main`, HEAD `55a72a3` au
moment du test) — exactement les deux fichiers du sous-module
`nita_sdk.client` qui diffèrent. `e2e/Dockerfile` les copie par-dessus
l'installation pip standard, uniquement pour que l'E2E puisse exécuter
réellement le scénario callback (Objectif 2) malgré le paquet PyPI obsolète.

**Ce n'est PAS un correctif de `payment_nita`** (le module n'est pas modifié) ;
c'est un contournement de test pour une dépendance externe cassée. À supprimer
dès que `nita-transfert-sdk` est republié sur PyPI avec `callback.py` inclus —
remplacer alors l'étape `COPY sdk-patch/...` du Dockerfile par un simple bump
de version dans `ARG NITA_SDK_VERSION`.
