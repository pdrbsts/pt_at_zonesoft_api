# -*- coding: utf-8 -*-
import base64
import json
import logging
import requests

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

    def _sync_zonesoft_products_for_picking(self, base_host, app_key, app_secret, client_id, timeout_val, store_id):
        self.ensure_one()
        endpoint = f"{base_host}products/saveInstances"
        prod_map = {}
        AccountMove = self.env['account.move']

        for move in self.move_ids:
            if not move.product_id:
                raise UserError(_("A linha com o artigo '%s' não tem produto válido.") % (move.name or 'Sem descrição'))

            code_raw = move.product_id.default_code
            if code_raw and code_raw.isdigit():
                prod_code = int(code_raw)
            else:
                try:
                    res_next = AccountMove._send_zonesoft_request(
                        f"{base_host}products/getNextCodigo", {"product": {}}, app_key, app_secret, client_id, timeout_val
                    )
                    if res_next.status_code == 200:
                        prod_code = res_next.json().get('Response', {}).get('Content', {}).get('product', {}).get('codigo')
                    else:
                        prod_code = 1100000 + move.product_id.id
                except Exception:
                    prod_code = 1100000 + move.product_id.id

            sale_line = getattr(move, 'sale_line_id', False)
            if sale_line:
                tax_rate = sum(sale_line.tax_id.mapped('amount'))
                price_unit = sale_line.price_unit
            else:
                tax_rate = sum(move.product_id.taxes_id.mapped('amount')) or 23.0
                price_unit = move.product_id.lst_price or 1.0

            prod_name = (move.product_id.name or move.name or 'Artigo')[:50]

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
            except Exception as e:
                _logger.warning("Falha ao pré-sincronizar produto ZoneSoft: %s", str(e))

            prod_map[move.id] = prod_code

        return prod_map

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

                vat_clean = AccountMove._clean_vat(partner.vat, partner.name)
                zs_client_code = partner.id if (partner.name and partner.name.upper() != 'CONSUMIDOR FINAL' and vat_clean != '999999990') else 0

                prod_map = picking._sync_zonesoft_products_for_picking(base_host, app_key, app_secret, client_id, timeout_val, store_id)

                vendas = []
                for move in picking.move_ids:
                    if not move.product_id:
                        continue
                    prod_code = prod_map.get(move.id)
                    if not prod_code:
                        code_raw = move.product_id.default_code
                        prod_code = int(code_raw) if (code_raw and code_raw.isdigit()) else (1100000 + move.product_id.id)

                    qty = float(getattr(move, 'quantity', getattr(move, 'product_uom_qty', 1.0)))
                    sale_line = getattr(move, 'sale_line_id', False)
                    price_unit = float(sale_line.price_unit if sale_line else (move.product_id.lst_price or 1.0))
                    discount = float(sale_line.discount if sale_line else 0.0)

                    vendas.append({
                        'codigo': prod_code,
                        'qtd': qty,
                        'punit': price_unit,
                        'desconto': discount,
                        'obs': move.description_picking or move.product_id.name or '',
                        'armazem': 1,
                    })

                today_str = str(fields.Date.today())
                now_str = fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                time_str = fields.Datetime.now().strftime("%H:%M:%S")

                gt_payload = {
                    'transportdocument': {
                        'loja': store_id,
                        'doc': 'GT',
                        'numero': 0,
                        'anulado': 0,
                        'sync': 1,
                        'cliente': zs_client_code,
                        'fornecedor': 0,
                        'emp': 0,
                        'contribuinte': vat_clean,
                        'nome': partner.name or 'CONSUMIDOR FINAL',
                        'morada': f"{partner.street or ''} {partner.zip or ''} {partner.city or ''}".strip() or "------",
                        'data': today_str,
                        'datahora': now_str,
                        'datacarga': today_str,
                        'horacarga': time_str,
                        'datadescarga': today_str,
                        'horadescarga': time_str,
                        'carga': f"{company.street or ''}".strip() or "Morada Origem",
                        'carga_localidade': company.city or "Localidade",
                        'carga_codigo_postal': company.zip or "4000-000",
                        'descarga': f"{partner.street or ''}".strip() or "Morada Destino",
                        'descarga_localidade': partner.city or "Localidade",
                        'descarga_codigo_postal': partner.zip or "4000-000",
                        'docforn': picking.name,
                        'docext': 0,
                        'ivaincluido': 1,
                        'pagamento': 1,
                        'vendas': vendas
                    }
                }

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

                    if isinstance(inv_resp, dict):
                        doc_errors = inv_resp.get('_errors') or []
                        if doc_errors:
                            err_msg = _("Erro ZoneSoft API ao emitir Guia de Transporte: %s") % json.dumps(doc_errors)
                            picking._handle_certified_picking_error(err_msg, raise_exception)
                            continue

                    if response.status_code not in (200, 201):
                        err_msg = f"ZoneSoft API Error ({response.status_code}): {response.text}"
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    if not inv_resp:
                        err_msg = f"Resposta inválida da ZoneSoft API: {response.text}"
                        picking._handle_certified_picking_error(err_msg, raise_exception)
                        continue

                    doc_code = inv_resp.get('doc', 'GT')
                    serie = inv_resp.get('serie', '')
                    numero = inv_resp.get('numero', '')
                    certified_number = f"{doc_code} {serie}/{numero}".strip()
                    atcud = inv_resp.get('atcud') or inv_resp.get('hash') or 'N/A'
                    qr_code = inv_resp.get('qr_code') or inv_resp.get('pdf') or ''
                    pdf_url = inv_resp.get('pdf')

                    pdf_b64 = None
                    if pdf_url:
                        pdf_resp = requests.get(pdf_url, timeout=timeout_val)
                        if pdf_resp.status_code == 200:
                            pdf_b64 = base64.b64encode(pdf_resp.content).decode('utf-8')

                    if not pdf_b64:
                        err_msg = f"A ZoneSoft API registou a Guia ({certified_number}) mas não retornou o URL do PDF."
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
                        err_msg = "A API não retornou o PDF certificado da Guia de Transporte."
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
