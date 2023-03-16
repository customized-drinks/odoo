from odoo import models, fields, api


class EmiproAppVersionDetails(models.Model):
    _inherit = 'emipro.app.version.details'

    def disable_notification_amazon_ept(self, module_name):
        """
        This method are used to find the update details of specific module, and disable the
        notification for that specific module for the customer.
        -----------------
        :param module_name: string
        :return: True
        """
        module = self.env['ir.module.module'].sudo()
        modules = module.search([('shortdesc', 'in', [module_name, 'Common Connector Library'])])
        if modules:
            details = self.sudo().search([('module_id', 'in', modules.ids)])
            if self.sudo().user_has_groups('amazon_ept.group_amazon_manager_ept') and details:
                details.write({'is_notify': False})
        return True
