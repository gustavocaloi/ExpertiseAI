# feat

## Cards de documentos

### Excluir Cards
- [x] Funcionalidade de excluir um documento. Criado botão com o visual da plataforma. O botão fica habilitado para administrador quando a gestão de acesso está ligada e para usuário anônimo quando a gestão está desligada. Com gestão ligada e usuário sem perfil admin, o botão aparece desabilitado. Observação: documento em processamento também fica com exclusão desabilitada.

- [x] Ao invés da escrita `excluir`, foi aplicado um ícone de lixeira.


### Alterar Cards

- [x] Criado botão `Editar` ao lado esquerdo do botão de excluir, usando ícone de edição. O botão reutiliza o fluxo de edição do documento publicado.


### Badge Falha
- [x] Em caso de falha no processamento, o badge `Falha` exibe a descrição completa no hover. A descrição explícita foi removida do card.

## Estrutura
### Layout
- [x] As sessões de `Nova área` e `Nova categoria` foram movidas para o topo, deixando a lista de conteúdos cadastrados abaixo.

## LOG
- [x] Criada a variável de ambiente `EXPAI_LOG_LEVEL` para controlar o nível global de logs (`INFO`, `WARN`, `ERRO`, `DEBUG`). O bootstrap da aplicação agora configura o root logger e os loggers do `uvicorn` com esse nível.

## Infra / Operação
- [x] Aplicados limites de CPU e memória nos composes do projeto: `6g` de RAM e `2.0` CPUs.
- [x] Documentada no `README` uma referência operacional de capacidade para processamento de PDFs por faixa de páginas, baseada no histórico observado do projeto.
