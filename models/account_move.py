# -*- coding: utf-8 -*-
import base64
import hmac
import hashlib
import json
import requests
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    certified_invoice_status = fields.Selection([
        ('not_sent', 'Não Enviada'),
        ('pending', 'Em Processamento'),
        ('sent', 'Emitida & Certificada'),
        ('error', 'Erro no Envio')
    ], string="Estado Fatura AT", default='not_sent', copy=False, readonly=True)

    certified_invoice_number = fields.Char(string="Nº Fatura Certificada AT", copy=False, readonly=True)
    certified_invoice_atcud = fields.Char(string="Código ATCUD", copy=False, readonly=True)
    certified_invoice_qr_code = fields.Text(string="Dados / Link QR Code", copy=False, readonly=True)
    certified_invoice_error_log = fields.Text(string="Último Erro API", copy=False, readonly=True)
    certified_invoice_sent_date = fields.Datetime(string="Data de Emissão na API", copy=False, readonly=True)

    def action_post(self):
        res = super(AccountMove, self).action_post()
        ICP = self.env['ir.config_parameter'].sudo()
        auto_send = ICP.get_param('pt_at_invoice_api.auto_send', 'True')
        if auto_send in ('True', 'true', '1', True):
            for move in self:
                if move.move_type in ('out_invoice', 'out_refund') and move.certified_invoice_status != 'sent':
                    try:
                        move.action_send_certified_invoice(raise_exception=False)
                    except Exception as e:
                        _logger.error("Erro ao enviar fatura %s para API certificada: %s", move.name, str(e))
        return res

    def _prepare_certified_invoice_payload_generic(self):
        self.ensure_one()
        partner = self.partner_id
        company = self.company_id

        doc_type = 'FT' if self.move_type == 'out_invoice' else ('NC' if self.move_type == 'out_refund' else 'ND')

        lines = []
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note')):
            tax_rate = sum(line.tax_ids.mapped('amount'))
            lines.append({
                'product_id': line.product_id.id,
                'product_code': line.product_id.default_code or str(line.product_id.id),
                'name': line.name or line.product_id.name or 'Artigo',
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_rate': tax_rate,
                'price_subtotal': line.price_subtotal,
                'price_total': line.price_total,
            })

        payload = {
            'document_type': doc_type,
            'internal_reference': self.name,
            'invoice_date': str(self.invoice_date or fields.Date.today()),
            'due_date': str(self.invoice_date_due or self.invoice_date or fields.Date.today()),
            'currency': self.currency_id.name or 'EUR',
            'company': {
                'name': company.name,
                'vat': self._clean_vat(company.vat, company.name),
                'street': company.street or '',
                'zip': company.zip or '',
                'city': company.city or '',
                'country': company.country_id.code or 'PT',
            },
            'customer': {
                'id': partner.id,
                'name': partner.name or 'CONSUMIDOR FINAL',
                'vat': self._clean_vat(partner.vat, partner.name),
                'street': partner.street or '',
                'street2': partner.street2 or '',
                'zip': partner.zip or '',
                'city': partner.city or '',
                'country': partner.country_id.code or 'PT',
                'email': partner.email or '',
                'phone': partner.phone or '',
            },
            'items': lines,
            'totals': {
                'amount_untaxed': self.amount_untaxed,
                'amount_tax': self.amount_tax,
                'amount_total': self.amount_total,
            }
        }
        return payload

    @api.model
    def _clean_vat(self, vat_val, partner_name=False):
        """
        Sanitize and format NIF / VAT for PT tax authority.
        For Consumidor Final or missing/invalid NIFs, Portugal AT requires '999999990'.
        """
        if partner_name and str(partner_name).strip().upper() == 'CONSUMIDOR FINAL':
            return '999999990'
        if not vat_val:
            return '999999990'

        vat_clean = str(vat_val).strip().upper()
        if vat_clean.startswith('PT'):
            vat_clean = vat_clean[2:].strip()
        vat_clean = vat_clean.replace(' ', '').replace('-', '').replace('.', '')

        if vat_clean.isdigit() and len(vat_clean) == 9:
            return vat_clean

        return '999999990'

    def _send_zonesoft_request(self, endpoint, payload_dict, app_key, app_secret, client_id, timeout_val):
        json_str = json.dumps(payload_dict, separators=(',', ':'))
        sig = hmac.new(
            app_secret.encode('utf-8'),
            json_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        headers = {
            'Content-Type': 'application/json',
            'X-ZS-APP-KEY': app_key,
            'X-ZS-CLIENT-ID': str(client_id),
            'X-ZS-SIGNATURE': sig,
        }
        return requests.post(endpoint, data=json_str, headers=headers, timeout=timeout_val)

    def _sync_zonesoft_client(self, base_host, app_key, app_secret, client_id, timeout_val):
        self.ensure_one()
        partner = self.partner_id
        vat_clean = self._clean_vat(partner.vat, partner.name)

        if not partner.name or partner.name.upper() == 'CONSUMIDOR FINAL' or vat_clean == '999999990':
            return 0, '999999990'

        client_code = partner.id
        client_payload = {
            "client": [
                {
                    "codigo": client_code,
                    "nome": partner.name[:50],
                    "contribuinte": vat_clean,
                    "morada": (partner.street or "------")[:250],
                    "codpostal": (partner.zip or "0000-000")[:20],
                    "localidade": (partner.city or "------")[:50],
                    "email": (partner.email or "")[:50],
                    "telefone": (partner.phone or "")[:50],
                    "pais": (partner.country_id.code or "PT")[:2],
                    "datacriacao": fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "bloqueado": 0,
                }
            ]
        }
        endpoint = f"{base_host}clients/saveInstances"
        try:
            _logger.info("A pré-sincronizar cliente ZoneSoft (ID %s): %s", client_code, partner.name)
            res = self._send_zonesoft_request(endpoint, client_payload, app_key, app_secret, client_id, timeout_val)
            _logger.info("Resposta sync cliente ZoneSoft: Status %s - %s", res.status_code, res.text[:200])
            if res.status_code not in (200, 201):
                _logger.warning("Pré-sincronização de cliente recusada pela ZoneSoft (Status %s). A utilizar cliente genérico (0) com NIF %s.", res.status_code, vat_clean)
                return 0, vat_clean
        except Exception as e:
            _logger.warning("Falha ao pré-sincronizar cliente ZoneSoft: %s", str(e))
            return 0, vat_clean

        return client_code, vat_clean

    def _sync_zonesoft_products(self, base_host, app_key, app_secret, client_id, timeout_val, store_id):
        self.ensure_one()
        endpoint = f"{base_host}products/saveInstances"
        prod_map = {}

        for line in self.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note')):
            if not line.product_id:
                raise UserError(_("A linha com a descrição '%s' não tem nenhum artigo/produto selecionado. Todas as linhas da fatura devem ter um artigo atribuído antes de emitir na API certificada.") % (line.name or 'Sem descrição'))

            code_raw = line.product_id.default_code
            if code_raw and code_raw.isdigit():
                prod_code = int(code_raw)
            else:
                try:
                    res_next = self._send_zonesoft_request(f"{base_host}products/getNextCodigo", {"product": {}}, app_key, app_secret, client_id, timeout_val)
                    if res_next.status_code == 200:
                        prod_code = res_next.json().get('Response', {}).get('Content', {}).get('product', {}).get('codigo')
                    else:
                        prod_code = 1100000 + line.product_id.id
                except Exception:
                    prod_code = 1100000 + line.product_id.id

            tax_rate = sum(line.tax_ids.mapped('amount'))
            prod_name = (line.product_id.name or line.name or 'Artigo')[:50]

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
                "precorevenda": float(line.price_unit),
                "precovenda": float(line.price_unit),
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
                res = self._send_zonesoft_request(endpoint, prod_payload, app_key, app_secret, client_id, timeout_val)
                _logger.info("Resposta sync produto ZoneSoft: Status %s - %s", res.status_code, res.text[:200])
            except Exception as e:
                _logger.warning("Falha ao pré-sincronizar produto ZoneSoft: %s", str(e))

            prod_map[line.id] = prod_code

        return prod_map

    def action_send_certified_invoice(self, raise_exception=True):
        ICP = self.env['ir.config_parameter'].sudo()
        provider = ICP.get_param('pt_at_invoice_api.provider', 'zonesoft')
        environment = ICP.get_param('pt_at_invoice_api.environment', 'production')
        timeout_val = int(ICP.get_param('pt_at_invoice_api.http_timeout', 30))

        for move in self:
            if move.state != 'posted':
                msg = _("Apenas faturas no estado 'Confirmado' podem ser enviadas para a API certificada.")
                if raise_exception:
                    raise UserError(msg)
                continue

            if move.move_type not in ('out_invoice', 'out_refund'):
                continue

            if provider == 'zonesoft':
                app_key = ICP.get_param('pt_at_invoice_api.app_key', '9F1C3E8F9F1C3E8F23233E233EA9A9E0A9E0FFFF4C405777ADED4C405777ADED')
                app_secret = ICP.get_param('pt_at_invoice_api.app_secret', '1206EE64363DB7BCC20DD69FE52483FC')
                client_id = ICP.get_param('pt_at_invoice_api.client_id', '1')
                store_id = int(ICP.get_param('pt_at_invoice_api.store_id', '1'))

                base_host = "https://api.zonesoft.org/v3/" if environment == 'production' else "https://sandbox1.zonesoft.org/v3/"

                # Step 1: Pre-sync Client to ZoneSoft catalog
                zs_client_code, vat_clean = move._sync_zonesoft_client(base_host, app_key, app_secret, client_id, timeout_val)

                # Step 2: Pre-sync Products & get assigned ZoneSoft product codes
                prod_map = move._sync_zonesoft_products(base_host, app_key, app_secret, client_id, timeout_val, store_id)

                # Step 3: Prepare Invoice Document
                doc_type = 'FT' if move.move_type == 'out_invoice' else ('NC' if move.move_type == 'out_refund' else 'VD')

                vendas = []
                for line in move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note')):
                    prod_code = prod_map.get(line.id)
                    if not prod_code:
                        code_raw = line.product_id.default_code
                        prod_code = int(code_raw) if (code_raw and code_raw.isdigit()) else (1100000 + line.product_id.id)

                    vendas.append({
                        'codigo': prod_code,
                        'qtd': float(line.quantity),
                        'punit': float(line.price_unit),
                        'desconto': float(line.discount),
                        'obs': line.name or line.product_id.name or '',
                        'armazem': 1,
                    })

                invoice_payload = {
                    'invoicedocument': {
                        'loja': store_id,
                        'doc': doc_type,
                        'cliente': zs_client_code,
                        'fornecedor': 0,
                        'emp': 0,
                        'contribuinte': vat_clean,
                        'nome': move.partner_id.name or 'CONSUMIDOR FINAL',
                        'morada': f"{move.partner_id.street or ''} {move.partner_id.zip or ''} {move.partner_id.city or ''}".strip() or "------",
                        'ivaincluido': 1,
                        'pagamento': 1,
                        'vendas': vendas
                    }
                }

                endpoint = f"{base_host}invoicedocuments/saveInstance"

                try:
                    response = move._send_zonesoft_request(endpoint, invoice_payload, app_key, app_secret, client_id, timeout_val)
                    if response.status_code == 401:
                        err_msg = _(
                            "ZoneSoft API Error (401 Unauthorized): Autenticação recusada pela ZoneSoft.\n"
                            "Verifique se o 'ZoneSoft Client-ID' configurado em Definições > Contabilidade é o Client-ID correto "
                            "associado à sua APP-KEY e APP-SECRET no portal developer.zonesoft.org."
                        )
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    res_json = {}
                    try:
                        res_json = response.json()
                    except Exception:
                        pass

                    inv_resp = res_json.get('invoicedocument')
                    if not inv_resp and isinstance(res_json.get('Response'), dict):
                        inv_resp = res_json.get('Response', {}).get('Content', {}).get('invoicedocument')

                    if isinstance(inv_resp, list) and len(inv_resp) > 0:
                        inv_resp = inv_resp[0]

                    # Check for internal error inside invoicedocument response array/dict (handles status 422 too)
                    if isinstance(inv_resp, dict):
                        doc_errors = inv_resp.get('_errors') or []
                        vendas_list = inv_resp.get('vendas') or []
                        vendas_errors = []
                        if isinstance(vendas_list, list):
                            for idx, v_item in enumerate(vendas_list):
                                if isinstance(v_item, dict):
                                    v_err = v_item.get('_errors') or v_item.get('error')
                                    if v_err:
                                        desc = v_item.get('obs') or v_item.get('descricao') or f"Linha {idx+1}"
                                        vendas_errors.append(f"{desc}: {json.dumps(v_err)}")

                        all_err_str = json.dumps(doc_errors) + json.dumps(vendas_errors)

                        if doc_errors or vendas_errors:
                            if '-5000' in all_err_str or 'Erro de Autenticacao/Autorizacao' in all_err_str:
                                err_msg = _(
                                    "Erro na Autoridade Tributária (AT - Código -5000):\n"
                                    "O documento foi processado na ZoneSoft, mas a comunicação com a AT falhou devido às credenciais AT da Loja %s.\n"
                                    "Verifique no Portal ZoneSoft (Gestão de Lojas > Loja %s) se o sub-utilizador das Finanças (Webservices AT) está ativo e com as credenciais corretas."
                                ) % (store_id, store_id)
                            elif vendas_errors:
                                err_msg = _("Erro de validação nas linhas/produtos da fatura na ZoneSoft:\n%s") % "\n".join(vendas_errors)
                            elif 'Check proper instance for errors!' in all_err_str:
                                err_msg = _(
                                    "Erro de validação nas linhas da fatura na ZoneSoft:\n"
                                    "Uma ou mais linhas não possuem um artigo/produto válido selecionado ou contêm um preço/taxa inválidos."
                                )
                            else:
                                err_msg = _("Erro no modelo ZoneSoft API: %s") % json.dumps(doc_errors)

                            move._handle_certified_api_error(err_msg, raise_exception)
                            continue

                    if response.status_code not in (200, 201):
                        err_msg = f"ZoneSoft API Error ({response.status_code}): {response.text}"
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    if not inv_resp:
                        err_msg = f"Resposta inválida da ZoneSoft API: {response.text}"
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    doc_code = inv_resp.get('doc', 'FT')
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
                        err_msg = f"A ZoneSoft API registou o documento ({certified_number}) mas não retornou o URL do PDF."
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    move._process_certified_success(certified_number, atcud, qr_code, pdf_b64)

                except Exception as e:
                    err_msg = f"Falha de ligação à API ZoneSoft: {str(e)}"
                    move._handle_certified_api_error(err_msg, raise_exception)

            else:
                # Generic REST API or Mock API execution
                endpoint = ICP.get_param('pt_at_invoice_api.endpoint', 'http://localhost:8069/api/v1/mock_certified_invoice')
                token = ICP.get_param('pt_at_invoice_api.token', 'sample_bearer_token_12345')

                payload = move._prepare_certified_invoice_payload_generic()
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}' if token else ''
                }

                try:
                    if '/api/v1/mock_certified_invoice' in endpoint:
                        request_data = {'params': payload}
                    else:
                        request_data = payload

                    response = requests.post(endpoint, json=request_data, headers=headers, timeout=timeout_val)
                    if response.status_code not in (200, 201):
                        err_msg = f"HTTP Error {response.status_code}: {response.text}"
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    res_json = response.json()
                    if 'result' in res_json:
                        res_json = res_json['result']

                    if res_json.get('status') != 'success' and not res_json.get('certified_number'):
                        err_msg = res_json.get('message') or res_json.get('error') or "Resposta da API sem sucesso"
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    certified_number = res_json.get('certified_number', f"FT {move.name}")
                    atcud = res_json.get('atcud', '0-00000000')
                    qr_code = res_json.get('qr_code', '')
                    pdf_b64 = res_json.get('pdf_b64')

                    if not pdf_b64 and res_json.get('pdf_url'):
                        pdf_resp = requests.get(res_json['pdf_url'], timeout=timeout_val)
                        if pdf_resp.status_code == 200:
                            pdf_b64 = base64.b64encode(pdf_resp.content).decode('utf-8')

                    if not pdf_b64:
                        err_msg = "A API não retornou o PDF certificado da fatura."
                        move._handle_certified_api_error(err_msg, raise_exception)
                        continue

                    move._process_certified_success(certified_number, atcud, qr_code, pdf_b64)

                except Exception as e:
                    err_msg = f"Falha na comunicação com a API: {str(e)}"
                    move._handle_certified_api_error(err_msg, raise_exception)

        return True

    def _process_certified_success(self, certified_number, atcud, qr_code, pdf_b64):
        self.ensure_one()
        filename_clean = certified_number.replace('/', '_').replace(' ', '_')
        attachment = self.env['ir.attachment'].create({
            'name': f"Fatura_Certificada_{filename_clean}.pdf",
            'type': 'binary',
            'datas': pdf_b64,
            'res_model': 'account.move',
            'res_id': self.id,
            'res_field': 'invoice_pdf_report_file',
            'mimetype': 'application/pdf',
        })

        self.write({
            'name': certified_number,
            'certified_invoice_status': 'sent',
            'certified_invoice_number': certified_number,
            'certified_invoice_atcud': atcud,
            'certified_invoice_qr_code': qr_code,
            'certified_invoice_error_log': False,
            'certified_invoice_sent_date': fields.Datetime.now(),
            'message_main_attachment_id': attachment.id,
            'invoice_pdf_report_file': pdf_b64,
        })

        self.message_post(
            body=f"<b>Fatura Certificada Emitida com Sucesso pela API (ZoneSoft/AT)</b><br/>"
                 f"<b>Nº Certificado:</b> {certified_number}<br/>"
                 f"<b>Código ATCUD:</b> {atcud}<br/>"
                 f"<b>QR Code / Link:</b> {qr_code or 'N/A'}",
            attachment_ids=[attachment.id]
        )

    def _handle_certified_api_error(self, err_msg, raise_exception=True):
        self.ensure_one()
        self.write({
            'certified_invoice_status': 'error',
            'certified_invoice_error_log': err_msg,
        })
        self.message_post(body=f"<b style='color:red;'>Erro ao emitir Fatura Certificada AT:</b><br/>{err_msg}")
        if raise_exception:
            raise UserError(f"Erro na Emissão de Fatura Certificada AT:\n\n{err_msg}")
