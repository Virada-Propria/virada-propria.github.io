# Aplicação controlada de um lote

O modo `apply` grava o lote aprovado no repositório. Não autoriza publicação e não executa git add, commit, push, PR ou merge. O modo `simular` continua sem gravar páginas públicas. O Manual/HTML-base identificados em `canonico/vigente.json` permanecem as referências de produção.

## Uso

1. Trabalhar na branch `automacao-publicacao-v2`, com origin correto e árvore Git limpa. Não guardar ZIPs ou revisões fora de `_producao/` dentro do checkout; preferir uma pasta de trabalho externa. A infraestrutura ainda não commitada nesta etapa fará o apply real bloquear por árvore suja, intencionalmente.
2. Rodar a simulação com `-Browser -Online`. Corrigir o lote e registrar as evidências da revisão integrada. Reexecutar o mesmo ZIP com `-Revisoes` até obter `qc_concluido: true`. A revisão inclui o índice de Profissões. Mudanças no ZIP, conteúdo público ou referências invalidam a aprovação anterior.
3. Executar explicitamente:

```powershell
./_producao/executar.ps1 -Acao apply -Zip 'C:/lotes/aprovado.zip' -Run 'C:/caminho/vp-dry-run-aprovado' -Revisoes 'C:/revisoes/aprovada.json'
```

Os argumentos `-Browser` e `-Online` são opcionais somente no dry-run. O apply sempre exige navegador e validação externa; não oferece bypass de QC, revisão, branch ou estado Git.

## Transação e revalidação

- Confere aprovação anterior, ZIP, plano, fingerprint, bytes do artefato e configuração de isolamento. Reexecuta o dry-run com as mesmas evidências; nunca confia somente no booleano de um relatório editável.
- Usa um lock exclusivo em `.git/vp-apply.lock` para impedir aplicações concorrentes. Recusa caminhos com symlink/junction, colisões de capitalização, rotas reservadas e destinos internos.
- Audita o candidato completo antes da escrita, incluindo `/profissoes/` e sitemap. Um índice legado fora do padrão bloqueia a operação; sua presença não equivale a aprovação.
- Guarda cópias e journal em diretório temporário externo. Grava apenas os caminhos do plano reconstruído, preservando a organização dos assets. Cada arquivo é substituído atomicamente.
- Lê de volta os arquivos escritos, monta o preview a partir deles e repete os QCs editorial, comercial/navegação e técnico, inclusive canonical, title/meta, H1, OG, JSON-LD, Analytics, imagens, links internos/externos/afiliados, rotas, responsividade, sitemap e isolamento. A revisão semântica continua vinculada aos mesmos bytes aprovados, sem inventar nova aprovação.
- Compara todos os hashes com a saída aprovada. Falha, resposta externa pendente, cobertura incompleta do navegador ou alteração concorrente bloqueiam a conclusão. Restaura os arquivos tocados e remove somente os novos arquivos/diretórios da própria operação.

O sucesso retorna `aplicado: true`, `publicacao_liberada: false`, `qc_pos_gravacao`, arquivos alterados, hashes, estado Git e diretório de evidências. A CLI retorna 0 no sucesso e 1 no bloqueio. O relatório completo é `relatorio.json`; `git-diff.patch` e `git-diff-stat.txt` mostram o diff antes de qualquer commit. Como git diff não mostra arquivos novos não rastreados, o relatório complementa sua saída com `git diff --no-index` desses arquivos, sem adicioná-los ao index.

```powershell
./_producao/executar.ps1 -Acao preview -Run 'C:/caminho/vp-apply-...'
```

O preview é uma cópia dos bytes efetivamente lidos do checkout após a gravação, com hashes verificados; não é uma nova renderização. Não serve a raiz do repositório, não executa Analytics e não publica nada. Capturas ainda exigem inspeção visual; rede externa bloqueada no navegador pode produzir fonte fallback.

Em interrupção abrupta (queda de energia/processo), o lock e o journal permitem identificar a transação interrompida. Não há promessa de atomicidade de vários arquivos sob perda de energia. Preserve backup/journal, confira e restaure os destinos registrados antes de remover o lock. Se a restauração automática falhar, o relatório aponta `recuperacao_manual` e mantém o lock. Não reexecute sobre uma recuperação incompleta.

## Fronteira de publicação

`_config.yml` usa uma configuração JSON válida como YAML, com include vazio e exclusões explícitas para `_producao`, AGENTS/README, testes, fixtures, exemplos, manifests, relatórios, temporários, ZIPs, documentos e scripts internos, incluindo variantes de capitalização. O validador aceita somente essa configuração conhecida; `.nojekyll`, workflows ou mudanças de include/exclude bloqueiam o apply. Não foi criado deploy.

O inventário do preview aceita somente HTML/assets públicos e robots/sitemap. Nenhum relatório, lote, revisão ou backup é gravado em destinos públicos. O QC rejeita referências internas, inclusive `/_producao/`, e arquivos fora do inventário permitido. As exclusões são compatíveis com o [filtro do Jekyll 3.10.0](https://github.com/jekyll/jekyll/blob/v3.10.0/lib/jekyll/entry_filter.rb). Não foi realizado novo build remoto nem instalado Jekyll local nesta etapa; antes de um merge/publicação autorizado, verificar o artefato efetivo do Pages novamente.

## Exemplos exclusivamente sintéticos

`exemplos/gerar_apply.py --browser` cria um repositório temporário separado, com commit inicial exclusivamente de fixture, origin nominal sem fazer rede Git, conteúdo e aprovação sintéticos. Executa navegador real; respostas externas são simuladas. Nunca aplica no checkout real e não usa Estética Automotiva.

`exemplos/apply-sintetico.json` contém o relatório completo, inclusive QCs pós-gravação. `apply-bloqueado.json` demonstra recusa de nova aplicação com a árvore já modificada. Os testes também comprovam bloqueios por dependência, imagem, link, canonical adulterado, aprovação forjada, falha parcial de escrita e rede/navegador pendentes, com restauração.

Para um lote real ainda serão necessários os dados e evidências aprovados, logo oficial, `/empreendedorismo/`, índice de Profissões conforme o padrão e validação dos destinos reais de afiliados. O código não preenche dependências com conteúdo fictício. O lote sintético não constitui autorização editorial nem teste de fornecedores reais.
