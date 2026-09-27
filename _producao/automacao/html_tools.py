"""HTML parsing, constrained content and canonical template rendering."""
from copy import deepcopy
from html import escape
import json
import re
from urllib.parse import urlsplit
from lxml import etree, html

BASE_URL = 'https://virada-propria.github.io'
NAMES = {'a-profissao': 'A profissão', 'formacao': 'Formação', 'equipamentos': 'Equipamentos'}
ALLOWED = set('p h2 h3 ul ol li strong em b i a figure figcaption img div section table thead tbody tr th td caption blockquote br span'.split())
ATTRS = set('id class href target rel src alt width height loading scope colspan rowspan aria-label'.split())
CLASSES = set('product-card info-box attention-box table-wrap cta cta-secondary'.split())

def parse(text):
    return html.document_fromstring(text)

def classes(tree, name):
    return tree.xpath('//*[contains(concat(" ", normalize-space(@class), " "), $name)]', name=' ' + name + ' ')

def text_of(node):
    return ' '.join(node.text_content().split())

def serialize(node):
    return html.tostring(node, encoding='unicode', method='html')

def document(node):
    return '<!DOCTYPE html>\n' + serialize(node)

def fragment(content):
    root = html.fragment_fromstring(content, create_parent='div')
    for node in root.iterdescendants():
        if not isinstance(node.tag, str):
            node.getparent().remove(node); continue
        if node.tag not in ALLOWED:
            raise ValueError(f'Elemento não permitido no corpo: {node.tag}')
        for key, value in node.attrib.items():
            if key not in ATTRS:
                raise ValueError(f'Atributo não permitido: {key}')
            if key == 'class' and not set(value.split()) <= CLASSES:
                raise ValueError(f'Classe fora dos componentes canônicos: {value}')
            if key in ('href', 'src'):
                url = urlsplit(value)
                if value.startswith('//') or (url.scheme and url.scheme != 'https') or url.username or url.password:
                    raise ValueError(f'URL não permitida: {value}')
                if key == 'src' and (url.scheme or not value.startswith('/assets/')):
                    raise ValueError('Imagens do corpo devem usar caminho local /assets/')
        if node.tag == 'a' and not node.get('href'):
            raise ValueError('Link sem href')
    return root

def inner(node):
    return escape(node.text or '') + ''.join(serialize(child) for child in node)

def fill(source, values):
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise ValueError(f'Campo canônico não preenchido: {key}')
        return values[key] if key in ('ARTICLE_BODY_HTML', 'SCHEMA_JSON_LD') else escape(str(values[key]), quote=True)
    return re.sub(r'\{\{([A-Z0-9_]+)\}\}', replace, source)

class Renderer:
    def __init__(self, source):
        base = parse(source)
        self.templates = {t.get('id'): inner(t) for t in base.xpath('//template')}
        for node in base.xpath('//template | //comment()'):
            node.getparent().remove(node)
        self.shell = document(base)
        self.css = base.xpath('//style')[0].text

    def page(self, template, values, route, title, description, kind='Article', customize=None):
        model = parse('<html><body>' + self.templates[template] + '</body></html>')
        if customize:
            customize(model)
        body = inner(model.find('body'))
        url = BASE_URL + route
        schema = {'@context': 'https://schema.org', '@type': kind, 'headline': title,
                  'description': description, 'url': url,
                  'isPartOf': {'@type': 'WebSite', 'name': 'Virada Própria', 'url': BASE_URL + '/'}}
        values = dict(values, TITLE=title, META_DESCRIPTION=description, CANONICAL_URL=url,
                      OG_TYPE='article' if kind == 'Article' else 'website', OG_TITLE=title,
                      OG_DESCRIPTION=description, PAGE_TYPE='article' if kind == 'Article' else 'collection',
                      SCHEMA_JSON_LD=json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c'))
        shell = re.sub(r'(<main id="page-content">).*?(</main>)', lambda m: m[1] + body + m[2], self.shell, flags=re.S)
        return fill(shell, values)

    def article(self, article, profession, name, body, next_article):
        category = article['categoria']
        values = dict(PROFESSION_NAME=name, PROFESSION_SLUG=profession, CATEGORY_NAME=NAMES[category],
                      CATEGORY_SLUG=category, ARTICLE_TITLE_SHORT=article['titulo'], H1=article['titulo'],
                      LEAD=article['abertura'], ARTICLE_BODY_HTML=body)
        def customize(model):
            if next_article:
                values.update(NEXT_ARTICLE_SLUG=next_article['slug'], NEXT_ARTICLE_TITLE=next_article['titulo'])
            else:
                node = classes(model, 'next-article')[0]; node.getparent().remove(node)
        return self.page('vp-article-page', values, f'/{profession}/{article["slug"]}/',
                         article['titulo'], article['descricao'], customize=customize)

    def hub(self, manifest):
        p = manifest['pauta']
        return self.page('vp-profession-home', dict(PROFESSION_NAME=p['nome_profissao'],
                         PROFESSION_SLUG=manifest['profissao'], PROFESSION_INTRO=p['introducao_profissao']),
                         f'/{manifest["profissao"]}/', p['nome_profissao'], p['introducao_profissao'], 'CollectionPage')

    def category(self, manifest, category, catalog):
        p, profession = manifest['pauta'], manifest['profissao']
        data = p['categorias'][category]
        def customize(model):
            container = classes(model, 'category-list')[0]
            card = next(n for n in container if n.tag == 'article')
            container.clear(); container.set('class', 'category-list')
            for slug in data['ordem']:
                article = catalog[slug]
                markup = fill(serialize(card), dict(ARTICLE_01_TITLE=article['titulo'],
                              ARTICLE_01_SUMMARY=article.get('resumo', article.get('descricao', '')),
                              ARTICLE_01_SLUG=slug, PROFESSION_SLUG=profession))
                container.append(html.fragment_fromstring(markup))
        return self.page('vp-category-page', dict(PROFESSION_NAME=p['nome_profissao'],
                         PROFESSION_SLUG=profession, CATEGORY_NAME=NAMES[category], CATEGORY_INTRO=data['introducao']),
                         f'/{profession}/{category}/', f'{NAMES[category]} - {p["nome_profissao"]}',
                         data['introducao'], 'CollectionPage', customize)

def update_index(source, manifest):
    """Modify only the profession card on the preview copy; preserve other cards."""
    tree = parse(source)
    grids = classes(tree, 'grid')
    if len(grids) != 1:
        raise ValueError('Índice /profissoes/: ponto de inserção ambíguo')
    route, name = f'/{manifest["profissao"]}/', manifest['pauta']['nome_profissao']
    card = html.fragment_fromstring('<article class="card"><div class="card-top"><h3></h3></div>'
                                   '<div class="card-body"><p></p><a class="link"></a></div></article>')
    card.xpath('.//h3')[0].text = name
    card.xpath('.//p')[0].text = manifest['pauta']['introducao_profissao']
    link = card.xpath('.//a')[0]; link.set('href', route); link.text = f'Explorar {name} →'
    existing = grids[0].xpath('.//article[.//a[@href=$route]]', route=route)
    if len(existing) > 1:
        raise ValueError('Índice contém profissão duplicada')
    if existing:
        existing[0].getparent().replace(existing[0], card)
    else:
        grids[0].append(card)
    for old in classes(tree, 'coming-card'):
        headings = old.xpath('.//strong')
        if headings and text_of(headings[0]).casefold() == name.casefold():
            old.getparent().remove(old)
    return document(tree)
