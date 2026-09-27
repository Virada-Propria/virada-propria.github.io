# Diagnóstico do GitHub Pages

Consulta realizada em 27/09/2026. Nenhuma configuração remota foi alterada.

## Revalidação autenticada do checkpoint

Antes do commit do checkpoint, `gh api repos/Virada-Propria/virada-propria.github.io/pages` confirmou diretamente `build_type: legacy`, `source.branch: main`, `source.path: /`, `status: built`. A limitação da consulta inicial descrita abaixo foi resolvida com a CLI autenticada. O único workflow continua sendo o dinâmico `pages-build-deployment`.

O último build é `1237669811`, publicado a partir de `bf9de882895c16af720b38b16ed704804d2c92b2`. A árvore remota main não contém configuração Jekyll personalizada, `.nojekyll` ou workflows versionados. O push apenas de `automacao-publicacao-v2` não atualiza a origem de publicação. Os caminhos públicos `/_producao/canonico/vigente.json` e `/_producao/OPERACAO.md` retornaram HTTP 404. A exclusão de diretórios com underscore pelo Jekyll permanece aplicável; arquivos enviados à branch continuam acessíveis pelo repositório público, não pelo site.

## Evidência observada

- Repositório: `Virada-Propria/virada-propria.github.io`, público.
- Um workflow ativo retornado pela API: `pages-build-deployment`, id `359903547`, caminho dinâmico `dynamic/pages/pages-build-deployment`.
- Nenhum YAML de workflow versionado no checkout; sem `.nojekyll`, `_config.yml` ou Gemfile.
- Última execução consultada: `36077770555`, concluída com sucesso em 25/09/2026, commit `bf9de882895c16af720b38b16ed704804d2c92b2` (igual ao HEAD inicial local).
- O log do job `107892743758` registra checkout `ref: main`, build com `source: .`, destino `./_site`, `Configuration file: none`, `github-pages v232` e `jekyll v3.10.0`.
- O upload usa `INPUT_PATH: ./_site`; portanto, o comportamento observado é publicação da branch main, pasta raiz, após processamento por Jekyll.
- A consulta sem autenticação ao endpoint `/pages` retornou 404; o conector não permite esse endpoint. A conclusão acima provém do build efetivamente executado, não de acesso à tela administrativa Settings/Pages. Uma alteração remota posterior ao último build ainda precisa ser descartada antes da publicação.

[Execução](https://github.com/Virada-Propria/virada-propria.github.io/actions/runs/36077770555) · [Log do build](https://github.com/Virada-Propria/virada-propria.github.io/actions/runs/36077770555/job/107892743758)

## Isolamento da produção

No processamento padrão do Jekyll, diretórios iniciados por `_` não são copiados para o site. Portanto, `_producao/` fica fora do conteúdo público sob a configuração observada. Não existe `include` customizado no build investigado.

Isso NÃO é uma garantia independente do mecanismo de publicação. Se houver `.nojekyll`, inclusão explícita em configuração ou upload direto da raiz, os arquivos internos poderão chegar ao site. Antes de qualquer publicação futura, revalidar a configuração remota e inspecionar o artefato final para exigir ausência de `_producao/`. O importador sinaliza mudança local de configuração, mas não consulta a rede nem valida um artefato real nesta etapa.

Na investigação inicial, `AGENTS.md` ainda não tinha exclusão explícita. A etapa `apply` adicionou `_config.yml` local à branch de trabalho, excluindo AGENTS.md, `_producao/`, testes, manifests, relatórios, ZIPs e temporários. O arquivo usa JSON válido como YAML, include vazio e padrões também para variantes de capitalização. O apply recusa configurações diferentes da lista conhecida em `automacao/publicacao.py`. Isso não modifica o Pages remoto enquanto a branch não for incorporada à origem publicada.

Exclusão do Pages não é confidencialidade no GitHub: quando versionados e enviados, arquivos de `_producao/` estarão acessíveis no repositório público. Não armazenar segredos, credenciais ou dados privados de lotes nesse diretório versionado.

Não foi criado workflow, deploy ou `.nojekyll`. Somente a configuração local de exclusão Jekyll foi adicionada nesta etapa; sitemap/robots públicos permanecem intactos. Os exemplos de apply são executados em repositórios temporários separados. Um build real do Jekyll não foi executado nesta etapa; antes de publicação autorizada, conferir novamente o artefato real do Pages.

Fontes: [GitHub Pages e Jekyll](https://docs.github.com/en/pages/setting-up-a-github-pages-site-with-jekyll/about-github-pages-and-jekyll) e [bypass com .nojekyll](https://github.blog/news-insights/bypassing-jekyll-on-github-pages/).
