"""Single ZIP -> isolated import -> canonical build -> QC -> review -> preview flow."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from xml.etree import ElementTree as ET
from lxml import html
import importar as inp
from html_tools import Renderer, parse, classes, text_of, serialize, inner, fragment, BASE_URL, update_index
import imagens
import validar
import revisao
from qc import item

PUBLIC_SUFFIXES = {'.html','.htm','.png','.jpg','.jpeg','.webp','.gif','.svg','.css','.js','.woff','.woff2','.ico'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def public_files(root, check_git):
    if check_git:
        names = subprocess.check_output(['git','-C',str(root),'ls-files','-z'], encoding='utf-8').split('\0')
    else:
        names = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()]
    return sorted(n for n in names if n and not any(p.startswith(('.', '_')) for p in n.split('/'))
                  and (Path(n).suffix.lower() in PUBLIC_SUFFIXES or n in ('robots.txt','sitemap.xml')))

def process(path, root=inp.ROOT, check_git=True, evidence=None, browser=False, online=False):
    initial = inp.preflight(path, root, check_git)
    report = {k:initial[k] for k in ('modo','pacote_aceito','publicacao_liberada','arquivos_publicos_alterados','erros_entrada')}
    if 'git' in initial:
        report['git'] = initial['git']
    report.update(qcs={g:[] for g in ('editorial','comercial','tecnico')}, plano=[], revisao=[], concluido=False)
    if not initial['pacote_aceito']:
        return report
    files = inp.inspect_zip(path)
    manifest = inp.read_json(files['manifest.json'].decode('utf-8-sig'))
    run = Path(tempfile.mkdtemp(prefix='vp-dry-run-'))
    site, inbox = run / 'site', run / 'entrada'
    site.mkdir(); inbox.mkdir()
    report.update(diretorio=str(run), lote=manifest['id'], versao_canonica='1.1', zip_sha256=sha(path.read_bytes()))
    (run / 'run.json').write_text(json.dumps({'lote':manifest['id'],'modo':'dry-run'}), encoding='utf-8')
    errors = report['qcs']['tecnico']
    def fail(code, detail, ref='Manual 11.33; 12.20'):
        errors.append(item(code,'reprovado',ref,detail))
    def write(rel, data):
        inp.safe_path(rel)
        output = site / rel
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data if isinstance(data,bytes) else data.encode('utf-8'))
    baseline, changed, generated, assets = {}, {}, {}, {}
    try:
        for name, data in files.items():
            target = inbox / inp.safe_path(name)
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        for name in public_files(root, check_git):
            if not inp.local_file(root,name):
                raise ValueError(f'Arquivo público inseguro: {name}')
            data = (root/name).read_bytes(); baseline[name] = sha(data); write(name,data)
        canonical, integrity = inp.canonical_errors()
        if integrity:
            raise ValueError('; '.join(integrity))
        renderer = Renderer((inp.PRODUCTION/'canonico'/canonical['html_base']['arquivo']).read_text(encoding='utf-8'))
        # Dependencies must be approved inputs, never generated filler.
        for dependency in manifest.get('dependencias',[]):
            dest = dependency['destino']
            rel = dest.lstrip('/') + ('index.html' if dest.endswith('/') else '')
            data = files[dependency['arquivo_zip']]
            if (site/rel).exists() and (site/rel).read_bytes() != data:
                fail('DEPENDENCIA_SOBRESCRITA', dest); continue
            if dest.endswith('.png'):
                assets[dest] = imagens.inspect(data,dest)
            else:
                # Complete approved page is validated by the same technical QC later.
                generated[dest] = data.decode('utf-8-sig')
            write(rel,data)
        for a in manifest['materias']:
            for image in a['imagens']:
                dest = image['caminho']; rel = inp.safe_path(dest.lstrip('/'))
                source = image.get('arquivo_zip')
                if source:
                    data = files[source]
                    if (site/rel).exists() and (site/rel).read_bytes() != data:
                        fail('ASSET_SOBRESCRITA',dest); continue
                elif inp.local_file(site,rel):
                    data = (site/rel).read_bytes()
                else:
                    fail('IMAGEM_AUSENTE',dest); continue
                try:
                    assets[dest] = imagens.inspect(data,dest)
                    write(rel,data)
                except Exception as exc:
                    fail('IMAGEM_INVALIDA', f'{dest}: {exc}', 'Manual 10; 12.6')
        logo = '/assets/img/logo-virada-propria.png'
        if inp.local_file(site,logo.lstrip('/')):
            try:
                assets[logo] = imagens.inspect((site/logo.lstrip('/')).read_bytes(),logo)
            except Exception as exc:
                fail('LOGO_INVALIDO',str(exc))
        else:
            fail('LOGO_AUSENTE',logo)
        profession, pauta = manifest['profissao'], manifest['pauta']
        catalog = {a['slug']:a for a in manifest['materias']}
        orders = pauta['categorias']
        ordered = [slug for c in orders.values() for slug in c['ordem']]
        if len(ordered) != len(set(ordered)):
            fail('PAUTA_DUPLICADA','Matéria repetida entre categorias','Manual 6.8–6.10')
        existing_articles = {p.parent.name for p in (site/profession).glob('*/index.html') if p.parent.name not in inp.CATEGORIES}
        if existing_articles - set(ordered):
            fail('PAUTA_INCOMPLETA',str(sorted(existing_articles-set(ordered))),'Manual 6.9–6.10')
        for slug in ordered:
            if slug in inp.CATEGORIES:
                fail('SLUG_RESERVADO',slug); continue
            if slug not in catalog:
                page = site/profession/slug/'index.html'
                if page.is_file():
                    tree = parse(page.read_text(encoding='utf-8'))
                    h1, meta = tree.xpath('//h1'), tree.xpath('//meta[@name="description"]/@content')
                    if len(h1) == 1 and meta:
                        catalog[slug] = dict(slug=slug,titulo=text_of(h1[0]),descricao=meta[0])
                    else:
                        fail('DEPENDENCIA_METADADOS',slug)
                else:
                    fail('PAUTA_DESTINO_AUSENTE',slug,'Manual 7.17')
        expected_nav = {}
        for a in manifest['materias']:
            slug, category = a['slug'], a['categoria']
            order = orders[category]['ordem']
            if slug not in order:
                fail('MATERIA_FORA_DA_ORDEM',slug,'Manual 6.10'); continue
            if not all(a.get(k) for k in ('descricao','abertura')) or not pauta.get('nome_profissao'):
                fail('DADOS_MONTAGEM_AUSENTES',slug + ': descrição, abertura ou nome da profissão'); continue
            next_slug = order[order.index(slug)+1] if order.index(slug)+1 < len(order) else None
            if next_slug and next_slug not in catalog:
                fail('PROXIMA_AUSENTE',next_slug); continue
            try:
                content = files[a['conteudo']].decode('utf-8-sig')
                if not a['conteudo'].endswith('.html'):
                    raise ValueError('Montagem requer fragmento HTML; converter o texto no próprio lote antes de reprocessar')
                body = fragment(content)
                imagens.apply(body,a['imagens'],assets)
                body.set('id','vp-reportagem')
                page = renderer.article(a,profession,pauta['nome_profissao'],serialize(body),catalog.get(next_slug))
                route = f'/{profession}/{slug}/'
                generated[route] = page
                expected_nav[slug] = ([f'/{profession}/{next_slug}/'] if next_slug else []) + [f'/{profession}/{category}/',f'/{profession}/']
            except (ValueError,KeyError) as exc:
                fail('MONTAGEM_ARTIGO',f'{slug}: {exc}')
        if all(pauta.get(k) for k in ('nome_profissao','introducao_profissao')):
            generated[f'/{profession}/'] = renderer.hub(manifest)
        else:
            fail('HUB_DADOS_PENDENTES',profession,'Manual 6.3')
        for category,data in orders.items():
            if not data.get('introducao') or not pauta.get('nome_profissao'):
                fail('CATEGORIA_DADOS_PENDENTES',category,'Manual 6.9'); continue
            if all(slug in catalog for slug in data['ordem']):
                generated[f'/{profession}/{category}/'] = renderer.category(manifest,category,catalog)
        # Navigation of existing v1.1 dependencies can be updated in the overlay only.
        for category,data in orders.items():
            for index,slug in enumerate(data['ordem']):
                if slug in {a['slug'] for a in manifest['materias']} or slug not in catalog:
                    continue
                path_existing = site/profession/slug/'index.html'
                tree = parse(path_existing.read_text(encoding='utf-8'))
                nav = classes(tree,'article-nav')
                if len(nav) != 1:
                    fail('DEPENDENCIA_LEGADA',slug + ': incluir a matéria no lote para migração canônica'); continue
                # Reuse the canonical navigation fragment, never the old navigation design.
                next_slug = data['ordem'][index+1] if index+1 < len(data['ordem']) else None
                if next_slug and next_slug not in catalog:
                    continue
                stub = dict(catalog[slug], categoria=category, abertura='')
                sample = parse(renderer.article(stub,profession,pauta['nome_profissao'],'',catalog.get(next_slug)))
                nav[0].getparent().replace(nav[0],classes(sample,'article-nav')[0])
                from html_tools import document
                generated[f'/{profession}/{slug}/'] = document(tree)
        for route,page in list(generated.items()):
            if logo in assets:
                # Add dimensions to the approved logo; do not transform its pixels.
                tree = parse(page)
                for node in tree.xpath('//img[@src=$src]',src=logo):
                    node.set('width',str(assets[logo]['width'])); node.set('height',str(assets[logo]['height']))
                from html_tools import document
                page = document(tree); generated[route] = page
            write(route.lstrip('/')+'index.html',page)
        if f'/{profession}/' in generated:
            index = site/'profissoes/index.html'
            if index.is_file():
                write('profissoes/index.html',update_index(index.read_text(encoding='utf-8'),manifest))
            else:
                fail('INDICE_AUSENTE','/profissoes/')
        sitemap = site/'sitemap.xml'
        if sitemap.is_file():
            ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
            ET.register_namespace('',ns)
            xml = ET.fromstring(sitemap.read_bytes())
            if xml.tag != '{'+ns+'}urlset':
                raise ValueError('Sitemap não é urlset compatível')
            known = [x.text for x in xml.findall('{'+ns+'}url/{'+ns+'}loc')]
            if len(known) != len(set(known)):
                fail('SITEMAP_DUPLICADO','URLs preexistentes duplicadas')
            for route in generated:
                if BASE_URL+route not in known:
                    ET.SubElement(ET.SubElement(xml,'{'+ns+'}url'),'{'+ns+'}loc').text = BASE_URL+route
            write('sitemap.xml',ET.tostring(xml,encoding='utf-8',xml_declaration=True))
        else:
            fail('SITEMAP_AUSENTE','sitemap.xml')
        title_registry, desc_registry = validar.registries(site)
        for route,page in generated.items():
            errors.extend(validar.technical(page,route,site,renderer.css,title_registry,desc_registry))
        for a in manifest['materias']:
            route = f'/{profession}/{a["slug"]}/'
            if route in generated:
                checks = validar.article_qc(a,generated[route],manifest,site,assets,expected_nav[a['slug']])
                for group,items in checks.items():
                    report['qcs'][group].extend(items)
        report['imagens'] = assets
        report['paginas_montadas'] = list(generated)
        for file in site.rglob('*'):
            if file.is_file():
                rel = file.relative_to(site).as_posix()
                digest = sha(file.read_bytes())
                if baseline.get(rel) != digest:
                    changed[rel] = digest
                    report['plano'].append(dict(arquivo=rel,acao='atualizar' if rel in baseline else 'criar',sha256=digest))
        fingerprint = sha(json.dumps(dict(zip=report['zip_sha256'],baseline=baseline,changed=changed,canonical=canonical),sort_keys=True).encode())
        report['fingerprint'] = fingerprint
        requests = revisao.template(inp.PRODUCTION/'canonico'/canonical['manual']['arquivo'],fingerprint,list(generated))
        for row in list(errors):
            if row['codigo'] == 'IMAGENS_ADAPTACAO':
                slug = row['detalhe'].split(':',1)[0]
                requests['avaliacoes'].append(dict(pagina=f'/{profession}/{slug}/',
                    id='imagem-adaptacao-' + sha(row['detalhe'].encode())[:16], grupo='tecnico',
                    referencia=row['referencia'], criterio='Justificar a adaptação de imagens: ' + row['detalhe'],
                    status='pendente', evidencia=''))
                errors.remove(row)
        (run/'revisao.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2),encoding='utf-8')
        report['revisao'] = revisao.evaluate(requests, inp.read_json(evidence.read_text(encoding='utf-8')) if evidence else None)
        if browser:
            from browser_qc import verify
            report['browser'] = verify(run,list(generated))
            for row in report['browser'].get('checks',[]):
                errors.append(item('BROWSER_LAYOUT','aprovado' if row['ok'] else 'reprovado','Manual 11.17–11.19',json.dumps(row,ensure_ascii=False)))
            if report['browser'].get('error'):
                errors.append(item('BROWSER_PENDENTE','pendente','Manual 11.17',report['browser']['error']))
        else:
            errors.append(item('BROWSER_PENDENTE','pendente','Manual 11.17','Executar novamente com --browser para verificação desktop/mobile'))
        from links import inspect_links
        external = sorted({u for a in manifest['materias'] for p in a['produtos'] for u in p['links_aprovados']} | {u for a in manifest['materias'] for u in a.get('fontes_externas',[])})
        report['links_externos'] = inspect_links(external,online)
        report['qcs']['comercial'].extend(report['links_externos'])
        if any((root/n).exists() for n in ('.nojekyll','_config.yml','.github/workflows')):
            fail('PAGES_REVALIDAR_ISOLAMENTO','Configuração local mudou em relação à investigada')
        report['publicacao'] = dict(autorizada=False, motivos=['Dry-run: sem aplicação, commit, push, PR ou merge.',
                                  'Revalidar Pages e excluir AGENTS.md antes da publicação de infraestrutura.'])
        for name,digest in baseline.items():
            if sha((root/name).read_bytes()) != digest:
                fail('ORIGEM_ALTERADA_DURANTE_EXECUCAO',name)
    except Exception as exc:
        fail('PROCESSAMENTO_INTERROMPIDO',str(exc))
    findings = [x for group in report['qcs'].values() for x in group] + report['revisao']
    report['bloqueios'] = sum(x['status']=='reprovado' for x in findings)
    report['pendencias'] = sum(x['status']=='pendente' for x in findings)
    report['qc_concluido'] = not report['bloqueios'] and not report['pendencias'] and bool(report.get('paginas_montadas'))
    report['concluido'] = report['qc_concluido']
    (run/'relatorio.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
