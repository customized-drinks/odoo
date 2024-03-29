# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.


import time
import base64
import csv
from io import StringIO
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.iap.tools import iap_tools
from ..endpoint import DEFAULT_ENDPOINT


class RatingReportHistory(models.Model):
    _name = "rating.report.history"
    _description = "Rating Report History"
    _inherit = ['mail.thread']
    _order = 'id desc'

    @api.depends('seller_id')
    def _compute_company(self):
        """
        This method will set company in rating report history records.
        :return:
        """
        for record in self:
            company_id = record.seller_id.company_id.id if record.seller_id else False
            if not company_id:
                company_id = self.env.company.id
            record.company_id = company_id

    def _compute_rating_count(self):
        """
        This method will count rating reports.
        :return:
        """
        rating_obj = self.env['rating.rating']
        self.rating_count = rating_obj.search_count([('amz_rating_report_id', '=', self.id)])

    def _compute_log_count(self):
        """
        Find all log associated with this report
        :return:
        """
        log_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('rating.report.history').id
        self.log_count = log_obj.search_count([('res_id', '=', self.id), ('model_id', '=', model_id)])

    name = fields.Char(size=256)
    state = fields.Selection(
        [('draft', 'Draft'), ('SUBMITTED', 'SUBMITTED'), ('_SUBMITTED_', 'SUBMITTED'),
         ('IN_QUEUE', 'IN_QUEUE'), ('IN_PROGRESS', 'IN_PROGRESS'),
         ('_IN_PROGRESS_', 'IN_PROGRESS'), ('DONE', 'DONE'), ('_DONE_', 'Report Received'),
         ('_DONE_NO_DATA_', 'DONE_NO_DATA'), ('FATAL', 'FATAL'),
         ('processed', 'PROCESSED'),  ('CANCELLED', 'CANCELLED'), ('_CANCELLED_', 'CANCELLED')],
        string='Report Status', default='draft')
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False,
                                help="Select Seller id from you wanted to get Rating Report.")
    attachment_id = fields.Many2one('ir.attachment', string="Attachment")
    instance_id = fields.Many2one("amazon.instance.ept", string="Instance")
    report_id = fields.Char('Report ID', readonly='1')
    report_type = fields.Char(size=256, help="Amazon Report Type")
    report_request_id = fields.Char('Report Request ID', readonly='1')
    report_document_id = fields.Char(string='Report Document ID',
                                     help="Report Document id to recognise unique request document reference")
    start_date = fields.Datetime(help="Report Start Date")
    end_date = fields.Datetime(help="Report End Date")
    requested_date = fields.Datetime(default=time.strftime("%Y-%m-%d %H:%M:%S"),
                                     help="Report Requested Date")
    user_id = fields.Many2one('res.users', string="Requested User",
                              help="Track which odoo user has requested report")
    company_id = fields.Many2one('res.company', string="Company", copy=False,
                                 compute="_compute_company", store=True)
    rating_count = fields.Integer(compute="_compute_rating_count", store=False)
    log_count = fields.Integer(compute="_compute_log_count", store=False)
    amz_rating_report_ids = fields.One2many('rating.rating', 'amz_rating_report_id',
                                            string="Ratings")

    @api.onchange('seller_id')
    def on_change_seller_id(self):
        """
        This Method relocates check seller and write start date and end date.
        :return: This Method return updated value.
        """
        if self.seller_id:
            self.start_date = datetime.now() - timedelta(self.seller_id.rating_report_days)
            self.end_date = datetime.now()

    def unlink(self):
        """
        This method will raise UserError when processed rating report was deleted.
        :return:
        """
        """
        This Method if report is processed then raise UserError.
        """
        for report in self:
            if report.state == 'processed':
                raise UserError(_('You cannot delete processed report.'))
        return super(RatingReportHistory, self).unlink()

    @api.model
    def default_get(self, fields):
        """
        This method will set rating report type in rating report record.
        :param fields: dict {}
        :return: dict {}
        """
        res = super(RatingReportHistory, self).default_get(fields)
        if not fields:
            return res
        res.update({'report_type': 'GET_SELLER_FEEDBACK_DATA'})
        return res

    @api.model
    def create(self, vals):
        """
        This method will set rating report name.
        :param vals: dict {}
        :return: rating.report.history() object
        """
        try:
            sequence_id = self.env.ref('amazon_ept.seq_rating_report_job').ids
            if sequence_id:
                report_name = self.env['ir.sequence'].get_id(sequence_id[0])
            else:
                report_name = '/'
        except:
            report_name = '/'
        vals.update({'name': report_name})
        return super(RatingReportHistory, self).create(vals)

    def list_of_process_logs(self):
        """
        List All Mismatch Details for Rating Report.
        :return:
        """
        model_id = self.env['ir.model']._get('rating.report.history').id
        action = {
            'domain': "[('res_id', '=', " + str(self.id) + "), ('model_id','='," + str(
                model_id) + ")]",
            'name': 'Rating Report Logs',
            'view_mode': 'tree,form',
            'res_model': 'common.log.book.ept',
            'type': 'ir.actions.act_window',
        }
        return action

    @api.model
    def auto_import_rating_report(self, args={}):
        """
        This Method relocate import rating using crone.
        :param args: This Argument relocate seller id when the crone run in this argument given amazon seller id
        :return: This Method Return Boolean(True).
        """
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].browse(seller_id)
            if seller.rating_report_last_sync_on:
                start_date = seller.rating_report_last_sync_on
                start_date = datetime.strftime(start_date, '%Y-%m-%d %H:%M:%S')
                start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S')
                start_date = start_date + timedelta(days=seller.rating_report_days * -1 or -3)

            else:
                start_date = datetime.now() - timedelta(days=30)
                start_date = start_date.strftime("%Y-%m-%d %H:%M:%S")
            date_end = datetime.now()
            date_end = date_end.strftime("%Y-%m-%d %H:%M:%S")
            report_type = 'GET_SELLER_FEEDBACK_DATA'
            rating_report = self.create({'report_type': report_type,
                                         'seller_id': seller_id,
                                         'start_date': start_date,
                                         'end_date': date_end,
                                         'state': 'draft',
                                         'requested_date': time.strftime("%Y-%m-%d %H:%M:%S")
                                         })
            rating_report.with_context(is_auto_process=True).request_report()
            seller.write({'rating_report_last_sync_on': date_end})
        return True

    @api.model
    def auto_process_rating_report(self, args={}):
        """
        This Method Relocate auto process rating rating using crone.
        :param args: This Argument relocate seller id when the crone run in this argument given amazon seller id
        :return: This Method Return Boolean(True).
        """
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].browse(seller_id)
            rating_report = self.search([('seller_id', '=', seller.id),
                                         ('state', 'in', ['_SUBMITTED_', '_IN_PROGRESS_', '_DONE_',
                                                          'SUBMITTED', 'IN_PROGRESS', 'DONE','IN_QUEUE'])])
            for report in rating_report:
                if report.state not in ('_DONE_', 'DONE'):
                    report.with_context(is_auto_process=True).get_report_request_list()
                if report.report_document_id and report.state in ('_DONE_', 'DONE') and not report.attachment_id:
                    report.with_context(is_auto_process=True).get_report()
                if report.attachment_id:
                    report.with_context(is_auto_process=True).process_rating_report()
                self._cr.commit()
        return True

    def list_of_rating(self):
        """
        This Method relocate list of amazon rating.
        :return:
        """
        rating_obj = self.env['rating.rating']
        records = rating_obj.search([('amz_rating_report_id', '=', self.id)])
        action = {
            'domain': "[('id', 'in', " + str(records.ids) + " )]",
            'name': 'Amazon Rating',
            'view_mode': 'tree,form',
            'res_model': 'rating.rating',
            'type': 'ir.actions.act_window',
        }
        return action

    def amz_search_or_create_rating_report_log(self):
        """
        This method will return existing rating report log record if not exist
        then create new log record.
        :return: common.log.book.ept() object
        """
        common_log_book_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('rating.report.history').id
        log_rec = common_log_book_obj.search(
            [('module', '=', 'amazon_ept'), ('model_id', '=', model_id), ('res_id', '=', self.id)])
        if not log_rec:
            log_rec = common_log_book_obj.amazon_create_transaction_log('import', model_id, self.id)
        return log_rec

    def request_report(self):
        """
        Request GET_SELLER_FEEDBACK_DATA Report from Amazon for specific date range.
        :return: Boolean
        """
        shipping_report_obj = self.env['shipping.report.request.history']
        if not self.seller_id:
            raise UserError(_('Please select Seller'))
        start_date, end_date = self.report_start_and_end_date()
        kwargs = shipping_report_obj.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update({
            'emipro_api': 'create_report_sp_api',
            'report_type': self.report_type,
            'start_date': start_date,
            'end_date': end_date,
        })
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            if self._context.get('is_auto_process', False):
                job = self.amz_search_or_create_rating_report_log()
                job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
            else:
                raise UserError(_(response.get('error', {})))
        if response.get('result', {}):
            self.update_report_history(response.get('result', {}))
        return True

    def report_start_and_end_date(self):
        """
        Prepare Start and End Date for request reports
        :return: start_date, end_date
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

    def get_report_request_list(self):
        """
        This Method relocates get report list from amazon.
        :return: This Method return boolean(True/False).
        """
        self.ensure_one()
        shipping_report_obj = self.env['shipping.report.request.history']
        if not self.seller_id:
            raise UserError(_('Please select Seller'))
        if self.report_id:
            kwargs = shipping_report_obj.prepare_amazon_request_report_kwargs(self.seller_id)
            kwargs.update({'emipro_api': 'get_report_sp_api', 'report_id': self.report_id})
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
            if response.get('error', False):
                if self._context.get('is_auto_process', False):
                    job = self.amz_search_or_create_rating_report_log()
                    job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
                else:
                    raise UserError(_(response.get('error', {})))
            if response.get('result', {}):
                self.update_report_history(response.get('result', {}))
                if self.state in ['_DONE_', 'DONE'] and self.report_document_id:
                    self.get_report()
        return True

    def update_report_history(self, request_result):
        """
        Update Report History in odoo
        :param request_result:
        :return:
        """
        report_id = request_result.get('reportId', '')
        report_document_id = request_result.get('reportDocumentId', '')
        report_state = request_result.get('processingStatus', 'SUBMITTED')
        return_values = {}
        if not self.report_document_id and report_document_id:
            return_values.update({'report_document_id': report_document_id})
        if report_state:
            return_values.update({'state': report_state})
        if not self.report_id and report_id:
            return_values.update({'report_id': report_id})
        self.write(return_values)
        return True

    def get_report(self):
        """
        This Method relocates get rating report as an attachment in rating reports form view.
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
                    job = self.amz_search_or_create_rating_report_log()
                    job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
                else:
                    raise UserError(_(response.get('error', {})))
            else:
                result = response.get('result', {})
            if result:
                result = result.get('document', '')
                result = result.encode()
                result = base64.b64encode(result)
                file_name = "Rating_report_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
                attachment = self.env['ir.attachment'].create({
                    'name': file_name,
                    'datas': result,
                    'res_model': 'mail.compose.message',
                    'type': 'binary'
                })
                self.message_post(body=_("<b>Rating Report Downloaded</b>"),
                                  attachment_ids=attachment.ids)
                self.write({'attachment_id': attachment.id})
                seller.write({'rating_report_last_sync_on': datetime.now()})
        return True

    def download_report(self):
        """
        This Method relocates download amazon rating report.
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

    def process_rating_report(self):
        """
        This Method process rating report.
        :return:This Method return boolean(True/False).
        """
        self.ensure_one()
        ir_cron_obj = self.env['ir.cron']
        if not self._context.get('is_auto_process', False):
            ir_cron_obj.with_context({'raise_warning': True}).find_running_schedulers(
                'ir_cron_process_rating_request_report_seller_', self.seller_id.id)
        amazon_process_job_log_obj = self.env['common.log.book.ept']
        sale_order_obj = self.env['sale.order']
        rating_obj = self.env['rating.rating']
        ir_model = self.env['ir.model']
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))
        if not self.seller_id:
            raise UserError(_("Seller is not defined for processing report"))
        imp_file = StringIO(base64.b64decode(self.attachment_id.datas).decode())
        reader = csv.DictReader(imp_file, delimiter='\t')
        model_id = self.env['ir.model']._get('rating.report.history').id
        ir_model = ir_model.search([('model', '=', 'sale.order')])
        job = amazon_process_job_log_obj.search([('model_id', '=', model_id),
             ('res_id', '=', self.id)])
        if not job:
            job = amazon_process_job_log_obj.create({
                'module': 'amazon_ept',
                'type': 'import',
                'model_id': model_id,
                'res_id': self.id,
                'active': True,
                'log_lines': [(0, 0, {'message': 'Import Rating Report Process'})]
            })
        for row in reader:
            amz_order_id = row.get('Order ID', '')
            amz_rating_value = row.get('Rating', '')
            amz_rating_comment = row.get('Comments', '')
            amz_your_response = row.get('Your Response', '')
            amz_rating_date = row.get('Date', '')
            try:
                amz_rating_date = datetime.strptime(amz_rating_date, '%m/%d/%y')
            except:
                amz_rating_date = datetime.strptime(amz_rating_date, '%d/%m/%y')
            amazon_sale_order = sale_order_obj.search(
                [('amz_order_reference', '=', amz_order_id),
                 ('amz_instance_id', 'in', self.seller_id.instance_ids.ids)])
            if not amazon_sale_order:
                job.write({'log_lines': [
                    (0, 0, {'message': 'This Order %s does not exist in odoo' % (amz_order_id),
                            'order_ref': amz_order_id})]})
                continue
            amazon_order_rating = rating_obj.search(
                [('res_model', '=', 'sale.order'), ('res_id', '=', amazon_sale_order.id)])
            if not amazon_order_rating:
                rating_obj.create({
                    'rating': float(amz_rating_value) if amz_rating_value is not None else False,
                    'feedback': amz_rating_comment,
                    'res_model_id': ir_model.id,
                    'res_id': amazon_sale_order.id,
                    'consumed': True,
                    'partner_id': amazon_sale_order.partner_id.id,
                    'amz_instance_id': amazon_sale_order.amz_instance_id.id,
                    'amz_fulfillment_by': amazon_sale_order.amz_fulfillment_by,
                    'amz_rating_report_id': self.id,
                    'publisher_comment': amz_your_response,
                    'amz_rating_submitted_date': amz_rating_date
                })
            else:
                job.write({'log_lines': [\
                    (0, 0, {'message': 'For This Order %s rating already exist in odoo' % amz_order_id,
                            'order_ref': amz_order_id})]})
        self.write({'state': 'processed'})
        return True
