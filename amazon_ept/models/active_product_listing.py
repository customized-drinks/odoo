# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Added class ActiveProductListingReportEpt and added function to request for the active
product report and get the active product from the amazon and process to sync the product
and process to create the odoo and amazon product.
"""

import base64
import csv
import os
import time
from io import StringIO
from io import BytesIO
import re

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError
from odoo.tools.misc import xlsxwriter

from ..endpoint import DEFAULT_ENDPOINT


class ActiveProductListingReportEpt(models.Model):
    """
    Added class to process for get amazon product report and process to create odoo and amazon
    product
    """
    _name = "active.product.listing.report.ept"
    _description = "Active Product"
    _inherit = ['mail.thread']
    _order = 'id desc'

    @api.model
    @api.depends('seller_id')
    def _compute_company(self):
        """
        The below method sets company in a particular record
        of Sync Active Product Listing.
        :return:
        """
        for record in self:
            company_id = record.seller_id.company_id.id if record.seller_id else False
            if not company_id:
                company_id = self.env.company.id
            record.company_id = company_id

    def _compute_log_count(self):
        """
        Find all stock moves associated with this report
        :return:
        """
        log_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('active.product.listing.report.ept').id
        log_ids = log_obj.search([('res_id', '=', self.id), ('model_id', '=', model_id)]).ids
        self.log_count = log_ids.__len__()

        # Set the boolean field mismatch_details as True if found mismatch details in log lines
        if self.env['common.log.lines.ept'].search_count([('log_book_id', 'in', log_ids),
                                                          ('mismatch_details', '=', True)]):
            self.mismatch_details = True
        else:
            self.mismatch_details = False

    name = fields.Char(size=256, help='Record number')
    instance_id = fields.Many2one('amazon.instance.ept', string='Instance', help='Record of instance')
    report_id = fields.Char('Report ID', readonly='1', help='ID of report')
    report_request_id = fields.Char('Report Request ID', readonly='1', help='Request ID of the report')
    attachment_id = fields.Many2one('ir.attachment', string='Attachment', help='Record of attachment')
    report_type = fields.Char(size=256, help='Type of report')
    state = fields.Selection([('draft', 'Draft'), ('_SUBMITTED_', 'SUBMITTED'), ('_IN_PROGRESS_', 'IN_PROGRESS'),
                              ('_CANCELLED_', 'CANCELLED'), ('_DONE_', 'DONE'), ('CANCELLED', 'CANCELLED'),
                              ('SUBMITTED', 'SUBMITTED'), ('DONE', 'DONE'), ('FATAL', 'FATAL'),
                              ('IN_PROGRESS', 'IN_PROGRESS'), ('IN_QUEUE', 'IN_QUEUE'),
                              ('_DONE_NO_DATA_', 'DONE_NO_DATA'), ('processed', 'PROCESSED'),
                              ('imported', 'Imported'), ('partially_processed', 'Partially Processed'),
                              ('closed', 'Closed')], string='Report Status', default='draft', help='State of record')
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False, help='ID of seller')
    user_id = fields.Many2one('res.users', string="Requested User", help='ID of user')
    company_id = fields.Many2one('res.company', string="Company", copy=False,
                                 compute="_compute_company", store=True, help='ID of company')
    update_price_in_pricelist = fields.Boolean(string='Update price in pricelist?', default=False,
                                               help='Update or create product line in pricelist if ticked.')
    auto_create_product = fields.Boolean(string='Auto create product?', default=False,
                                         help='Create product in ERP if not found.')
    log_count = fields.Integer(compute="_compute_log_count", string="Log Counter",
                               help="Count number of created Stock Move")
    report_document_id = fields.Char(string='Report Document Reference', help='Request Document ID')
    mismatch_details = fields.Boolean(compute='_compute_log_count', string='Mismatch Details',
                                      help='True if found mismatch details in log line')
    last_sync_line = fields.Integer(string="Last sync line",
                                    help="Used to identify the last process line of active products listing report.")

    def list_of_process_logs(self):
        """
        This method return list of log view records of Sync Active Product Listing model.
        :return: ir.actions.act_window() action
        """
        model_id = self.env['ir.model']._get('active.product.listing.report.ept').id
        action = {
            'domain': "[('res_id', '=', " + str(self.id) + " ),('model_id','='," + str(
                model_id) + ")]",
            'name': 'Active Product Logs',
            'view_mode': 'tree,form',
            'res_model': 'common.log.book.ept',
            'type': 'ir.actions.act_window',
        }
        return action

    @api.model
    def create(self, vals):
        """
        Inherited method to sets name of a particular record as per the sequence.
        :param vals: dict {} for create record for Sync Active Product Listing
        :return: active.product.listing.report.ept() object
        """
        sequence = self.env.ref('amazon_ept.seq_active_product_list', raise_if_not_found=False)
        report_name = sequence.next_by_id() if sequence else '/'
        vals.update({'name': report_name})
        return super(ActiveProductListingReportEpt, self).create(vals)

    def update_report_history(self, request_result):
        """
         Define method for updates the report history and changes state of a particular record.
        :param request_result:
        :return: boolean (TRUE/FALSE)
        """
        report_id = request_result.get('reportId', '')
        report_document_id = request_result.get('reportDocumentId', '')
        report_state = request_result.get('processingStatus', 'SUBMITTED')
        product_listing_values = {}
        if report_document_id:
            product_listing_values.update({'report_document_id': report_document_id})
        if report_state:
            product_listing_values.update({'state': report_state})
        if report_id:
            product_listing_values.update({'report_id': report_id})
        self.write(product_listing_values)
        return True

    def get_product_report_request_args(self, seller, emipro_api):
        """
        Defined method to optimise the code and used to request for amazon product
        operations.
        :param seller: amazon.seller.ept() object
        :param emipro_api: api name for get response from amazon
        :return: dict {}
        """
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        kwargs = {'merchant_id': seller.merchant_id and str(seller.merchant_id) or False,
                  'app_name': 'amazon_ept_spapi',
                  'account_token': account.account_token,
                  'emipro_api': emipro_api,
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': seller.country_id.amazon_marketplace_code or
                                             seller.country_id.code,}
        return kwargs

    def request_report(self):
        """
        Define method for request report based on the spapi.
        :return: boolean(TRUE/FALSE)
        """
        seller = self.instance_id.seller_id
        if not seller:
            raise UserError(_('Please select instance'))
        marketplace_ids = tuple([self.instance_id.market_place_id])
        kwargs = self.get_product_report_request_args(seller, 'create_marketplace_report_sp_api')
        kwargs.update({'marketplace_ids': marketplace_ids,
                       'report_type': self.report_type or 'GET_MERCHANT_LISTINGS_DATA',})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            raise UserError(_(response.get('error')))
        result = response.get('result', {})
        self.update_report_history(result)
        return True

    def get_report_request_list(self):
        """
        Define method for checks status and gets the report list based on the sp api.
        :return: boolean(TRUE/FALSE)
        """
        self.ensure_one()
        seller = self.instance_id.seller_id
        if not seller:
            raise UserError(_('Please select Seller'))
        if not self.report_id:
            return True
        kwargs = self.get_product_report_request_args(seller, 'get_report_sp_api')
        kwargs.update({'report_id': self.report_id})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            raise UserError(_(response.get('error')))
        result = response.get('result', {})
        self.update_report_history(result)
        if self.state in ['_DONE_', 'DONE'] and self.report_document_id:
            self.get_report()
        return True

    def get_report(self):
        """
        Define method for gets the record of the report and also adds the same as an attachment
        based on the sp api.
        :return: boolean(TRUE/FALSE)
        """
        self.ensure_one()
        seller = self.instance_id.seller_id
        if not seller:
            raise UserError(_('Please select seller'))
        if not self.report_document_id:
            return True
        kwargs = self.get_product_report_request_args(seller, 'get_report_document_sp_api')
        kwargs.update({'reportDocumentId': self.report_document_id,})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            raise UserError(_(response.get('error')))
        result = response.get('result', {})
        result = result.get('document', '')
        result = result.encode()
        result = base64.b64encode(result)
        file_name = "Active_Product_List_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': result,
            'res_model': 'mail.compose.message',
            'type': 'binary'
        })
        self.message_post(body=_("<b>Active Product Report Downloaded</b>"),
                          attachment_ids=attachment.ids)
        self.write({'attachment_id': attachment.id})
        return True

    def download_report(self):
        """
        Define method for downloads the report in excel format.
        :return: An action containing URL of excel attachment or bool
        """
        self.ensure_one()
        # Get filestore path of an attachment and create new excel file there.
        file_store = self.env["ir.attachment"]._filestore()
        file_name = file_store + "/Active_Product_List_" + time.strftime("%Y_%m_%d_%H%M%S") + '.xlsx'
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet()
        header_format = workbook.add_format({'bold': True})
        # Collect data from csv attachment file and convert it to excel.
        data = StringIO(base64.b64decode(self.attachment_id.datas).decode('utf-8'))
        reader = csv.reader(data, delimiter='\t')
        for r, row in enumerate(reader):
            for c, col in enumerate(row):
                if r == 0:
                    worksheet.write(r, c, col, header_format)
                    continue
                else:
                    if bool(re.match('^(?=.)([+-]?([0-9]*)(\.([0-9]+))?)$', col)):
                        col = float(col)
                    worksheet.write(r, c, col)
        workbook.close()
        # Create file pointer of excel file for reading purpose.
        excel_file = open(file_name, "rb")
        file_pointer = BytesIO(excel_file.read())
        file_pointer.seek(0)
        # Create an attachment from that file pointer.
        new_attachment = self.env['ir.attachment'].create({
            "name": "Active_Product_List_" + time.strftime("%Y_%m_%d_%H%M%S"),
            "datas": base64.b64encode(file_pointer.read()),
            "type": "binary"
        })
        # Close file pointer and file and remove file from filestore.
        file_pointer.close()
        excel_file.close()
        os.remove(file_name)
        # Download an attachment if it is created.
        if new_attachment:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % new_attachment.id,
                'target': 'self',
            }
        return False

    def reprocess_sync_products(self):
        """
        Define method to reprocess of sync products and delete previous logs.
        :return:
        """
        model_id = self.env['ir.model']._get('active.product.listing.report.ept').id
        previous_logs = self.env["common.log.book.ept"].search([('res_id', '=', self.id), ('model_id', '=', model_id)])
        if previous_logs:
            previous_logs.unlink()
        self.sync_products()

    @staticmethod
    def get_fulfillment_type(fulfillment_channel):
        """
        Define method for returns the fulfillment type value.
        :param fulfillment_channel: amazon fulfillment channel
        :return: amazon fulfillment
        """
        if fulfillment_channel and fulfillment_channel == 'DEFAULT':
            return 'FBM'  # 'MFN'
        return 'FBA'  # 'AFN'

    def update_pricelist_items(self, seller_sku, price):
        """
        Define method for creates or updates the price of a product in the pricelist.
        :param seller_sku: seller sku
        :param price: sync active product price
        :return:
        """
        pricelist_item_obj = self.env['product.pricelist.item']
        product_obj = self.env['product.template']
        if self.instance_id.pricelist_id and self.update_price_in_pricelist:
            item = self.instance_id.pricelist_id.item_ids.filtered(
                lambda i: i.product_tmpl_id.default_code == seller_sku)
            if item and not item.fixed_price == float(price):
                item.fixed_price = price
            if not item:
                product = product_obj.search([('default_code', '=', seller_sku)])
                pricelist_item_obj.create({'product_tmpl_id': product.id,
                                           'min_quantity': 1,
                                           'fixed_price': price,
                                           'pricelist_id': self.instance_id.pricelist_id.id})

    def sync_products(self):
        """
        Define method for syncs the amazon products and also creates record of log if error is generated.
        :return: boolean(TRUE/FALSE)
        """
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))
        if not self.instance_id:
            raise UserError(_("Instance not found "))
        if not self.instance_id.pricelist_id:
            raise UserError(_("Please configure Pricelist in Amazon Marketplace"))
        amazon_product_ept_obj = self.env['amazon.product.ept']
        product_obj = self.env['product.product']
        log_book_obj = self.env['common.log.book.ept']
        common_log_line_obj = self.env['common.log.lines.ept']
        log_model_id = common_log_line_obj.get_model_id('active.product.listing.report.ept')
        model_id = common_log_line_obj.get_model_id('product.product')
        log_rec = log_book_obj.search([('module', '=', 'amazon_ept'),
                                       ('model_id', '=', log_model_id),
                                       ('res_id', '=', self.id)], limit=1)
        if not log_rec:
            log_rec = log_book_obj.amazon_create_transaction_log('import', log_model_id, self.id)
        imp_file = StringIO(base64.b64decode(self.attachment_id.datas).decode())
        reader = csv.DictReader(imp_file, delimiter='\t')
        price_list_id = self.instance_id.pricelist_id
        # get import file headers name
        headers = reader.fieldnames
        process_count = 0
        skip_header = self.read_import_file_header(headers, model_id, log_rec, common_log_line_obj)
        if skip_header:
            raise UserError(_("The Header of this report must be in English Language,"
                              " Please contact Emipro Support for further Assistance."))
        for row in reader:
            if reader.line_num <= self.last_sync_line:
                continue
            if 'fulfilment-channel' in row.keys():
                fulfillment_type = self.get_fulfillment_type(row.get('fulfilment-channel', ''))
            else:
                fulfillment_type = self.get_fulfillment_type(row.get('fulfillment-channel', ''))
            seller_sku = row.get('seller-sku', '').strip()
            odoo_product_id = product_obj.search(
                ['|', ('default_code', '=ilike', seller_sku), ('barcode', '=ilike', seller_sku)])
            amazon_product_id = amazon_product_ept_obj.search_amazon_product(
                self.instance_id.id, seller_sku, fulfillment_by=fulfillment_type)
            if not amazon_product_id and not odoo_product_id:
                amazon_product = amazon_product_ept_obj.search(
                    ['|', ('active', '=', False), ('active', '=', True), ('seller_sku', '=', seller_sku)], limit=1)
                odoo_product_id = amazon_product.product_id
            if amazon_product_id:
                self.create_or_update_amazon_product_ept(amazon_product_id, amazon_product_id.product_id.id,
                                                         fulfillment_type, row)
                if self.update_price_in_pricelist and row.get('price', False):
                    price_list_id.set_product_price_ept(amazon_product_id.product_id.id, float(row.get('price')))
            else:
                if len(odoo_product_id.ids) > 1:
                    seller_sku = row.get('seller-sku', '').strip()
                    message = """Multiple product found for same sku %s in ERP """ % (seller_sku)
                    common_log_line_obj.amazon_create_product_log_line(
                        message, model_id, False, seller_sku, fulfillment_type, log_rec, mismatch=True)
                    continue
                self.create_odoo_or_amazon_product_ept(odoo_product_id, fulfillment_type, row, log_rec)
                process_count += 1
            if process_count >= 100:
                process_count = 0
                self.write({'last_sync_line': reader.line_num})
                self._cr.commit()
        if not log_rec.log_lines:
            log_rec.unlink()
        self.write({'state': 'processed'})
        return True

    def read_import_file_header(self, headers, model_id, log_rec, comman_log_line_obj):
        """
        This method read import file headers name are correct or not.
        @:param : headers - list of import file headers
        @:param : model_id - object of model for created log line
        @:param : log_rec - object of common log book model
        @:param : comman_log_line_obj - object of common log lines book model
        :return: boolean(True/False).
        """
        skip_header = False
        if self.auto_create_product and 'item-name' not in headers:
            message = 'Import file is skipped due to header item-name is incorrect or blank'
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, False, False,
                                                               False, log_rec, mismatch=True)
            skip_header = True
        elif 'seller-sku' not in headers:
            message = 'Import file is skipped due to header seller-sku is incorrect or blank'
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, False, False,
                                                               False, log_rec, mismatch=True)
            skip_header = True
        elif 'fulfilment-channel' not in headers and 'fulfillment-channel' not in headers:
            message = 'Import file is skipped due to header fulfilment-channel is incorrect or blank'
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, False, False,
                                                               False, log_rec, mismatch=True)
            skip_header = True
        return skip_header

    def create_or_update_amazon_product_ept(self, amazon_product_id, odoo_product_id, fulfillment_type, row):
        """
        Define method for create amazon product if not exist otherwise update details in exist
        amazon product.
        @:param amazon_product_id : amazon product id
        @:param odoo_product_id : odoo product
        @:param fulfillment_type : selling on
        @:param row : report data
        :return: boolean(True/False).
        """
        amazon_product_ept_obj = self.env['amazon.product.ept']
        description = row.get('item-description', '') and row.get('item-description', '')
        name = row.get('item-name', '') and row.get('item-name', '')
        seller_sku = row.get('seller-sku', '').strip()
        amz_product_values = {
            'name': name,
            'long_description': description,
            'seller_sku': seller_sku,
            'fulfillment_by': fulfillment_type,
            'product_asin': row.get('asin1'),
            'exported_to_amazon': True,
        }
        if amazon_product_id:
            amazon_product_id.write(amz_product_values)
            return True
        amz_product_values.update({'product_id': odoo_product_id.id,
                                   'instance_id': self.instance_id.id,})
        amazon_product_ept_obj.create(amz_product_values)
        return True

    def create_odoo_or_amazon_product_ept(self, odoo_product_id, fulfillment_type, row, log_rec):
        """
        This method is used to create odoo or amazon product.
        @:param odoo_product_id : odoo product id
        @:param fulfillment_type : selling on
        @:param row : report line data
        @:param log_rec : log record.
        :return: boolean(True/False).
        """
        product_obj = self.env['product.product']
        comman_log_line_obj = self.env['common.log.lines.ept']
        model_id = comman_log_line_obj.get_model_id('product.product')
        created_product = False
        seller_sku = row.get('seller-sku', '').strip()
        price_list_id = self.instance_id.pricelist_id
        if odoo_product_id:
            self.create_or_update_amazon_product_ept(False, odoo_product_id, fulfillment_type, row)
            if self.update_price_in_pricelist and row.get('price', False):
                price_list_id.set_product_price_ept(odoo_product_id.id, float(row.get('price')))
        else:
            if self.auto_create_product:
                if not row.get('item-name', ''):
                    message = """ Line Skipped due to product name not found of seller sku %s || Instance %s
                    """ % (seller_sku, self.instance_id.name)
                    is_mismatch = True
                else:
                    created_product = product_obj.create(
                        {'default_code': seller_sku,
                         'name': row.get('item-name', ''),
                         'type': 'product'})
                    self.create_or_update_amazon_product_ept(False, created_product, fulfillment_type, row)
                    message = """ Product created for seller sku %s || Instance %s """ % (
                        seller_sku, self.instance_id.name)
                    is_mismatch = False
                    if self.update_price_in_pricelist and row.get('price', False):
                        price_list_id.set_product_price_ept(created_product.id, float(row.get('price')))
            else:
                message = """ Line Skipped due to product not found seller sku %s || Instance %s
                """ % (seller_sku, self.instance_id.name)
                is_mismatch = True
            comman_log_line_obj.amazon_create_product_log_line(
                message, model_id, created_product, seller_sku, fulfillment_type, log_rec, row.get('item-name'),
                mismatch=is_mismatch)
        return True
