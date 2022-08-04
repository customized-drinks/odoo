# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added class, methods and fields to import and process amazon removal order report.
"""
import base64
import csv
import time
from io import StringIO
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.tools import float_round, float_compare
from ..endpoint import DEFAULT_ENDPOINT


class AmazonRemovalOrderReportHistory(models.Model):
    """
    Added class to import and process removal order report.
    """
    _name = "amazon.removal.order.report.history"
    _description = "Removal Order Report"
    _inherit = ['mail.thread']
    _order = 'id desc'

    def _compute_removal_pickings(self):
        """
        This method will count the number of removal pickings.
        :return:
        """
        for record in self:
            record.removal_count = len(record.removal_picking_ids.ids)

    def list_of_removal_pickings(self):
        """
        This method will return the action of removal order pickings.
        :return: ir.actions.act_window() action
        """
        action = {
            'domain': "[('id', 'in', " + str(self.removal_picking_ids.ids) + " )]",
            'name': 'Removal Order Pickings',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'type': 'ir.actions.act_window',
        }
        return action

    @api.depends('seller_id')
    def _compute_removal_company(self):
        """
        This will set the company in removal order report.
        :return:
        """
        for record in self:
            company_id = record.seller_id.company_id.id if record.seller_id else False
            if not company_id:
                company_id = self.env.company.id
            record.company_id = company_id

    name = fields.Char(size=256, help="This Field relocates removal order report name.")
    state = fields.Selection([('draft', 'Draft'),
                              ('_SUBMITTED_', 'SUBMITTED'),
                              ('_IN_PROGRESS_', 'IN_PROGRESS'),
                              ('_CANCELLED_', 'CANCELLED'),
                              ('_DONE_', 'DONE'),
                              ('partially_processed', 'Partially Processed'),
                              ('IN_PROGRESS', 'IN_PROGRESS'), ('FATAL', 'FATAL'),
                              ('CANCELLED', 'CANCELLED'), ('DONE', 'DONE'),
                              ('IN_QUEUE', 'IN_QUEUE'), ('SUBMITTED', 'SUBMITTED'),
                              ('_DONE_NO_DATA_', 'DONE_NO_DATA'),
                              ('processed', 'PROCESSED')],
                             string='Report Status', default='draft',
                             help="This Field relocates state of removal order report process.")
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False,
                                help="Select Seller id from you wanted to get Shipping report")
    attachment_id = fields.Many2one('ir.attachment', string="Attachment", help="This Field relocates attachment id.")
    instance_id = fields.Many2one("amazon.instance.ept", string="Instance", help="This Field relocates instance")
    removal_picking_ids = fields.One2many("stock.picking", 'removal_order_report_id',
                                          string="Pickings", help="This Field relocates removal picking ids.")
    removal_count = fields.Integer(compute="_compute_removal_pickings", help="This Field relocates removal count.")
    report_id = fields.Char(size=256, string='Report ID', help="This Field relocates report id.")
    report_type = fields.Char(size=256, help='This Field relocates report type.')
    report_request_id = fields.Char(string='Report Request ID', readonly='1',
                                    help="This Field relocates report request id of amazon.")
    report_document_id = fields.Char(string='Report Document ID',
                                     help="Report Document id to recognise unique request document reference")
    start_date = fields.Datetime(help="Report Start Date")
    end_date = fields.Datetime(help="Report End Date")
    requested_date = fields.Datetime(default=time.strftime("%Y-%m-%d %H:%M:%S"), help="Report Requested Date")
    user_id = fields.Many2one('res.users', string="Requested User", help="Track which odoo user has requested report")
    company_id = fields.Many2one('res.company', string="Company", copy=False,
                                 compute="_compute_removal_company", store=True, help="This Field relocates company")
    log_count = fields.Integer(compute="_compute_logs_record")
    mismatch_details = fields.Boolean(compute='_compute_logs_record', string='Mismatch Details',
                                      help='True if found any mismatch details in log line')

    def unlink(self):
        """
        This Method raise UserError when processed report will be deleted.
        :return:
        """
        for report in self:
            if report.state == 'processed':
                raise UserError(_('You cannot delete processed report.'))
        return super(AmazonRemovalOrderReportHistory, self).unlink()

    def list_of_logs(self):
        """
        This method will return the removal order mismatch logs.
        :return: ir.actions.act_window() action
        """
        model_id = self.env['ir.model']._get('amazon.removal.order.report.history').id
        action = {
            'domain': "[('res_id', '=', " + str(self.id) + " ), ('model_id', '=', " + str( \
                model_id) + ")]",
            'name': 'MisMatch Logs',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'common.log.book.ept',
            'type': 'ir.actions.act_window',
        }
        return action

    def _compute_logs_record(self):
        """
        This method will count the number logs for removal order report.
        :return:
        """
        common_log_book_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('amazon.removal.order.report.history').id
        log_ids = common_log_book_obj.search([('res_id', '=', self.id), ('model_id', '=', model_id)]).ids
        self.log_count = log_ids.__len__()

        # Set the Boolean field mismatch_details as True if found mismatch details in log lines
        if self.env['common.log.lines.ept'].search_count(
                [('log_book_id', 'in', log_ids), ('mismatch_details', '=', True)]):
            self.mismatch_details = True
        else:
            self.mismatch_details = False

    @api.constrains('start_date', 'end_date')
    def _check_duration(self):
        """
        This Method check date duration,
        :return: This Method return Boolean(True/False)
        """
        if self.start_date and self.end_date < self.start_date:
            raise UserError(_('Error!\nThe start date must be precede its end date.'))
        return True

    @api.onchange('seller_id')
    def on_change_seller_id(self):
        """
        This Method relocates check seller and write start date and end date.
        :return: This Method return updated value.
        """
        if self.seller_id:
            self.start_date = datetime.now() - timedelta(self.seller_id.removal_order_report_days)
            self.end_date = datetime.now()

    @api.model
    def default_get(self, fields):
        """
        This Method relocates default get and set removal order report type.
        :param fields: dict {}
        :return: dict {}
        """
        res = super(AmazonRemovalOrderReportHistory, self).default_get(fields)
        if not fields:
            return res
        res.update({'report_type': 'GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA'})
        return res

    @api.model
    def create(self, vals):
        """
        This method will update the report name as sequence wise.
        :param vals: dict {}
        :return: amazon.removal.order.report.history() object
        """
        sequence = self.env.ref('amazon_ept.seq_removal_order_report_job', raise_if_not_found=False)
        report_name = sequence.next_by_id() if sequence else '/'
        vals.update({'name': report_name})
        return super(AmazonRemovalOrderReportHistory, self).create(vals)

    def request_report(self):
        """
        Request GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA Report from Amazon for specific
        date range.
        :return: This Method return Boolean(True/False).
        """
        seller, report_type = self.seller_id, self.report_type
        shipping_report_obj = self.env['shipping.report.request.history']
        if not seller:
            raise UserError(_('Please select Seller'))
        start_date, end_date = self.report_start_and_end_date()
        kwargs = shipping_report_obj.prepare_amazon_request_report_kwargs(seller)
        kwargs.update({'emipro_api': 'create_report_sp_api', 'report_type': report_type,
                       'start_date': start_date, 'end_date': end_date,})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', {}):
            if self._context.get('is_auto_process', False):
                job = self.amz_removal_search_or_create_job()
                job.write({'log_lines': [(0, 0, {
                    'message': 'Removal Order Report Process ' + response.get('error', {})})]})
            else:
                raise UserError(_(response.get('error', {})))
        if response.get('result', {}):
            result = response.get('result', {})
            self.update_report_history(result)
        return True

    def report_start_and_end_date(self):
        """
        Prepare start date and end Date for request reports
        :return: start_date and end_date
        """
        start_date, end_date = self.start_date, self.end_date
        if start_date:
            db_import_time = time.strptime(str(start_date), "%Y-%m-%d %H:%M:%S")
            db_import_time = time.strftime("%Y-%m-%dT%H:%M:%S", db_import_time)
            start_date = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(
                time.mktime(time.strptime(db_import_time, "%Y-%m-%dT%H:%M:%S"))))
            start_date = str(start_date) + 'Z'
        else:
            today = datetime.now()
            earlier = today - timedelta(days=30)
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

    def update_report_history(self, request_result):
        """
        This Method relocates update Report History in odoo.
        :param request_result: This arguments relocates request result.
        :return: This Method return Boolean(True/False).
        """
        report_id = request_result.get('reportId', '')
        report_document_id = request_result.get('reportDocumentId', '')
        report_state = request_result.get('processingStatus', 'SUBMITTED')
        return_values = {}
        if not self.report_document_id and report_document_id:
            return_values.update({'report_document_id': report_document_id})
        if report_state:
            return_values.update({'state': report_state})
        if report_id:
            return_values.update({'report_id': report_id})
        self.write(return_values)
        return True

    def get_report_request_list(self):
        """
        This Method relocates get report list from amazon.
        :return: This Method return boolean(True/False).
        """
        self.ensure_one()
        shipping_report_obj = self.env['shipping.report.request.history']
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select Seller'))
        if self.report_id:
            kwargs = shipping_report_obj.prepare_amazon_request_report_kwargs(self.seller_id)
            kwargs.update({'emipro_api': 'get_report_sp_api', 'report_id': self.report_id})
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
            if response.get('error', {}):
                if self._context.get('is_auto_process', False):
                    job = self.amz_removal_search_or_create_job()
                    job.write({'log_lines': [(0, 0, {
                        'message': 'Removal Order Report Process ' + response.get('error', {})})]})
                else:
                    raise UserError(_(response.get('error', {})))
            if response.get('result', {}):
                result = response.get('result', {})
                self.update_report_history(result)
        return True

    def get_report(self):
        """
        This Method relocates get removal order report as an attachment in removal order reports form view.
        :return: This Method return boolean(True/False).
        """
        self.ensure_one()
        shipping_report_obj = self.env['shipping.report.request.history']
        result = {}
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select seller'))
        if self.report_document_id:
            kwargs = shipping_report_obj.prepare_amazon_request_report_kwargs(self.seller_id)
            kwargs.update({'emipro_api': 'get_report_document_sp_api', 'reportDocumentId': self.report_document_id, })
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
            if response.get('error', False):
                if self._context.get('is_auto_process', False):
                    job = self.amz_removal_search_or_create_job()
                    job.write({'log_lines': [(0, 0, {
                        'message': 'Removal Order Report Process ' + response.get('error', {})})]})
                else:
                    raise UserError(_(response.get('error', {})))
            else:
                result = response.get('result', {})
            if result:
                result = result.get('document', '')
                result = result.encode()
                result = base64.b64encode(result)
                file_name = "Removal_Order_Report_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
                attachment = self.env['ir.attachment'].create({
                    'name': file_name,
                    'datas': result,
                    'res_model': 'mail.compose.message',
                    'type': 'binary'
                })
                self.message_post(body=_("<b>Removal Order Report Downloaded</b>"),
                                  attachment_ids=attachment.ids)
                self.write({'attachment_id': attachment.id})
                seller.write({'removal_order_report_last_sync_on': datetime.now()})
        return True

    def download_report(self):
        """
        This Method relocates download amazon removal order report.
        :return:This Method return boolean(True/False).
        """
        self.ensure_one()
        if self.attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % (self.attachment_id.id),
                'target': 'self',
            }
        return True

    def amz_removal_search_or_create_job(self):
        """
        Search or create common log book record.
        :return: common.log.book.ept()
        """
        amazon_process_job_log_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('amazon.removal.order.report.history').id
        job = amazon_process_job_log_obj.search(
            [('model_id', '=', model_id), ('res_id', '=', self.id)])
        if job and job.log_lines:
            job.log_lines.unlink()
        if not job:
            job = amazon_process_job_log_obj.create({
                'module': 'amazon_ept',
                'type': 'import',
                'active': True,
                'model_id': model_id,
                'res_id': self.id,
            })
        return job

    def process_removal_order_report(self):
        """
        This Method relocates process removal order report.
         - read csv file and process removal order report.
         - create order if order not found in odoo then create.
         - Check amazon removal order exist order in not in ERP.
         - If disposal line dict or return line dict found then process process removal lines.
        :Updated by: Kishan Sorani on date 10-Aug-2021
        :MOD: Processed Pending Order from Removal Order Report file.
        :return: boolean.
        """
        self.ensure_one()
        ir_cron_obj = self.env['ir.cron']
        if not self._context.get('is_auto_process', False):
            ir_cron_obj.with_context({'raise_warning': True}).find_running_schedulers(
                'ir_cron_process_fba_removal_order_report_seller_', self.seller_id.id)
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))
        if not self.seller_id:
            raise UserError(_("Seller is not defined for processing report"))
        imp_file = StringIO(base64.b64decode(self.attachment_id.datas).decode())
        reader = csv.DictReader(imp_file, delimiter='\t')
        disposal_line_dict, return_line_dict, order_dict, liquidations_line_dict = {}, {}, {}, {}
        job = self.amz_removal_search_or_create_job()
        for row in reader:
            if not row.get('order-type', '') or row.get('order-type', '') == 'order-type':
                continue
            if row.get('order-status', '') not in ['Completed', 'Cancelled', 'Pending']:
                continue
            order_id = row.get('order-id', '')
            existing_order, skip_line = self.check_amazon_order_exist_order_not(row, job)
            if existing_order and existing_order.state == row.get('order-status', ''):
                continue
            if not existing_order and row.get('order-status', '') in ['Completed', 'Pending']:
                order_dict.get(order_id).append(
                    row) if order_id in order_dict else order_dict.update({order_id: [row]})
            if not skip_line and existing_order:
                disposal_line_dict, return_line_dict, liquidations_line_dict = self.amz_prepare_disposal_and_removal_line_dict(
                    existing_order, row, job, disposal_line_dict, return_line_dict, liquidations_line_dict)
        if order_dict:
            existing_order, disposal_line_dict, return_line_dict, liquidations_line_dict = self.create_order_if_not_found_in_odoo(
                order_dict, job, disposal_line_dict, return_line_dict, liquidations_line_dict)
        if disposal_line_dict or return_line_dict or liquidations_line_dict:
            self.process_removal_lines(disposal_line_dict, return_line_dict, liquidations_line_dict, job)
        is_mismatch_logs = True if job.log_lines.filtered(lambda l: l.mismatch_details) else False
        state = 'partially_processed' if is_mismatch_logs else 'processed'
        self.write({'state': state})
        if job and not job.log_lines:
            job.unlink()
        return True

    @staticmethod
    def amz_prepare_disposal_and_removal_line_dict(existing_order, rows, job, disposal_line_dict,
                                                   return_line_dict, liquidations_line_dict):
        """
        Prepare disposal and removal lines dictionary from file data
        :param existing_order: amazon.removal.order.ept()
        :param rows: list(dict())
        :param job: common.log.book.ept()
        :param disposal_line_dict: dict{key: [row]}
        :param return_line_dict: dict{key: [row]}
        :return: dict{key: [row]}, dict{key: [row]}
        @author: Keyur Kanani
        """
        rows = [rows] if not isinstance(rows, list) else rows
        for row in rows:
            order_type = row.get('order-type', '')
            order_id = row.get('order-id', '')
            amazon_removal_order_config = existing_order.instance_id.removal_order_config_ids.filtered(
                lambda l, row=row: l.removal_disposition == row.get('order-type', ''))
            if not amazon_removal_order_config:
                message = "Configuration not found for order-type {} || order-id {} ".format(
                    row.get('order-type', ''), order_id)
                job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
            else:
                key = (existing_order.id, amazon_removal_order_config.id)
                if order_type == 'Disposal':
                    if key in disposal_line_dict:
                        disposal_line_dict.get(key).append(row)
                    else:
                        disposal_line_dict.update({key: [row]})
                elif order_type == 'Return':
                    if key in return_line_dict:
                        return_line_dict.get(key).append(row)
                    else:
                        return_line_dict.update({key: [row]})
                elif order_type == 'Liquidations':
                    if key in liquidations_line_dict:
                        liquidations_line_dict.get(key).append(row)
                    else:
                        liquidations_line_dict.update({key: [row]})
                else:
                    message = "Order type {} || skipped of {} ".format(order_type, order_id)
                    job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
        return disposal_line_dict, return_line_dict, liquidations_line_dict

    def create_order_if_not_found_in_odoo(self, order_dict, job, disposal_line_dict,
                                          return_line_dict, liquidations_line_dict):
        """
        Creating removal order if order not found in odoo.
        :param order_dict: dict()
        :param job: common.log.book.ept()
        :param disposal_line_dict: dict{key: [row]}
        :param return_line_dict: dict{key: [row]}
        :return: amazon.removal.order.ept(), dict{key: [row]}, dict{key: [row]}
        @author: Keyur Kanani

        Updated code to pass the job id with the context during process the disposal_order_pickings.
        @author: twinkalc
        :Updated by: Kishan Sorani on date 10-Aug-2021
        :Mod: Process can not create Removal Order:
              1) Return order and all lines have no shipped quantity
              2) Disposal order and all lines have no disposed quantity
        """
        amazon_removal_order_obj = self.env['amazon.removal.order.ept']
        ctx = self._context.copy()
        ctx.update({'job_id': job})
        removal_order = []
        for order_id, rows in list(order_dict.items()):
            instance = self.seller_id.instance_ids.filtered(
                lambda l: l.is_allow_to_create_removal_order)
            if not instance:
                instance = self.seller_id.instance_ids[0]
            lines = []
            skip_lines = 0
            for row in rows:
                order_type = row.get('order-type', '')
                amazon_product = self.get_amazon_product(row.get('sku', ''), instance)
                if not amazon_product:
                    message = "Line is skipped due to product not found in ERP || Order ref {} ||" \
                              "Seller sku {} ".format(order_id, row.get('sku', ''))
                    job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
                    continue
                if float(row.get('requested-quantity', 0.0)) <= 0.0:
                    message = "Line is skipped due to request qty not found in file || " \
                              "Order ref {} || Seller sku {}".format(order_id, row.get('sku', ''))
                    job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
                    continue
                if order_type == 'Disposal' and float(row.get('disposed-quantity', 0.0)) <= 0.0:
                    skip_lines += 1
                if order_type == 'Return' and float(row.get('shipped-quantity', 0.0)) <= 0.0:
                    skip_lines += 1
                if order_type == 'Liquidations' and float(row.get('shipped-quantity', 0.0)) <= 0.0:
                    skip_lines += 1
                vals = {'amazon_product_id': amazon_product.id, 'removal_disposition': order_type}
                if row.get('disposition', '') == 'Unsellable':
                    vals.update({'unsellable_quantity': float(row.get('requested-quantity', 0.0))})
                else:
                    vals.update({'sellable_quantity': float(row.get('requested-quantity', 0.0))})
                lines.append((0, 0, vals))
            # Not create Removal order if all lines of order are skip
            if len(rows) == skip_lines:
                continue
            if lines:
                removal_vals = self.prepare_amz_removal_order_vals_ept(order_id, order_type, instance, lines)
                removal_order = amazon_removal_order_obj.create(removal_vals)
                removal_order.write({'state': 'plan_approved'})
                if order_type == 'Disposal':
                    sell_pick, unsell_pick = removal_order.with_context(ctx).disposal_order_pickings()
                    if sell_pick:
                        sell_pick.write({'removal_order_report_id': self.id})
                    if unsell_pick:
                        unsell_pick.write({'removal_order_report_id': self.id})
                if order_type == 'Return':
                    pickings = removal_order.with_context(ctx).removal_order_procurements()
                    pickings.write({'removal_order_report_id': self.id})
                if order_type == 'Liquidations':
                    sell_pick, unsell_pick = removal_order.with_context(ctx).disposal_order_pickings()
                    if sell_pick:
                        sell_pick.write({'removal_order_report_id': self.id})
                    if unsell_pick:
                        unsell_pick.write({'removal_order_report_id': self.id})
                disposal_line_dict, return_line_dict, liquidations_line_dict = self.amz_prepare_disposal_and_removal_line_dict(
                    removal_order, rows, job, disposal_line_dict, return_line_dict, liquidations_line_dict)
        return removal_order, disposal_line_dict, return_line_dict, liquidations_line_dict

    def prepare_amz_removal_order_vals_ept(self, order_id, order_type, instance, lines):
        """
        Prepare removal order values
        :param order_id: amazon removal order id
        :param order_type: amazon removal order type [Return / Disposal]
        :param instance: amazon.instance.ept()
        :param lines: list()
        :return: dict{}
        @author: Keyur Kanani
        """
        try:
            ship_add_id = self.seller_id.amz_fba_liquidation_partner.id if order_type == 'Liquidations' else self.company_id.partner_id.id
        except Exception:
            raise UserError(_("FBA Liquidation Partner is Missing! "
                              "Please Configure FBA Liquidation Partner in Amazon Seller Configuration."))
        return {
            'name': order_id or '',
            'removal_disposition': order_type or '',
            'warehouse_id': instance.removal_warehouse_id.id if instance else False,
            'ship_address_id': ship_add_id,
            'company_id': self.seller_id.company_id.id,
            'instance_id': instance.id if instance else False,
            'removal_order_lines_ids': lines or []

        }

    def check_amazon_order_exist_order_not(self, row, job):
        """
        This Method relocates check amazon order exist or not.If exist then find order with order ref.
        :param row: dict{}
        :param job: common.log.book.ept()
        :return: amazon.removal.order.ept(), boolean(True / False)
        """
        amz_removal_order_obj = self.env['amazon.removal.order.ept']
        order_id = row.get('order-id', '')
        order_status = row.get('order-status', '')
        skip_line = False
        existing_order = amz_removal_order_obj.search([('name', '=', order_id)])
        if not existing_order and order_status == 'Cancelled':
            message = "Removal order not found for processing order-id {} ".format(order_id)
            job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
            skip_line = True
        elif len(existing_order.ids) > 1:
            message = "Multiple Order found for processing order-id {} ".format(order_id)
            job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
            skip_line = True
        elif existing_order and order_status == 'Cancelled':
            remove_order_picking_ids = existing_order.removal_order_picking_ids
            picking_ids = remove_order_picking_ids.filtered(lambda x: x.state not in ['done', 'cancel'])
            if picking_ids:
                picking_ids.action_cancel()
            if remove_order_picking_ids and not remove_order_picking_ids.filtered(lambda x: x.state not in ['cancel']):
                existing_order.write({'state' : 'Cancelled'})
            skip_line = True
        return existing_order, skip_line

    def get_amazon_product(self, sku, instance):
        """
        This Method relocates get amazon product using product sku and instance of amazon.
        :param sku: This Arguments relocates sku of removal order product amazon.
        :param instance: This Arguments instance of amazon.
        :return: This Method return amazon product.
        """
        amazon_product = self.env['amazon.product.ept'].search(
            [('seller_sku', '=', sku), ('instance_id', '=', instance.id),
             ('fulfillment_by', '=', 'FBA')], limit=1)
        return amazon_product

    def process_removal_lines(self, disposal_line_dict, return_line_dict, liquidations_line_dict, job):
        """
        This Method relocates process removal order lines.
        :param disposal_line_dict: dict()
        :param return_line_dict: dict()
        :param job: common.log.book.ept()
        :return: boolean
        """
        if disposal_line_dict:
            self.process_disposal_lines(disposal_line_dict, job)
        if return_line_dict:
            self.process_return_lines(return_line_dict, job)
        if liquidations_line_dict:
            self.process_disposal_lines(liquidations_line_dict, job)
        return True

    def process_disposal_lines(self, disposal_line_dict, job):
        """
        This Method relocates process disposal line.
        If dispose quantity found grater 0 then check move processed or not.
        If dispose quantity found less or equal 0 then search stock move.
        :param disposal_line_dict: list(dict{key: [row]})
        :param job: common.log.book.ept()
        :return: list()
        @author: Keyur Kanani
        """
        amz_removal_order_config_obj = self.env['removal.order.config.ept']
        amz_removal_order_obj = self.env['amazon.removal.order.ept']
        pickings = []
        for order_key, rows in list(disposal_line_dict.items()):
            order = amz_removal_order_obj.browse(order_key[0])
            config = amz_removal_order_config_obj.browse(order_key[1])
            picking_vals = self.amz_removal_pickings_dict(order, config)
            unsellable_source_location_id = order.disposition_location_id.id
            sellable_source_location_id = order.instance_id.fba_warehouse_id.lot_stock_id.id
            for row in rows:
                disposed_qty = float(row.get('disposed-quantity', 0.0) or 0.0)
                canceled_qty = float(row.get('cancelled-quantity', 0.0) or 0.0)
                shipped_qty = float(row.get('shipped-quantity', 0.0) or 0.0)
                product = self.find_amazon_product_for_process_removal_line(row, job,
                                                                            order.instance_id.id)
                if product:
                    source_location_id = unsellable_source_location_id if row.get(
                        'disposition', '') == 'Unsellable' else sellable_source_location_id
                    picking_vals.update(
                        {'source_location_id': source_location_id, 'product_id': product, 'order': order})
                    if disposed_qty > 0.0:
                        move_pickings, skip_line = self.amz_removal_procesed_qty_ept(row, picking_vals, disposed_qty, job)
                        if skip_line:
                            continue
                        if move_pickings:
                            pickings += move_pickings
                    if shipped_qty > 0.0:
                        mv_pickings, skip_line = self.amz_removal_procesed_qty_ept(row, picking_vals, shipped_qty, job)
                        if skip_line:
                            continue
                        if mv_pickings:
                            pickings += mv_pickings
                    if canceled_qty > 0.0:
                        self.amz_removal_canceled_qty_ept(row, picking_vals, canceled_qty, job)
        if pickings:
            pickings = list(set(pickings))
            self.process_picking(pickings)
        return pickings

    @staticmethod
    def amz_removal_pickings_dict(order, config):
        """
        Prepare Removal order pickings filtered values.
        :param order: amazon.removal.order.ept()
        :param config: removal.order.config.ept()
        :return: dict{}
        """
        return {
            'remaining_pickings': order.removal_order_picking_ids.filtered(
                lambda l: l.state not in ['done', 'cancel']),
            'processed_pickings': order.removal_order_picking_ids.filtered(lambda l: l.state == 'done'),
            'canceled_pickings': order.removal_order_picking_ids.filtered(lambda l: l.state == 'cancel'),
            'location_dest_id': config.location_id.id or False,
        }

    def amz_removal_canceled_qty_ept(self, row, picking_vals, quantity, job):
        """
         Processing removal orders cancelled quantities from report.
        :param row: dict()
        :param picking_vals: dict()
        :param quantity: float
        :param job: common.log.book.ept()
        :return: boolean
        @author: Keyur Kanani
        :Updated by: Kishan Sorani on date 10-Aug-2021
        MOD: Processed cancel quantity of Removal Order
        """
        remaining_pickings = picking_vals.get('remaining_pickings').ids if \
            picking_vals.get('remaining_pickings') else []
        processed_pickings = picking_vals.get('processed_pickings').ids if \
            picking_vals.get('remaining_pickings') else []
        remaining_processed_pickings = list(set(remaining_pickings + processed_pickings))
        stock_move_obj = self.env['stock.move']
        order_ref = row.get('order-id', '')
        sku = row.get('sku', '')
        qty = quantity
        if quantity:
            canceled_moves = stock_move_obj.search([('product_id', '=', picking_vals.get('product_id', False)),
                                                    ('state', '=', 'cancel'),
                                                    ('picking_id', 'in', remaining_processed_pickings),
                                                    ('location_id', '=', picking_vals.get('source_location_id', False))])
            if canceled_moves:
                qty = self.check_move_processed_or_not(picking_vals.get('product_id', False),
                                                       canceled_moves, job, sku, quantity, order_ref)
        if qty > 0.0:
            moves = self.amz_get_stock_move_from_picking_ept(picking_vals.get('product_id', False),
                                                             picking_vals.get('remaining_pickings', False),
                                                             picking_vals.get('source_location_id', False),
                                                             picking_vals.get('location_dest_id', False),
                                                             ['done', 'cancel'])
            if not moves:
                message = 'Move not found for processing sku {} order ref {}'.format(
                    sku, picking_vals.get('order', '').name)
                job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
            if moves:
                self.update_cancel_qty_ept(moves, qty)
        return True

    def amz_removal_procesed_qty_ept(self, row, picking_vals, quantity, job):
        """
        Process removal order processed or shipped quantities.
        :param row: dict()
        :param picking_vals: dict()
        :param quantity: float
        :param job: common.log.book.ept()
        :return: list()
        @author: Keyur Kanani
        :Updated by: Kishan Sorani on date 10-Aug-2021
        MOD: Processed Pending Return and Disposal orders and process
            create back orders for partially done quantity
        """
        order_ref = row.get('order-id', '')
        sku = row.get('sku', '')
        qty = quantity
        move_pickings = []
        skip_line = False
        if picking_vals.get('processed_pickings', False):
            existing_move = self.amz_get_stock_move_from_picking_ept( \
                picking_vals.get('product_id', False),
                picking_vals.get('processed_pickings', False),
                picking_vals.get('source_location_id', False),
                picking_vals.get('location_dest_id', False), 'done')
            if existing_move:
                qty = self.check_move_processed_or_not(picking_vals.get('product_id', False),
                                                       existing_move, job, sku, quantity, order_ref)
        if qty > 0.0:
            moves = self.amz_get_stock_move_from_picking_ept(picking_vals.get('product_id', False),
                                                             picking_vals.get('remaining_pickings', False),
                                                             picking_vals.get('source_location_id', False),
                                                             picking_vals.get('location_dest_id', False),
                                                             ['done', 'cancel'])
            if moves:
                move_pickings = self.create_pack_operations_ept(moves, qty)
            else:
                message = 'Move not found for processing sku {} order ref {}'.format(
                    sku, picking_vals.get('order', '').name)
                job.write({'log_lines': [(0, 0, {'message': message, 'mismatch_details': True})]})
                skip_line = True
        return move_pickings, skip_line

    @staticmethod
    def amz_get_stock_move_from_picking_ept(product_id, pickings_ids, source_location_id, location_dest_id, state):
        """
        Filter stock move based on product,source location and destination location from picking
        object.
        :param product_id: integer
        :param pickings_ids: stock.picking()
        :param source_location_id: integer
        :param location_dest_id: integer
        :param state : stock move state
        :return: stock.move()
        @author: Keyur Kanani
        :Updated by: Kishan Sorani on date 10-Aug-2021
        MOD: Find stock move based on stock move state
        """
        if state == 'done':
            return pickings_ids.move_lines.filtered(
                lambda l: l.product_id.id == product_id and l.location_id.id == source_location_id
                          and l.location_dest_id.id == location_dest_id and l.state == state)
        return pickings_ids.move_lines.filtered(
            lambda l: l.product_id.id == product_id and l.location_id.id == source_location_id and
                      l.location_dest_id.id == location_dest_id and l.state not in state)

    def process_return_lines(self, return_line_dict, job):
        """
        This Method relocates processed return removal order lines.
        This Method find amazon product for process removal line.
        This Method check move processed or not.
        :param return_line_dict: This Arguments relocates dictionary of return line.
        :param job: common.log.book.ept()
        :return: This Method return pickings.
        """
        procurement_rule_obj = self.env['stock.rule']
        amz_removal_order_config_obj = self.env['removal.order.config.ept']
        amz_removal_order_obj = self.env['amazon.removal.order.ept']
        pickings = []
        for order_key, rows in list(return_line_dict.items()):
            order = amz_removal_order_obj.browse(order_key[0])
            config = amz_removal_order_config_obj.browse(order_key[1])
            picking_vals = self.amz_removal_pickings_dict(order, config)
            procurement_rule = procurement_rule_obj.search(
                [('route_id', '=', config.unsellable_route_id.id),
                 ('location_src_id', '=', order.disposition_location_id.id)])
            unsellable_source_location_id = procurement_rule.location_src_id.id
            unsellable_dest_location_id = procurement_rule.location_id.id
            procurement_rule = procurement_rule_obj.search([
                ('route_id', '=', config.sellable_route_id.id),
                ('location_src_id', '=', order.instance_id.fba_warehouse_id.lot_stock_id.id)])
            sellable_source_location_id = procurement_rule.location_src_id.id
            sellable_dest_location_id = procurement_rule.location_id.id
            for row in rows:
                product = self.find_amazon_product_for_process_removal_line(row, job,
                                                                            order.instance_id.id)
                if not product:
                    continue
                shipped_qty = float(row.get('shipped-quantity', 0.0))
                canceled_qty = float(row.get('cancelled-quantity', 0.0))
                source_location_id = unsellable_source_location_id if row.get(
                    'disposition', '') == 'Unsellable' else sellable_source_location_id
                location_dest_id = unsellable_dest_location_id if row.get(
                    'disposition', '') == 'Unsellable' else sellable_dest_location_id
                picking_vals.update({'location_dest_id': location_dest_id or False,
                                     'source_location_id': source_location_id or False,
                                     'product_id': product, 'order': order})
                if shipped_qty > 0.0:
                    move_pickings, skip_lines = self.amz_removal_procesed_qty_ept(row, picking_vals,
                                                                                  shipped_qty, job)
                    if skip_lines:
                        continue
                    if move_pickings:
                        pickings += move_pickings
                if canceled_qty > 0.0:
                    self.amz_removal_canceled_qty_ept(row, picking_vals, canceled_qty, job)
        if pickings:
            pickings = list(set(pickings))
            self.process_picking(pickings)
        return pickings

    def find_amazon_product_for_process_removal_line(self, line, job, instance):
        """
        This Method relocates find amazon product for processed removal order line.
        :param line: This Arguments relocates Line of return line dictionary.
        :param job: This Arguments relocates job log of removal order log.
        :param instance: This Arguments instance of amazon.
        :return: This Method return process removal order product.
        """
        amazon_product_obj = self.env['amazon.product.ept']
        sku = line.get('sku', '')
        asin = line.get('fnsku', '')
        amazon_product = amazon_product_obj.search([('seller_sku', '=', sku),
                                                    ('fulfillment_by', '=', 'FBA'),
                                                    ('instance_id', '=', instance)], limit=1)
        if not amazon_product:
            amazon_product = amazon_product_obj.search([('product_asin', '=', asin),
                                                        ('fulfillment_by', '=', 'FBA'),
                                                        ('instance_id', '=', instance)], limit=1)
        product = amazon_product.product_id.id if amazon_product else False
        if not amazon_product:
            job.write({'log_lines': [
                (0, 0, {'message': 'Product  not found for SKU {} & ASIN {}'.format(sku, asin),
                        'mismatch_details': True})]})
        return product

    @staticmethod
    def check_move_processed_or_not(product_id, existing_move, job, sku, qty, order_ref):
        """
        check existing move is processed or not.
        :param existing_move: stock.move()
        :param product_id: product reference
        :param job: common.log.book.ept()
        :param sku: str
        :param qty: float
        :param order_ref: str
        :return: quantity (float)
        @author: Keyur Kanani
        """
        for move in existing_move:
            qty -= move.product_qty
        if qty <= 0.0:
            job.write({'log_lines': [(0, 0, {
                'message': """Move already processed Product {} || sku {} Qty {} ||
                Order ref {} """.format(product_id, sku, qty, order_ref)
            })]})
        return qty

    def update_cancel_qty_ept(self, moves, quantity):
        """
        This Method relocates update cancel qty.
        :param moves: This Arguments relocates stock move.
        :param quantity: This Arguments relocates cancel quantity.
        :return: This Method return boolean(True/False).
        """
        stock_move_obj = self.env['stock.move']
        for move in moves:
            if quantity > move.product_qty:
                qty = move.product_qty
            else:
                qty = quantity
            if qty == move.product_qty:
                move._action_cancel()
            else:
                new_move_vals = move._split(qty)
                new_move = stock_move_obj.create(new_move_vals)
                new_move = new_move._action_confirm(merge=False)
                new_move._action_cancel()
            quantity = quantity - qty
            if quantity <= 0.0:
                break
        return True

    def process_picking(self, pickings):
        """
        This Method relocates process picking and change state.
        :param pickings: list().
        :return: Boolean(True/False).
        """
        stock_picking_obj = self.env['stock.picking']
        for picking in pickings:
            picking = stock_picking_obj.browse(picking)
            picking._action_done()
            picking.write({'removal_order_report_id': self.id})
            removal_order_picking_ids = picking.removal_order_id.removal_order_picking_ids.filtered(
                lambda l: l.is_fba_wh_picking and l.state != 'done')
            if not removal_order_picking_ids:
                picking.removal_order_id.write({'state': 'Completed'})
        return True

    def create_pack_operations_ept(self, moves, quantity):
        """
        This Method relocates create pack operation.
        This Method creates stock move line for existing move and if any quantity left then create
        stock move line.
        :param moves: stock.move()
        :param quantity: float
        :return: list()
        """
        pick_ids = []
        stock_move_line_obj = self.env['stock.move.line']
        for move in moves:
            qty_left = quantity
            if qty_left <= 0.0:
                break
            mv_done_qty = sum(line.qty_done for line in move.move_line_ids)
            move_line_remaning_qty = move.product_uom_qty - mv_done_qty #move.move_line_ids.qty_done
            operations = move.move_line_ids.filtered(lambda o: o.qty_done <= 0 and not o.result_package_id)
            for operation in operations:
                op_qty = operation.product_uom_qty if operation.product_uom_qty <= qty_left else qty_left
                operation.write({'qty_done': op_qty})
                self._put_in_pack(operation)
                qty_left = float_round(qty_left - op_qty,
                                       precision_rounding=operation.product_uom_id.rounding,
                                       rounding_method='UP')
                move_line_remaning_qty = move_line_remaning_qty - op_qty
                if qty_left <= 0.0:
                    break
            picking = move.picking_id
            if qty_left > 0.0 and move_line_remaning_qty > 0.0:
                op_qty = move_line_remaning_qty if move_line_remaning_qty <= qty_left else qty_left
                sml_vals = self.amz_create_removal_stock_move_line_vals(move, picking, op_qty)
                stock_move_line_obj.create(sml_vals)
                pick_ids.append(move.picking_id.id)
                qty_left = float_round(qty_left - op_qty,
                                       precision_rounding=move.product_id.uom_id.rounding,
                                       rounding_method='UP')
                if qty_left <= 0.0:
                    break
            if qty_left > 0.0:
                sml_vals = self.amz_create_removal_stock_move_line_vals(move, picking, qty_left)
                stock_move_line_obj.create(sml_vals)
            pick_ids.append(move.picking_id.id)
        return pick_ids

    @staticmethod
    def amz_create_removal_stock_move_line_vals(move, picking, op_qty):
        """
        Prepare stock move line values for removal orders stock move.
        :param move: stock.move()
        :param picking: stock.picking()
        :param op_qty: float
        :return: dict()
        @author: Keyur Kanani
        """
        return {
            'product_id': move.product_id.id,
            'product_uom_id': move.product_id.uom_id.id,
            'picking_id': move.picking_id.id,
            'qty_done': float(op_qty) or 0.0,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'move_id': move.id,
        }

    def _put_in_pack(self, operation, package=False):
        """
        This Method relocates put in pack stock move line.
        :param operation: This Arguments relocates stock move line.
        :param package: This Arguments relocates package.
        :return: This Method return Boolean(True/False).
        """
        operation_ids = self.env['stock.move.line']
        if float_compare(operation.qty_done, operation.product_uom_qty,
                         precision_rounding=operation.product_uom_id.rounding) >= 0:
            operation_ids |= operation
        else:
            quantity_left_todo = float_round(
                operation.product_uom_qty - operation.qty_done,
                precision_rounding=operation.product_uom_id.rounding,
                rounding_method='UP')
            new_operation = operation.copy(
                default={'product_uom_qty': operation.qty_done, 'qty_done': operation.qty_done})
            operation.write({'product_uom_qty': quantity_left_todo, 'qty_done': 0.0})
            operation_ids |= new_operation
        if package:
            operation_ids.write({'result_package_id': package.id})
        return True

    @api.model
    def auto_import_removal_order_report(self, args={}):
        """
        This method is used to import removal order report via cron.
        :param args: dict {}
        :return: boolean(TRUE/FALSE)
        """
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].browse(seller_id)
            if seller.removal_order_report_last_sync_on:
                start_date = seller.removal_order_report_last_sync_on
                start_date = datetime.strftime(start_date, '%Y-%m-%d %H:%M:%S')
                start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S')
                start_date = start_date + timedelta(
                    days=seller.removal_order_report_days * -1 or -3)
            else:
                today = datetime.now()
                earlier = today - timedelta(days=30)
                start_date = earlier.strftime("%Y-%m-%d %H:%M:%S")
            date_end = datetime.now()
            date_end = date_end.strftime("%Y-%m-%d %H:%M:%S")
            rem_report = self.create({'report_type': 'GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA',
                                      'seller_id': seller_id, 'start_date': start_date,
                                      'end_date': date_end, 'state': 'draft',
                                      'requested_date': time.strftime("%Y-%m-%d %H:%M:%S")})
            rem_report.with_context(is_auto_process=True).request_report()
            seller.write({'removal_order_report_last_sync_on': date_end})
        return True

    @api.model
    def auto_process_removal_order_report(self, args={}):
        """
        This method is used to process removal order report via cron
        :param args: dict {}
        :return: boolean (TRUE/FALSE)
        """
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].search([('id', '=', seller_id)])
            rem_reports = self.search([('seller_id', '=', seller.id),
                                       ('state', 'in', ['_SUBMITTED_', '_IN_PROGRESS_',
                                                        'SUBMITTED', 'IN_PROGRESS', 'IN_QUEUE'])])
            for report in rem_reports:
                report.with_context(is_auto_process=True).get_report_request_list()

            rem_reports = self.search([('seller_id', '=', seller.id),
                                       ('state', 'in', ['_DONE_', '_SUBMITTED_', '_IN_PROGRESS_',
                                                        'DONE', 'SUBMITTED', 'IN_PROGRESS']),
                                       ('report_document_id', '!=', False)])
            for report in rem_reports:
                if not report.attachment_id:
                    report.with_context(is_auto_process=True).get_report()
                if report.state in ['_DONE_', 'DONE'] and report.attachment_id:
                    report.with_context(is_auto_process=True).process_removal_order_report()
                self._cr.commit()
        return True
