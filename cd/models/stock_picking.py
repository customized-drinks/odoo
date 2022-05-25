# -*- coding: utf-8 -*-

from odoo import models, _, fields, api
from odoo.exceptions import UserError
import PyPDF2
import tempfile
import os
import base64
import io

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Another Operation'),
        ('confirmed', 'Waiting'),
        ('assigned', 'Ready'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', compute='_compute_state',
        copy=False, index=True, readonly=True, store=True, tracking=True,
        help=" * Draft: The transfer is not confirmed yet. Reservation doesn't apply.\n"
             " * Waiting another operation: This transfer is waiting for another operation before being ready.\n"
             " * Waiting: The transfer is waiting for the availability of some products.\n(a) The shipping policy is \"As soon as possible\": no product could be reserved.\n(b) The shipping policy is \"When all products are ready\": not all the products could be reserved.\n"
             " * Ready: The transfer is ready to be processed.\n(a) The shipping policy is \"As soon as possible\": at least one product has been reserved.\n(b) The shipping policy is \"When all products are ready\": all product have been reserved.\n"
             " * Processing: The transfer is being processed.\n"
             " * Done: The transfer has been processed.\n"
             " * Cancelled: The transfer has been cancelled.")

    delivery_note = fields.Text('Delivery Notes')
    relabel = fields.Char('Re-label')

    def _action_done(self):
        """Call `_action_done` on the `stock.move` of the `stock.picking` in `self`.
        This method makes sure every `stock.move.line` is linked to a `stock.move` by either
        linking them to an existing one or a newly created one.

        If the context key `cancel_backorder` is present, backorders won't be created.

        :return: True
        :rtype: bool
        """
        self._check_company()

        todo_moves = self.mapped('move_lines').filtered(
            lambda self: self.state in ['draft', 'waiting', 'partially_available', 'assigned', 'confirmed',
                                        'processing'])
        for picking in self:
            if picking.owner_id:
                picking.move_lines.write({'restrict_partner_id': picking.owner_id.id})
                picking.move_line_ids.write({'owner_id': picking.owner_id.id})
        todo_moves._action_done(cancel_backorder=self.env.context.get('cancel_backorder'))
        self.write({'date_done': fields.Datetime.now(), 'priority': '0'})

        # if incoming moves make other confirmed/partially_available moves available, assign them
        done_incoming_moves = self.filtered(lambda p: p.picking_type_id.code == 'incoming').move_lines.filtered(
            lambda m: m.state == 'done')
        done_incoming_moves._trigger_assign()

        self._send_confirmation_email()
        return True

    def do_unreserve(self):
        self.move_lines._do_unreserve()
        self.package_level_ids.filtered(lambda p: not p.move_ids).unlink()

    def set_processing(self):
        self.move_lines._set_processing()

    #
    # def _find_mail_template(self, force_confirmation_template=False):
    #     template_id = False
    #
    #     if force_confirmation_template or (self.state == 'sale' and not self.env.context.get('proforma', False)):
    #         template_id = int(self.env['ir.config_parameter'].sudo().get_param('sale.default_confirmation_template'))
    #         template_id = self.env['mail.template'].search([('id', '=', template_id)]).id
    #         if not template_id:
    #             template_id = self.env['ir.model.data'].xmlid_to_res_id('sale.mail_template_sale_confirmation', raise_if_not_found=False)
    #     if not template_id:
    #         template_id = self.env['ir.model.data'].xmlid_to_res_id('sale.email_template_edi_sale', raise_if_not_found=False)
    #
    #     return template_id
    #
    # def action_tracking_send(self):
    #     ''' Opens a wizard to compose an email, with relevant mail template loaded by default '''
    #     self.ensure_one()
    #     template_id = self._find_mail_template()
    #     template = self.env['mail.template'].browse(template_id)
    #     ctx = {
    #         'default_model': 'sale.order',
    #         'default_res_id': self.ids[0],
    #         'default_use_template': bool(template_id),
    #         'default_template_id': template_id,
    #         'default_composition_mode': 'comment',
    #         'custom_layout': "mail.mail_notification_paynow",
    #         'force_email': True
    #     }
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'view_mode': 'form',
    #         'res_model': 'mail.compose.message',
    #         'views': [(False, 'form')],
    #         'view_id': False,
    #         'target': 'new',
    #         'context': ctx,
    #     }

    def download_shipping_labels(self):
        # get all attachments for available pickings if exists.
        attachment_ids = self.env['ir.attachment'].search(
            [('res_model', '=', 'stock.picking'), ('res_id', 'in', self.ids), ('mimetype', '=', 'application/pdf')])
        if attachment_ids:
            try:
                pdfWriter = PyPDF2.PdfFileWriter()
                temp_path = tempfile.gettempdir()
                # get individual pdf and add its pages to pdfWriter
                for rec in attachment_ids:
                    if 'LabelDHL' not in rec.name:
                        continue
                    file_reader = PyPDF2.PdfFileReader(io.BytesIO(base64.b64decode(rec.datas)))
                    for pageNum in range(file_reader.numPages):
                        pageObj = file_reader.getPage(pageNum)
                        pdfWriter.addPage(pageObj)

                outfile_name = "Shipping_Labels.pdf"
                outfile_path = os.path.join(temp_path, outfile_name)
                # create a temp file and write data to create new combined pdf
                pdfOutputFile = open(outfile_path, 'wb')
                pdfWriter.write(pdfOutputFile)
                pdfOutputFile.close()


                final_attachment_id = False
                # Read the new combined pdf and store it in attachment to get download url
                with open(outfile_path, 'rb') as data:
                    datas = base64.b64encode(data.read())
                    attachment_obj = self.env['ir.attachment']
                    final_attachment_id = attachment_obj.sudo().create(
                        {'name': "Shipping_Labels", 'store_fname': outfile_name, 'datas': datas})

                # Delete the temp file to release space
                if os.path.exists(outfile_path):
                    os.remove(outfile_path)
                download_url = '/web/content/' + str(final_attachment_id.id) + '?download=true'
                base_url = 'http://localhost:8069'
                # base_url = self.env['ir.config_parameter'].get_param('web.base.url')
                return {
                    'name': 'Report',
                    'type': 'ir.actions.act_url',
                    'url': str(base_url) + str(download_url),
                    'target': 'new',
                }
            except Exception as e:
                raise UserError(_(e))
        else:
            raise UserError(_("No shipping labels available for selected records."))

