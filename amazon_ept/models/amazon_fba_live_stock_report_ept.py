# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Added class to get the  amazon live stock report and prepare sellable and unsellable
inventory and process that and added custom fields to store the seller, instance and
inventory information in created inventory report record
"""

import base64
import csv
import time
from datetime import datetime, timedelta
from io import StringIO
from dateutil import parser
import pytz

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError

from ..endpoint import DEFAULT_ENDPOINT

utc = pytz.utc


class AmazonLiveStockReportEpt(models.Model):
    """
    Class used to get the inventory report and process for
    manage sellable and unsellable inventory.
    """
    _name = "amazon.fba.live.stock.report.ept"
    _description = "Amazon Live Stock Report"
    _inherit = ['mail.thread']
    _order = 'id desc'

    @api.depends('seller_id')
    def _compute_company(self):
        """
        This method will set company in FBA Live Inventory report record.
        :return:
        """
        for record in self:
            company_id = record.seller_id.company_id.id if record.seller_id else False
            if not company_id:
                company_id = self.env.company.id
            record.company_id = company_id

    @api.model
    def create(self, vals):
        """
        Inherited method which help to set report name in FBA Live Inventory report.
        :param vals: dict {} report values
        :return: amazon.fba.live.stock.report.ept() object
        """
        sequence = self.env.ref('amazon_ept.seq_import_live_stock_report_job', raise_if_not_found=False)
        report_name = sequence.next_by_id() if sequence else '/'
        vals.update({'name': report_name})
        return super(AmazonLiveStockReportEpt, self).create(vals)

    def list_of_inventory(self):
        """
        This method will display the list of inventory records
        :return: ir.actions.act_window() action
        """
        action = {
            'domain': "[('id', 'in', " + str(self.inventory_ids.ids) + " )]",
            'name': 'FBA Live Stock Inventory',
            'view_mode': 'tree,form',
            'res_model': 'stock.inventory',
            'type': 'ir.actions.act_window',
        }
        return action

    def _compute_inventory_count(self):
        """
        This method will count the number of inventory records.
        :return:
        """
        for record in self:
            record.inventory_count = len(record.inventory_ids.ids)

    name = fields.Char(size=256)
    state = fields.Selection([('draft', 'Draft'), ('SUBMITTED', 'SUBMITTED'),
                              ('_SUBMITTED_', 'SUBMITTED'), ('IN_QUEUE', 'IN_QUEUE'),
                              ('IN_PROGRESS', 'IN_PROGRESS'), ('_IN_PROGRESS_', 'IN_PROGRESS'),
                              ('DONE', 'DONE'), ('_DONE_', 'DONE'), ('_DONE_NO_DATA_', 'DONE_NO_DATA'),
                              ('FATAL', 'FATAL'), ('processed', 'PROCESSED'),
                              ('CANCELLED', 'CANCELLED'), ('_CANCELLED_', 'CANCELLED')],
                             string='Report Status', default='draft',
                             help="This Field relocates state of fba live inventory process.")
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False,
                                help="Select Seller id from you wanted to get Shipping report")
    attachment_id = fields.Many2one('ir.attachment', string="Attachment",
                                    help="This Field relocates attachment id.")
    report_id = fields.Char('Report ID', readonly='1', help="This Field relocates report id.")
    report_type = fields.Char(size=256, help='This Field relocates report type.')
    report_request_id = fields.Char('Report Request ID', readonly='1',
                                    help="This Field relocates report request id of amazon.")
    report_document_id = fields.Char('Report Document ID', help="Report Document Reference")
    start_date = fields.Datetime(help="Report Start Date")
    end_date = fields.Datetime(help="Report End Date")
    requested_date = fields.Datetime(default=time.strftime("%Y-%m-%d %H:%M:%S"), help="Report Requested Date")
    report_date = fields.Date()
    inventory_ids = fields.One2many('stock.inventory', 'fba_live_stock_report_id', string='Inventory',
                                    help="This Field relocates inventory ids.")
    user_id = fields.Many2one('res.users', string="Requested User",
                              help="Track which odoo user has requested report")
    company_id = fields.Many2one('res.company', string="Company", copy=False, compute="_compute_company",
                                 store=True, help="This Field relocates amazon company")
    amz_instance_id = fields.Many2one('amazon.instance.ept', string="Amazon Instance",
                                      help="This Field relocates amazon instance.")
    amazon_program = fields.Selection(related="seller_id.amazon_program")
    inventory_count = fields.Integer(compute="_compute_inventory_count",
                                     help="This Field relocates Inventory count.")
    log_count = fields.Integer(compute="_compute_log_count")

    def unlink(self):
        """
        Inherited method which help to raise error message if trying to delete the processed
        FBA Live Inventory report.
        :return:
        """
        for report in self:
            if report.state == 'processed':
                raise UserError(_('You cannot delete processed report.'))
        return super(AmazonLiveStockReportEpt, self).unlink()

    def list_of_logs(self):
        """
        This method will help to display the mismatch log of processed FBA inventory report
        :return: ir.actions.act_window() action
        """
        model_id = self.env['ir.model']._get('amazon.fba.live.stock.report.ept').id
        action = {
            'domain': "[('res_id', '=', " + str(self.id) + " ), ('model_id', '=', " + str(model_id)
                      + ")]",
            'name': 'MisMatch Logs',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'common.log.book.ept',
            'type': 'ir.actions.act_window',
        }
        return action

    def _compute_log_count(self):
        """
        This method will count the number of logs in FBA Live Inventory report.
        :return:
        """
        common_log_book_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('amazon.fba.live.stock.report.ept').id
        self.log_count = common_log_book_obj.search_count(
            [('model_id', '=', model_id), ('res_id', '=', self.id)])

    @api.model
    def auto_import_amazon_fba_live_stock_report(self, args={}):
        """
        This method will help to import amazon fba live inventory reports.
        If European Seller:
            [PAN EU, EFN, CEP]: Import report Seller wise
            MCI: Import Report Instance wise
        :param args: dict {}
        :return: boolean (TRUE/FALSE)
        """
        seller_id = args.get('seller_id', False)
        uk_instance_id = args.get('uk_instance_id', False)
        seller = self.env['amazon.seller.ept'].browse(seller_id)
        instance_ids = []

        if not seller:
            return True
        if seller.inventory_report_last_sync_on:
            start_date = seller.inventory_report_last_sync_on
            start_date = datetime.strftime(start_date, '%Y-%m-%d %H:%M:%S')
            start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S')
            start_date = start_date + timedelta(
                days=seller.live_inv_adjustment_report_days * -1 or -3)

        else:
            start_date = datetime.strptime(
                datetime.now() and datetime.now().strftime("%Y-%m-%d %H:%M:%S"), '%Y-%m-%d %H:%M:%S')
            start_date = start_date + timedelta(days=seller.live_inv_adjustment_report_days * -1 or -3)
        date_end = datetime.now()
        date_end = date_end.strftime("%Y-%m-%d %H:%M:%S")

        if seller.is_another_soft_create_fba_inventory:
            if not start_date or not date_end:
                raise UserError(_('Please select Date Range'))
            vals = {'start_date': start_date,
                    'end_date': date_end,
                    'seller_id': seller}
            if args.get('instance_id', False) or uk_instance_id:
                instance_id = self.env['amazon.instance.ept'].browse(args.get('instance_id') or uk_instance_id)
                vals.update({'us_region_instance_id': instance_id})
            return self.with_context(is_auto_process=True).get_inventory_report(vals)

        if seller.amazon_program in ('pan_eu', 'cep'):
            if uk_instance_id:
                instance_ids = self.env['amazon.instance.ept'].browse(uk_instance_id)
            self.with_context(is_auto_process=True).create_and_request_amazon_live_inventory_report(
                seller, instance_ids, False, False, False)

        elif not seller.is_european_region and not seller.amz_fba_us_program == 'narf':
            report_date = datetime.now()
            if args.get('instance_id', False):
                instance_ids = self.env['amazon.instance.ept'].browse(args.get('instance_id'))
            else:
                instance_ids = seller.instance_ids

            self.with_context(is_auto_process=True).create_and_request_amazon_live_inventory_report(
                seller, instance_ids, report_date, start_date, date_end)

        elif seller.amazon_program == 'efn' or seller.amz_fba_us_program == 'narf':
            # If seller is NARF then pass Amazon.com marketplace
            # If seller is efn then must be pass seller efn inventory country marketplace.
            if seller.amz_fba_us_program == 'narf':
                instance_ids = seller.instance_ids.filtered(
                    lambda instance: instance.market_place_id == 'ATVPDKIKX0DER')
            else:
                instance_ids = seller.instance_ids.filtered(
                    lambda instance: instance.country_id.id == seller.store_inv_wh_efn.id)

            self.with_context(is_auto_process=True).create_and_request_amazon_live_inventory_report(
                seller, instance_ids, False, start_date, date_end)

        elif seller.amazon_program in ('mci', 'efn+mci'):
            if args.get('instance_id', False):
                instance_ids = self.env['amazon.instance.ept'].browse(args.get('instance_id'))
            else:
                instance_ids = seller.instance_ids
            self.with_context(is_auto_process=True).create_and_request_amazon_live_inventory_report(
                seller, instance_ids, False, start_date, date_end)

        return True

    def create_and_request_amazon_live_inventory_report(self, seller_id, instance_ids, report_date,
                                                        start_date, end_date):
        """
        Define method which help to create and request FBA Live Inventory Report as per
        seller and instances
        :param seller_id: amazon.seller.ept() object
        :param instance_ids: list of amazon.instance.ept() object
        :param report_date: report date
        :param start_date: report start date
        :param end_date: report end date
        :return: list of amazon.fba.live.stock.report.ept() objects ids
        """
        is_auto_process = self._context.get('is_auto_process', False)
        report_type = 'GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA'
        fba_live_stock_report_ids = []
        live_inventory_request_report_record = self.env['amazon.fba.live.stock.report.ept']
        fba_live_stock_report_values = {'seller_id': seller_id.id, 'report_type': report_type,
                                        'report_date': report_date, 'start_date': start_date,
                                        'end_date': end_date}

        if not instance_ids:
            fba_live_stock_report = live_inventory_request_report_record.create(fba_live_stock_report_values)
            fba_live_stock_report.with_context(is_auto_process=True).request_report() if is_auto_process else \
                fba_live_stock_report.request_report()
            fba_live_stock_report_ids.append(fba_live_stock_report.id)
            return fba_live_stock_report_ids

        for instance in instance_ids:
            fba_live_stock_report_values.update({'amz_instance_id': instance.id, })
            fba_live_stock_report = live_inventory_request_report_record.create(fba_live_stock_report_values)
            fba_live_stock_report.with_context(is_auto_process=True).request_report() if is_auto_process else\
                fba_live_stock_report.request_report()
            fba_live_stock_report_ids.append(fba_live_stock_report.id)
        return fba_live_stock_report_ids

    def get_inventory_report(self, vals):
        """
        Define method which help to process prepare inventory report ids and return
        the created inventory records
        :param vals: dict {} start date, end date and seller
        :return: list of amazon.fba.live.stock.report.ept() records
        """
        amazon_process_job_log_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('amazon.fba.live.stock.report.ept').id
        inv_report_ids = []
        start_date = vals.get('start_date', '')
        end_date = vals.get('end_date', '')
        seller = vals.get('seller_id', False)
        instance = vals.get('us_region_instance_id', False)
        if start_date and end_date:
            start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S')
            end_date = datetime.strptime(str(end_date), '%Y-%m-%d %H:%M:%S')
        elif self.inventory_report_last_sync_on:
            start_date = self.inventory_report_last_sync_on
            start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S')
            end_date = datetime.strptime(str(end_date), '%Y-%m-%d %H:%M:%S')
        else:
            start_date = datetime.now() + timedelta(
                days=seller.live_inv_adjustment_report_days * -1 or -3)
            start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S')
            date_end = datetime.now()
            end_date = date_end.strftime("%Y-%m-%d %H:%M:%S")

        log_rec = amazon_process_job_log_obj.amazon_create_transaction_log('import', model_id, self.id)

        inv_report_ids = self.prepare_amazon_inventory_report_ids_ept(
            seller, inv_report_ids, start_date, end_date, log_rec, instance)

        if inv_report_ids:
            action = self.env.ref('amazon_ept.action_live_stock_report_ept', False)
            result = action.read()[0] if action else {}

            if len(inv_report_ids) > 1:
                result['domain'] = "[('id','in',[" + ','.join(map(str, inv_report_ids)) + "])]"
            else:
                res = self.env.ref('amazon_ept.amazon_live_stock_report_form_view_ept', False)
                result['views'] = [(res and res.id or False, 'form')]
                result['res_id'] = inv_report_ids[0] if inv_report_ids else False
            return result

    def prepare_amazon_inventory_report_ids_ept(self, seller, inv_report_ids, start_date, end_date,
                                                log_rec, instance=False):
        """
        This method is used to prepare amazon inventory report ids.
        :param seller: amazon.seller.ept() object
        :param inv_report_ids: list of inventory report ids
        :param start_date: report start date
        :param end_date: report end date
        :param log_rec: common.log.book.ept() object
        :param instance: amazon.instance.ept() object
        :return: list of inventory report ids
        """
        report_type = 'GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA'
        if (seller.amazon_program in ('pan_eu', 'cep') or not seller.is_european_region) and (not seller.amz_fba_us_program == 'narf'):
            inv_report_ids = self.get_live_inventory_report(report_type, inv_report_ids, start_date,
                                                            end_date, log_rec, seller, seller.amazon_program, instance)
        else:
            start_date = (datetime.today().date() - timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            end_date = (datetime.today().date() - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')
            inv_report_ids = self.get_live_inventory_report(report_type, inv_report_ids, start_date,
                                                            end_date, log_rec, seller, seller.amazon_program, instance)
        return inv_report_ids

    def prepare_amz_live_inventory_report_kwargs(self, seller, emipro_api):
        """
        Prepare General Amazon Request dictionary.
        :param seller: amazon.seller.ept()
        :param emipro_api : name of api to request for different amazon operation
        :return: dict {}
        """
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        return {'merchant_id': seller.merchant_id if seller.merchant_id else False,
                'app_name': 'amazon_ept_spapi',
                'emipro_api': emipro_api,
                'account_token': account.account_token,
                'dbuuid': dbuuid,
                'amazon_marketplace_code': seller.country_id.amazon_marketplace_code or
                                           seller.country_id.code, }

    def get_live_inventory_report(self, report_type, inv_report_ids, start_date, end_date, job,
                                  seller, amazon_program, instance_id=False):
        """
        This method is used to get the live inventory report based on amazon
        program return the inventory record ids and update the
        inventory_report_last_sync_on.
        :param report_type: fba live inventory report
        :param inv_report_ids: fba live inventory report ids
        :param start_date: fba live inventory report start date
        :param end_date: fba live inventory report end date
        :param job: common.log.boo.ept() object
        :param seller: amazon.seller.ept() object
        :param amazon_program: seller amazon program
        :param instance_id: amazon.instance.ept() object
        :return: list of fba live inventory report records ids
        """
        list_of_wrapper = []
        if instance_id:
            instances = instance_id
        else:
            instances = seller.instance_ids
        if not seller.is_european_region:
            con_start_date, con_end_date = self.report_start_and_end_date_cron(start_date, end_date)
            kwargs = self.prepare_amz_live_inventory_report_kwargs(seller, 'get_reports_sp_api')
            kwargs.update({'start_date': con_start_date, 'end_date': con_end_date,
                           'report_type': [report_type], 'marketplaceids': instances.mapped('market_place_id')})
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
            if response.get('error', False):
                if self._context.get('is_auto_process', False):
                    job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
                else:
                    raise UserError(_(response.get('error', {})))
            else:
                list_of_wrapper = response.get('result', {})

            if instance_id:
                inv_report_ids = self.with_context({
                    'amz_instance_id': instances.id}).request_for_amazon_live_inv_report_ids(
                    seller, list_of_wrapper, inv_report_ids)
            else:
                inv_report_ids = self.request_for_amazon_live_inv_report_ids(seller, list_of_wrapper, inv_report_ids)
        if amazon_program in ('pan_eu', 'cep', 'efn', 'mci', 'mci+efn'):
            con_start_date, con_end_date = self.report_start_and_end_date_cron(start_date, end_date)
            if amazon_program == 'pan_eu' and not instance_id:
                instances = instances.filtered(lambda x: not x.market_place_id == 'A1F83G8C2ARO7P')
            kwargs = self.prepare_amz_live_inventory_report_kwargs(seller, 'get_reports_sp_api')
            kwargs.update({'start_date': con_start_date, 'end_date': con_end_date,
                           'report_type': [report_type], 'marketplaceids': instances.mapped('market_place_id')})
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
            if response.get('error', False):
                if self._context.get('is_auto_process', False):
                    job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
                else:
                    raise UserError(_(response.get('error', {})))
            else:
                list_of_wrapper = response.get('result', {})
            if instance_id:
                inv_report_ids = self.with_context(
                    {'amz_instance_id': instances.id}).request_for_amazon_live_inv_report_ids(
                    seller, list_of_wrapper, inv_report_ids)
            else:
                inv_report_ids = self.request_for_amazon_live_inv_report_ids(seller, list_of_wrapper, inv_report_ids)
        if inv_report_ids:
            seller.write({'inventory_report_last_sync_on': end_date})
        return inv_report_ids

    def request_for_amazon_live_inv_report_ids(self, seller, list_of_wrapper, inv_report_ids):
        """
        This method is used to process the result and based on that it will find
        report exist if not than create and return the list of inventory records
        :param seller: amazon.seller.ept() object
        :param list_of_wrapper: list of fba live inventory report response
        :param inv_report_ids: list of fba live inventory report records ids
        :return: list of fba live inventory report records ids
        """
        ctx = self._context.copy() or {}
        latest_report = []
        list_of_wrapper = list_of_wrapper.get('reports', {}) if list_of_wrapper else []
        for result in list_of_wrapper:
            processing_status = result.get('processingStatus', '')
            processing_endtime = result.get('dataEndTime', '')
            if not latest_report and processing_status in ('DONE', '_DONE_'):
                latest_report.append(result)
            if latest_report and latest_report[0].get('dataEndTime') < processing_endtime \
                    and processing_status in ('_DONE_', 'DONE'):
                latest_report = [result]

        for report in latest_report:
            amz_start_date = parser.parse(str(report.get('dataStartTime'))).astimezone(utc).strftime('%Y-%m-%d %H:%M:%S')
            amz_end_date = parser.parse(str(report.get('dataEndTime'))).astimezone(utc).strftime('%Y-%m-%d %H:%M:%S')
            submitted_date = parser.parse(str(report.get('createdTime'))).astimezone(utc).strftime('%Y-%m-%d %H:%M:%S')
            report_id = report.get('reportId', '')
            report_document_id = report.get('reportDocumentId', '')
            report_type = report.get('reportType', '')
            state = report.get('processingStatus', '')
            report_exist = self.search(['|', ('report_document_id', '=', report_document_id), ('report_id', '=', report_id),
                                        ('report_type', '=', report_type)])
            if report_exist:
                report_exist = report_exist[0]
                inv_report_ids.append(report_exist.id)
                continue
            inventory_report_values = {'report_type': report_type,
                                       'report_document_id': report_document_id,
                                       'report_id': report_id,
                                       'start_date': amz_start_date,
                                       'end_date': amz_end_date,
                                       'requested_date': submitted_date,
                                       'state': state,
                                       'seller_id': seller.id,
                                       'user_id': self._uid,}
            if ctx.get('amz_instance_id', False):
                instance_id = ctx.get('amz_instance_id')
                inventory_report_values.update({'amz_instance_id': instance_id})

            inv_report_id = self.create(inventory_report_values)
            inv_report_ids.append(inv_report_id.id)
        return inv_report_ids

    @staticmethod
    def report_start_and_end_date_cron(start_date, end_date):
        """
        Prepare start date and end Date for request reports
        :param start_date: fba inventory report start date
        :param end_date: fba inventory report end date
        :return: start_date and end_date
        """
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

    @api.model
    def auto_process_amazon_fba_live_stock_report(self, args={}):
        """
        This method will process fba live stock report via cron
        :param args: dict {} of seller details
        :return: boolean(TRUE/FALSE)
        """
        seller_id = args.get('seller_id', False)
        seller = self.env['amazon.seller.ept'].browse(seller_id)
        if not seller:
            return True
        fba_live_stock_report_ids = self.search([('seller_id', '=', seller.id),
                                                 ('state', 'in', ['_SUBMITTED_', '_IN_PROGRESS_', 'SUBMITTED',
                                                                  'IN_PROGRESS', 'IN_QUEUE'])])
        for live_stock_report_id in fba_live_stock_report_ids:
            live_stock_report_id.with_context(is_auto_process=True).get_report_request_list()

        reports = self.search([('seller_id', '=', seller.id),
                               ('state', 'in', ['_DONE_', '_SUBMITTED_', '_IN_PROGRESS_', 'IN_QUEUE',
                                                'SUBMITTED', 'IN_PROGRESS', 'DONE']),
                               ('report_document_id', '!=', False)])
        for report in reports:
            if report.state in ['_DONE_', 'DONE'] and not report.attachment_id:
                report.with_context(is_auto_process=True).get_report()
            if report.state in ['_DONE_', 'DONE'] and report.attachment_id:
                report.with_context(is_auto_process=True).process_fba_live_stock_report()
            self._cr.commit()
        return True

    @api.constrains('start_date', 'end_date')
    def _check_duration(self):
        """
        This Method check date duration,
        :return: This Method return Boolean(True/False)
        """
        if self.start_date and self.end_date < self.start_date:
            raise UserError(_('Error!\nThe start date must be precede its end date.'))
        return True

    def request_report(self):
        """
        Request GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA Report
                from Amazon for specific date range.
        :return: This Method return Boolean(True/False).
        """
        amazon_instance = self.env['amazon.instance.ept']
        seller, report_type = self.seller_id, self.report_type
        if not seller:
            raise UserError(_('Please select Seller'))
        start_date, end_date = self.report_start_and_end_date()
        if self.amz_instance_id:
            marketplaceids = self.amz_instance_id.mapped('market_place_id')
        elif seller.amz_fba_us_program == 'narf':
            marketplaceids = ['ATVPDKIKX0DER']
        else:
            if seller.amazon_program in ('pan_eu', 'cep'):
                instances = amazon_instance.search([('seller_id', '=', seller.id),
                                                    ('market_place_id', '!=', 'A1F83G8C2ARO7P')])
            else:
                instances = amazon_instance.search([('seller_id', '=', seller.id)])
            marketplaceids = tuple(map(lambda x: x.market_place_id, instances))
        if start_date and end_date:
            kwargs = self.prepare_amz_live_inventory_report_kwargs(seller, 'create_report_sp_api')
            kwargs.update({'start_date': start_date, 'end_date': end_date, })
        else:
            kwargs = self.prepare_amz_live_inventory_report_kwargs(seller, 'create_report_without_date_sp_api')
        kwargs.update({'report_type': report_type, 'marketplaceids': marketplaceids})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            if self._context.get('is_auto_process', False):
                job = self.create_amazon_live_inventory_report_logs()
                job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
            else:
                raise UserError(_(response.get('error', {})))
        if response.get('result', {}):
            self.update_report_history(response.get('result', {}))
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

    @api.model
    def update_report_history(self, request_result):
        """
        This Method relocates update Report History in odoo.
        :param request_result: This arguments relocates request result.
        :return: This Method return Boolean(True/False).
        """
        report_id = request_result.get('reportId', '')
        report_document_id = request_result.get('reportDocumentId', '')
        report_state = request_result.get('processingStatus', 'SUBMITTED')
        stock_live_inventory_values = {}
        if report_document_id:
            stock_live_inventory_values.update({'report_document_id': report_document_id})
        if report_state:
            stock_live_inventory_values.update({'state': report_state})
        if report_id:
            stock_live_inventory_values.update({'report_id': report_id})
        self.write(stock_live_inventory_values)
        return True

    def get_report_request_list(self):
        """
        This Method relocates get report list from amazon.
        :return: This Method return boolean(True/False).
        """
        self.ensure_one()
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select Seller'))
        if not self.report_id:
            return True
        kwargs = self.prepare_amz_live_inventory_report_kwargs(seller, 'get_report_sp_api')
        kwargs.update({'report_id': self.report_id})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            if self._context.get('is_auto_process', False):
                job = self.create_amazon_live_inventory_report_logs()
                job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
            else:
                raise UserError(_(response.get('error', {})))
        if response.get('result', {}):
            self.update_report_history(response.get('result', {}))
            if self.state in ['_DONE_', 'DONE'] and self.report_document_id:
                self.get_report()
        return True

    def get_report(self):
        """
        This Method relocates get live inventory report as an attachment in amazon fba live stock
        report ept form view.
        :return: This Method return boolean(True/False).
        """
        self.ensure_one()
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select seller'))
        if not self.report_document_id:
            return True
        kwargs = self.prepare_amz_live_inventory_report_kwargs(seller, 'get_report_document_sp_api')
        kwargs.update({'reportDocumentId': self.report_document_id, })
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('error', False):
            if self._context.get('is_auto_process', False):
                job = self.create_amazon_live_inventory_report_logs()
                job.write({'log_lines': [(0, 0, {'message': response.get('error', {})})]})
            else:
                raise UserError(_(response.get('error', {})))
        if response.get('result', {}):
            result = response.get('result', {})
            result = result.get('document', '')
            result = result.encode()
            result = base64.b64encode(result)
            file_name = "Fba_Live_report_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
            attachment = self.env['ir.attachment'].create({
                'name': file_name,
                'datas': result,
                'res_model': 'mail.compose.message',
                'type': 'binary'
            })
            self.message_post(body=_("<b>Live Inventory Report Downloaded</b>"),
                              attachment_ids=attachment.ids)
            self.write({'attachment_id': attachment.id})
        return True

    def download_report(self):
        """
        This Method relocates download amazon fba live stock  report.
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

    def process_fba_live_stock_report(self):
        """
        This Method relocates processed fba live stock reports.
        This Method prepare sellable line dict, unsellable line dict and
            generate inventory based on sellable line dict, unsellable line.
        :return: boolean(TRUE/FALSE)
        """
        self.ensure_one()
        ir_cron_obj = self.env['ir.cron']
        if not self._context.get('is_auto_process', False):
            ir_cron_obj.with_context({'raise_warning': True}).find_running_schedulers(
                'ir_cron_process_fba_live_stock_report_seller_', self.seller_id.id)
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))

        imp_file = StringIO(base64.decodebytes(self.attachment_id.datas).decode())
        reader = csv.DictReader(imp_file, delimiter='\t')
        job = self.create_amazon_live_inventory_report_logs()

        sellable_line_dict, unsellable_line_dict = self.fill_dictionary_from_file_by_instance(reader, job)
        if self.amz_instance_id:
            amz_warehouse = self.amz_instance_id.fba_warehouse_id or False
        else:
            fba_warehouse_ids = self.seller_id.amz_warehouse_ids.filtered(lambda l: l.is_fba_warehouse)
            amz_warehouse = fba_warehouse_ids[0] if fba_warehouse_ids else False

        if amz_warehouse:
            self.create_stock_inventory_from_amazon_live_report(
                sellable_line_dict, unsellable_line_dict, amz_warehouse, self.id, seller=self.seller_id, job=job)

        if job and not job.log_lines:
            job.unlink()

        self.write({'state': 'processed'})
        self.set_fulfillment_channel_sku()
        return True

    def create_amazon_live_inventory_report_logs(self):
        """
        This method will help to find or create log book record for FBA Live Inventory report.
        :return: common.log.book.ept() object
        """
        amazon_process_job_log_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('amazon.fba.live.stock.report.ept').id
        log_rec = amazon_process_job_log_obj.search([('model_id', '=', model_id), ('res_id', '=', self.id)])
        if log_rec and log_rec.log_lines:
            log_rec.log_lines.unlink()
        if not log_rec:
            log_rec = amazon_process_job_log_obj.amazon_create_transaction_log('import', model_id, self.id)
        return log_rec

    def fill_dictionary_from_file_by_instance(self, reader, job):
        """
        This method is used to prepare sellable product qty dict and unsellable product qty dict
        as per the instance selected in report.
        This qty will be passed to create stock inventory adjustment report.
        :param reader: This Arguments relocates report of amazon fba live inventory data.
        :param job: This Arguments relocates job log of amazon fba live inventory.
        :return: This Method prepare and return sellable line dict, unsellable line dict.
        """
        sellable_line_dict = {}
        unsellable_line_dict = {}
        product_obj = self.env['product.product']
        for row in reader:
            seller_sku = row.get('sku', '') or row.get('seller-sku', '')
            afn_listing = row.get('afn-listing-exists', '')
            if afn_listing == '' or not seller_sku:
                continue
            amazon_product = self.process_report_and_find_amazon_product(row)
            odoo_product = amazon_product.product_id if amazon_product else False
            if not odoo_product:
                odoo_product = product_obj.search([('default_code', '=', seller_sku)], limit=1)
                if not odoo_product:
                    message = "Product not found for seller sku %s" % (seller_sku)
                    job.write({'log_lines': [(0, 0, {'message': message, 'default_code': seller_sku})]})
                    continue

            sellable_qty = sellable_line_dict.get(odoo_product, 0.0)
            if self.seller_id.amz_is_reserved_qty_included_inventory_report:
                sellable_line_dict.update(
                    {odoo_product: sellable_qty + float(row.get('afn-fulfillable-quantity', 0.0)) + float(
                        row.get('afn-reserved-quantity', 0.0))})
            else:
                sellable_line_dict.update(
                    {odoo_product: sellable_qty + float(row.get('afn-fulfillable-quantity', 0.0))})
            unsellable_qty = unsellable_line_dict.get(odoo_product, 0.0)
            unsellable_line_dict.update({odoo_product: unsellable_qty + float(row.get('afn-unsellable-quantity', 0.0))})
        return sellable_line_dict, unsellable_line_dict

    def process_report_and_find_amazon_product(self, row):
        """
        This method will process report and find the amazon product and return that
        :param row:
        :return: amazon.product.ept() object
        """
        amazon_product_obj = self.env['amazon.product.ept']
        amazon_instance_obj = self.env['amazon.instance.ept']
        instance_ids = amazon_instance_obj.search([('seller_id', '=', self.seller_id.id)]).ids
        seller_sku = row.get('sku', '') or row.get('seller-sku', '')
        domain = [('seller_sku', '=', seller_sku), ('fulfillment_by', '=', 'FBA')]
        if self.amz_instance_id:
            domain.append(('instance_id', '=', self.amz_instance_id.id))
        else:
            domain.append(('instance_id', 'in', instance_ids))

        amazon_product = amazon_product_obj.search(domain, limit=1)
        if not amazon_product:
            product_asin = row.get('asin', '')
            domain = [('product_asin', '=', product_asin), ('fulfillment_by', '=', 'FBA')]
            if self.amz_instance_id:
                domain.append(('instance_id', '=', self.amz_instance_id.id))
            else:
                domain.append(('instance_id', 'in', instance_ids))
            amazon_product = amazon_product_obj.search(domain, limit=1)
        return amazon_product

    def create_fba_live_stock_report(self, line_dict, location_ids, inventory_name,
                                     inventory_report_id, amazon_warehouse_location, amazon_company):

        """
        This Method relocates prepare inventory dictionary.
        :param line_dict: This Arguments relocates sellable line dict, unsellable line dict.
        :param location_ids: This Arguments relocates amazon warehouse stock location ids list.
        :param inventory_name: This Arguments relocates inventory name.
        :param inventory_report_id: This Arguments relocates inventory report id.
        :param amazon_warehouse_location: This Arguments relocates amazon warehouse location.o
        :param amazon_company: This Arguments relocates amazon company based on amazon warehouse.
        :return: This Method prepare and return inventory dictionary.
        """
        inventory_line_list = []
        product_ids = []
        sellable_products = []
        for product, product_qty in line_dict.items():
            if product.id in sellable_products:
                continue
            sellable_products.append(product.id)
            theoretical_qty_dict = self._get_theoretical_qty(product, product_qty,
                                                             amazon_warehouse_location)

            for product_line in theoretical_qty_dict:
                inventory_line_list.append((0, 0, product_line))
                product_ids.append(product_line['product_id'])

        return {
            'name': inventory_name,
            'fba_live_stock_report_id': inventory_report_id,
            'location_ids': [(6, 0, location_ids or False)],
            'date': time.strftime("%Y-%m-%d %H:%M:%S"),
            'company_id': amazon_company,
            'line_ids': inventory_line_list,
            'product_ids': [(6, 0, product_ids)]
        }

    @staticmethod
    def start_inventory(inventory, seller, job):
        """
        This Method relocates start inventory and done inventory.
        :param inventory: This Arguments relocates created inventory object.
        :param seller: This Arguments relocates fba report seller.
        :param job: This Arguments relocates job log of amazon fba live inventory.
        """
        if inventory:
            try:
                inventory.action_start()
                if seller.validate_stock_inventory_for_report:
                    inventory._action_done()
            except Exception as exception:
                message = 'Error found while creating inventory %s.' % (str(exception))
                job.write({'log_lines': [(0, 0, {'message': message})]})

    def create_stock_inventory_from_amazon_live_report(self, sellable_line_dict, unsellable_line_dict,
                                                       amz_warehouse, inventory_report_id, seller=False, job=''):
        """
        This Method relocates create stock inventory from amazon live report.
        This Method prepare inventory dictionary and create inventory.
        :param sellable_line_dict: This Arguments relocates sellable line dict.
        :param unsellable_line_dict: This Arguments relocates unsellable line dict.
        :param amz_warehouse:  This Arguments relocates amazon warehouse based on seller.
        :param inventory_report_id: This Arguments relocates inventory report id.
        :param seller: This Arguments relocates fba report seller.
        :param job: This Arguments relocates job log of amazon fba live inventory.
        :return: This Method return boolean (True/False).
        """
        amazon_live_stock_report_obj = self.env['amazon.fba.live.stock.report.ept']
        stock_inventory = self.env['stock.inventory']
        inventory_report = amazon_live_stock_report_obj.browse(inventory_report_id)
        amazon_company = amz_warehouse.company_id.id if amz_warehouse.company_id else False

        if sellable_line_dict:
            name = inventory_report.name or "INV-HIST"
            inventory_name = 'Sellable_%s' % name
            location_ids = amz_warehouse.lot_stock_id.ids
            amazon_warehouse_location = amz_warehouse.lot_stock_id.id
            inventory_vals = self.create_fba_live_stock_report(sellable_line_dict, location_ids,
                                                               inventory_name,
                                                               inventory_report_id,
                                                               amazon_warehouse_location,
                                                               amazon_company)
            inventory = stock_inventory.create(inventory_vals)
            self.start_inventory(inventory, seller, job)
        if not amz_warehouse.unsellable_location_id:
            message = 'unsellable location not found for warehouse %s.' % (amz_warehouse.name)
            job.write({'log_lines': [(0, 0, {'message': message})]})
        else:
            if unsellable_line_dict:
                name = inventory_report.name or "INV-HIST"
                unsellable_inventory_name = 'Unsellable_%s' % name
                amz_warehouse_ids = amz_warehouse.unsellable_location_id.ids
                amazon_warehouse_location = amz_warehouse.unsellable_location_id.id
                unsellable_inventory_vals = self.create_fba_live_stock_report(
                    unsellable_line_dict, amz_warehouse_ids, unsellable_inventory_name,
                    inventory_report_id, amazon_warehouse_location, amazon_company)
                unsellable_inventory = stock_inventory.create(unsellable_inventory_vals)
                self.start_inventory(unsellable_inventory, seller, job)
        return True

    def _get_theoretical_qty(self, product, file_qty, location):
        """
        This Method relocates get theoretical qty based on product,file_qty and location.
        :param product: This Arguments relocates product of amazon.
        :param file_qty: This Arguments relocates file quantity of amazon.
        :param location: This Arguments relocates location of amazon.
        :return: This Method return theoretical inventory line.
        """
        location_obj = self.env['stock.location']
        locations = location_obj.search([('id', 'child_of', [location])])
        domain = ' location_id in %s and product_id = %s'
        args = (tuple(locations.ids), (product.id,))
        vals = []
        flag = True
        self._cr.execute('''
           SELECT product_id, sum(quantity) as product_qty, location_id, lot_id as prod_lot_id, package_id, owner_id as partner_id
           FROM stock_quant WHERE''' + domain + '''
           GROUP BY product_id, location_id, lot_id, package_id, partner_id''', args)

        for product_line in self._cr.dictfetchall():
            for key, value in product_line.items():
                if not value:
                    product_line[key] = False
            product_line['inventory_id'] = self.id
            product_line['theoretical_qty'] = product_line['product_qty']
            if flag:
                product_line['product_qty'] = file_qty
                flag = False
            else:
                product_line['product_qty'] = 0.0
            if product_line['product_id']:
                product_line['product_uom_id'] = product.uom_id.id
            vals.append(product_line)

        if not vals and file_qty > 0.0:
            vals.append({'product_id': product.id,
                         'inventory_id': self.id,
                         'theoretical_qty': 0.0,
                         'location_id': location,
                         'product_qty': file_qty,
                         'product_uom_id': product.uom_id.id, })
        return vals

    def set_fulfillment_channel_sku(self):
        """
        This Method relocates set fulfillment channel sku.
        :return: This Method return boolean(True/False).
        """
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))
        amazon_product_ept_obj = self.env['amazon.product.ept']
        imp_file = StringIO(base64.decodebytes(self.attachment_id.datas).decode())
        reader = csv.DictReader(imp_file, delimiter='\t')
        for row in reader:
            seller_sku = row.get('sku', False)
            fulfillment_channel_sku = row.get('fnsku', False)
            amazon_product = amazon_product_ept_obj.search(
                [('seller_sku', '=', seller_sku), ('fulfillment_by', '=', 'FBA')])
            for product in amazon_product:
                if not product.fulfillment_channel_sku:
                    product.update({'fulfillment_channel_sku': fulfillment_channel_sku})
        return True
