odoo.define('datev_tax_amount_widget', function (require) {
    'use strict'
    let AbstractField = require('web.AbstractField')
    let fieldRegistry = require('web.field_registry')
    let taxAmount = AbstractField.extend({
        _renderReadonly: function () {
            let formattedTaxAmount = (this.recordData.price_total - this.recordData.price_subtotal).toLocaleString('de-DE')
            this.value = formattedTaxAmount
            this.$el.text(formattedTaxAmount)
        },
    })
    fieldRegistry.add('datev_tax_amount', taxAmount)
    return {
        taxAmount: taxAmount,
    }
})

odoo.define('datev_tax_rate_widget', function (require) {
    'use strict'
    let AbstractField = require('web.AbstractField')
    let fieldRegistry = require('web.field_registry')
    let taxRate = AbstractField.extend({
        _renderReadonly: function () {
            let account = this.recordData.account_id.data.display_name
            let taxRateValue = '0'
            if (account.includes('4301') || account.includes('4311')) {
                taxRateValue = 7
            } else if (account.includes('4402') || account.includes('4316')) {
                taxRateValue = 19
            }
            this.value = taxRateValue
            this.$el.text(taxRateValue)
        },
    })
    fieldRegistry.add('datev_tax_rate', taxRate)
    return {
        taxRate: taxRate,
    }
})


odoo.define('datev_vat', function (require) {
    'use strict'
    let AbstractField = require('web.AbstractField')
    let fieldRegistry = require('web.field_registry')
    let vat = AbstractField.extend({
        _renderReadonly: function () {
            let formattedVat = this.value
            if (formattedVat !== false) {
                formattedVat = formattedVat.substring(2, formattedVat.length - 1)
            }
            this.value = formattedVat
            this.$el.text(formattedVat)
        },
    })
    fieldRegistry.add('datev_vat', vat)
    return {
        vat: vat,
    }
})
