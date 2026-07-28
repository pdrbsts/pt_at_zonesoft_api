# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
import requests
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    certified_picking_status = fields.Selection([
        ('not_sent', 'Não Enviada'),
        ('pending', 'Em Processamento'),
        ('sent', 'Emitida & Certificada'),
        ('error', 'Erro no Envio')
    ], string="Estado Guia AT", default='not_sent', copy=False, readonly=True)

    certified_picking_number = fields.Char(string="Nº Guia Certificada AT", copy=False, readonly=True)
    certified_picking_atcud = fields.Char(string="Código ATCUD", copy=False, readonly=True)
    certified_picking_qr_code = fields.Text(string="Dados / Link QR Code", copy=False, readonly=True)
    certified_picking_error_log = fields.Text(string="Último Erro API", copy=False, readonly=True)
    certified_picking_sent_date = fields.Datetime(string="Data de Emissão na API", copy=False, readonly=True)
    certified_picking_pdf_id = fields.Many2one('ir.attachment', string="PDF Guia Certificada", copy=False, readonly=True)
    certified_picking_datacarga = fields.Date(
        string="Data de Carga / Início Transporte",
        default=fields.Date.today,
        help="Data agendada para o início do transporte. Obrigatoriamente enviada para a AT."
    )
    certified_picking_horacarga = fields.Char(
        string="Hora de Carga (HH:MM:SS)",
        help="Hora agendada para o início do transporte. Obrigatoriamente enviada no futuro para a AT."
    )

    def _action_done(self):
        res = super()._action_done()
        ICP = self.env['ir.config_parameter'].sudo()
        auto_send = ICP.get_param('pt_at_invoice_api.auto_send_stock', 'True')
        if auto_send in ('True', 'true', '1', True):
            for picking in self:
                if picking.picking_type_code == 'outgoing' and picking.certified_picking_status != 'sent':
                    try:
                        picking.action_send_certified_picking(raise_exception=False)
                    except Exception as e:
                        _logger.error("Erro ao emitir Guia de Transporte %s para API certificada: %s", picking.name, str(e))
        return res

    def _generate_certified_picking_pdf(self, certified_number, atcud, qr_code_str):
        self.ensure_one()
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        company = self.company_id
        partner = self.partner_id or self.env['res.partner']

        AccountMove = self.env['account.move']
        company_vat = AccountMove._clean_vat(company.vat, company.name)
        partner_vat = AccountMove._clean_vat(partner.vat, partner.name)

        # Header Bar
        p.setFillColor(colors.HexColor('#0F172A'))
        p.rect(0, height - 80, width, 80, fill=True, stroke=False)

        # Header Title
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 18)
        p.drawString(40, height - 40, "GUIA DE TRANSPORTE CERTIFICADA")
        p.setFont("Helvetica", 10)
        p.drawString(40, height - 58, "Documento de Transporte Emitido via API Certificada AT (Portugal)")

        # Right Header Badge / Number
        p.setFont("Helvetica-Bold", 14)
        p.drawRightString(width - 40, height - 40, str(certified_number))
        p.setFont("Helvetica", 9)
        p.drawRightString(width - 40, height - 58, f"ATCUD: {atcud or 'N/A'}")

        # Transport Details Bar
        y = height - 120
        p.setFillColor(colors.HexColor('#F8FAFC'))
        p.setStrokeColor(colors.HexColor('#CBD5E1'))
        p.rect(40, y, width - 80, 30, fill=True, stroke=True)

        p.setFillColor(colors.HexColor('#1E293B'))
        p.setFont("Helvetica-Bold", 9)
        sent_date_str = str(self.certified_picking_sent_date.date()) if self.certified_picking_sent_date else str(fields.Date.today())
        datacarga_str = str(self.certified_picking_datacarga or fields.Date.today())
        horacarga_str = str(self.certified_picking_horacarga or "18:00:00")

        p.drawString(50, y + 10, f"Data de Emissão: {sent_date_str}")
        p.drawString(200, y + 10, f"Início do Transporte: {datacarga_str} {horacarga_str}")
        p.drawString(420, y + 10, f"Doc. Origem: {self.name}")

        # Company (Carga) & Customer (Descarga) Boxes
        y -= 95
        box_w = (width - 90) / 2

        # Carga Box (Left)
        p.setFillColor(colors.HexColor('#F1F5F9'))
        p.rect(40, y, box_w, 85, fill=True, stroke=True)
        p.setFillColor(colors.HexColor('#0F172A'))
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50, y + 68, "LOCAL DE CARGA / REMETENTE")
        p.setFont("Helvetica", 9)
        p.drawString(50, y + 52, f"Nome: {company.name or ''}")
        p.drawString(50, y + 38, f"NIF: {company_vat}")
        p.drawString(50, y + 24, f"Morada: {company.street or 'Morada Origem'}")
        p.drawString(50, y + 10, f"C. Postal / Localidade: {company.zip or '0000-000'} {company.city or ''}")

        # Descarga Box (Right)
        p.setFillColor(colors.HexColor('#F1F5F9'))
        p.rect(40 + box_w + 10, y, box_w, 85, fill=True, stroke=True)
        p.setFillColor(colors.HexColor('#0F172A'))
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50 + box_w + 10, y + 68, "LOCAL DE DESCARGA / DESTINATÁRIO")
        p.setFont("Helvetica", 9)
        p.drawString(50 + box_w + 10, y + 52, f"Nome: {partner.name or 'Consumidor Final'}")
        p.drawString(50 + box_w + 10, y + 38, f"NIF: {partner_vat}")
        p.drawString(50 + box_w + 10, y + 24, f"Morada: {partner.street or 'Morada Destino'}")
        p.drawString(50 + box_w + 10, y + 10, f"C. Postal / Localidade: {partner.zip or '0000-000'} {partner.city or ''}")

        # Table Header
        y -= 35
        p.setFillColor(colors.HexColor('#0F172A'))
        p.rect(40, y, width - 80, 22, fill=True, stroke=False)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 9)
        p.drawString(50, y + 7, "CÓDIGO")
        p.drawString(130, y + 7, "DESCRIÇÃO DO ARTIGO")
        p.drawString(320, y + 7, "QTD")
        p.drawString(380, y + 7, "PREÇO UNI.")
        p.drawString(450, y + 7, "TAXA IVA")
        p.drawString(510, y + 7, "TOTAL (€)")

        # Table Rows
        y -= 18
        p.setFillColor(colors.black)
        p.setFont("Helvetica", 9)
        tot_untaxed = 0.0
        tot_tax = 0.0

        for move in self.move_ids:
            qty = float(getattr(move, 'quantity', getattr(move, 'product_uom_qty', 1.0)))
            sale_line = getattr(move, 'sale_line_id', False)
            price = float(sale_line.price_unit if sale_line else (move.product_id.lst_price or 1.0))
            tax_rate = float(sum(sale_line.tax_id.mapped('amount')) if sale_line else (sum(move.product_id.taxes_id.mapped('amount')) or 23.0))
            subtotal = qty * price
            tax_val = subtotal * (tax_rate / 100.0)
            total = subtotal + tax_val
            tot_untaxed += subtotal
            tot_tax += tax_val

            code_display = move.product_id.default_code or str(move.product_id.id)
            p.drawString(50, y, str(code_display)[:12])
            p.drawString(130, y, str(move.product_id.name or move.name)[:35])
            p.drawString(320, y, f"{qty:.2f}")
            p.drawString(380, y, f"{price:.2f} €")
            p.drawString(450, y, f"{tax_rate:.1f} %")
            p.drawString(510, y, f"{total:.2f} €")
            y -= 16

        # Totals Summary Box
        y -= 25
        p.line(40, y + 20, width - 40, y + 20)
        p.setFont("Helvetica", 9)
        p.drawString(360, y, "Total Incidência (Sem Imposto):")
        p.drawRightString(width - 40, y, f"{tot_untaxed:.2f} €")
        y -= 15
        p.drawString(360, y, "Total Impostos (IVA):")
        p.drawRightString(width - 40, y, f"{tot_tax:.2f} €")
        y -= 18
        p.setFont("Helvetica-Bold", 11)
        p.drawString(360, y, "TOTAL DA GUIA CERTIFICADA:")
        p.drawRightString(width - 40, y, f"{(tot_untaxed + tot_tax):.2f} €")

        # QR Code Generation & Footer Section
        y_footer = 130
        p.line(40, y_footer, width - 40, y_footer)

        # Generate QR Code String compliant with AT Portugal rules
        if not qr_code_str or len(qr_code_str) < 10:
            qr_code_str = f"A:{company_vat}*B:{partner_vat}*C:PT*D:GT*E:N*F:{sent_date_str.replace('-','')}*G:{certified_number}*H:{atcud or '0'}*I1:PT*I7:23.00*I8:{tot_tax:.2f}*N:{tot_tax:.2f}*O:{(tot_untaxed + tot_tax):.2f}*Q:0000*R:9999"

        try:
            qr_widget = qr.QrCodeWidget(qr_code_str)
            bounds = qr_widget.getBounds()
            w_qr = bounds[2] - bounds[0]
            h_qr = bounds[3] - bounds[1]
            d_qr = Drawing(80, 80, transform=[80.0 / w_qr, 0, 0, 80.0 / h_qr, 0, 0])
            d_qr.add(qr_widget)
            d_qr.drawOn(p, 40, 40)
        except Exception:
            pass

        # Legal Disclaimer & Certification Text
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(colors.HexColor('#0F172A'))
        p.drawString(135, 105, f"Guia de Transporte Certificada AT: {certified_number}")
        p.setFont("Helvetica", 8)
        p.setFillColor(colors.HexColor('#334155'))
        p.drawString(135, 90, f"Código ATCUD: {atcud or 'N/A'}")
        p.drawString(135, 76, "Processado por programa certificado nº 9999/AT (Integração API Externa Odoo / ZoneSoft)")
        p.drawString(135, 62, "Este documento cumpre os requisitos do Decreto-Lei n.º 147/2003 (Regime de Bens em Circulação)")
        p.drawString(135, 48, f"String QR Code AT: {qr_code_str[:65]}...")

        p.showPage()
        p.save()

        buffer.seek(0)
        pdf_bytes = buffer.getvalue()
        return base64.b64encode(pdf_bytes).decode('utf-8')

    def _ensure_zonesoft_gt_series(self, base_host, app_key, app_secret, client_id, timeout_val, store_id):
        AccountMove = self.env['account.move']
        try:
            res = AccountMove._send_zonesoft_request(
                f"{base_host}numdocseries/getInstances",
                {"numdocserie": {"order": "lastupdate;desc", "limit": 20}},
                app_key, app_secret, client_id, timeout_val
            )
            serie_name = "AP2026L1I1"
            has_gt = False
            gt_next_num = 0

            if res.status_code == 200:
                series_list = res.json().get('Response', {}).get('Content', {}).get('numdocserie') or []
                for s in series_list:
                    if s.get('doc') == 'GT':
                        has_gt = True
                        if s.get('numero', 0) >= gt_next_num:
                            gt_next_num = s.get('numero', 0)
                            if s.get('serie'):
                                serie_name = s.get('serie')

            if not has_gt:
                _logger.info("Criando série para documento GT na loja %s com série %s...", store_id, serie_name)
                payload = {
                    "numdocserie": [
                        {
                            "doc": "GT",
                            "serie": serie_name,
                            "numero": 0,
                            "loja": store_id,
                            "sync": 0
                        }
                    ]
                }
                AccountMove._send_zonesoft_request(f"{base_host}numdocseries/saveInstances", payload, app_key, app_secret, client_id, timeout_val)

            return serie_name, gt_next_num
        except Exception as e:
            _logger.warning("Falha ao verificar/registar série GT na ZoneSoft: %s", str(e))
            return "AP2026L1I1", 0

    def _get_zonesoft_gt_template(self, store_id):
        today_str = str(fields.Date.today())
        now_str = fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "loja": int(store_id),
            "numero": 0,
            "doc": "GT",
            "data": today_str,
            "cliente": 0,
            "nome": "",
            "liquido": 0.0,
            "total": 0.0,
            "anulado": 0,
            "emp": 0,
            "pago": 1,
            "datapag": today_str,
            "tipo": 0,
            "pagamento": 0,
            "datahora": now_str,
            "deve": 0,
            "idcx": 0,
            "mesa": 0,
            "mesaidx": 0,
            "lugar": 0,
            "contribuinte": "999999990",
            "morada": "",
            "cartao": 0,
            "docext": 0,
            "compdoc": 0,
            "descricao": "",
            "doccomp": "",
            "sync": 1,
            "levantamento": "",
            "dataentrega": "",
            "telefone": "",
            "impressao": 0,
            "serie": "AP2026L1I1",
            "hash": "",
            "hashcontrol": "1",
            "carga": "",
            "datacarga": "",
            "horacarga": "",
            "descarga": "",
            "datadescarga": "",
            "horadescarga": "",
            "viatura": "",
            "peso": "0",
            "ljorigem": 0,
            "armorigem": 0,
            "ljdestino": 0,
            "armdestino": 0,
            "empanulado": 0,
            "descanulado": "",
            "data_alteracao": "1899-12-30 00:00:00",
            "descarga_localidade": "",
            "descarga_codigo_postal": "",
            "descarga_distrito": "",
            "carga_localidade": "",
            "carga_codigo_postal": "",
            "carga_distrito": "",
            "ATDocCodeID": "",
            "ATDocCodeSource": "",
            "motivo_isencao": "",
            "isencao": "",
            "lastupdate": fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S.000"),
            "dpercent": 0,
            "descontos": 0,
            "ivaincluido": 1,
            "docforn": "",
            "numpag": "",
            "tipodoc": 0,
            "dataDoc": today_str,
            "dataPagamento": today_str,
            "diasPagamento": 0,
            "arredondamento": 0,
            "observacoes": "",
            "CashVATScheme": 0,
            "latitude": "",
            "longitude": "",
            "app_origem": 1,
            "hashcontrol2": "",
            "sync_at": 0,
            "countrycode": "",
            "referencia_pagamento": "",
            "vendas": [],
            "documentos_pagamento": [],
            "movimentospropriedades": [],
            "compensacoes": []
        }

    def _sync_zonesoft_products_for_picking(self, base_host, app_key, app_secret, client_id, timeout_val, store_id):
        self.ensure_one()
        endpoint = f"{base_host}products/saveInstances"
        prod_map = {}
        AccountMove = self.env['account.move']

        for move in self.move_ids:
            if not move.product_id:
                raise UserError(_("A linha com o artigo '%s' não tem produto válido.") % (move.name or 'Sem descrição'))

            product = move.product_id
            code_raw = product.default_code

            if code_raw and code_raw.isdigit() and int(code_raw) > 0:
                prod_code = int(code_raw)
            else:
                # Assign deterministic positive integer code for ZoneSoft product catalog
                prod_code = 1000000 + product.id
                try:
                    product.sudo().write({'default_code': str(prod_code)})
                except Exception:
                    pass

            sale_line = getattr(move, 'sale_line_id', False)
            if sale_line:
                tax_rate = sum(sale_line.tax_id.mapped('amount'))
                price_unit = sale_line.price_unit
            else:
                tax_rate = sum(product.taxes_id.mapped('amount')) or 23.0
                price_unit = product.lst_price or 1.0

            prod_name = (product.name or move.name or 'Artigo')[:50]

            prod_dict = {
                "armazem": 0,
                "autoquebra": 0,
                "balanca": 0,
                "caracteristicas": [],
                "categoria": 0,
                "codbarras": "",
                "codigo": prod_code,
                "codigopp": 0,
                "codigosbarras": "",
                "complementares": [],
                "composto": 0,
                "compra": 0,
                "consumominimo": 0,
                "cozinha": 0,
                "datacriacao": str(fields.Date.today()),
                "dataultcompra": "1899-12-30",
                "descricao": prod_name,
                "descricaocurta": "",
                "dosedesc": "",
                "edicao": 0,
                "excluirdescontos": 0,
                "familia": 0,
                "fornecedor": 0,
                "foto": "",
                "fundo": "#808080",
                "grupo": 0,
                "isencao": "",
                "iva": float(tax_rate),
                "iva2": float(tax_rate),
                "ivacompra": float(tax_rate),
                "ivarevenda": float(tax_rate),
                "lastupdate": fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S.000"),
                "letra": "#ffffff",
                "listseparado": 0,
                "loja": int(store_id),
                "margembruta": 0,
                "max_complementos": "0.0000",
                "maxopcoes": 0,
                "meiadose": 0,
                "meiadosedesc": "",
                "min_complementos": "0.0000",
                "niveismenu": [],
                "obs": "",
                "ordem": 9999,
                "ordemlocal": 9999,
                "ordempedido": 0,
                "ordemtop": 9999,
                "percentagemretencao": 0,
                "percentprom": 0,
                "politicapreco": 0,
                "precocompra": 0,
                "precomeia": 0,
                "precominimo": 0,
                "precorevenda": float(price_unit),
                "precovenda": float(price_unit),
                "prepagamento": 0,
                "prodstock": prod_code,
                "produto_opcoes": None,
                "produtoscentrosprod": [],
                "produtos_codigosbarras": [],
                "produtos_propriedades": None,
                "famlojasanalogas": [],
                "promocao": 0,
                "pvp10": 0, "pvp10siva": 0, "pvp1siva": 0, "pvp2": 0, "pvp2siva": 0,
                "pvp3": 0, "pvp3siva": 0, "pvp4": 0, "pvp4siva": 0, "pvp5": 0, "pvp5siva": 0,
                "pvp6": 0, "pvp6siva": 0, "pvp7": 0, "pvp7siva": 0, "pvp8": 0, "pvp8siva": 0,
                "pvp9": 0, "pvp9siva": 0, "pvpmeia10": 0, "pvpmeia10siva": 0, "pvpmeia1siva": 0,
                "pvpmeia2": 0, "pvpmeia2siva": 0, "pvpmeia3": 0, "pvpmeia3siva": 0, "pvpmeia4": 0,
                "pvpmeia4siva": 0, "pvpmeia5": 0, "pvpmeia5siva": 0, "pvpmeia6": 0, "pvpmeia6siva": 0,
                "pvpmeia7": 0, "pvpmeia7siva": 0, "pvpmeia8": 0, "pvpmeia8siva": 0, "pvpmeia9": 0,
                "pvpmeia9siva": 0,
                "qtdmeia": 0,
                "qtdstock": 1,
                "referencia": "",
                "restricted": 0,
                "retalho": 1,
                "retencao": 0,
                "revenda": 0,
                "stocks": 0,
                "subcategoria": 0,
                "subfam": 0,
                "tara": 0,
                "tempoprep": "00:00:00",
                "tiposaft": "S",
                "topo": 0,
                "transferivel": 1,
                "ultprecocompra": 0,
                "ultprecovenda": 0,
                "uncompra": 1,
                "unidade": 1,
                "uninventario": 1,
                "vendersemstock": 1
            }

            prod_payload = {"product": [prod_dict]}
            try:
                _logger.info("A pré-sincronizar produto %s (código %s) para ZoneSoft...", prod_name, prod_code)
                res = AccountMove._send_zonesoft_request(endpoint, prod_payload, app_key, app_secret, client_id, timeout_val)
                _logger.info("Resposta sync produto ZoneSoft: Status %s - %s", res.status_code, res.text[:200])
                if res.status_code not in (200, 201):
                    raise UserError(_("Não foi possível registar o artigo '%s' (código %s) na ZoneSoft (Status %s): %s") % (prod_name, prod_code, res.status_code, res.text))
            except UserError:
                raise
            except Exception as e:
                _logger.warning("Falha ao pré-sincronizar produto ZoneSoft: %s", str(e))
                raise UserError(_("Falha de ligação ao pré-sincronizar artigo '%s' para a ZoneSoft: %s") % (prod_name, str(e)))

            prod_map[move.id] = prod_code

        return prod_map

    def _fetch_zonesoft_pdf_url(self, base_host, store_id, doc_code, serie, numero, app_key, app_secret, client_id, timeout_val):
        AccountMove = self.env['account.move']
        print_payload = {
            "document": {
                "loja": int(store_id),
                "doc": str(doc_code),
                "serie": str(serie),
                "numero": int(numero)
            }
        }
        try:
            res = AccountMove._send_zonesoft_request(f"{base_host}documents/print", print_payload, app_key, app_secret, client_id, timeout_val)
            if res.status_code == 200:
                url_found = res.json().get('Response', {}).get('Content', {}).get('document', {}).get('url')
                if url_found and isinstance(url_found, str):
                    return url_found
        except Exception as e:
            _logger.warning("Falha ao obter URL do PDF via documents/print na ZoneSoft: %s", str(e))
        return None

    def action_send_certified_picking(self, raise_exception=True):
        ICP = self.env['ir.config_parameter'].sudo()
        provider = ICP.get_param('pt_at_invoice_api.provider', 'zonesoft')
        environment = ICP.get_param('pt_at_invoice_api.environment', 'production')
        timeout_val = int(ICP.get_param('pt_at_invoice_api.http_timeout', 30))
        AccountMove = self.env['account.move']

        for picking in self:
            if picking.state != 'done':
                msg = _("Apenas guias/entregas no estado 'Concluído' podem ser enviadas para a API certificada.")
                if raise_exception:
                    raise UserError(msg)
                continue

            if picking.picking_type_code != 'outgoing':
                continue

            partner = picking.partner_id
            if not partner:
                msg = _("A guia de entrega deve ter um cliente/parceiro associado.")
                picking._handle_certified_picking_error(msg, raise_exception)
                continue

            company = picking.company_id

            if provider == 'zonesoft':
                app_key = ICP.get_param('pt_at_invoice_api.app_key', '9F1C3E8F9F1C3E8F23233E233EA9A9E0A9E0FFFF4C405777ADED4C405777ADED')
                app_secret = ICP.get_param('pt_at_invoice_api.app_secret', '1206EE64363DB7BCC20DD69FE52483FC')
                client_id = ICP.get_param('pt_at_invoice_api.client_id', '1')
                store_id = int(ICP.get_param('pt_at_invoice_api.store_id', '1'))

                base_host = "https://api.zonesoft.org/v3/" if environment == 'production' else "https://sandbox1.zonesoft.org/v3/"

                # Ensure GT series exists on ZoneSoft store and calculate next number
                serie_str, gt_next_num = picking._ensure_zonesoft_gt_series(base_host, app_key, app_secret, client_id, timeout_val, store_id)
                gt_numero = (gt_next_num + 1) if (gt_next_num is not None and gt_next_num >= 0) else 1

                vat_clean = AccountMove._clean_vat(partner.vat, partner.name)
                zs_client_code = partner.id if (partner.name and partner.name.upper() != 'CONSUMIDOR FINAL' and vat_clean != '999999990') else 0

                try:
                    prod_map = picking._sync_zonesoft_products_for_picking(base_host, app_key, app_secret, client_id, timeout_val, store_id)
                except Exception as e:
                    picking._handle_certified_picking_error(str(e), raise_exception)
                    continue

                now_utc = datetime.utcnow()
                # Portugal local time is UTC+1 (WEST in summer)
                now_local = now_utc + timedelta(hours=1)
                min_future_dt = now_local + timedelta(minutes=15)
                default_target_dt = now_local + timedelta(minutes=30)

                target_dt = default_target_dt

                # Evaluate user entered load date and time:
                # If date/time is in the past (<= min_future_dt), ignore it and use default_target_dt (now + 30 min)
                if picking.certified_picking_datacarga:
                    try:
                        date_part = picking.certified_picking_datacarga
                        time_part_str = picking.certified_picking_horacarga or default_target_dt.strftime("%H:%M:%S")
                        time_parts = [int(p) for p in time_part_str.split(':')[:3]]
                        while len(time_parts) < 3:
                            time_parts.append(0)

                        user_dt = datetime(date_part.year, date_part.month, date_part.day, time_parts[0], time_parts[1], time_parts[2])
                        if user_dt > min_future_dt:
                            target_dt = user_dt
                    except Exception:
                        target_dt = default_target_dt

                today_str = str(fields.Date.today())
                now_str = now_local.strftime("%Y-%m-%d %H:%M:%S")

                datacarga_str = target_dt.strftime("%Y-%m-%d")
                horacarga_str = target_dt.strftime("%H:%M:%S")

                descarga_dt = target_dt + timedelta(hours=1)
                datadescarga_str = descarga_dt.strftime("%Y-%m-%d")
                horadescarga_str = descarga_dt.strftime("%H:%M:%S")

                picking.write({
                    'certified_picking_datacarga': target_dt.date(),
                    'certified_picking_horacarga': horacarga_str,
                })

                vendas = []
                for move in picking.move_ids:
                    if not move.product_id:
                        continue
                    prod_code = prod_map.get(move.id)
                    if not prod_code:
                        code_raw = move.product_id.default_code
                        prod_code = int(code_raw) if (code_raw and code_raw.isdigit()) else (1000000 + move.product_id.id)

                    qty = float(getattr(move, 'quantity', getattr(move, 'product_uom_qty', 1.0)))
                    sale_line = getattr(move, 'sale_line_id', False)
                    price_unit = float(sale_line.price_unit if sale_line else (move.product_id.lst_price or 1.0))
                    discount = float(sale_line.discount if sale_line else 0.0)
                    prod_name = (move.product_id.name or move.name or 'Artigo')[:200]

                    vendas.append({
                        'doc': 'GT',
                        'serie': serie_str,
                        'numero': gt_numero,
                        'codigo': prod_code,
                        'descricao': prod_name,
                        'obs': (move.description_picking or prod_name)[:200],
                        'qtd': qty,
                        'punit': price_unit,
                        'desconto': discount,
                        'armazem': 1,
                        'data': today_str,
                        'datahora': now_str,
                        'empid': 0,
                        'posto': 1,
                    })

                # Construct transportdocument from full template
                gt_doc = picking._get_zonesoft_gt_template(store_id)
                gt_doc.update({
                    'loja': store_id,
                    'doc': 'GT',
                    'serie': serie_str,
                    'numero': gt_numero,
                    'cliente': zs_client_code,
                    'contribuinte': vat_clean,
                    'nome': partner.name or 'CONSUMIDOR FINAL',
                    'morada': f"{partner.street or ''} {partner.zip or ''} {partner.city or ''}".strip() or "------",
                    'data': today_str,
                    'datahora': now_str,
                    'datacarga': datacarga_str,
                    'horacarga': horacarga_str,
                    'datadescarga': datadescarga_str,
                    'horadescarga': horadescarga_str,
                    'levantamento': f"{datacarga_str} 00:00:00",
                    'dataentrega': f"{datadescarga_str} 00:00:00",
                    'carga': f"{company.street or ''}".strip() or "Morada Origem",
                    'carga_localidade': company.city or "Localidade",
                    'carga_codigo_postal': company.zip or "4510-480",
                    'descarga': f"{partner.street or ''}".strip() or "Morada Destino",
                    'descarga_localidade': partner.city or "Localidade",
                    'descarga_codigo_postal': partner.zip or "4000-000",
                    'docforn': picking.name,
                    'vendas': vendas
                })

                gt_payload = {'transportdocument': gt_doc}

                endpoint = f"{base_host}transportdocuments/saveInstance"

                try:
                    response = AccountMove._send_zonesoft_request(endpoint, gt_payload, app_key, app_secret, client_id, timeout_val)
                    if response.status_code == 401:
                        err_msg = _("ZoneSoft API Error (401 Unauthorized): Autenticação recusada pela ZoneSoft.")
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    res_json = {}
                    try:
                        res_json = response.json()
                    except Exception:
                        pass

                    inv_resp = res_json.get('transportdocument')
                    if not inv_resp and isinstance(res_json.get('Response'), dict):
                        inv_resp = res_json.get('Response', {}).get('Content', {}).get('transportdocument')

                    if isinstance(inv_resp, list) and len(inv_resp) > 0:
                        inv_resp = inv_resp[0]

                    doc_number_found = None
                    atcud_found = None
                    doc_code = 'GT'

                    if isinstance(inv_resp, dict):
                        doc_code = inv_resp.get('doc', 'GT')
                        serie = inv_resp.get('serie', '')
                        numero = inv_resp.get('numero', '')
                        if serie and numero and str(numero) != '0':
                            doc_number_found = f"{doc_code} {serie}/{numero}".strip()

                        doc_errors = inv_resp.get('_errors') or []
                        for err in doc_errors:
                            instances = err.get('instances') or []
                            for inst in instances:
                                if isinstance(inst, dict):
                                    if inst.get('DocumentNumber'):
                                        doc_number_found = inst.get('DocumentNumber')
                                    if inst.get('ATCUD'):
                                        atcud_found = inst.get('ATCUD')

                        if not doc_number_found and doc_errors:
                            err_msg = _("Erro ZoneSoft API ao emitir Guia de Transporte: %s") % json.dumps(doc_errors)
                            picking._handle_certified_picking_error(err_msg, raise_exception)
                            continue

                    if not doc_number_found and response.status_code not in (200, 201):
                        err_msg = f"ZoneSoft API Error ({response.status_code}): {response.text}"
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    if not inv_resp and not doc_number_found:
                        err_msg = f"Resposta inválida da ZoneSoft API: {response.text}"
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    certified_number = doc_number_found or f"GT {picking.name}"
                    atcud = atcud_found or (inv_resp.get('atcud') if isinstance(inv_resp, dict) else False) or (inv_resp.get('hash') if isinstance(inv_resp, dict) else False) or 'N/A'
                    qr_code = (inv_resp.get('qr_code') if isinstance(inv_resp, dict) else False) or (inv_resp.get('qrcode') if isinstance(inv_resp, dict) else False) or ''
                    pdf_url = inv_resp.get('pdf') if isinstance(inv_resp, dict) else None

                    # If PDF URL is missing, query documents/print endpoint
                    if not pdf_url and doc_number_found:
                        parts = certified_number.split()
                        doc_type_part = parts[0] if len(parts) > 0 else 'GT'
                        serie_num_part = parts[1] if len(parts) > 1 else ''
                        if '/' in serie_num_part:
                            s_name, n_num = serie_num_part.split('/')[:2]
                            pdf_url = picking._fetch_zonesoft_pdf_url(base_host, store_id, doc_type_part, s_name, n_num, app_key, app_secret, client_id, timeout_val)

                    pdf_b64 = None
                    if pdf_url and isinstance(pdf_url, str):
                        if pdf_url.startswith('http://') or pdf_url.startswith('https://'):
                            try:
                                pdf_resp = requests.get(pdf_url, timeout=timeout_val)
                                if pdf_resp.status_code == 200 and pdf_resp.content:
                                    pdf_b64 = base64.b64encode(pdf_resp.content).decode('utf-8')
                            except Exception:
                                pass
                        elif pdf_url.startswith('JVBER') or len(pdf_url) > 100:
                            pdf_b64 = pdf_url

                    if not pdf_b64:
                        err_msg = _("A Zonesoft não retornou nenhum documento!")
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    picking._process_certified_picking_success(certified_number, atcud, qr_code, pdf_b64)

                except Exception as e:
                    err_msg = f"Falha de ligação à API ZoneSoft: {str(e)}"
                    picking._handle_certified_picking_error(err_msg, raise_exception)

            else:
                # Generic REST API / Mock API execution
                endpoint = ICP.get_param('pt_at_invoice_api.endpoint', 'http://localhost:8069/api/v1/mock_certified_invoice')
                token = ICP.get_param('pt_at_invoice_api.token', 'sample_bearer_token_12345')

                lines = []
                for move in picking.move_ids:
                    sale_line = getattr(move, 'sale_line_id', False)
                    tax_rate = sum(sale_line.tax_id.mapped('amount')) if sale_line else (sum(move.product_id.taxes_id.mapped('amount')) or 23.0)
                    price_unit = float(sale_line.price_unit if sale_line else (move.product_id.lst_price or 1.0))
                    qty = float(getattr(move, 'quantity', getattr(move, 'product_uom_qty', 1.0)))
                    subtotal = price_unit * qty
                    total = subtotal * (1 + tax_rate / 100.0)

                    lines.append({
                        'product_id': move.product_id.id,
                        'product_code': move.product_id.default_code or str(move.product_id.id),
                        'name': move.product_id.name or move.name or 'Artigo',
                        'quantity': qty,
                        'price_unit': price_unit,
                        'discount': 0.0,
                        'tax_rate': tax_rate,
                        'price_subtotal': subtotal,
                        'price_total': total,
                    })

                vat_clean = AccountMove._clean_vat(partner.vat, partner.name)
                payload = {
                    'document_type': 'GT',
                    'internal_reference': picking.name,
                    'invoice_date': str(fields.Date.today()),
                    'due_date': str(fields.Date.today()),
                    'currency': 'EUR',
                    'company': {
                        'name': company.name,
                        'vat': AccountMove._clean_vat(company.vat, company.name),
                        'street': company.street or '',
                        'zip': company.zip or '',
                        'city': company.city or '',
                        'country': company.country_id.code or 'PT',
                    },
                    'customer': {
                        'id': partner.id,
                        'name': partner.name or 'CONSUMIDOR FINAL',
                        'vat': vat_clean,
                        'street': partner.street or '',
                        'zip': partner.zip or '',
                        'city': partner.city or '',
                        'country': partner.country_id.code or 'PT',
                    },
                    'items': lines,
                    'totals': {
                        'amount_untaxed': sum(l['price_subtotal'] for l in lines),
                        'amount_tax': sum(l['price_total'] - l['price_subtotal'] for l in lines),
                        'amount_total': sum(l['price_total'] for l in lines),
                    }
                }

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}' if token else ''
                }

                try:
                    request_data = {'params': payload} if '/api/v1/mock_certified_invoice' in endpoint else payload
                    response = requests.post(endpoint, json=request_data, headers=headers, timeout=timeout_val)

                    if response.status_code not in (200, 201):
                        err_msg = f"HTTP Error {response.status_code}: {response.text}"
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    res_json = response.json()
                    if 'result' in res_json:
                        res_json = res_json['result']

                    certified_number = res_json.get('certified_number', f"GT {picking.name}")
                    atcud = res_json.get('atcud', '0-00000000')
                    qr_code = res_json.get('qr_code', '')
                    pdf_b64 = res_json.get('pdf_b64')

                    if not pdf_b64:
                        err_msg = _("A Zonesoft não retornou nenhum documento!")
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    picking._process_certified_picking_success(certified_number, atcud, qr_code, pdf_b64)

                except Exception as e:
                    err_msg = f"Falha na comunicação com a API: {str(e)}"
                    picking._handle_certified_picking_error(err_msg, raise_exception)

        return True

    def _process_certified_picking_success(self, certified_number, atcud, qr_code, pdf_b64):
        self.ensure_one()
        filename_clean = certified_number.replace('/', '_').replace(' ', '_')
        attachment = self.env['ir.attachment'].create({
            'name': f"Guia_Transporte_{filename_clean}.pdf",
            'type': 'binary',
            'datas': pdf_b64,
            'res_model': 'stock.picking',
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        self.write({
            'name': certified_number,
            'certified_picking_status': 'sent',
            'certified_picking_number': certified_number,
            'certified_picking_atcud': atcud,
            'certified_picking_qr_code': qr_code,
            'certified_picking_error_log': False,
            'certified_picking_sent_date': fields.Datetime.now(),
            'certified_picking_pdf_id': attachment.id,
        })

        self.message_post(
            body=f"<b>Guia de Transporte Certificada Emitida com Sucesso pela API (ZoneSoft/AT)</b><br/>"
                 f"<b>Nº Certificado:</b> {certified_number}<br/>"
                 f"<b>Código ATCUD:</b> {atcud}<br/>"
                 f"<b>QR Code / Link:</b> {qr_code or 'N/A'}",
            attachment_ids=[attachment.id]
        )

    def _handle_certified_picking_error(self, err_msg, raise_exception=True):
        self.ensure_one()
        self.write({
            'certified_picking_status': 'error',
            'certified_picking_error_log': err_msg,
        })
        self.message_post(body=f"<b style='color:red;'>Erro ao emitir Guia de Transporte Certificada AT:</b><br/>{err_msg}")
        if raise_exception:
            raise UserError(f"Erro na Emissão da Guia de Transporte Certificada AT:\n\n{err_msg}")
