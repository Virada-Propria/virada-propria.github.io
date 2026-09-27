"""Executable QC of the assembled artifact, plus evidence-based semantic review."""
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, unquote
from lxml import html
from html_tools import BASE_URL, classes, parse, text_of
from qc import item

DISCLAIMER = 'Disclaimer: as análises são independentes, mas há links afiliados no site que geram comissões qualificadas.'

def add(group, code, ok, ref, detail):
    group.append(item(code, 'aprovado' if ok else 'reprovado', ref, detail))

def internal_target(url, route):
    parsed = urlsplit(urljoin(BASE_URL + route, url))
    if parsed.netloc != urlsplit(BASE_URL).netloc:
        return None
    path = unquote(parsed.path)
    if '\\' in path or any(x in ('.', '..') for x in path.split('/')):
        raise ValueError('Link interno inseguro')
    return path, unquote(parsed.fragment)

def link_exists(site, url, route):
    target = internal_target(url, route)
    if target is None:
        return True
    path, anchor = target
    rel = path.lstrip('/') + ('index.html' if path.endswith('/') else '')
    from importar import local_file
    if not local_file(site, rel):
        return False
    if anchor:
        return bool(parse((site / rel).read_text(encoding='utf-8')).xpath('//*[@id=$id]', id=anchor))
    return True

def article_qc(article, page, manifest, site, asset_info, expected_nav):
    tree, groups = parse(page), {g: [] for g in ('editorial', 'comercial', 'tecnico')}
    e, c, t = (groups[g] for g in ('editorial', 'comercial', 'tecnico'))
    body = tree.xpath('//*[@id="vp-reportagem"]')[0]
    text = text_of(body)
    forbidden = re.findall(r'\b(?:preferimos|recomendamos|nossa preferência|nós escolheríamos)\b', text, re.I)
    add(e, 'VOZ_EDITORIAL', not forbidden, 'Manual 2.9', ', '.join(forbidden) or 'Sem preferência pessoal explícita')
    add(e, 'TERMOS_INTERNOS', not re.search(r'\b(?:topo|meio|fundo) de funil\b', text, re.I), 'Manual 4.1', 'Classificação de funil não aparece no corpo')
    add(e, 'CONTEUDO_PRESENTE', bool(text), 'Manual 2.1; 12.4', article['slug'])
    objects = {p['natureza'] for p in article['produtos']}
    expected_category = 'formacao' if article.get('objeto') == 'formacao' or objects and objects <= {'curso', 'livro'} else 'equipamentos' if article['tipo'] != 'informativa' and objects == {'fisico'} else 'a-profissao'
    add(e, 'CATEGORIA', article['categoria'] == expected_category, 'Manual 6.8', expected_category)
    products = {p['id']: p for p in article['produtos']}
    approved = {u for p in products.values() for u in p['links_aprovados']}
    sources = set(article.get('fontes_externas', []))
    links = body.xpath('.//a[@href]')
    for link in links:
        href, rel = link.get('href'), set(link.get('rel', '').split())
        target = internal_target(href, f'/{manifest["profissao"]}/{article["slug"]}/')
        if target is None:
            parsed = urlsplit(href)
            add(c, 'LINK_EXTERNO_DECLARADO', href in approved | sources and parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password,
                'Manual 9.5; 11.25', href)
            if href in approved or 'sponsored' in rel:
                add(c, 'AFILIADO_APROVADO', href in approved, 'Manual 9.5–9.6', href)
                add(c, 'SPONSORED', 'sponsored' in rel, 'Manual 9.4', href)
            if link.get('target') == '_blank':
                add(c, 'NOOPENER', 'noopener' in rel, 'Manual 11.26', href)
        add(c, 'ANCORA_DESCRITIVA', text_of(link).casefold() not in ('clique aqui', 'saiba mais', 'veja aqui', ''), 'Manual 7.4', text_of(link))
    actual_hrefs = [link.get('href') for link in links]
    for declared in article['links_internos']:
        add(c, 'LINK_CONTEXTUAL_DECLARADO', declared in actual_hrefs, 'Manual 7.2', declared)
    for related in article.get('comerciais_relacionados', []):
        add(c, 'CAMINHO_COMERCIAL', related in actual_hrefs, 'Manual 2.14; 7.6', related)
    for product in products.values():
        count = sum(h in product['links_aprovados'] for h in actual_hrefs)
        minimum = 3 if article['tipo'] == 'review' else 1 if article['tipo'] == 'comparativo' else 0
        if article['monetizada']:
            add(c, 'LINKS_POR_PRODUTO', count >= minimum, 'Manual 5.10; 5.20', f"{product['id']}: {count}/{minimum}")
        if article['tipo'] == 'comparativo' and product.get('review'):
            add(c, 'LINK_REVIEW', product['review'] in actual_hrefs, 'Manual 5.19', product['review'])
        images = [i for i in article['imagens'] if i.get('produto') == product['id']]
        fingerprints = {asset_info[i['caminho']]['pixels_sha256'] for i in images if i['caminho'] in asset_info}
        minimum_images = 3 if article['tipo'] == 'review' else 1 if article['tipo'] == 'comparativo' else 0
        if product['natureza'] == 'fisico':
            add(t, 'IMAGENS_POR_PRODUTO', len(fingerprints) >= minimum_images, 'Manual 5.9; 5.21; 10.5', f"{product['id']}: {len(fingerprints)}/{minimum_images} imagens distintas")
        elif len(fingerprints) < minimum_images:
            t.append(item('IMAGENS_ADAPTACAO', 'pendente', 'Manual 5.33', article['slug'] + ': ' + product['id']))
    actual_nav = [a.get('href') for nav in classes(tree, 'article-nav') for a in nav.xpath('.//a')]
    add(c, 'NAVEGACAO_ESTRUTURAL', actual_nav == expected_nav, 'Manual 6.10–6.12', str(actual_nav))
    return groups

def technical(page, route, site, css, title_registry, description_registry):
    tree, results = parse(page), []
    def check(code, ok, ref, detail):
        add(results, code, ok, ref, route + ': ' + detail)
    check('ESTRUTURA_HTML', page.lstrip().lower().startswith('<!doctype html>') and tree.get('lang') == 'pt-BR', 'Manual 11.2', 'doctype e idioma')
    check('CHARSET_VIEWPORT', bool(tree.xpath('//meta[translate(@charset,"UTF","utf")="utf-8"]')) and bool(tree.xpath('//meta[@name="viewport"]')), 'Manual 11.2', 'charset e viewport')
    titles, descriptions = tree.xpath('//title'), tree.xpath('//meta[@name="description"]/@content')
    title = text_of(titles[0]) if titles else ''
    desc = descriptions[0] if descriptions else ''
    check('TITLE', len(titles) == 1 and bool(title) and len(title_registry.get(title, [])) == 1, 'Manual 11.4', title)
    check('META_DESCRIPTION', len(descriptions) == 1 and bool(desc) and len(description_registry.get(desc, [])) == 1, 'Manual 11.5', desc)
    check('H1', len(tree.xpath('//h1')) == 1, 'Manual 8.5', 'um H1')
    levels = [int(n.tag[1]) for n in tree.xpath('//h1 | //h2 | //h3 | //h4 | //h5 | //h6')]
    check('HEADINGS', all(b <= a + 1 for a, b in zip(levels, levels[1:])), 'Manual 11.27', str(levels))
    check('ROBOTS', tree.xpath('//meta[@name="robots"]/@content') == ['index,follow,max-image-preview:large'], 'Manual 11.6', 'robots público')
    check('CANONICAL', tree.xpath('//link[@rel="canonical"]/@href') == [BASE_URL + route], 'Manual 11.7', route)
    expected_og = {'og:locale': 'pt_BR', 'og:site_name': 'Virada Própria', 'og:url': BASE_URL + route}
    check('OPEN_GRAPH', all(tree.xpath('//meta[@property=$p]/@content', p=k) == [v] for k,v in expected_og.items()) and all(len(tree.xpath('//meta[@property=$p]/@content', p=k)) == 1 for k in ('og:title','og:description','og:type')), 'Manual 11.9', 'metadados sociais')
    try:
        schemas = tree.xpath('//script[@type="application/ld+json"]/text()')
        data = json.loads(schemas[0])
        valid = len(schemas) == 1 and data['url'] == BASE_URL + route and data['headline'] == text_of(tree.xpath('//h1')[0]) and data['description'] == desc
        valid = valid and data.get('@type') in ('Article','CollectionPage') and not re.search('datePublished|dateModified', schemas[0])
    except (IndexError, KeyError, ValueError):
        valid = False
    check('JSON_LD', valid, 'Manual 11.10–11.12', 'schema coerente e sem datas')
    check('DATAS_PUBLICAS', not tree.xpath('//time') and not re.search(r'(?:Publicado|Atualizado)\s+em\s+\d', text_of(tree), re.I), 'Manual 11.11', 'sem datas editoriais públicas')
    check('ANALYTICS', tree.xpath('//script[@src]/@src') == ['https://www.googletagmanager.com/gtag/js?id=G-4Y7LQYY0P9'] and "gtag('config', 'G-4Y7LQYY0P9')" in page, 'Manual 11.3', 'tag oficial')
    check('CSS_CANONICO', tree.xpath('//style/text()') == [css], 'Manual 1; 11.34', 'CSS idêntico à base')
    nav = classes(tree, 'global-nav')
    check('MENU_GLOBAL', len(nav) == 1 and [(text_of(a), a.get('href')) for a in nav[0].xpath('.//a')] == [('Início','/'),('Empreendedorismo','/empreendedorismo/'),('Profissões','/profissoes/')], 'Manual 1.2', 'menu global')
    check('DISCLAIMER', text_of(tree).count(DISCLAIMER) == 1 and DISCLAIMER in ' '.join(text_of(n) for n in tree.xpath('//footer')), 'Manual 1.10; 9.16', 'aviso único no rodapé')
    check('PLACEHOLDERS', not re.search(r'\{\{[^{}]+\}\}', page) and not tree.xpath('//template'), 'Manual 11.36', 'sem campos/template remanescentes')
    for node in tree.xpath('//a[@href] | //img[@src]'):
        url = node.get('href') if node.tag == 'a' else node.get('src')
        try:
            valid = link_exists(site, url, route)
        except (ValueError, OSError):
            valid = False
        check('DESTINO_EXISTE', valid, 'Manual 7.17; 11.23–11.24', url)
        if node.tag == 'img':
            check('IMAGEM_ATRIBUTOS', bool(node.get('alt')) and bool(node.get('width')) and bool(node.get('height')), 'Manual 10.10; 10.13', url)
    return results

def registries(site):
    titles, descriptions = {}, {}
    for path in site.rglob('index.html'):
        tree = parse(path.read_text(encoding='utf-8'))
        title = tree.xpath('//title')
        desc = tree.xpath('//meta[@name="description"]/@content')
        if title:
            titles.setdefault(text_of(title[0]), []).append(str(path))
        if desc:
            descriptions.setdefault(desc[0], []).append(str(path))
    return titles, descriptions
