# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api
from odoo.osv import expression


class ProductCustomerInfo(models.Model):
    _name = "product.customer.info"
    _rec_name = "partner_id"

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    customer_product_name = fields.Char('Customer Product Name')
    customer_product_code = fields.Char('Customer Product Code')
    product_tmpl_id = fields.Many2one(
        'product.template', 'Product Template', check_company=True,
        index=True, ondelete='cascade')
    product_tmpl_id_2 = fields.Many2one(
        'product.template', 'Product Template', check_company=True,
        index=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', 'Company',
        default=lambda self: self.env.company.id, index=1)
    product_id = fields.Many2one(
        'product.product', 'Product Variant', check_company=True, required=True,
        help="If not set, the customer price will apply to all variants of this product.")


class ProductTemplateExtended(models.Model):
    _inherit = "product.template"

    customer_ids = fields.One2many('product.customer.info', 'product_tmpl_id', 'Customers',
                                   help="Define customer pricelists.")
    variant_customer_ids = fields.One2many('product.customer.info', 'product_tmpl_id')


class ProductProductExtended(models.Model):
    _inherit = "product.product"

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        if not args:
            args = []
        if name:
            positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
            product_ids = []
            if operator in positive_operators:
                product_ids = list(
                    self._search([('default_code', '=', name)] + args, limit=limit, access_rights_uid=name_get_uid))
                if not product_ids:
                    product_ids = list(
                        self._search([('barcode', '=', name)] + args, limit=limit, access_rights_uid=name_get_uid))
            if not product_ids and operator not in expression.NEGATIVE_TERM_OPERATORS:
                # Do not merge the 2 next lines into one single search, SQL search performance would be abysmal
                # on a database with thousands of matching products, due to the huge merge+unique needed for the
                # OR operator (and given the fact that the 'name' lookup results come from the ir.translation table
                # Performing a quick memory merge of ids in Python will give much better performance
                product_ids = list(self._search(args + [('default_code', operator, name)], limit=limit))
                if not limit or len(product_ids) < limit:
                    # we may underrun the limit because of dupes in the results, that's fine
                    limit2 = (limit - len(product_ids)) if limit else False
                    product2_ids = self._search(args + [('name', operator, name), ('id', 'not in', product_ids)],
                                                limit=limit2, access_rights_uid=name_get_uid)
                    product_ids.extend(product2_ids)
            elif not product_ids and operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = expression.OR([
                    ['&', ('default_code', operator, name), ('name', operator, name)],
                    ['&', ('default_code', '=', False), ('name', operator, name)],
                ])
                domain = expression.AND([args, domain])
                product_ids = list(self._search(domain, limit=limit, access_rights_uid=name_get_uid))
            if not product_ids and operator in positive_operators:
                ptrn = re.compile('(\[(.*?)\])')
                res = ptrn.search(name)
                if res:
                    product_ids = list(self._search([('default_code', '=', res.group(2))] + args, limit=limit,
                                                    access_rights_uid=name_get_uid))
            # still no results, partner in context: search on supplier info as last hope to find something
            if not product_ids and self._context.get('partner_id'):
                # Extended ########
                customers_ids = self.env['product.customer.info']._search([
                    ('partner_id', '=', self._context.get('partner_id')),
                    '|',
                    ('customer_product_code', operator, name),
                    ('customer_product_name', operator, name)], access_rights_uid=name_get_uid)
                # ##########################
                suppliers_ids = self.env['product.supplierinfo']._search([
                    ('name', '=', self._context.get('partner_id')),
                    '|',
                    ('product_code', operator, name),
                    ('product_name', operator, name)], access_rights_uid=name_get_uid)
                if customers_ids or suppliers_ids:
                    product_ids = self._search(['|', ('product_tmpl_id.customer_ids', 'in', customers_ids),
                                                ('product_tmpl_id.seller_ids', 'in', suppliers_ids)], limit=limit,
                                               access_rights_uid=name_get_uid)
        else:
            product_ids = self._search(args, limit=limit, access_rights_uid=name_get_uid)
        return product_ids


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def get_sale_order_line_multiline_description_sale(self, product):
        description = super(SaleOrderLine, self).get_sale_order_line_multiline_description_sale(product)
        partner_id = self.order_id.partner_id
        if product.customer_ids:
            customer_id = self.env['product.customer.info'].search(
                [('product_id', '=', product.id), ('partner_id', '=', partner_id.id)], limit=1)
            if customer_id.partner_id.id == partner_id.id:
                if customer_id.customer_product_name and customer_id.customer_product_code:
                    new_name = customer_id.customer_product_name
                    new_code = customer_id.customer_product_code
                    new_desc = '[' + new_code + '] ' + new_name
                    description = new_desc
                elif customer_id.customer_product_name:
                    new_name = customer_id.customer_product_name
                    new_desc = new_name
                    if product.default_code:
                        new_desc = '[' + product.default_code + '] ' + new_desc
                    description = new_desc
                elif customer_id.customer_product_code:
                    new_code = customer_id.customer_product_code
                    new_desc = '[' + new_code + '] '
                    if product.name:
                        new_desc = new_desc + product.name
                    description = new_desc
        return description
