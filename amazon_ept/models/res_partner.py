# -*- coding: utf-8 -*-pack
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import itertools
from odoo import api, models, fields
from odoo.addons.iap.tools import iap_tools
from ..endpoint import DEFAULT_ENDPOINT


class ResPartner(models.Model):
    """
    Inherited for VAT configuration in partner of Warehouse.
    """
    _inherit = "res.partner"

    is_amz_customer = fields.Boolean("Is Amazon Customer?")

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if not self.env.context.get('is_amazon_partner', True):
            args = [('is_amz_customer', '=', False)] + list(args)
        return super(ResPartner, self)._search(args, offset, limit, order, count, access_rights_uid)

    @api.onchange("country_id")
    def _onchange_country_id(self):
        """
        Inherited for updating the VAT number of the partner as per the VAT configuration.
        @author: Maulik Barad on Date 13-Jan-2020.
        """
        warehouse_obj = self.env["stock.warehouse"]
        vat_config_obj = self.env["vat.config.ept"]
        if self.country_id:
            warehouses = warehouse_obj.search([("company_id", "=", self.env.company.id)])
            warehouse_partner = warehouses.filtered(\
                lambda warehouse: warehouse.partner_id and warehouse.partner_id.id == self._origin.id and not warehouse.partner_id.vat)
            if warehouse_partner:
                vat_config_record = vat_config_obj.search([("company_id", "=", self.env.company.id)])
                vat_config_line = vat_config_record.vat_config_line_ids.filtered(lambda x: x.country_id == self.country_id)
                if vat_config_line:
                    self.write({"vat": vat_config_line.vat})
        return super(ResPartner, self)._onchange_country_id()

    @api.model
    def create(self, vals):
        if vals.get('is_amz_customer', False):
            vals.update({'allow_search_fiscal_based_on_origin_warehouse': True})
        return super(ResPartner, self).create(vals)

    def auto_delete_customer_pii_details(self):
        """
        Auto Archive Customer's PII Details after 30 days of Import as per Amazon MWS Policies.
        :return:
        """
        if not self.env['amazon.seller.ept'].search([]):
            return True
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        kwargs = {
            'app_name': 'amazon_ept',
            'account_token': account.account_token,
            'dbuuid': dbuuid,
            'updated_records': 'Scheduler for delete PII data has been started.'
        }
        partner_to_skip = tuple(self.env.company.search([]).partner_id.ids)
        partner_to_skip_query = """select partner_id, partner_invoice_id, partner_shipping_id from sale_order
                                where amz_instance_id is not null and sale_order.create_date>=current_date-30
                                and sale_order.amz_is_outbound_order = False"""
        self.env.cr.execute(partner_to_skip_query)
        results = self._cr.fetchall()
        partner_to_skip += tuple(set(list(itertools.chain(*results))))
        partner_to_skip = tuple(set(partner_to_skip))
        iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/delete_pii', params=kwargs, timeout=1000)
        query = f"""update res_partner set name=concat('Amazon-',T.sale_name),commercial_company_name='Amazon', 
                    display_name='Amazon', 
                    street=NULL,street2=NULL,email=NULL,city=NULL,phone=NULL,mobile=NULL
                    from
                    (select r1.id as partner_id,r2.id as partner_invoice_id,r3.id as 
                    partner_shipping_id, string_agg(sale_order.name, ', ') as sale_name from sale_order
                    inner join res_partner r1 on r1.id=sale_order.partner_id
                    inner join res_partner r2 on r2.id=sale_order.partner_invoice_id
                    inner join res_partner r3 on r3.id=sale_order.partner_shipping_id
                    where amz_instance_id is not null and sale_order.create_date<=current_date-30 
                    and r1.name not like 'Amazon%' and sale_order.amz_is_outbound_order = False
                    group by r1.id, r2.id, r3.id)T
                    where res_partner.id in 
                    (T.partner_id,T.partner_invoice_id,T.partner_shipping_id) 
                    and res_partner.id not in {partner_to_skip}
                    """
        self.env.cr.execute(query)

        if self.env.cr.rowcount:
            kwargs.update({'updated_records': 'Archived %d customers' % self.env.cr.rowcount})
            iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/delete_pii', params=kwargs, timeout=1000)
        return True

    @api.model
    def update_action_context_for_amazon_customers(self):
        """
        Add is_amazon_partner key to context of window actions for all res.partner model window actions.
        Here we check if is_amazon_partner key found then we will not add it twice again.
        If this key not found in any window action then just upgrade amazon app.
        """
        window_actions = self.env['ir.actions.act_window']
        partner_actions = window_actions.search([('res_model','=','res.partner')])
        for act in partner_actions:
            if act.context.find('is_amazon_partner') < 0:
                if act.context == "{}":
                    new_context = "{'is_amazon_partner': False}"
                else:
                    new_context = "{}{}".format(act.context[:-1], ", 'is_amazon_partner': False}")
                act.write({'context':new_context})
