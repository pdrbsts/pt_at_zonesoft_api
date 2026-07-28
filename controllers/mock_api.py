# -*- coding: utf-8 -*-
import base64
import io
import random
from odoo import http
from odoo.http import request
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

class CertifiedInvoiceMockController(http.Controller):

    @http.route('/api/v1/mock_certified_invoice', type='json', auth='public', methods=['POST'], csrf=False)
    def mock_certified_invoice(self, **kwargs):
        payload = request.dispatcher.jsonrequest
        # If payload was wrapped in params (Odoo JSON-RPC standard)
        if 'params' in payload and isinstance(payload['params'], dict):
            data = payload['params']
        else:
            data = payload

        doc_type = data.get('document_type', 'FT')
        internal_ref = data.get('internal_reference', 'INV/2026/0001')
        customer = data.get('customer', {})
        company = data.get('company', {})
        items = data.get('items', [])
        totals = data.get('totals', {})

        seq_num = random.randint(1000, 9999)
        certified_number = f"{doc_type} 2026/{seq_num}"
        atcud = f"0-AT{random.randint(100000, 999999)}-{seq_num}"
        qr_code = f"A:{company.get('vat','999999990')}*B:{customer.get('vat','999999990')}*C:PT*D:{doc_type}*E:N*F:20260728*G:{certified_number}*H:{atcud}*I1:PT*I7:{totals.get('amount_tax',0.0):.2f}*I8:{totals.get('amount_total',0.0):.2f}"

        # Generate PDF using ReportLab
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header Title
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, "FATURA CERTIFICADA (AUTORIDADE TRIBUTÁRIA PT)")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 68, "Emitida via API de Integração Externa Certificada")

        # Company Info (Left)
        p.setFont("Helvetica-Bold", 11)
        p.drawString(50, height - 100, f"EMISSOR: {company.get('name', 'Empresa Exemplo Lda')}")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 115, f"NIF: {company.get('vat', '999999990')}")
        p.drawString(50, height - 130, f"Morada: {company.get('street', '')} {company.get('zip', '')} {company.get('city', '')}")

        # Customer Info (Right)
        p.setFont("Helvetica-Bold", 11)
        p.drawString(320, height - 100, f"CLIENTE: {customer.get('name', 'Consumidor Final')}")
        p.setFont("Helvetica", 10)
        p.drawString(320, height - 115, f"NIF: {customer.get('vat', '999999990')}")
        p.drawString(320, height - 130, f"Morada: {customer.get('street', '')} {customer.get('zip', '')} {customer.get('city', '')}")

        # Document Details Box
        p.setStrokeColor(colors.gray)
        p.setFillColor(colors.HexColor('#F0F4F8'))
        p.rect(50, height - 200, 495, 50, fill=True, stroke=True)

        p.setFillColor(colors.black)
        p.setFont("Helvetica-Bold", 11)
        p.drawString(65, height - 175, f"Documento Certificado: {certified_number}")
        p.setFont("Helvetica", 10)
        p.drawString(65, height - 190, f"Data: {data.get('invoice_date')}  |  Ref. Interna Odoo: {internal_ref}")
        p.drawString(320, height - 175, f"Código ATCUD: {atcud}")

        # Items Table Header
        y = height - 230
        p.setFillColor(colors.HexColor('#1E293B'))
        p.rect(50, y, 495, 20, fill=True, stroke=False)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 9)
        p.drawString(55, y + 6, "DESCRIÇÃO / ARTIGO")
        p.drawString(280, y + 6, "QTD")
        p.drawString(330, y + 6, "PREÇO UNI.")
        p.drawString(410, y + 6, "IVA %")
        p.drawString(470, y + 6, "TOTAL (€)")

        # Table Rows
        p.setFillColor(colors.black)
        p.setFont("Helvetica", 9)
        y -= 18
        for item in items:
            p.drawString(55, y, str(item.get('name', 'Artigo'))[:40])
            p.drawString(280, y, f"{item.get('quantity', 1):.2f}")
            p.drawString(330, y, f"{item.get('price_unit', 0.0):.2f} €")
            p.drawString(410, y, f"{item.get('tax_rate', 0.0):.1f} %")
            p.drawString(470, y, f"{item.get('price_total', 0.0):.2f} €")
            y -= 16

        # Totals Section
        y -= 20
        p.line(50, y + 15, 545, y + 15)
        p.setFont("Helvetica", 10)
        p.drawString(350, y, "Total Sem Imposto:")
        p.drawString(470, y, f"{totals.get('amount_untaxed', 0.0):.2f} €")
        y -= 15
        p.drawString(350, y, "Total Impostos (IVA):")
        p.drawString(470, y, f"{totals.get('amount_tax', 0.0):.2f} €")
        y -= 18
        p.setFont("Helvetica-Bold", 12)
        p.drawString(350, y, "TOTAL CERTIFICADO:")
        p.drawString(470, y, f"{totals.get('amount_total', 0.0):.2f} €")

        # AT Certification Footer
        p.setFont("Helvetica-Oblique", 8)
        p.setFillColor(colors.HexColor('#475569'))
        p.drawString(50, 60, "Processado por programa certificado nº 9999/AT (Ponte API Externa Odoo)")
        p.drawString(50, 48, f"ATCUD: {atcud}")
        p.drawString(50, 36, f"QR Code String: {qr_code[:80]}...")

        p.showPage()
        p.save()

        buffer.seek(0)
        pdf_bytes = buffer.getvalue()
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return {
            'status': 'success',
            'certified_number': certified_number,
            'atcud': atcud,
            'qr_code': qr_code,
            'pdf_b64': pdf_b64,
            'message': 'Fatura emitida com sucesso via API Certificada'
        }
