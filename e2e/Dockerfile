# Image Odoo 17 + dépendance pip du module payment_nita.
#
# `nita-transfert-sdk` (import `nita_sdk`) est publié sur PyPI (cf. memory
# sdk-npm-publication). Il est encore en pré-version (0.1.0b1) : on épingle la
# version exacte plutôt que `--pre` pour éviter d'entraîner des pré-versions
# des dépendances transitives (pydantic) dans l'installation.
#
# CORRECTIF TEMPORAIRE (voir sdk-patch/README.md) : au 2026-10-01, le paquet
# PyPI 0.1.0b1 (seule version publiée) ne contient PAS
# `nita_sdk.client.callback` (`verify_callback`/`NitaCallbackError`), ajouté au
# monorepo nita-sdks APRES cette publication et jamais republié. Sans ce
# correctif, le controller webhook de payment_nita casse a l'import
# (ImportError -> 500 sur /payment/nita/webhook). On écrase donc les deux
# fichiers concernés de `nita_sdk/client/` par la version a jour du monorepo,
# commitee dans `sdk-patch/`. A retirer des que PyPI est republie (remplacer
# alors par un simple bump de NITA_SDK_VERSION).
FROM odoo:17.0

USER root

ARG NITA_SDK_VERSION=0.1.0b1

RUN pip3 install --no-cache-dir "nita-transfert-sdk==${NITA_SDK_VERSION}"

COPY sdk-patch/nita_sdk_client/callback.py sdk-patch/nita_sdk_client/__init__.py \
     /usr/local/lib/python3.10/dist-packages/nita_sdk/client/

USER odoo
