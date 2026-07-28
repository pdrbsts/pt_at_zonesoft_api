# Portugal AT Certified Invoicing API Bridge (ZoneSoft API & REST)

![Odoo Version](https://img.shields.io/badge/Odoo-18.0%20Community-blue)
![License](https://img.shields.io/badge/License-LGPL--3-green)
![Portugal AT](https://img.shields.io/badge/Localization-Portugal%20AT-red)

Módulo de integração para Odoo 18 Community Edition para emissão de faturas certificadas em Portugal através da API v3 da **ZoneSoft** e suporte a **REST API Generic/Mock**.

---

## 🚀 Funcionalidades

- **Integração Nativa com ZoneSoft API v3**: Envio automático de documentos de faturação (`FT`, `NC`, `ND`/`VD`) diretamente para a ZoneSoft e comunicação com a Autoridade Tributária (AT).
- **Tratamento Automático de Consumidor Final (NIF 999999990)**:
  - Formatação e sanitização automática de NIFs portugueses (remoção de `PT`, espaços e pontuação).
  - Conversão automática de clientes genéricos ou sem NIF para o NIF fiscal padrão em Portugal (**`999999990`**).
- **Sincronização de Clientes e Produtos**:
  - Registo e sincronização automática de parceiros com os parâmetros obrigatórios da ZoneSoft (`datacriacao`, `bloqueado`, `pais`).
  - Sincronização automática de catálogo de produtos e taxas de IVA.
- **Certificação & Anexo de Documentos**:
  - Obtenção do número de documento certificado oficial (ex.: `FT AP2026L2II1/1`).
  - Obtenção do código **ATCUD** e link/URL para o **QR Code**.
  - Download automático do PDF certificado oficial e associação direta ao Chatter e anexos principais da fatura (`message_main_attachment_id`).
- **Diagnóstico e Erros AT**:
  - Leitura inteligente de erros da API, incluindo mensagens de erro da AT (Código `-5000` - Credenciais de Webservices das Finanças na Loja ZoneSoft).
  - Validação de produtos e linhas de fatura antes da submissão.

---

## 🛠️ Requisitos

- **Odoo**: 18.0 Community ou Enterprise Edition.
- **Python Dependencies**: `requests` (incluído no ambiente padrão do Odoo).
- **Conta ZoneSoft API v3**:
  - `APP-KEY`, `APP-SECRET`, `CLIENT-ID` e `STORE-ID` (obtidos no portal [developer.zonesoft.org](https://developer.zonesoft.org)).
  - Sub-utilizador do Portal das Finanças / AT (Webservices) ativo e configurado na Loja no Portal ZoneSoft.

---

## 📥 Instalação no Odoo Community 18

### 1. Clonar ou copiar o módulo para a diretoria `custom_addons`

Na sua máquina ou servidor Odoo:

```bash
cd /opt/odoo/custom_addons
git clone https://github.com/SEU_UTILIZADOR/pt_at_zonesoft_api.git pt_at_invoice_api
```

> **Nota**: Garanta que a pasta do módulo se chama `pt_at_invoice_api` dentro da sua diretoria de `custom_addons`.

### 2. Configurar o ficheiro `odoo.conf`

Certifique-se de que a diretoria `custom_addons` está incluída na propriedade `addons_path`:

```ini
[options]
addons_path = /opt/odoo/odoo/addons,/opt/odoo/custom_addons
```

### 3. Atualizar a Lista de Módulos e Instalar

#### Opção A (Via Linha de Comandos - Recomendado):
```bash
/opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin -c /etc/odoo.conf -d NOME_DA_SUA_BD -u pt_at_invoice_api --stop-after-init
systemctl restart odoo
```

#### Opção B (Via Interface Gráfica Odoo):
1. Aceda ao Odoo com um utilizador Administrador.
2. Ative o **Modo de Criador / Developer Mode** nas Definições.
3. Aceda ao menu **Aplicações** ➔ Clique em **Atualizar Lista de Aplicações**.
4. Pesquise por `Portugal AT Certified Invoicing API Bridge` (ou `pt_at_invoice_api`).
5. Clique em **Instalar**.

---

## ⚙️ Configuração

1. No Odoo, aceda a **Definições** ➔ **Contabilidade**.
2. Desloque até à secção **Faturação Certificada AT (Portugal)**.
3. Configure os parâmetros da API:
   - **Fornecedor API**: Selecione `ZoneSoft API v3`.
   - **Ambiente**: Selecione `Produção` ou `Sandbox`.
   - **ZoneSoft App Key**: A sua `X-ZS-APP-KEY`.
   - **ZoneSoft App Secret**: O seu `App Secret` para assinatura HMAC-SHA256.
   - **ZoneSoft Client-ID**: O seu `X-ZS-CLIENT-ID`.
   - **ID da Loja (Store ID)**: Número da Loja registada na ZoneSoft (ex.: `1` ou `2`).
   - **Envio Automático**: Ative para emitir na API automaticamente ao confirmar a fatura.
4. Clique em **Guardar**.

---

## 💻 Utilização

1. Aceda a **Contabilidade** ➔ **Faturas de Clientes**.
2. Crie e valide uma fatura de cliente.
3. Na fatura no estado **Confirmado**:
   - Se o envio automático estiver ativo, o documento é emitido imediatamente.
   - Caso contrário, clique no botão **"Emitir Fatura Certificada (API)"** no cabeçalho.
4. Após o processamento:
   - O estado passa a **Emitida & Certificada**.
   - O número certificado (ex.: `FT AP2026L2II1/1`) e o código **ATCUD** ficam registados na aba **Fatura Certificada AT**.
   - O PDF certificado oficial emitido pela ZoneSoft/AT fica automaticamente anexado à fatura no **Chatter**.

---

## 🔍 Resolução de Problemas (Troubleshooting)

### 1. Erro AT - Código `-5000` (Erro de Autenticação/Autorização)
**Sintoma**: `Erro na Autoridade Tributária (AT - Código -5000)`  
**Causa**: O documento foi validado na ZoneSoft, mas a comunicação entre a ZoneSoft e a AT falhou.  
**Solução**: Aceda ao **Portal ZoneSoft** ➔ **Gestão de Lojas** ➔ Selecione a sua Loja ➔ Verifique se as credenciais do sub-utilizador das Finanças (Webservices AT) estão ativas e corretas.

### 2. Erro de Validação de Linhas (`Check proper instance for errors!`)
**Sintoma**: `Erro de validação nas linhas da fatura na ZoneSoft`  
**Causa**: Uma linha da fatura não tem nenhum produto/artigo selecionado (linha em branco) ou possui quantidade/preço inválidos.  
**Solução**: Edite a fatura no Odoo, remova a linha sem produto (ou selecione um produto válido) e tente emitir novamente.

---

## 📄 Licença

Este módulo está licenciado sob a **LGPL-3**.
