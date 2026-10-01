/** @odoo-module **/

import paymentForm from '@payment/js/payment_form';

/**
 * Joint le numéro MyNITA (saisi dans `payment_nita.inline_form`, cf.
 * views/payment_nita_templates.xml) aux paramètres envoyés à la route
 * /payment/transaction, pour qu'il atterrisse sur `payment.transaction.nita_phone`.
 *
 * Le patch JS seul ne suffit pas : le contrôleur générique `payment.PaymentPortal`
 * rejette toute clé inconnue (`_validate_transaction_kwargs`) et ne reporte vers la
 * création de la transaction que `custom_create_values`. L'autre moitié de la glue
 * (whitelist de `nita_phone` + injection dans `custom_create_values`) est dans
 * `payment_nita/controllers/main.py` (override de `PaymentPortal`).
 *
 * R1 — points vérifiés contre le source Odoo 17.0 officiel (addons/payment/static/
 * src/js/payment_form.js) au moment de l'écriture, à reconfirmer contre le conteneur
 * réel de la Task 10 :
 *   - Le widget `paymentForm` s'étend via `publicWidget.Widget.extend`/`.include`
 *     (pas un composant OWL) ; le patch se fait avec `paymentForm.include({...})`
 *     et `this._super(...arguments)`.
 *   - `_prepareTransactionRouteParams()` est l'unique point où les paramètres de la
 *     route /payment/transaction sont assemblés ; étendre son retour est le moyen
 *     normal d'ajouter un champ custom (cf. patron utilisé par les modules
 *     `payment_<provider>` de première partie).
 *   - `this.paymentContext.providerCode` est déjà renseigné à ce stade (affecté
 *     dans `_submitForm` avant l'appel à `_initiatePaymentFlow`, qui appelle
 *     `_prepareTransactionRouteParams`).
 */
paymentForm.include({

    /**
     * @override
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = this._super(...arguments);
        if (this.paymentContext.providerCode !== 'nita') {
            return transactionRouteParams;
        }
        return {
            ...transactionRouteParams,
            'nita_phone': this._nitaGetPhoneValue(),
        };
    },

    /**
     * Lit la valeur saisie dans le formulaire inline NITA.
     *
     * R1 : recherche par attribut `name` dans tout le formulaire de paiement plutôt
     * que scopée au conteneur `[name="o_payment_inline_form"]` de l'option NITA
     * sélectionnée, car un seul provider NITA est censé être actif à la fois. À
     * confirmer en E2E si plusieurs instances du provider NITA peuvent coexister
     * sur la même page (auquel cas il faudrait scoper via `paymentOptionId`).
     *
     * @private
     * @return {String}
     */
    _nitaGetPhoneValue() {
        const input = this.el.querySelector('input[name="nita_phone"]');
        return input ? input.value.trim() : '';
    },
});
