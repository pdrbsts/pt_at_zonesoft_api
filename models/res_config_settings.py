# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pt_at_provider = fields.Selection([
        ('zonesoft', 'ZoneSoft REST API v3'),
        ('mock', 'Simulador / Mock Internal API'),
        ('generic', 'API REST Genérica Customizada')
    ], string="Provedor de API", config_parameter='pt_at_invoice_api.provider', default='zonesoft')

    pt_at_app_key = fields.Char(
        string="ZoneSoft App-Key",
        config_parameter='pt_at_invoice_api.app_key',
        default="9F1C3E8F9F1C3E8F23233E233EA9A9E0A9E0FFFF4C405777ADED4C405777ADED"
    )
    pt_at_app_secret = fields.Char(
        string="ZoneSoft App-Secret",
        config_parameter='pt_at_invoice_api.app_secret',
        default="1206EE64363DB7BCC20DD69FE52483FC"
    )
    pt_at_client_id = fields.Char(
        string="ZoneSoft Client-ID",
        config_parameter='pt_at_invoice_api.client_id',
        default="1"
    )
    pt_at_store_id = fields.Integer(
        string="ID da Loja ZoneSoft",
        config_parameter='pt_at_invoice_api.store_id',
        default=1
    )

    pt_at_api_endpoint = fields.Char(
        string="Endpoint Personalizado (se Genérico)",
        config_parameter='pt_at_invoice_api.endpoint',
        default="https://api.zonesoft.org/v3/invoicedocuments/saveInstance"
    )
    pt_at_api_token = fields.Char(
        string="Token (se Genérico)",
        config_parameter='pt_at_invoice_api.token',
        default="sample_bearer_token_12345"
    )
    pt_at_auto_send = fields.Boolean(
        string="Enviar Automaticamente ao Confirmar Fatura",
        config_parameter='pt_at_invoice_api.auto_send',
        default=True
    )
    pt_at_environment = fields.Selection([
        ('production', 'Produção (api.zonesoft.org)'),
        ('sandbox', 'Sandbox / Testes (sandbox1.zonesoft.org)')
    ], string="Ambiente da API", config_parameter='pt_at_invoice_api.environment', default='production')

    pt_at_http_timeout = fields.Integer(
        string="Timeout da API (segundos)",
        config_parameter='pt_at_invoice_api.http_timeout',
        default=30
    )
