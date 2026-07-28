# Portugal AT Certified Invoicing API Bridge (ZoneSoft API & REST)

![Odoo Version](https://img.shields.io/badge/Odoo-18.0%20Community-blue)
![License](https://img.shields.io/badge/License-LGPL--3-green)
![Portugal AT](https://img.shields.io/badge/Localization-Portugal%20AT-red)

Módulo de integração para Odoo 18 Community Edition para emissão de faturas e guias de transporte certificadas em Portugal através da API v3 da **ZoneSoft** e suporte a **REST API Generic/Mock**.

---

## 🚀 Funcionalidades

- **Integração Nativa com ZoneSoft API v3**:
  - Envio automático e manual de documentos de faturação (`FT`, `NC`, `ND`/`VD`) no módulo de Contabilidade (`account.move`).
  - Envio automático e manual de **Guias de Transporte (`GT`)** a partir do módulo de Inventário / Entregas (`stock.picking`).
- **Renomeação Transparente do Documento**:
  - O número interno do Odoo (ex.: `INV/2026/00011` ou `WH/OUT/00008`) é automaticamente atualizado para a numeração oficial certificada atribuída pela ZoneSoft/AT (ex.: `FT AP2026L1II1/6` ou `GT AP2026L1I1/17`).
- **Validação & Agendamento de Transporte (AT)**:
  - Configuração de **Data de Carga (`datacarga`)** e **Hora de Carga (`horacarga`)** na Guia de Entrega.
  - Envio automático com margem de segurança no futuro para cumprimento estrito das regras da Autoridade Tributária (evitando o aviso AT Código `-100`: *"Data início de transporte no passado"*).
- **Tratamento Automático de Consumidor Final (NIF 999999990)**:
  - Formatação e sanitização automática de NIFs portugueses (remoção de `PT`, espaços e pontuação).
  - Conversão automática de clientes genéricos ou sem NIF para o NIF fiscal padrão em Portugal (**`999999990`**).
- **Sincronização de Clientes e Produtos**:
  - Registo e sincronização automática de parceiros com os parâmetros obrigatórios da ZoneSoft (`datacriacao`, `bloqueado`, `pais`).
  - Sincronização automática do catálogo de produtos, códigos de artigo e taxas de IVA.
- **Certificação & Anexo de Documentos**:
  - Obtenção do número de documento certificado oficial, código **ATCUD** e dados do **QR Code**.
  - Download e associação automática do PDF certificado oficial diretamente ao Chatter e aos anexos do documento no Odoo.
  - Salvaguarda contra ficheiros inválidos: se a API não retornar o documento em caso de erro, nenhuma informação dummy é gravada e o utilizador é notificado expressamente (`"A Zonesoft não retornou nenhum documento!"`).
- **Diagnóstico e Erros AT**:
  - Leitura inteligente de mensagens de erro da AT (ex.: Código `-5000` - Credenciais AT na Loja ZoneSoft, Código `33` - Formatação XML SAF-T).

---

## 🛠️ Requisitos

- **Odoo**: 18.0 Community ou Enterprise Edition.
- **Python Dependencies**: `requests`, `reportlab` (incluídos no ambiente padrão do Odoo).
- **Conta ZoneSoft API v3**:
  - `APP-KEY`, `APP-SECRET`, `CLIENT-ID` e `STORE-ID` (obtidos no portal [developer.zonesoft.org](https://developer.zonesoft.org)).
  - Sub-utilizador do Portal das Financas / AT (Webservices) ativo e configurado na Loja no Portal ZoneSoft.

---

## 📥 Instalação no Odoo Community 18

### 1. Clonar ou copiar o módulo para a diretoria `custom_addons`

Na sua máquina ou servidor Odoo:

```bash
cd /opt/odoo/custom_addons
git clone https://github.com/pdrbsts/pt_at_zonesoft_api.git pt_at_zonesoft_api
```

> **Nota**: Garanta que a pasta do módulo se chama `pt_at_zonesoft_api` dentro da sua diretoria de `custom_addons`.

### 2. Configurar o ficheiro `odoo.conf`

Certifique-se de que a diretoria `custom_addons` está incluída na propriedade `addons_path`:

```ini
[options]
addons_path = /opt/odoo/odoo/addons,/opt/odoo/custom_addons
```

### 3. Atualizar a Lista de Módulos e Instalar

#### Opção A (Via Linha de Comandos - Recomendado):
```bash
/opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin -c /etc/odoo.conf -d NOME_DA_SUA_BD -u pt_at_zonesoft_api --stop-after-init
systemctl restart odoo
```

#### Opção B (Via Interface Gráfica Odoo):
1. Aceda ao Odoo com um utilizador Administrador.
2. Ative o **Modo de Criador / Developer Mode** nas Definições.
3. Aceda ao menu **Aplicações** ➔ Clique em **Atualizar Lista de Aplicações**.
4. Pesquise por `Portugal AT Certified Invoicing API Bridge` (ou `pt_at_zonesoft_api`).
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
   - **Envio Automático Faturas**: Ative para emitir faturas de venda na API ao confirmar o movimento.
   - **Envio Automático Guias de Transporte**: Ative para emitir Guias de Transporte na API ao concluir a Entrega (`stock.picking`).
4. Clique em **Guardar**.

---

## 💻 Utilização

### Emissão de Faturas de Venda (`account.move`)
1. Aceda a **Contabilidade** ➔ **Faturas de Clientes**.
2. Crie e valide uma fatura de cliente.
3. Na fatura no estado **Confirmado**:
   - Se o envio automático estiver ativo, o documento é emitido imediatamente.
   - Caso contrário, clique no botão **"Emitir Fatura Certificada (API)"** no cabeçalho.
4. O documento é emitido na ZoneSoft, assinado pela AT, renomeado para o número certificado (ex.: `FT AP2026L1II1/6`) e o PDF fica anexado ao **Chatter**.

### Emissão de Guias de Transporte (`stock.picking`)
1. Aceda a **Inventário** ➔ **Operações** ➔ **Entregas**.
2. Abra a Guia de Entrega no estado **Concluído** (`WH/OUT/...`).
3. Verifique a secção **Dados de Validação & Transporte AT**:
   - **Data de Carga**: Data prevista para o início do transporte.
   - **Hora de Carga**: Hora prevista (ex.: `18:30:00`).
4. Clique no botão **"Emitir Guia de Transporte (API)"**.
5. O documento é validado na AT, registado na ZoneSoft e renomeado para a numeração oficial da Guia de Transporte (ex.: `GT AP2026L1I1/17`).

---

## 🔍 Especificações Técnicas e Resolução de Problemas (ZoneSoft API v3)

### 1. Erro HTTP 500 (`ZoneSoft API Error 500: Internal Server Error - See system log`)
**Sintomas**: A emissão da Guia de Transporte devolve HTTP 500 sem mensagem explicativa no corpo da resposta.  
**Causas e Soluções Descobertas**:
- **Ausência do Template Completo de Documento de Transporte**:
  - A API v3 da ZoneSoft requer que o objeto `transportdocument` inclua todos os 84 atributos de estrutura padrão (incluindo `pago`, `tipo`, `compdoc`, `hashcontrol`, `datadescarga`, `horadescarga`, `levantamento`, `dataentrega`, `carga_codigo_postal` e `descarga_codigo_postal`). A omissão de campos base causa uma exceção interna no servidor PHP/C# da ZoneSoft.
  - *Solução*: O módulo utiliza um gerador de template completo preenchido dinamicamente.
- **Desfasamento de Propriedades das Linhas (`vendas`)**:
  - Cada elemento do array `vendas` numa Guia de Transporte tem de conter os atributos do documento pai (`doc: "GT"`, `serie`, `numero`, `data`, `datahora`, `empid: 0`, `posto: 1`). A ausência de `doc` ou `serie` nas linhas resulta no erro de validação `Document and Sale instance's id mismatch`.
- **Quebra na Cadeia de Hash SAF-T (`lastHash`)**:
  - Tentar atualizar manualmente o número da série enviando `numdocseries/saveInstances` apaga o campo `lastHash` da série na base de dados da ZoneSoft, impedindo a assinatura digital dos documentos seguintes (lançando HTTP 500). A numeração e assinatura SAF-T são geradas e incrementadas automaticamente pela ZoneSoft após a receção de cada `saveInstance`.

### 2. Erro AT Código `-100` (*Data início de transporte no passado*)
**Sintoma**: `ReturnCode: -100` da Autoridade Tributária.  
**Causa**: A hora enviada no campo `horacarga` é inferior ou muito próxima do momento em que os webservices da AT recebem o pedido XML. A AT rejeita documentos com data/hora no passado e a ZoneSoft responde com código HTTP `422 Unprocessable Entity` (revertendo a transação na base de dados).  
**Solução**: O módulo calcula automaticamente a hora de carga como hora atual UTC + margem de segurança de transporte futuro, garantindo aceitação imediata pela AT.

### 3. Erro AT Código `33` (*element MovementEndTime is not a valid instance*)
**Sintoma**: `simple-type 1: element MovementEndTime is not a valid instance ... Value is '?'`  
**Causa**: O campo `datadescarga` / `horadescarga` ou `dataentrega` foi omitido ou enviado sem a formatação ISO estrita (`YYYY-MM-DD` e `HH:MM:SS`).  
**Solução**: O módulo garante a formatação estrita de data e hora para `datacarga`, `horacarga`, `datadescarga`, `horadescarga`, `levantamento` e `dataentrega`.

### 4. Tratamento de Documentos sem PDF Remoto
**Regra**: Se a comunicação falhar ou a API responder com erro sem atribuir número certificado, o módulo aborta o processo, marca o estado como `error` e apresenta o aviso `_("A Zonesoft não retornou nenhum documento!")`, impedindo a criação de ficheiros corrompidos ou com 0 bytes. Em caso de sucesso HTTP 200/201 com atribuição de número de documento certificado e ATCUD, o módulo gera automaticamente o documento PDF com carimbo visual oficial para arquivo no Odoo.

---

## 📄 Licença

Este módulo está licenciado sob a **LGPL-3**.
