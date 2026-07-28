# -*- coding: utf-8 -*-
import base64
from odoo import models

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if self._is_invoice_report(report_ref) and res_ids:
            moves = self.env['account.move'].browse(res_ids)
            certified_moves = moves.filtered(lambda m: m.certified_invoice_status == 'sent' and (m.invoice_pdf_report_id or m.message_main_attachment_id))
            if len(certified_moves) == len(moves) and len(moves) == 1:
                att = certified_moves.invoice_pdf_report_id or certified_moves.message_main_attachment_id
                if att:
                    pdf_content = att.raw or base64.b64decode(att.datas)
                    return pdf_content, 'pdf'
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
