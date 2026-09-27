# Verificação da retomada — 27/09/2026

- Branch: automacao-publicacao-v2; origin: https://github.com/Virada-Propria/virada-propria.github.io.git.
- 41 testes unittest passaram em 9,478 s. Incluem regressão de placeholders/JSON-LD, integração da adaptação de imagens e ida/volta das evidências até QC concluído, mantendo publicação não autorizada. Esse último teste usa mocks de rede/navegador para testar exclusivamente a coordenação.
- Navegador real Edge: 16/16 verificações passaram no fixture isolado com dependências sintéticas (oito páginas, 390/1440 px). Evidência: exemplos/browser-fixture.json. Não se trata de aprovação editorial.
- Exemplo contra o checkout real: oito páginas montadas, 41 ocorrências de bloqueio, três pendências. Os bloqueios repetidos correspondem ao logo oficial ausente e à rota /empreendedorismo/ ausente; 16 deles vêm do navegador detectar o logo quebrado. Pendências: revisão canônica e duas verificações HTTP não executadas para URLs sintéticas example.com.
- ZIP inválido recusado antes da importação por ../escape.txt.
- Preview HTTP real e isolamento verificados em teste; captura mobile inspecionada, sem overflow, com logo ausente corretamente visível. Captura: exemplos/preview-review-mobile.png.
- git diff --exit-code e git diff --cached --exit-code retornaram zero. Nenhum arquivo público versionado alterado; somente AGENTS.md e _producao/ permanecem não rastreados. Sem commit, push, PR ou merge.

Correções desta retomada: detecção precisa de placeholders; launcher integrado para simular/preview/browser/revisões/rede; execução estável de capturas no Edge com GPU desabilitada; adaptação de imagens incluída na revisão integrada; exemplos e documentação atualizados. Referências canônicas e páginas públicas preservadas.

Limites: sem validação de afiliados reais nesta rodada; fontes externas bloqueadas no teste de navegador, portanto visual com fallback; precisão editorial e identidade das imagens exigem revisão baseada no Manual. Não há aplicação/publicação automatizada autorizada nesta etapa.
