# Image Odoo 17 + dépendance pip du module payment_nita.
#
# `nita-transfert-sdk` (import `nita_sdk`) est publié sur PyPI en pré-version : on épingle
# la version exacte plutôt que `--pre` pour ne pas entraîner de pré-versions des
# dépendances transitives (pydantic). 0.1.0b2 contient `NitaClient` et `url_retour`.
FROM odoo:17.0

USER root

ARG NITA_SDK_VERSION=0.1.0b2

RUN pip3 install --no-cache-dir "nita-transfert-sdk==${NITA_SDK_VERSION}"

USER odoo
