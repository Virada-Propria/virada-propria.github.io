"""Three skeleton QCs. File presence never approves editorial or visual quality."""
def item(code, status, reference, detail):
    return dict(codigo=code, status=status, referencia=reference, detalhe=detail)

def editorial(manifest):
    return [item('EDITORIAL_REVISAO', 'pendente', 'Manual 12.8; capítulos 2–5 e 8',
                 'Revisar pauta, pesquisa, intenção, redação, fatos e fontes. A aprovação declarada no manifest precisa de conferência.')]

def comercial(manifest):
    results = []
    for article in manifest['materias']:
        for product in article['produtos']:
            if article['monetizada'] and not product['links_aprovados']:
                results.append(item('LINK_APROVADO_AUSENTE', 'reprovado', 'Manual 9.5–9.6', product['id']))
    results.append(item('COMERCIAL_REVISAO', 'pendente', 'Manual 12.8; capítulos 5–7 e 9',
                        'Conferir aprovação real, destino e distribuição dos links no HTML, CTAs, disclaimer e navegação renderizada.'))
    return results

def tecnico(manifest, exists, dependencies):
    results = list(dependencies)
    for article in manifest['materias']:
        images = article['imagens']
        for image in images:
            results.append(item('IMAGEM_ARQUIVO', 'aprovado' if exists(image) else 'reprovado',
                                'Manual 10.3; 11.23; 12.6', image['caminho']))
        for product in article['produtos']:
            count = len({i['caminho'] for i in images if i.get('produto') == product['id'] and exists(i)})
            minimum = 3 if article['tipo'] == 'review' else 1 if article['tipo'] == 'comparativo' else 0
            if count < minimum:
                status = 'reprovado' if product['natureza'] == 'fisico' else 'pendente'
                results.append(item('IMAGENS_INSUFICIENTES', status, 'Manual 5.9; 5.21; 5.33',
                                    f"{article['slug']}: {product['id']}: {count}/{minimum}; cursos/livros permitem adaptação revisada"))
        results.append(item('IMAGENS_REVISAO', 'pendente', 'Manual capítulos 5 e 10; 12.6',
                            f"{article['slug']}: confirmar necessidade, origem aprovada, modelo exato, variedade, enquadramento, alt e otimização."))
    results.append(item('TECNICO_REVISAO', 'pendente', 'Manual 12.8; capítulos 1, 10 e 11',
                        'Montagem/inspeção do HTML, SEO técnico, Analytics, links, layout, performance e responsividade ainda não implementadas.'))
    return results
