---
type: server
name: 
hostname: 
organization: 
project: 
environment: 
provider: 
ip_address: 
os: 
ssh_alias: 
status: 
criticality: 
last_verified: 
---

# {{name}}

## Visão Geral

- **Organização:** [[{{organization}}]]
- **Projeto:** [[{{project}}]]
- **Hostname / IP:** `{{hostname}}` / `{{ip_address}}`
- **Ambiente:** `{{environment}}`
- **Provedor:** `{{provider}}`
- **Status:** `{{status}}`
- **Criticidade:** `{{criticality}}`

## Serviços Hospedados

- [[Serviço]]

## Acesso e Conectividade

- **SSH Alias:** `ssh {{ssh_alias}}`
- **Portas Relevantes:** `22`
- **Autenticação:** Autenticação via chave SSH configurada na estação/servidor (sem expor credenciais no vault).

## Armazenamento e Especificações

- **Sistema Operacional:** `{{os}}`
- **Recursos:** CPU, Memória, Disco

## Histórico de Changes e Incidentes

- [[CHG-...]]
- [[INC-...]]

## Notas Operacionais e Manutenção

Orientações de operação e comandos específicos.
