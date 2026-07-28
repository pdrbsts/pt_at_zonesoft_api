{
    'name': 'Portugal AT Certified Invoicing API Bridge',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Ponte de integração API para emissão de faturas certificadas AT em Portugal',
    'description': """
Módulo de Integração com API de Faturação Certificada (Portugal - Autoridade Tributária)
========================================================================================
- Envia os dados do cliente (NIF, Morada, Nome) e artigos (linhas, quantidades, preços, impostos) para uma API externa de faturação certificada.
- Recebe o PDF oficial certificado, o número da fatura emitida, o código ATCUD e o QR Code.
- Anexa o PDF retornado à fatura no Chatter e define-o como documento principal (message_main_attachment_id) para envio por e-mail e impressão.
- Permite envio automático ao confirmar a fatura ou envio manual através do botão "Emitir Fatura Certificada".
- Inclui um endpoint de simulação (Mock API) para testes imediatos.
    """,
    'author': 'Antigravity AI',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
