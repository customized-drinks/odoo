# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added to perform the amazon import, export operations and added onchange and methods
to process for different amazon operations.
"""

import base64
import csv
import xlrd
import time
from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO
import os

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError, ValidationError

from ..endpoint import DEFAULT_ENDPOINT


class AmazonProcessImportExport(models.TransientModel):
    """
    Added class to perform amazon import and export operations.
    """
    _name = 'amazon.process.import.export'
    _description = 'Amazon Import Export Process'

    seller_id = fields.Many2one('amazon.seller.ept', string='Amazon Seller',
                                help="Select Amazon Seller Account")

    amazon_program = fields.Selection(related="seller_id.amazon_program")

    us_amazon_program = fields.Selection(related="seller_id.amz_fba_us_program")
    instance_id = fields.Many2one('amazon.instance.ept', string='Instance',
                                  help="This Field relocates amazon instance.")
    order_removal_instance_id = fields.Many2one('amazon.instance.ept', string='Removal Instance',
                                                help="This instance is used for the Removal order.")
    is_another_soft_create_fba_inventory = fields.Boolean(
        related="seller_id.is_another_soft_create_fba_inventory",
        string="Does another software create the FBA Inventory reports?",
        help="Does another software create the FBA Inventory reports")
    instance_ids = fields.Many2many("amazon.instance.ept", 'amazon_instance_import_export_rel',
                                    'process_id', 'instance_id', "Instances",
                                    help="Select Amazon Marketplaces where you want to perform "
                                         "opetations.")
    list_settlement_report = fields.Boolean("List settlement report?")
    report_start_date = fields.Datetime("Start Date", help="Start date of report.")
    report_end_date = fields.Datetime("End Date", help="End date of report.")
    selling_on = fields.Selection([
        ('FBM', 'FBM'),
        ('FBA', 'FBA'),
        ('fba_fbm', 'FBA & FBM')
    ], 'Operation For')
    operations = fields.Selection([
        ('Export_Stock_From_Odoo_To_Amazon', 'Export Stock from Odoo to Amazon'),
        ('Update_Track_Number_And_Ship_Status', 'Update Tracking Number & Shipment Status'),
        ('Check_Cancel_Orders_FBM', 'Check Cancel Orders'),
        ('Import_FBM_Shipped_Orders', 'Import FBM Shipped Orders'),
        ('Import_Missing_Unshipped_Orders', 'Import Missing UnShipped Orders'),
        ('Import_Unshipped_Orders', 'Import Unshipped Orders')
    ], 'FBM Operations')
    fba_operations = fields.Selection([
        ('Import_Pending_Orders', 'Import Pending Orders'),
        ('Check_Cancel_Orders_FBA', 'Check Cancel Orders'),
        ('Shipment_Report', 'Shipment Report'),
        ('Stock_Adjustment_Report', 'Stock Adjustment Report'),
        ('Removal_Order_Report', 'Removal Order Report'),
        ('Customer_Return_Report', 'Customer Return Report'),
        ('removal_order_request', 'Removal Order Request'),
        ('Import Inbound Shipment', 'Import Inbound Shipment'),
        ('Create_Inbound_Shipment_Plan', 'Create Inbound Shipment Plan'),
        ('fba_live_inventory_report', 'FBA Live Inventory')
    ], 'Operations')

    both_operations = fields.Selection([
        ('Import_Product', 'Map Product'),
        ('Sync_Active_Products', 'Sync Active Products'),
        ('Export_Price_From_Odoo_To_Amazon', 'Export Price From Odoo to Amazon'),
        ('List_Settlement_Report', 'List Settlement report'),
        ('request_rating_report', 'Request Rating Report'),
        ('vcs_tax_report', 'VCS Tax Report')
    ], 'FBA & FBM Operations')
    is_vcs_enabled = fields.Boolean('Is VCS Report Enabled ?', default=False, store=False)
    is_split_report = fields.Boolean('Is Split Report ?', default=False)
    split_report_by_days = fields.Selection([
        ('3', '3'),
        ('7', '7'),
        ('15', '15')
    ])
    fbm_order_updated_after_date = fields.Datetime('Updates After')
    import_fba_pending_sale_order = fields.Boolean('Sale order(Only Pending Orders)',
                                                   help="System will import pending FBA orders "
                                                        "from Amazon")
    check_order_status = fields.Boolean("Check Cancelled Order in Amazon",
                                        help="If ticked, system will check the orders status in "
                                             "canceled in Amazon, then system will cancel that "
                                             "order "
                                             "is Odoo too.")
    export_inventory = fields.Boolean()
    export_product_price = fields.Boolean('Update Product Price')
    updated_after_date = fields.Datetime('Updated After')
    shipment_id = fields.Char()
    from_warehouse_id = fields.Many2one('stock.warehouse', string="From Warehouse")
    update_price_in_pricelist = fields.Boolean(string='Update price in pricelist?', default=False,
                                               help='Update or create product line in pricelist '
                                                    'if ticked.')
    auto_create_product = fields.Boolean(string='Auto create product?', default=False,
                                         help='Create product in ERP if not found.')
    file_name = fields.Char(string='Name')
    choose_file = fields.Binary(string="Select File")
    delimiter = fields.Selection([('tab', 'Tab'), ('semicolon', 'Semicolon'), ('comma', 'Comma')],
                                 string="Separator", default='comma')
    user_warning = fields.Text(string="Note: ", store=False)
    pan_eu_instance_id = fields.Many2one('amazon.instance.ept', string='Instance(UK)',
                                         help="This Field relocates amazon UK instance.")
    us_region_instance_id = fields.Many2one('amazon.instance.ept', string='Instance(US)',
                                            help="This Field relocates amazon North America Region instance.")
    country_code = fields.Char(related='seller_id.country_id.code', string='Country Code')
    mci_efn_instance_id = fields.Many2one('amazon.instance.ept', string='Instance(EU)',
                                          help="This Field relocates amazon MCI or MCI+EFN instance.")
    ship_to_address = fields.Many2one('res.partner', string='Ship To Address', help='Destination Address for Inbound Shipment')

    @api.onchange('report_start_date', 'report_end_date')
    def onchange_shipment_report_date(self):
        """
        Added onchange to allow option to split report based on selected date range difference is
        more than 7 days.
        """
        if self.report_start_date and self.report_end_date:
            count = self.report_end_date.date() - self.report_start_date.date()
            if count.days > 7 and not self.seller_id.is_another_soft_create_fba_shipment:
                self.is_split_report = True
            else:
                self.is_split_report = False

    @api.onchange('selling_on')
    def onchange_selling_on(self):
        """
        Added set operations vals false based on selling on.
        """
        self.operations = False
        self.fba_operations = False
        self.both_operations = False

    @api.onchange('operations')
    def onchange_operations(self):
        """
        On change of operations field it will check the active scheduler or scheduler
        exist then it's next run time.
        """
        self.export_inventory = False
        self.export_product_price = False
        self.list_settlement_report = False
        self.fbm_order_updated_after_date = False
        self.updated_after_date = False
        self.report_start_date = False
        self.report_end_date = False

        self.user_warning = None
        if self.operations == "Export_Stock_From_Odoo_To_Amazon":
            self.check_running_schedulers('ir_cron_auto_export_inventory_seller_')

        if self.operations == "Update_Track_Number_And_Ship_Status":
            self.check_running_schedulers('ir_cron_auto_update_order_status_seller_')

        if self.operations == "Check_Cancel_Orders_FBM":
            self.check_running_schedulers('ir_cron_auto_check_canceled_fbm_order_in_amazon_seller_')

        if self.operations == "Import_Unshipped_Orders":
            self.check_running_schedulers('ir_cron_import_amazon_orders_seller_')

    @api.onchange('fba_operations')
    def onchange_fba_operations(self):
        """
        On change of fba_operations field it set start and end date as per configurations from
        seller
        default start date is -3 days from the date.
        @author: Keyur Kanani
        :return:
        """
        self.user_warning = None
        if self.fba_operations == "Shipment_Report":
            self.report_start_date = datetime.now() - timedelta(self.seller_id.shipping_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_import_amazon_fba_shipment_report_seller_')

        if self.fba_operations == "Customer_Return_Report":
            self.report_start_date = datetime.now() - timedelta(
                self.seller_id.customer_return_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_auto_import_customer_return_report_seller_')

        if self.fba_operations == "Stock_Adjustment_Report":
            self.report_start_date = datetime.now() - timedelta(
                self.seller_id.inv_adjustment_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_create_fba_stock_adjustment_report_seller_')

        if self.fba_operations == "Removal_Order_Report":
            self.report_start_date = datetime.now() - timedelta(
                self.seller_id.removal_order_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_create_fba_removal_order_report_seller_')

        if self.fba_operations == "fba_live_inventory_report":
            self.report_start_date = datetime.now() - timedelta(
                self.seller_id.live_inv_adjustment_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_import_stock_from_amazon_fba_live_report_')

        if self.fba_operations == "Import_Pending_Orders":
            self.check_running_schedulers('ir_cron_import_amazon_fba_pending_order_seller_')

        if self.fba_operations == "Import Inbound Shipment":
            self.check_running_schedulers('ir_cron_inbound_shipment_check_status_')

    @api.onchange('both_operations')
    def onchange_both_operations(self):
        """
        On change of fba_fbm_operations field it will check the active scheduler or scheduler
        exist then it's next run time.
        @author: Keyur Kanani
        :return:
        """
        self.user_warning = None
        if self.both_operations == "List_Settlement_Report":
            self.check_running_schedulers('ir_cron_auto_import_settlement_report_seller_')
        if self.both_operations == "request_rating_report":
            self.report_start_date = datetime.now() - timedelta(self.seller_id.rating_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_rating_request_report_seller_')
        if self.both_operations == "vcs_tax_report":
            self.report_start_date = datetime.now() - timedelta(self.seller_id.fba_vcs_report_days)
            self.report_end_date = datetime.now()
            self.check_running_schedulers('ir_cron_auto_import_vcs_tax_report_seller_')

    def check_running_schedulers(self, cron_xml_id):
        """
        use: 1. If scheduler is running for ron_xml_id + seller_id, then this function will
        notify user that
                the process they are doing will be running in the scheduler.
                if they will do this process then the result cause duplicate.
            2. Also if scheduler is in progress in backend then the execution will give UserError
            Popup
                and terminates the process until scheduler job is done.
        :param cron_xml_id: string[cron xml id]
        :return:
        """
        cron_id = self.env.ref('amazon_ept.%s%d' % (cron_xml_id, self.seller_id.id),
                               raise_if_not_found=False)
        if cron_id and cron_id.sudo().active:
            res = cron_id.try_cron_lock()
            if self._context.get('raise_warning', False) and res and res.get('reason', False):
                raise UserError(_("You are not allowed to run this Action. \n"
                                  "The Scheduler is already started the Process of Importing "
                                  "Orders."))
            if res and res.get('result', {}):
                self.user_warning = "This process is executed through scheduler also, " \
                                    "Next Scheduler for this process will run in %s Minutes" \
                                    % res.get('result', {})
            elif res and res.get('reason', False):
                self.user_warning = res.get('reason', {})

    def import_export_processes(self):
        """
        Import / Export Operations are managed from here.
        as per selection on wizard this function will execute

        Updated by : twinkalc on 7th jan 2021
        Updated code to process for inv report for UK or Pan Eu.
        :return: True
        """
        sale_order_obj = self.env['sale.order']
        fbm_sale_order_report_obj = self.env['fbm.sale.order.report.ept']
        customer_return_report_obj = self.env['sale.order.return.report']
        amazon_product_obj = self.env['amazon.product.ept']
        stock_adjustment_report_obj = self.env['amazon.stock.adjustment.report.history']
        removal_order_request_report_record = self.env['amazon.removal.order.report.history']
        amazon_removal_order_obj = self.env['amazon.removal.order.ept']
        import_shipment_obj = self.env['amazon.inbound.import.shipment.ept']
        rating_report_obj = self.env['rating.report.history']
        vcs_tax_report_obj = self.env['amazon.vcs.tax.report.ept']
        seller_pending_order_marketplaces = defaultdict(list)
        cancel_order_marketplaces = defaultdict(list)
        cancel_order_marketplaces_fbm = defaultdict(list)
        seller_stock_instance = defaultdict(list)
        export_product_price_instance = defaultdict(list)

        if self.both_operations == "List_Settlement_Report":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_auto_import_settlement_report_seller_')
            vals = {'report_type': 'GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2',
                    'name': 'Amazon Settlement Reports',
                    'model_obj': self.env['settlement.report.ept'],
                    'sequence': self.env.ref('amazon_ept.seq_import_settlement_report_job'),
                    'tree_id': self.env.ref('amazon_ept.amazon_settlement_report_tree_view_ept'),
                    'form_id': self.env.ref('amazon_ept.amazon_settlement_report_form_view_ept'),
                    'res_model': 'settlement.report.ept',
                    'start_date': self.report_start_date,
                    'end_date': self.report_end_date
                    }
            return self.get_reports(vals)
        if self.both_operations == "request_rating_report":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_rating_request_report_seller_')
            if not self.report_start_date or not self.report_end_date:
                raise UserError(_('Please select Date Range.'))

            rating_report_record = rating_report_obj.create({
                'seller_id': self.seller_id.id,
                'start_date': self.report_start_date,
                'end_date': self.report_end_date
            })
            return {
                'name': _('Rating Report Request History'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'rating.report.history',
                'type': 'ir.actions.act_window',
                'res_id': rating_report_record.id
            }
        if self.operations == 'Update_Track_Number_And_Ship_Status':
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_auto_update_order_status_seller_')
            return sale_order_obj.amz_update_tracking_number(self.seller_id)

        if self.operations == 'Import_FBM_Shipped_Orders':
            return sale_order_obj.import_fbm_shipped_or_missing_unshipped_orders(self.seller_id, self.instance_ids,
                                                                                 self.fbm_order_updated_after_date, ['Shipped'])
        if self.operations == 'Import_Missing_Unshipped_Orders':
            return sale_order_obj.import_fbm_shipped_or_missing_unshipped_orders(self.seller_id, self.instance_ids,
                                                                                 self.fbm_order_updated_after_date,
                                                                                 ['Unshipped', 'PartiallyShipped'])

        if self.operations == "Import_Unshipped_Orders":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_import_amazon_orders_seller_')
            report_type = 'GET_FLAT_FILE_ORDER_REPORT_DATA_INVOICING' if self.seller_id.is_european_region else \
                'GET_FLAT_FILE_ORDER_REPORT_DATA_TAX'
            record = fbm_sale_order_report_obj.create({
                'seller_id': self.seller_id.id,
                'report_type': report_type,
            })
            record.request_report()
            return {
                'name': _('FBM Sale Order'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'fbm.sale.order.report.ept',
                'type': 'ir.actions.act_window',
                'res_id': record.id
            }
        if self.fba_operations == "Shipment_Report":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_import_amazon_fba_shipment_report_seller_')
            if not self.report_start_date or not self.report_end_date:
                raise UserError(_('Please select Date Range.'))

            return self.create_and_request_amazon_shipment_report()

        if self.fba_operations == 'Customer_Return_Report':
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_auto_import_customer_return_report_seller_')
            customer_return_report_record = customer_return_report_obj.create({
                'seller_id': self.seller_id.id,
                'start_date': self.report_start_date,
                'end_date': self.report_end_date
            })
            customer_return_report_record.request_customer_return_report()
            return {
                'name': _('Customer Return Report'),
                'view_mode': 'form',
                'res_model': 'sale.order.return.report',
                'type': 'ir.actions.act_window',
                'res_id': customer_return_report_record.id
            }
        if self.fba_operations == "Stock_Adjustment_Report":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_create_fba_stock_adjustment_report_seller_')
            if not self.report_start_date or not self.report_end_date:
                raise UserError(_('Please select Date Range.'))

            stock_adjustment_report_record = stock_adjustment_report_obj.create({
                'seller_id': self.seller_id.id,
                'start_date': self.report_start_date,
                'end_date': self.report_end_date
            })
            stock_adjustment_report_record.request_report()
            return {
                'name': _('Stock Adjustment Report Request History'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'amazon.stock.adjustment.report.history',
                'type': 'ir.actions.act_window',
                'res_id': stock_adjustment_report_record.id
            }

        if self.fba_operations == 'fba_live_inventory_report':
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_import_stock_from_amazon_fba_live_report_')
            return self.get_amazon_fba_live_stock_report_ids()

        if self.fba_operations == "Removal_Order_Report":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_create_fba_removal_order_report_seller_')
            if not self.report_start_date or not self.report_end_date:
                raise UserError(_('Please select Date Range.'))

            removal_order_request_report_record = removal_order_request_report_record.create({
                'seller_id': self.seller_id.id,
                'start_date': self.report_start_date,
                'end_date': self.report_end_date
            })
            return {
                'name': _('Removal Order Report Request History'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'amazon.removal.order.report.history',
                'type': 'ir.actions.act_window',
                'res_id': removal_order_request_report_record.id
            }
        if self.fba_operations == "removal_order_request":
            if not self.order_removal_instance_id or self.order_removal_instance_id and not \
                    self.order_removal_instance_id.is_allow_to_create_removal_order:
                raise UserError(_(
                    'This Seller no any instance configure removal order Please configure removal '
                    'order configuration.'))

            amazon_removal_order_obj = amazon_removal_order_obj.create({
                'removal_disposition': 'Return',
                'warehouse_id': self.order_removal_instance_id and
                                self.order_removal_instance_id.removal_warehouse_id.id or
                                False,
                'ship_address_id': self.order_removal_instance_id.company_id.partner_id.id,
                'company_id': self.seller_id.company_id.id,
                'instance_id': self.order_removal_instance_id.id,
            })
            return {
                'name': _('Removal Order Request'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'amazon.removal.order.ept',
                'type': 'ir.actions.act_window',
                'res_id': amazon_removal_order_obj.id
            }

        if self.fba_operations == "Import Inbound Shipment":
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_inbound_shipment_check_status_')
            import_shipment_obj.get_inbound_import_shipment(self.instance_id,
                                                            self.from_warehouse_id,
                                                            self.shipment_id,
                                                            self.ship_to_address)

        if self.fba_operations == "Create_Inbound_Shipment_Plan":
            return self.wizard_create_inbound_shipment_plan(self.instance_id)

        if self.both_operations == 'vcs_tax_report':
            if not self.seller_id.is_vcs_activated:
                raise UserError(
                    _("Please Select Invoice Upload Policy as per Seller Central Configurations."))
            self.with_context({'raise_warning': True}).check_running_schedulers(
                'ir_cron_auto_import_vcs_tax_report_seller_')
            vcs_report = vcs_tax_report_obj.create(
                {'report_type': 'SC_VAT_TAX_REPORT',
                 'seller_id': self.seller_id.id,
                 'start_date': self.report_start_date,
                 'end_date': self.report_end_date,
                 'state': 'draft'})
            vcs_report.request_report()
            self.seller_id.write({'vcs_report_last_sync_on': self.report_end_date})
            return {
                'name': _('Amazon VCS Tax Reports'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'amazon.vcs.tax.report.ept',
                'type': 'ir.actions.act_window',
                'res_id': vcs_report.id
            }

        if self.both_operations == "Sync_Active_Products":
            return self.create_sync_active_products(self.seller_id, self.instance_id,
                                                    self.update_price_in_pricelist,
                                                    self.auto_create_product)

        if self.both_operations == "Import_Product":
            return self.import_csv_file()

        if self.instance_ids:
            instance_ids = self.instance_ids
        else:
            instance_ids = self.seller_id.instance_ids

        for instance in instance_ids:
            if self.fba_operations == "Check_Cancel_Orders_FBA":
                cancel_order_marketplaces[instance.seller_id].append(instance.market_place_id)
            if self.operations == 'Check_Cancel_Orders_FBM':
                self.with_context({'raise_warning': True}).check_running_schedulers(
                    'ir_cron_auto_check_canceled_fbm_order_in_amazon_seller_')
                cancel_order_marketplaces_fbm[instance.seller_id].append(instance.market_place_id)
            if self.fba_operations == "Import_Pending_Orders":
                self.with_context({'raise_warning': True}).check_running_schedulers(
                    'ir_cron_import_amazon_fba_pending_order_seller_')
                seller_pending_order_marketplaces[instance.seller_id].append(
                    instance.market_place_id)
            if self.operations == 'Export_Stock_From_Odoo_To_Amazon':
                self.with_context({'raise_warning': True}).check_running_schedulers(
                    'ir_cron_auto_export_inventory_seller_')
                seller_stock_instance[instance.seller_id].append(instance)
            if self.both_operations == 'Export_Price_From_Odoo_To_Amazon':
                export_product_price_instance[instance.seller_id].append(instance)

        if cancel_order_marketplaces:
            for seller, marketplaces in cancel_order_marketplaces.items():
                sale_order_obj.cancel_amazon_fba_pending_sale_orders(seller,
                                                                     marketplaceids=marketplaces,
                                                                     instance_ids=instance_ids.ids or [])
        if cancel_order_marketplaces_fbm:
            for seller, marketplaces in cancel_order_marketplaces_fbm.items():
                sale_order_obj.cancel_amazon_fbm_pending_sale_orders(seller,
                                                                     marketplaceids=marketplaces, \
                                                                     instance_ids=instance_ids.ids or [])
        if seller_pending_order_marketplaces:
            for seller, marketplaces in seller_pending_order_marketplaces.items():
                sale_order_obj.import_fba_pending_sales_order(seller, marketplaces,
                                                              self.updated_after_date)

        if seller_stock_instance:
            for seller, instance_ids in seller_stock_instance.items():
                for instance in instance_ids:
                    instance.export_stock_levels()
        if export_product_price_instance:
            for seller, instance_ids in export_product_price_instance.items():
                for instance in instance_ids:
                    amazon_products = amazon_product_obj.search(
                        [('instance_id', '=', instance.id), ('exported_to_amazon', '=', True)])
                    if amazon_products:
                        amazon_products.update_price(instance)
        return True

    def create_and_request_amazon_shipment_report(self):
        """
        This method will import FBA Shipping report from amazon as per provided
        start and end date and create attachment record in odoo for process that file.
        :return: ir.actions.act_window() action
        """
        fba_shipping_report_obj = self.env['shipping.report.request.history']
        shipment_tree_view = self.env.ref('amazon_ept.amazon_shipping_report_request_history_tree_view_ept')
        shipment_form_view = self.env.ref('amazon_ept.amazon_shipping_report_request_history_form_view_ept')
        shipping_report_record_list = []
        report_type = 'GET_AMAZON_FULFILLED_SHIPMENTS_DATA_INVOICING' if self.seller_id.is_european_region else \
            'GET_AMAZON_FULFILLED_SHIPMENTS_DATA_TAX'
        if self.seller_id.is_another_soft_create_fba_shipment:
            shipment_report_values = {'report_type': report_type,
                                      'name': 'FBA Shipping Report', 'model_obj': fba_shipping_report_obj,
                                      'sequence': False,
                                      'tree_id': shipment_tree_view, 'form_id': shipment_form_view,
                                      'res_model': 'shipping.report.request.history',
                                      'start_date': self.report_start_date, 'end_date': self.report_end_date}
            return self.get_reports(shipment_report_values)
        elif self.is_split_report and not self.split_report_by_days:
            raise UserError(_('Please select the Split Report By Days.'))
        elif self.is_split_report and self.split_report_by_days:
            start_date = self.report_start_date
            end_date = False

            while start_date <= self.report_end_date:
                if end_date:
                    start_date = end_date
                if start_date >= self.report_end_date:
                    break
                end_date = (start_date + timedelta(int(self.split_report_by_days))) - timedelta(1)
                if end_date > self.report_end_date:
                    end_date = self.report_end_date

                shipping_report_record = fba_shipping_report_obj.create({
                    'report_type': report_type,
                    'seller_id': self.seller_id.id,
                    'start_date': start_date,
                    'end_date': end_date
                })
                shipping_report_record.request_report()
                shipping_report_record_list.append(shipping_report_record.id)
        else:
            shipping_report_record = fba_shipping_report_obj.create({
                'report_type': report_type,
                'seller_id': self.seller_id.id,
                'start_date': self.report_start_date,
                'end_date': self.report_end_date
            })
            shipping_report_record.request_report()

        return {
            'name': _('FBA Shipping Report'),
            'view_mode': 'tree, form',
            'views': [(shipment_tree_view.id, 'tree'),
                      (shipment_form_view.id, 'form')],
            'res_model': 'shipping.report.request.history',
            'type': 'ir.actions.act_window',
            'res_id': shipping_report_record_list
        }

    def get_amazon_fba_live_stock_report_ids(self):
        """
        This method will help to import FBA Live Inventory report from amazon to odoo
        as per specific start and end date range.
        :return: ir.actions.act_window() action
        """
        amz_inventory_report_obj = self.env['amazon.fba.live.stock.report.ept']
        instance_ids = []
        start_date = end_date = report_date = False
        if self.seller_id.is_another_soft_create_fba_inventory:
            vals = {'start_date': self.report_start_date,
                    'end_date': self.report_end_date,
                    'seller_id': self.seller_id,
                    'us_region_instance_id': self.us_region_instance_id or self.mci_efn_instance_id or self.pan_eu_instance_id or False
                    }
            fba_live_stock_report = amz_inventory_report_obj.get_inventory_report(vals)
            return fba_live_stock_report

        if self.amazon_program in ('pan_eu', 'cep'):
            instance_ids = self.pan_eu_instance_id

        elif not self.seller_id.is_european_region and not self.seller_id.amz_fba_us_program == 'narf':
            report_date = datetime.now()
            instance_ids = self.us_region_instance_id if self.us_region_instance_id else self.seller_id.instance_ids

        elif self.amazon_program in ('mci', 'efn+mci', 'efn') or self.seller_id.amz_fba_us_program == 'narf':
            # If seller is NARF then pass Amazon.com marketplace
            # If seller is efn then must be pass seller efn inventory country marketplace.
            if self.amazon_program in ('mci', 'efn+mci'):
                instance_ids = self.mci_efn_instance_id if self.mci_efn_instance_id else self.seller_id.instance_ids
            elif self.seller_id.amz_fba_us_program == 'narf':
                instance_ids = self.seller_id.instance_ids.filtered(lambda instance: instance.market_place_id == 'ATVPDKIKX0DER')
            else:
                instance_ids = self.seller_id.instance_ids.filtered(
                    lambda instance: instance.country_id.id == self.seller_id.store_inv_wh_efn.id)
            start_date = (datetime.today().date() - timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            end_date = (datetime.today().date() - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')

        fba_live_stock_report_ids = amz_inventory_report_obj.create_and_request_amazon_live_inventory_report(
            self.seller_id, instance_ids, report_date, start_date, end_date)

        if fba_live_stock_report_ids:
            return self.return_fba_live_inventory_tree_form_view(fba_live_stock_report_ids)

    @staticmethod
    def return_fba_live_inventory_tree_form_view(fba_live_stock_report_ids):
        """
        This method will return fba live inventory report tree or form view.
        :param fba_live_stock_report_ids:
        :return: ir.actions.act_window() action
        """
        if len(fba_live_stock_report_ids) > 1:
            return {
                'name': _('FBA Live Stock Report'),
                'view_type': 'tree',
                'view_mode': 'tree',
                'res_model': 'amazon.fba.live.stock.report.ept',
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', fba_live_stock_report_ids)]
            }
        return {
            'name': _('FBA Live Stock Report'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'amazon.fba.live.stock.report.ept',
            'type': 'ir.actions.act_window',
            'res_id': fba_live_stock_report_ids[0]
        }

    def prepare_merchant_report_dict(self, seller):
        """
        Added by Udit
        :return: This method will prepare merchant' informational dictionary which will
                 passed to  amazon api calling method.
        """
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        return {
            'merchant_id': seller.merchant_id and str(seller.merchant_id) or False,
            'auth_token': seller.auth_token and str(seller.auth_token) or False,
            'app_name': 'amazon_ept_spapi',
            'account_token': account.account_token,
            'emipro_api': 'get_reports_sp_api',
            'dbuuid': dbuuid,
            'amazon_marketplace_code': seller.country_id.amazon_marketplace_code or
                                       seller.country_id.code,
        }

    def get_reports(self, report_values):
        """
        This method will get list of reports of pass report values from amazon operation
        and create it's record in odoo.
        :param: report_values : requested report values dict {}
        :return: This method will redirecting us to settlement report tree view.
        """

        tree_id = report_values.get('tree_id', False)
        form_id = report_values.get('form_id', False)
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select Seller'))
        start_date, end_date = self.get_fba_reports_date_format()
        kwargs = self.sudo().prepare_merchant_report_dict(seller)
        report_types = report_values.get('report_type', '')
        instances = seller.instance_ids
        marketplace_ids = tuple(map(lambda x: x.market_place_id, instances))
        kwargs.update({'report_type': [report_types], 'start_date': start_date, 'end_date': end_date,
                       "marketplaceids":marketplace_ids})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            return UserError(_(response.get('error', {})))
        list_of_wrapper = response.get('result', {})
        odoo_report_ids = self.get_amazon_fba_report_ids(
            list_of_wrapper, report_values.get('start_date', ''), report_values.get('end_date', ''),
            report_values.get('model_obj', False), report_values.get('sequence', ''))
        if self._context.get('is_auto_process', False):
            return odoo_report_ids
        return {
            'type': 'ir.actions.act_window',
            'name': report_values.get('name', ''),
            'res_model': report_values.get('res_model', ''),
            'domain': [('id', 'in', odoo_report_ids)],
            'views': [(tree_id.id, 'tree'), (form_id.id, 'form')],
            'view_id': tree_id.id,
            'target': 'current'
        }

    def get_fba_reports_date_format(self):
        """
        Added by Udit
        This method will convert selected time duration in specific format to send it to amazon.
        If start date and end date is empty then system will automatically select past 90 days
        time duration.
        :return: This method will return converted start and end date.
        """
        start_date = self.report_start_date
        end_date = self.report_end_date
        if start_date:
            db_import_time = time.strptime(str(start_date), "%Y-%m-%d %H:%M:%S")
            db_import_time = time.strftime("%Y-%m-%dT%H:%M:%S", db_import_time)
            start_date = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(
                time.mktime(time.strptime(db_import_time, "%Y-%m-%dT%H:%M:%S"))))
            start_date = str(start_date) + 'Z'
        else:
            today = datetime.now()
            earlier = today - timedelta(days=90)
            earlier_str = earlier.strftime("%Y-%m-%dT%H:%M:%S")
            start_date = earlier_str + 'Z'
        if end_date:
            db_import_time = time.strptime(str(end_date), "%Y-%m-%d %H:%M:%S")
            db_import_time = time.strftime("%Y-%m-%dT%H:%M:%S", db_import_time)
            end_date = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(
                time.mktime(time.strptime(db_import_time, "%Y-%m-%dT%H:%M:%S"))))
            end_date = str(end_date) + 'Z'
        else:
            today = datetime.now()
            earlier_str = today.strftime("%Y-%m-%dT%H:%M:%S")
            end_date = earlier_str + 'Z'
        return start_date, end_date

    def get_amazon_fba_report_ids(self, list_of_wrapper, start_date, end_date, model_obj, sequence):
        """
        This method will create requested report record in odoo from the amazon spa pi response.
        :param list_of_wrapper: Dictionary of amazon api response.
        :param start_date: Selected start date in wizard in specific format.
        :param end_date: Selected end date in wizard in specific format.
        :param model_obj: requested reports model object
        :param sequence: requested reports sequence
        :return: This method will return list of newly created report ids.
        """
        odoo_report_ids = []
        list_of_wrapper = list_of_wrapper.get('reports', {}) if list_of_wrapper else []
        for report in list_of_wrapper:
            request_id = report.get('reportDocumentId', '')
            report_id = report.get('reportId', '')
            report_type = report.get('reportType', '')
            report_exist = model_obj.search(
                ['|', ('report_document_id', '=', request_id), ('report_id', '=', report_id),
                 ('report_type', '=', report_type)])
            if report_exist:
                report_exist = report_exist[0]
                odoo_report_ids.append(report_exist.id)
                continue
            report_values = self.prepare_amazon_fba_report_values(
                report_type, request_id, report_id, start_date, end_date, sequence)
            report_rec = model_obj.create(report_values)
            report_rec.get_report()
            self._cr.commit()
            odoo_report_ids.append(report_rec.id)
        return odoo_report_ids

    def prepare_amazon_fba_report_values(self, report_type, report_document_id, report_id, start_date,
                                         end_date, sequence):
        """
        Added by Udit
        :param report_type: Report type.
        :param report_document_id: Amazon report document id.
        :param report_id: Amazon report id.
        :param start_date: Selected start date in wizard in specific format.
        :param end_date: Selected end date in wizard in specific format.
        :return: This method will prepare and return settlement report vals.
        """
        try:
            if sequence:
                report_name = sequence.next_by_id()
            else:
                report_name = '/'
        except:
            report_name = '/'
        return {
            'name': report_name,
            'report_type': report_type,
            'report_document_id': report_document_id,
            'report_id': report_id,
            'start_date': start_date,
            'end_date': end_date,
            'state': 'DONE',
            'seller_id': self.seller_id.id,
            'user_id': self._uid,
        }

    def create_sync_active_products(self, seller_id, instance_id,
                                    update_price_in_pricelist, auto_create_product):
        """
            Process will create record of Active Product List of selected seller and instance
            @:param - seller_id - selected seller from wizard
            @:param - instance_id - selected instance from wizard
            @:param - update_price_in_pricelist - Boolean for create pricelist or not
            @:param - auto_create_product - Boolean for create product or not
            @author: Deval Jagad (16/11/2019)
        """
        if not instance_id:
            raise UserError(_('Please Select Instance'))
        active_product_listing_obj = self.env['active.product.listing.report.ept']
        form_id = self.env.ref('amazon_ept.active_product_listing_form_view_ept')
        vals = {'instance_id': instance_id.id,
                'seller_id': seller_id.id,
                'update_price_in_pricelist': update_price_in_pricelist or False,
                'auto_create_product': auto_create_product or False
                }

        active_product_listing = active_product_listing_obj.create(vals)
        try:
            active_product_listing.request_report()
        except Exception as exception:
            raise UserError(_(exception))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Active Product List',
            'res_model': 'active.product.listing.report.ept',
            'res_id': active_product_listing.id,
            'views': [(form_id.id, 'form')],
            'view_id': form_id.id,
            'target': 'current'
        }

    def download_sample_attachment(self):
        """
        This Method relocates download sample file of amazon.
        :return: This Method return file download file.
        @author: Deval Jagad (26/12/2019)
        """
        attachment = self.env['ir.attachment'].search([('name', '=', 'import_product_sample.xlsx'),
                                                       ('res_model', '=', 'amazon.process.import.export')])
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % (attachment.id),
            'target': 'new',
            'nodestroy': False,
        }

    def import_csv_file(self):
        """
        This Method relocates Import product csv in amazon listing and mapping of amazon product listing.
        """
        if not self.choose_file:
            raise UserError(_('Please Upload File.'))
        if os.path.splitext(self.file_name)[1].lower() not in ['.csv', '.xls', '.xlsx']:
            raise ValidationError(_("Invalid file format. You are only allowed to upload .csv, .xls or .xlsx file."))
        log_rec = self.create_amz_product_map_log()
        if os.path.splitext(self.file_name)[1].lower() == '.csv':
            map_products_count, log_rec = self.amz_map_import_csv_ept(log_rec)
        else:
            map_products_count, log_rec = self.amz_map_import_xls_ept(log_rec)
        if not log_rec.log_lines:
            log_rec.unlink()
        message = ("%s Products Imported Successfully!" % map_products_count) if map_products_count else "All Products Skipped!!, Please check Log Book."
        rainbow = {
            'effect': {
                'fadeout': 'none',
                'message': message,
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }
        mismatch_log_lines = log_rec.log_lines.filtered('mismatch_details').mapped('display_name')
        mismatch_logs = ', '.join(mismatch_log_lines) if mismatch_log_lines else ''
        if mismatch_logs:
            rainbow['effect'].update({'message': f'Some of the products are not imported you can check the logs: '
                                                 f'{mismatch_logs}'})
        return rainbow

    def amz_map_import_csv_ept(self, log_rec):
        """
        This method will help to read imported csv file.
        :param: log_rec: common.log.book.ept() object
        :return: mapped products count (int), common.log.book.ept() object
        """
        try:
            data = StringIO(base64.b64decode(self.choose_file).decode())
        except Exception:
            data = StringIO(base64.b64decode(self.choose_file).decode('ISO-8859-1'))
        content = data.read()
        delimiter = ('\t', csv.Sniffer().sniff(content.splitlines()[0]).delimiter)[bool(content)]
        csv_reader = csv.DictReader(content.splitlines(), delimiter=delimiter)
        headers = csv_reader.fieldnames
        # read imported file header is valid or not
        self.amz_read_import_file_header(headers)
        instance_dict = {}
        map_product_count = 0
        row_no = 1
        for line in csv_reader:
            row_no += 1
            skip_line = self.amz_read_import_file_with_product_list(line, row_no, log_rec)
            if not skip_line:
                instance_dict, map_product_count = self.amz_mapped_imports_products_ept(
                    line, instance_dict, map_product_count, log_rec)
        return map_product_count, log_rec

    def amz_map_import_xls_ept(self, log_rec):
        """
        This method will help to read imported xls or xlsx file.
        :param: common.log.book.ept() object
        :return: mapped products count (int), common.log.book.ept() object
        """
        sheets = xlrd.open_workbook(file_contents=base64.b64decode(self.choose_file.decode('UTF-8')))
        header = dict()
        is_header = False
        instance_dict = {}
        map_product_count = 0
        row_number = 1
        for sheet in sheets.sheets():
            for row_no in range(sheet.nrows):
                if not is_header:
                    headers = [d.value for d in sheet.row(row_no)]
                    # read imported file header is valid or not
                    self.amz_read_import_file_header(headers)
                    [header.update({d: headers.index(d)}) for d in headers]
                    is_header = True
                    continue
                row = dict()
                [row.update({k: sheet.row(row_no)[v].value}) for k, v in header.items() for c in
                 sheet.row(row_no)]
                row_number += 1
                skip_line = self.amz_read_import_file_with_product_list(row, row_number, log_rec)
                if not skip_line:
                    instance_dict, map_product_count = self.amz_mapped_imports_products_ept(
                        row, instance_dict, map_product_count, log_rec)
        return map_product_count, log_rec

    def amz_mapped_imports_products_ept(self, line, instance_dict, map_product_count, log_rec):
        """
        This method will map amazon products with odoo products.
        :line: Iterable line of imported file
        :instance_dict : {} {amazon_marketplace: amazon.instance.ept() object}
        :map_product_count : int total mapped products count
        :log_rec : common.log.book() object
        :return : instances dict - {}, mapped products count - int
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        product_obj = self.env["product.product"]
        amazon_product_ept_obj = self.env['amazon.product.ept']
        model_id = common_log_line_obj.get_model_id('product.product')
        amz_product_model_id = common_log_line_obj.get_model_id('amazon.product.ept')
        odoo_default_code = line.get('Internal Reference', '')
        seller_sku = line.get('Seller SKU', '')
        amazon_marketplace = line.get('Marketplace', '')
        fulfillment = line.get('Fulfillment', '')
        instance = False

        if amazon_marketplace:
            instance = instance_dict.get(amazon_marketplace)
            if not instance:
                instance = self.seller_id.instance_ids.filtered(
                    lambda l: l.marketplace_id.name == amazon_marketplace)
                instance_dict.update({amazon_marketplace: instance})

        if fulfillment not in ['FBA', 'FBM']:
            message = "Fulfillment_by should be FBA or FBM"
            common_log_line_obj.amazon_create_product_log_line(
                message, model_id, False, seller_sku, False, log_rec, mismatch=True)
            return instance_dict, map_product_count

        if not instance:
            message = """Amazon Marketplace Name[%s] not valid for seller sku %s and Internal Reference %s""" \
                      % (amazon_marketplace, seller_sku, odoo_default_code)
            common_log_line_obj.amazon_create_product_log_line(
                message, model_id, False, seller_sku, fulfillment, log_rec, mismatch=True)
            return instance_dict, map_product_count

        if instance and fulfillment and seller_sku:
            if not odoo_default_code:
                message = """Internal Reference Not found for seller sku %s""" % (seller_sku)
                common_log_line_obj.amazon_create_product_log_line(
                    message, model_id, False, seller_sku, fulfillment, log_rec, mismatch=True)
                return instance_dict, map_product_count

            product_id = product_obj.search(['|', ("default_code", "=ilike", odoo_default_code),
                                             ("barcode", "=ilike", odoo_default_code)], limit=1)
            amazon_product_id = amazon_product_ept_obj.search_amazon_product(instance.id, seller_sku,
                                                                             fulfillment_by=fulfillment)
            mismatch = False
            if amazon_product_id and amazon_product_id.product_id.id != product_id.id:
                if product_id:
                    amazon_product_id.product_id = product_id
                    message = """Odoo Product [%s] has been updated for Seller Sku [%s]""" \
                              % (odoo_default_code, seller_sku)
                else:
                    message = """Odoo Product not found for internal reference [%s]""" \
                              % (odoo_default_code)
                    mismatch = True
                if message:
                    common_log_line_obj.amazon_create_product_log_line(
                        message, model_id, amazon_product_id.product_id, seller_sku, fulfillment, log_rec,
                        mismatch=mismatch)
                return instance_dict, map_product_count

            if amazon_product_id:
                message = """Amazon product found for seller sku %s and Internal Reference %s""" \
                          % (seller_sku, odoo_default_code)
                common_log_line_obj.amazon_create_product_log_line(
                    message, model_id, amazon_product_id.product_id, seller_sku, fulfillment, log_rec)
                return instance_dict, map_product_count

            if not product_id:
                product_id = self.get_odoo_product_csv_data_ept(line, fulfillment, log_rec)
            if not product_id:
                return instance_dict, map_product_count

            self.create_amazon_listing(instance, product_id, line)
            map_product_count += 1
            message = """ Amazon product created for seller sku %s || Instance %s and mapped with odoo product %s """ % (
                seller_sku, instance.name, product_id.name)
            common_log_line_obj.amazon_create_product_log_line(
                message, amz_product_model_id, product_id, seller_sku, fulfillment, log_rec)

        return instance_dict, map_product_count

    def create_amz_product_map_log(self):
        log_book_obj = self.env['common.log.book.ept']
        log_vals = {
            'active': True,
            'type': 'import',
            'model_id': self.env['ir.model']._get('amazon.product.ept').id,
            'res_id': self.id,
            'module': 'amazon_ept'
        }
        log_rec = log_book_obj.create(log_vals)
        return log_rec

    def amz_read_import_file_with_product_list(self, line, row_number, log_rec):
        """
        This method read import csv, xls or xlsx file and check file columns name are valid name
        or columns entries of Title,Seller SKU,Internal Reference,Marketplace or Fulfillment
        are fill or not.If either Column name invalid or missing then create log record also
        create log record if column field are blank.
        :param : line - Iterable line of csv file
        :param : row_number - imported file line number
        :param : log_rec - object of common log book model
        :return: This Method return boolean(True/False).
        @author: Kishan Sorani
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id('product.product')
        seller_sku = line.get('Seller SKU')
        fullfillment_by = line.get('Fulfillment')
        skip_line = False
        if not line.get('Seller SKU'):
            message = "Line is skipped Seller SKU is required to create an product at line %s" % (row_number)
            common_log_line_obj.amazon_create_product_log_line(message, model_id, False, seller_sku, fullfillment_by,
                                                               log_rec, mismatch=True)
            skip_line = True
        elif self.auto_create_product and not line.get('Title'):
            message = 'Line is skipped Title is required to create an product at line %s' % (row_number)
            common_log_line_obj.amazon_create_product_log_line(message, model_id, False, seller_sku, fullfillment_by,
                                                               log_rec, mismatch=True)
            skip_line = True
        elif not line.get('Internal Reference'):
            message = 'Line is skipped Internal Reference is required to create an product at line %s' % (row_number)
            common_log_line_obj.amazon_create_product_log_line(message, model_id, False, seller_sku, fullfillment_by,
                                                               log_rec, mismatch=True)
            skip_line = True
        elif not line.get('Marketplace'):
            message = 'Line is skipped Marketplace is required to create an product at line %s' % (row_number)
            common_log_line_obj.amazon_create_product_log_line(message, model_id, False, seller_sku, fullfillment_by,
                                                               log_rec, mismatch=True)
            skip_line = True
        elif not line.get('Fulfillment'):
            message = 'Line is skipped Fulfillment is required to create an product at line %s' % (row_number)
            common_log_line_obj.amazon_create_product_log_line(message, model_id, False, seller_sku, fullfillment_by,
                                                               log_rec, mismatch=True)
            skip_line = True
        return skip_line

    def amz_read_import_file_header(self, headers):
        """
        This method read import file headers name are correct or not.
        :param : headers - list of import file headers
        :return: This Method return boolean(True/False).
        @author: Kishan Sorani
        """
        skip_header = False
        if self.auto_create_product and headers[0] != 'Title' or headers[1] != 'Internal Reference' or \
                headers[2] != 'Seller SKU' or headers[3] != 'Marketplace' or headers[4] != 'Fulfillment':
            skip_header = True
        if skip_header:
            raise UserError(_("The Header of this report must be correct,"
                              " Please contact Emipro Support for further Assistance."))
        return True

    def get_odoo_product_csv_data_ept(self, line_vals, fullfillment_by, log_rec):
        """
        This method will get the product vals and  find or create the odoo product.
        :param line_vals : csv file line data.
        return : odoo product.
        """
        product_obj = self.env['product.product']
        amazon_product_ept_obj = self.env['amazon.product.ept']
        comman_log_line_obj = self.env['common.log.lines.ept']
        model_id = comman_log_line_obj.get_model_id('product.product')
        amazon_product_name = line_vals.get('Title', '')
        odoo_default_code = line_vals.get('Internal Reference', '')
        seller_sku = line_vals.get('Seller SKU', '')

        amazon_product = amazon_product_ept_obj.search(['|', ('active', '=', False), ('active', '=', True),
                                                        ('seller_sku', '=', seller_sku)], limit=1)
        product_id = amazon_product.product_id if amazon_product else False

        if not product_id and self.auto_create_product:
            odoo_product_dict = {
                'name': amazon_product_name,
                'default_code': odoo_default_code,
                'type': 'product'
            }
            product_id = product_obj.create(odoo_product_dict)

            message = """ Odoo Product created for seller sku %s and Internal Reference %s """ % (
                seller_sku, odoo_default_code)
            comman_log_line_obj.amazon_create_product_log_line(
                message, model_id, product_id, seller_sku, fullfillment_by, log_rec)
        if not product_id:
            message = """ Line Skipped due to product not found seller sku %s || Internal 
                                Reference %s """ % (seller_sku, odoo_default_code)
            comman_log_line_obj.amazon_create_product_log_line(
                message, model_id, False, seller_sku, fullfillment_by, log_rec, mismatch=True)

        return product_id

    def create_amazon_listing(self, instance, product_id, line_vals):
        """
        This Method relocates if product exist in odoo and product doesn't exist in
        amazon create amazon product listing.
        :param instance: This arguments relocates instance of amazon.
        :param product_id: product record
        :param line_vals: amazon listing line vals
        :return: This method return boolean(True/False).
        @author: Deval Jagad (26/12/2019)
        """
        amazon_product_ept_obj = self.env['amazon.product.ept']
        amazon_product_name = line_vals.get('Title', '')
        seller_sku = line_vals.get('Seller SKU', '')
        fulfillment = line_vals.get('Fulfillment', '')

        amazon_product_ept_obj.create({'name': amazon_product_name or product_id.name,
                                       'fulfillment_by': fulfillment, 'product_id': product_id.id,
                                       'seller_sku': seller_sku, 'instance_id': instance.id,
                                       'exported_to_amazon': True})
        return True

    def wizard_create_inbound_shipment_plan(self, instance):
        """
        This method will create shipment plan record of selected seller and instance
        :return:
        """
        if not instance:
            raise UserError(_('Please Select Instance'))
        inbound_shipment_plan_obj = self.env['inbound.shipment.plan.ept']
        form_id = self.env.ref('amazon_ept.inbound_shipment_plan_form_view')
        warehouse_id = instance.warehouse_id
        vals = {'instance_id': instance.id,
                'warehouse_id': warehouse_id.id,
                'ship_from_address_id': warehouse_id.partner_id and warehouse_id.partner_id.id,
                'company_id': instance.company_id and instance.company_id.id,
                'ship_to_country': instance.country_id and instance.country_id.id}
        shipment_plan_id = inbound_shipment_plan_obj.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Inbound Shipment Plan',
            'res_model': 'inbound.shipment.plan.ept',
            'res_id': shipment_plan_id.id,
            'views': [(form_id.id, 'form')],
            'view_id': form_id.id,
            'target': 'current'
        }
