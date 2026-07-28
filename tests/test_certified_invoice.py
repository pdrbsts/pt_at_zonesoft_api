# -*- coding: utf-8 -*-
from odoo.tests import common

class TestCertifiedInvoiceVat(common.TransactionCase):

    def setUp(self):
        super(TestCertifiedInvoiceVat, self).setUp()
        self.AccountMove = self.env['account.move']

    def test_clean_vat_consumidor_final(self):
        vat = self.AccountMove._clean_vat("CONSUMIDOR FINAL", "CONSUMIDOR FINAL")
        self.assertEqual(vat, "999999990")

        vat2 = self.AccountMove._clean_vat(False, "CONSUMIDOR FINAL")
        self.assertEqual(vat2, "999999990")

        vat3 = self.AccountMove._clean_vat("PTCONSUMIDOR FINAL", "Cliente Sem NIF")
        self.assertEqual(vat3, "999999990")

    def test_clean_vat_valid_nif(self):
        vat = self.AccountMove._clean_vat("PT501234567", "Empresa Exemplo")
        self.assertEqual(vat, "501234567")

        vat2 = self.AccountMove._clean_vat("501 234 567", "Empresa Exemplo 2")
        self.assertEqual(vat2, "501234567")

    def test_process_certified_success_updates_name(self):
        partner = self.env['res.partner'].create({'name': 'Test Partner'})
        move = self.AccountMove.create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
        })
        move.name = 'INV/2026/00011'
        move._process_certified_success('FT AP2026L1II1/6', 'ATCUD123', 'QR123', 'dGVzdA==')
        self.assertEqual(move.name, 'FT AP2026L1II1/6')
        self.assertEqual(move.certified_invoice_number, 'FT AP2026L1II1/6')
        self.assertEqual(move.certified_invoice_status, 'sent')

