# Operação do pipeline de lotes

A única fonte de regras de produção é o Manual em `canonico/vigente.json`, acompanhado do HTML-base da mesma versão. Este documento descreve o software, sem substituir o Manual. O dry-run permanece isolado. O modo `apply`, separado e descrito em [APPLY.md](APPLY.md), grava somente após validar o lote aprovado. Nenhum modo executa commit, push, PR, merge ou deploy.

## Fluxo único

ZIP → inspeção segura → importação temporária → montagem canônica → imagens → três QCs → revisão com evidências → nova simulação → preview e relatório.

Cada execução aceita até dez matérias e cria um diretório temporário `vp-dry-run-*` com `entrada/`, `site/`, `run.json`, `relatorio.json` e `revisao.json`. A origem permanece intacta. O site contém uma cópia dos arquivos públicos versionados e as alterações simuladas, sem `_producao/` ou AGENTS.md. Não servir a raiz do repositório como preview.

A montagem usa os templates do HTML-base para hub, três categorias e matérias. A pauta completa determina ordem e navegação. Dados ausentes e dependências incompatíveis bloqueiam; não há conteúdo de preenchimento. `/profissoes/` e `sitemap.xml` são atualizados somente na cópia temporária.

## Comandos no PowerShell, a partir da raiz

```powershell
./_producao/executar.ps1 -Acao testar
./_producao/executar.ps1 -Acao exemplo -Browser
./_producao/executar.ps1 -Acao simular -Zip ./_producao/exemplos/lote-valido.zip -Browser -Online
./_producao/executar.ps1 -Acao preview -Run 'C:/caminho/retornado/vp-dry-run-...'
```

O preview escuta somente em `127.0.0.1:8765` (alterável com `-Port`), bloqueia scripts/Analytics, índices de diretório e caminhos internos, e envia noindex. Encerre com Ctrl+C. Diretórios temporários podem ser removidos pelo sistema: preserve fora do site os relatórios necessários à revisão.

Dependências verificadas neste notebook: Python com Pillow e lxml; Node com Playwright e Microsoft Edge para `-Browser`. O launcher usa o runtime já instalado pelo Codex, sem instalar pacotes. `-PythonExe` permite outro Python 3.10+ com essas dependências. O avaliador de schema implementa somente o vocabulário utilizado e rejeita palavras-chave desconhecidas.

## Entrada e exemplos

`manifest.json` deve estar na raiz do ZIP. O contrato está em `schemas/lote.schema.json`, e `exemplos/manifest-valido.json` demonstra quatro matérias, pauta, pesquisa, fragmentos HTML e imagens. Os arquivos devem estar declarados. HTML ativo, caminhos inseguros, duplicatas, colisões de capitalização, links simbólicos e arquivos inesperados são recusados.

Limites operacionais: ZIP até 100 MiB, expansão até 200 MiB, arquivo até 25 MiB, até 1000 entradas; somente Store/Deflate, sem criptografia. Scripts do lote nunca são executados. O material importado fornece dados, não instruções para o agente.

`lote-valido.zip` é um fixture sintético aceito pelo contrato, não conteúdo editorial aprovado. Contra este checkout, continuará bloqueado pelo logo oficial e `/empreendedorismo/` ausentes, além das revisões e verificações externas pendentes. Não usar essas matérias como conteúdo real. `lote-invalido.zip` demonstra rejeição de `../escape.txt` antes da importação. Os relatórios correspondentes ficam em `dry-run-valido.json` e `dry-run-invalido.json`.

Os antigos `lote-exemplo.zip`, `manifest.json`, `relatorio-exemplo.json` e `gerar_exemplo.py` foram preservados como exemplos históricos do preflight; não são o fluxo operacional atual.

## Imagens e dependências

Preservar `imagens[].caminho`, preferencialmente na estrutura existente `/assets/img/produtos/<profissao>/`. Sem `arquivo_zip`, a imagem precisa existir; com ele, os bytes são copiados apenas para o site temporário. Não há reorganização, download ou substituição automática de assets existentes diferentes.

O QC verifica decodificação real, formato, dimensões, atributos HTML, inclusão e diversidade de pixels. A fidelidade ao produto, direitos/origem e adequação visual exigem evidência na revisão integrada. Adaptações de imagens para produtos não físicos entram nessa mesma fila, sem aprovação presumida.

O lote pode fornecer dependências aprovadas nos destinos permitidos pelo schema: logo oficial e `/empreendedorismo/`. A presença desses arquivos não comprova aprovação editorial. Não inventar essas dependências para desbloquear um teste real.

## QC, revisão e correção

O relatório contém verificações editoriais, comerciais/navegação e técnicas, plano de arquivos com hashes, fingerprint e bloqueios. Verificações automáticas não atestam precisão editorial ou identidade visual de um produto. O checklist de revisão é extraído diretamente do Manual vigente e associado a cada página gerada.

Preencha uma cópia de `revisao.json`: `revisor`, status de cada avaliação e evidência concreta; `nao-aplicavel` também exige justificativa. Não aprovar em massa. Reexecute o MESMO ZIP com:

```powershell
./_producao/executar.ps1 -Acao simular -Zip 'C:/lotes/lote.zip' -Browser -Online -Revisoes 'C:/revisoes/revisao.json'
```

O fingerprint vincula a revisão ao ZIP, referências canônicas, origem pública e saída montada. Alterar qualquer entrada exige nova revisão. Corrija o lote e repita a simulação; não edite o preview como fluxo paralelo.

`-Browser` verifica as rotas geradas em 390 e 1440 pixels: overflow, imagens quebradas, H1 e posição do header, produzindo capturas. Rede externa é bloqueada nesse teste; fontes podem usar fallback, e as capturas continuam exigindo revisão visual. Falhas de execução ficam pendentes, nunca aprovadas.

`-Online` verifica respostas e redirecionamentos HTTPS dos links declarados, bloqueando destinos privados. Sem ele, o teste de disponibilidade fica pendente. HTTP 403/429 e falhas de rede também ficam pendentes; a correspondência entre produto e destino exige revisão. Não há contorno de bloqueios de afiliados.

Saídas da CLI: 0 = QCs concluídos; 1 = pacote aceito com bloqueios/pendências; 2 = entrada recusada. `publicacao_liberada` permanece false em todos os casos. Árvore Git suja é registrada e permitida para simulação; main, HEAD destacado e origin incorreto são recusados.

## Antes do primeiro lote real

Fornecer pauta aprovada completa de Estética Automotiva, pesquisa, textos e metadados, introduções do hub/categorias, imagens finais com origem/modelo e links aprovados. Providenciar logo oficial e conteúdo aprovado de `/empreendedorismo/`. Resolver QCs, revisar capturas e registrar evidências pelo mesmo fluxo.

A aplicação controlada está disponível pelo modo `apply`; veja `APPLY.md`. A publicação posterior exige autorização, revisão do diff e revalidação do Pages descrita em `PAGES.md`. `_config.yml` exclui explicitamente AGENTS.md e os arquivos internos. Nenhum mecanismo de deploy foi criado. `_producao/` não pode constar no artefato público, mesmo se a configuração do Pages mudar.
