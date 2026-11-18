# Backup e restauração da plataforma

No menu do usuário, abra **Backup e restauração**. **Baixar backup JSON** exporta a instalação inteira. Para restaurar, selecione esse JSON, digite `RESTAURAR` e clique em **Restaurar plataforma**. A operação substitui o estado atual; não mescla registros. Baixe um backup atual antes de restaurar.

## Permissões e alcance

A operação é global: o usuário deve ter o perfil `admin` ativo em **todas as empresas cadastradas**. Ser administrador de apenas uma empresa não permite ler nem substituir as demais. O papel `monitoria_admin` não concede essa permissão. Em uma instalação com uma única empresa, seus administradores podem usar a função. O servidor consulta as permissões atuais, independentemente dos papéis declarados no token.

O recurso é desabilitado quando `EXPAI_ACCESS_CONTROL_ENABLED=false`. O campo `can_manage_backup` de `/api/v1/auth/me` controla a visibilidade do menu; as rotas sempre validam a autorização novamente.

O arquivo inclui:

- Todas as tabelas da aplicação: empresas, usuários, hashes de senha, vínculos, perfis, áreas, categorias, permissões de módulo, restrições e auditoria.
- Documentos com seus UUIDs, metadados, versões, publicações, aprovações, anexos e índices de busca.
- Monitoria: configurações persistidas, organização, conversas, áudios, transcrições, avaliações, pilares, lotes e jobs.
- Histórico persistido de importações da base de conhecimento.

Configurações de implantação (`.env`, chave de assinatura JWT, chaves externas, URLs e flags de ambiente), código, logs, arquivos temporários de upload e modelos/cache do Docling não são dados restauráveis pelo JSON. Mantenha a configuração da infraestrutura separadamente. O arquivo não é criptografado: contém dados confidenciais e hashes que permitem manter as senhas originais; guarde-o com acesso restrito.

## Formato e compatibilidade

O JSON possui `format=expertise-ai-platform-backup`, `version=1`, data UTC, impressão do esquema SQLite, caminhos de origem, tabelas com colunas/registros e arquivos. Binários usam blocos Base64 de até 1 MiB de dados originais; cada arquivo registra tamanho e SHA-256. Células SQLite BLOB são representadas por um objeto `base64`. Os comandos SQL do arquivo nunca são executados: a importação usa o esquema instalado e consultas parametrizadas.

A restauração exige o mesmo esquema da instalação de origem. Para migrar entre máquinas, prepare a mesma versão da aplicação, configure os diretórios do destino e entre com seu administrador inicial para importar. Caminhos dos áudios são ajustados aos diretórios do destino, preservando IDs e UUIDs. Após uma restauração, tanto tokens de acesso quanto de renovação anteriores deixam de funcionar; entre com as credenciais existentes no backup. Se a restauração alterar a empresa padrão, recarregue a página antes do login.

## Consistência e recuperação

Backup e restauração adquirem um bloqueio exclusivo de armazenamento. Requisições REST/MCP, jobs de importação, workers de Monitoria, limpeza periódica e manutenção da KB participam do bloqueio. Se já houver uma operação em andamento, a solicitação de backup/restauração retorna `409`; aguarde e tente novamente. Durante o bloqueio, outras chamadas de API retornam `503` com `Retry-After`. Streams MCP abertos também podem impedir a aquisição do bloqueio; encerre-os antes da manutenção. Nenhum job ativo é cancelado para gerar o backup. Jobs de Monitoria na fila são preservados; uploads KB em processamento precisam terminar antes da exportação.

O banco é capturado com a API de backup do SQLite, incluindo alterações já confirmadas no WAL. Tabelas auxiliares internas do FTS são reconstruídas pelo próprio SQLite a partir das linhas da tabela virtual. A importação prepara um banco e diretórios temporários, valida formato, esquema, tabelas, relacionamentos, integridade SQLite, caminhos, conteúdo dos arquivos e existência de um administrador global antes de substituir dados.

Durante a substituição, mantém uma cópia anterior do banco e diretórios anteriores, com um diário local de recuperação. Uma exceção provoca rollback. Se o processo for encerrado durante essa fase, as APIs e workers permanecem bloqueados pelo diário; no próximo início, o serviço recupera o estado anterior **antes** da inicialização do banco. Reinicie usando os mesmos caminhos de armazenamento, especialmente `EXPAI_DB_PATH`. Não apague `.restore-journal.json` nem os diretórios temporários associados enquanto houver recuperação pendente. Falhas do disco ou perda dos próprios arquivos de recuperação exigem intervenção operacional.

## Operação e limites

- `EXPAI_BACKUP_MAX_MB` define o tamanho máximo do JSON exportado/importado; padrão: **512 MiB**. O upload também respeita limites do proxy reverso.
- A exportação escreve incrementalmente em arquivo temporário. A importação carrega o JSON em memória para validar; dimensione a memória com folga sobre o tamanho do arquivo. Base64 aumenta o tamanho dos binários em aproximadamente um terço.
- Reserve disco para o arquivo JSON, o banco temporário e cópias anterior/nova dos arquivos durante a restauração. O diretório temporário do sistema também precisa ter espaço para upload/download.
- Diretórios de KB, Monitoria e histórico de uploads devem ser independentes, sem links simbólicos; o banco deve ficar fora deles.
- O bloqueio usa `flock` em Linux/macOS. Todos os processos devem usar o mesmo `EXPAI_DATA_DIR` em armazenamento local com suporte a esse bloqueio. Escritas por scripts externos que não usam o bloqueio não são coordenadas: interrompa esses scripts durante a operação. Não há garantia para arquivos distribuídos entre hosts ou sistemas de arquivos sem essa semântica.
- Não restaure arquivos de origem desconhecida. SHA-256 verifica integridade dos arquivos, não autenticidade de quem gerou o backup.

## API

Todas as rotas exigem `Authorization: Bearer <token>` do administrador global.

| Método | Rota | Resultado |
| --- | --- | --- |
| GET | `/api/v1/admin/backup/status` | Formato, versão, limite em bytes e escopo global |
| POST | `/api/v1/admin/backup/export` | Download JSON com `Cache-Control: no-store` |
| POST | `/api/v1/admin/backup/restore` | Multipart com `file` e `confirmation=RESTAURAR`; retorna `status=restored`, contagem de arquivos e `login_required=true` |

Erros: `401` para autenticação inválida, `403` para falta de permissão/modo sem controle de acesso, `409` para armazenamento ocupado ou exportação inviável, `413` para arquivo muito grande e `422` para confirmação/backup inválido. Falhas de infraestrutura geram erro do servidor e acionam a recuperação quando a substituição já tiver começado.

## Verificação reproduzível

```bash
.venv/bin/python -m pytest tests/test_backup.py -q
# Com servidor estático apontando para app/ e Playwright instalado:
FRONTEND_URL=http://127.0.0.1:8766/static/index.html node scripts/check_backup.cjs
```

Os testes usam dados isolados. Cobrem round-trip de tabelas e arquivos, senhas, permissões, FTS, UUIDs, remapeamento de áudios, bloqueio entre processos, arquivos inválidos, limites, rollback por erro e recuperação após encerramento abrupto. O teste de navegador usa respostas simuladas e verifica download, confirmação, erros, logout, permissões e larguras de 320 a 1440 px; não substitui validação de usabilidade com administradores reais.
