# N8N Seed Workflow

Arquivo importavel:

- [expertiseai-seed-workflow.json](/Users/gustavocaloi/Documents/dev/ExpertiseAI/docs/n8n/expertiseai-seed-workflow.json)

## O que esse fluxo faz

- autentica em `POST /api/v1/auth/login`
- cria areas
- cria categorias por area
- cria documentos de teste
- opcionalmente publica os documentos

## Como usar

1. Importe o JSON no n8n.
2. Abra o node `Seed Config`.
3. Ajuste:
   - `baseUrl`
   - `companyId`
   - `email`
   - `password`
   - `documents`
   - `areas`
   - `categoriesPerArea`
   - `publish`
   - `seed`
4. Execute o workflow manualmente.

## Observacoes

- O fluxo envia `User-Agent` de navegador para reduzir bloqueios do Cloudflare.
- Se o Cloudflare do dominio continuar bloqueando a chamada, a liberacao precisa ser feita no proxy/WAF.
- O node `Run Seed` executa toda a logica em JavaScript, entao nao depende do script Python local.
