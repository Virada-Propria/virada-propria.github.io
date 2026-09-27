"""Read-only QC of actual publication bytes; never rebuild or repair HTML."""
import json
import re
from xml.etree import ElementTree as ET
from urllib.parse import urlsplit
import imagens
import importar
import validar
import publicacao
from html_tools import BASE_URL, Renderer, parse
from qc import item

def audit(run, manifest, routes, requests, evidence):
    site = run/'site'
    groups = {g:[] for g in ('editorial','comercial','tecnico')}
    def check(code, ok, detail):
        groups['tecnico'].append(item(code,'aprovado' if ok else 'reprovado','QC do artefato; Manual 11–12',detail))
    canonical, errors = importar.canonical_errors()
    for error in errors:
        check('CANONICO_INTEGRIDADE',False,error)
    renderer = Renderer((importar.PRODUCTION/'canonico'/canonical['html_base']['arquivo']).read_text(encoding='utf-8'))
    files = publicacao.inventory(site)
    check('ARTEFATO_SEM_INTERNOS', all(publicacao.public(n) for n in files) and
          len(files)==sum(p.is_file() for p in site.rglob('*')), 'inventário exclusivo de publicação')
    titles, descriptions = validar.registries(site)
    actual_routes = list(dict.fromkeys([*routes,'/profissoes/']))
    assets, external = {}, set()
    for file in (site/name for name in files if name.endswith(('.html','.htm'))):
        source=file.read_text(encoding='utf-8')
        from urllib.parse import unquote
        check('CONTEUDO_SEM_PRODUCAO', '_producao/' not in unquote(source).casefold().replace('\\','/'),file.relative_to(site).as_posix())
        tree = parse(source)
        for node in tree.xpath('//*[@href or @src or @srcset or @action or @data]'):
            for attr in ('href','src','srcset','action','data'):
                value=node.get(attr)
                if value:
                    values = [part.strip().split()[0] for part in value.split(',')] if attr=='srcset' else [value]
                    for value in values:
                        check('REFERENCIA_PUBLICA_SEM_INTERNO',not publicacao.internal_reference(value),file.relative_to(site).as_posix()+': '+value)
        for value in re.findall(r'url\([\s\"\x27]*([^\)\s\"\x27]+)',source):
            check('CSS_SEM_INTERNO',not publicacao.internal_reference(value),value)
    for file in site.rglob('*.css'):
        for value in re.findall(r'url\([\s\"\x27]*([^\)\s\"\x27]+)',file.read_text(encoding='utf-8')):
            check('CSS_SEM_INTERNO',not publicacao.internal_reference(value),file.relative_to(site).as_posix()+': '+value)
    for file in (site/name for name in files if name.endswith(('.css','.js','.svg'))):
        check('ASSET_SEM_PRODUCAO','_producao/' not in unquote(file.read_text(encoding='utf-8')).casefold().replace('\\','/'),file.relative_to(site).as_posix())
    for route in actual_routes:
        file=site/route.lstrip('/')/'index.html'
        check('ROTA_OBRIGATORIA',file.is_file(),route)
        if not file.is_file():
            continue
        page=file.read_text(encoding='utf-8')
        groups['tecnico'].extend(validar.technical(page,route,site,renderer.css,titles,descriptions))
        tree=parse(page)
        for node in tree.xpath('//img[@src]'):
            src=node.get('src')
            try:
                if not src.startswith('/') or not importar.local_file(site,src.lstrip('/')):
                    raise ValueError('asset ausente ou externo')
                assets[src]=imagens.inspect((site/src.lstrip('/')).read_bytes(),src)
                check('IMAGEM_BYTES_ATRIBUTOS',node.get('width')==str(assets[src]['width']) and
                      node.get('height')==str(assets[src]['height']),src)
            except (ValueError,OSError) as exc:
                check('IMAGEM_AUSENTE_OU_INVALIDA',False,src+': '+str(exc))
        for node in tree.xpath('//a[@href] | //link[@href] | //script[@src] | //source[@src]'):
            url=node.get('href') or node.get('src')
            if validar.internal_target(url,route) is not None:
                check('LINK_ASSET_INTERNO',validar.link_exists(site,url,route),route+': '+url)
            elif node.tag=='a':
                external.add(url)
    for article in manifest['materias']:
        route=f'/{manifest["profissao"]}/{article["slug"]}/'
        file=site/route.lstrip('/')/'index.html'
        if not file.is_file():
            check('MATERIA_AUSENTE',False,route); continue
        order=manifest['pauta']['categorias'][article['categoria']]['ordem']
        index=order.index(article['slug'])
        nav=([f'/{manifest["profissao"]}/{order[index+1]}/'] if index+1<len(order) else [])
        nav += [f'/{manifest["profissao"]}/{article["categoria"]}/',f'/{manifest["profissao"]}/']
        for group,rows in validar.article_qc(article,file.read_text(encoding='utf-8'),manifest,site,assets,nav).items():
            for row in rows:
                if row['codigo']=='IMAGENS_ADAPTACAO':
                    # This manual exception is evaluated by the fingerprint-bound review below.
                    continue
                groups[group].append(row)
        for declaration in article['imagens']:
            src=declaration['caminho']
            check('IMAGEM_DECLARADA_PRESENTE',src in assets and bool(parse(file.read_text(encoding='utf-8')).xpath('//img[@src=$src]',src=src)),src)
    for route in ('/','/profissoes/','/empreendedorismo/',f'/{manifest["profissao"]}/',
                  *(f'/{manifest["profissao"]}/{c}/' for c in importar.CATEGORIES)):
        check('DEPENDENCIA_ROTA',validar.link_exists(site,route,'/'),route)
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    xml=ET.fromstring((site/'sitemap.xml').read_bytes())
    locs=[n.text for n in xml.findall('s:url/s:loc',ns)]
    check('SITEMAP_ESTRUTURA',xml.tag=='{'+ns['s']+'}urlset','sitemap.xml')
    check('SITEMAP_UNICO',len(locs)==len(set(locs)),'sitemap.xml')
    for route in actual_routes:
        check('SITEMAP_ROTA',BASE_URL+route in locs,route)
    for loc in locs:
        check('SITEMAP_DESTINO',bool(loc) and loc.startswith(BASE_URL+'/') and validar.link_exists(site,loc,'/'),str(loc))
    import revisao
    review = revisao.evaluate(requests,evidence)
    from links import inspect_links
    external_results=inspect_links(sorted(external),True)
    groups['comercial'].extend(external_results)
    from browser_qc import verify
    browser=verify(run,actual_routes)
    expected={(route,width) for route in actual_routes for width in (390,1440)}
    observed={(r.get('route'),r.get('width')) for r in browser.get('checks',[])}
    check('BROWSER_COBERTURA',not browser.get('error') and expected==observed,str(browser.get('error') or len(observed)))
    for row in browser.get('checks',[]):
        check('BROWSER_LAYOUT',row.get('ok') is True,json.dumps(row,ensure_ascii=False))
    findings=[x for rows in groups.values() for x in rows]+review
    return dict(qcs=groups,revisao=review,browser=browser,links_externos=external_results,
                qc_concluido=bool(routes) and all(x['status'] in ('aprovado','nao-aplicavel') for x in findings),
                bloqueios=sum(x['status']=='reprovado' for x in findings),
                pendencias=sum(x['status']=='pendente' for x in findings))
