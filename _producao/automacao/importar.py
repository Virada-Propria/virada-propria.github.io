"""Entrada segura para o pipeline isolado. Nunca aplica alterações no portal."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile
import zlib
from schema import validate
import qc

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = Path(__file__).resolve().parents[1]
# Limites operacionais de recursos, não regras editoriais.
MAX_ZIP, MAX_TOTAL, MAX_FILE, MAX_ENTRIES = 100*1024**2, 200*1024**2, 25*1024**2, 1000
CATEGORIES = ('a-profissao', 'formacao', 'equipamentos')

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Chave JSON duplicada: {key}')
        result[key] = value
    return result

def read_json(data):
    def invalid(value):
        raise ValueError(f'Constante JSON inválida: {value}')
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid)

def safe_path(name):
    if not name or len(name) > 240 or '\\' in name or ':' in name or name.startswith('/'):
        raise ValueError(f'Caminho inseguro: {name}')
    for part in name.split('/'):
        if (not part or part in ('.', '..') or part.endswith(('.', ' '))
                or not re.fullmatch(r'[A-Za-z0-9_.-]+', part)
                or re.fullmatch(r'(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?', part)):
            raise ValueError(f'Caminho inseguro: {name}')
    return name

def local_file(root, name):
    """Case exato e sem symlink/junction, inclusive no Windows."""
    safe_path(name)
    current = root.resolve()
    for part in name.split('/'):
        if not current.is_dir() or part not in {p.name for p in current.iterdir()}:
            return False
        current = current / part
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            return False
        if not current.resolve().is_relative_to(root.resolve()):
            return False
    return current.is_file()

def inspect_zip(path):
    if path.stat().st_size > MAX_ZIP:
        raise ValueError('ZIP excede 100 MiB')
    files = {}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(x.file_size for x in entries) > MAX_TOTAL:
            raise ValueError('ZIP excede limite de entradas ou tamanho expandido')
        seen = set()
        for entry in entries:
            name = safe_path(entry.filename[:-1] if entry.is_dir() else entry.filename)
            if name.casefold() in seen:
                raise ValueError(f'Colisão de nomes: {name}')
            seen.add(name.casefold())
            if stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f'Tipo de entrada não permitido: {name}')
            if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError('ZIP criptografado ou compressão não suportada')
            if entry.file_size > MAX_FILE:
                raise ValueError(f'Arquivo excede 25 MiB: {name}')
            if not entry.is_dir():
                data = archive.read(entry)  # Confere descompressão e CRC; nunca extrai.
                if len(data) != entry.file_size:
                    raise ValueError(f'Tamanho inconsistente: {name}')
                files[name] = data
        folded = {n.casefold() for n in files}
        for name in seen:
            if any('/'.join(name.split('/')[:i]) in folded for i in range(1, len(name.split('/')))):
                raise ValueError('Colisão entre arquivo e diretório')
    return files

def git_snapshot(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8').strip()
    return dict(branch=git('branch', '--show-current'), origin=git('remote', 'get-url', 'origin'),
                head=git('rev-parse', 'HEAD'), status=git('status', '--porcelain=v1'))

def canonical_errors():
    base = PRODUCTION / 'canonico'
    current = read_json((base / 'vigente.json').read_text(encoding='utf-8'))
    errors = []
    for role in ('manual', 'html_base'):
        reference = current[role]
        safe_path(reference['arquivo'])
        path = base / reference['arquivo']
        if not local_file(base, reference['arquivo']) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
            errors.append(f'Referência canônica ausente ou modificada: {role}')
    return current, errors

def preflight(path, root=ROOT, check_git=True):
    report = dict(modo='simulacao', pacote_aceito=False, publicacao_liberada=False,
                  arquivos_publicos_alterados=[], erros_entrada=[], plano=[], qcs={})
    try:
        current, errors = canonical_errors()
        report['erros_entrada'].extend(errors)
        report['versao_canonica'] = current['versao']
        if check_git:
            report['git'] = git_snapshot(root)
            origin = report['git']['origin'].removesuffix('.git')
            if origin not in ('https://github.com/Virada-Propria/virada-propria.github.io',
                              'git@github.com:Virada-Propria/virada-propria.github.io'):
                report['erros_entrada'].append('Origin inesperado')
            if report['git']['branch'] in ('', 'main'):
                report['erros_entrada'].append('Use branch de trabalho; main e HEAD destacado não são aceitos')
        files = inspect_zip(path)
        report['zip_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        if 'manifest.json' not in files:
            raise ValueError('manifest.json deve estar na raiz do ZIP')
        manifest = read_json(files['manifest.json'].decode('utf-8-sig'))
        schema = read_json((PRODUCTION / 'schemas/lote.schema.json').read_text(encoding='utf-8'))
        report['erros_entrada'].extend(validate(manifest, schema))
        if report['erros_entrada']:
            return report
        if manifest['versao_canonica'] != current['versao']:
            raise ValueError('Versão do lote diferente da referência vigente')
        profession, articles = manifest['profissao'], manifest['materias']
        from publicacao import public, internal
        if profession in ('assets','profissoes','empreendedorismo') or internal(profession):
            raise ValueError('Profissão usa rota reservada ou interna')
        for article in articles:
            if any(not public(i['caminho'].lstrip('/')) for i in article['imagens']):
                raise ValueError('Imagem destinada a caminho interno ou não público')
        slugs = [a['slug'] for a in articles]
        if len(slugs) != len(set(slugs)) or set(slugs) & set(CATEGORIES):
            raise ValueError('Slug duplicado ou reservado para categoria')
        expected = {'manifest.json', manifest['pauta']['arquivo'], manifest['pauta']['pesquisa']}
        dependencies = manifest.get('dependencias', [])
        if len({d['destino'] for d in dependencies}) != len(dependencies):
            raise ValueError('Dependências globais duplicadas')
        expected.update(d['arquivo_zip'] for d in dependencies)
        destinations = {}
        for article in articles:
            expected.add(article['conteudo'])
            if not article['conteudo'].endswith(('.md', '.html', '.txt')):
                raise ValueError('Conteúdo deve ser MD, HTML ou TXT; nunca é executado')
            ids = [p['id'] for p in article['produtos']]
            if len(ids) != len(set(ids)):
                raise ValueError('IDs de produtos duplicados')
            if article['tipo'] == 'review' and len(ids) != 1:
                raise ValueError('Review deve identificar uma opção (Manual 4.3)')
            if article['tipo'] == 'comparativo' and len(ids) < 2:
                raise ValueError('Comparativo deve identificar duas ou mais opções (Manual 4.4)')
            image_paths = set()
            for image in article['imagens']:
                if image.get('produto') and image['produto'] not in ids:
                    raise ValueError('Imagem refere produto não declarado')
                if image['caminho'].casefold() in image_paths:
                    raise ValueError('Imagem duplicada na matéria')
                image_paths.add(image['caminho'].casefold())
                source = image.get('arquivo_zip')
                if source:
                    expected.add(source)
                key, identity = image['caminho'].casefold(), (image['caminho'], source)
                if key in destinations and destinations[key] != identity:
                    raise ValueError('Colisão entre destinos de imagens')
                destinations[key] = identity
        missing, extra = expected - files.keys(), files.keys() - expected
        if missing or extra:
            raise ValueError(f'Arquivos ausentes: {sorted(missing)}; não declarados: {sorted(extra)}')
        report['pacote_aceito'], report['lote'] = True, manifest['id']
        findings = []
        def finding(code, status, ref, detail):
            findings.append(qc.item(code, status, ref, detail))
        def exists_route(route):
            return local_file(root, route.lstrip('/') + 'index.html')
        routes = {f'/{profession}/{a["slug"]}/' for a in articles}
        categories = manifest['pauta']['categorias']
        full_order = [slug for category in categories.values() for slug in category['ordem']]
        if len(full_order) != len(set(full_order)):
            finding('PAUTA_ORDEM_DUPLICADA', 'reprovado', 'Manual 6.8–6.10', 'Matéria repetida entre categorias')
        for slug in full_order:
            route = f'/{profession}/{slug}/'
            if slug in CATEGORIES or (route not in routes and not exists_route(route)):
                finding('PAUTA_DESTINO_INVALIDO', 'reprovado', 'Manual 7.17', route)
            elif route not in routes:
                report['plano'].append(dict(tipo='dependencia-materia', rota=route, acao='revisar-navegacao'))
        for article in articles:
            route = f'/{profession}/{article["slug"]}/'
            order, next_route = categories[article['categoria']]['ordem'], None
            if article['slug'] not in order:
                finding('MATERIA_FORA_DA_ORDEM', 'reprovado', 'Manual 6.10', route)
            elif order.index(article['slug']) + 1 < len(order):
                next_route = f'/{profession}/{order[order.index(article["slug"]) + 1]}/'
            report['plano'].append(dict(tipo='materia', rota=route, acao='atualizar' if exists_route(route) else 'criar',
                                        navegacao=[r for r in (next_route, f'/{profession}/{article["categoria"]}/', f'/{profession}/') if r]))
            for link in article['links_internos']:
                if link not in routes and not exists_route(link):
                    finding('LINK_INTERNO_AUSENTE', 'reprovado', 'Manual 7.17', link)
        hub = f'/{profession}/'
        report['plano'].append(dict(tipo='hub', rota=hub, acao='atualizar' if exists_route(hub) else 'criar'))
        if not all(manifest['pauta'].get(k) for k in ('nome_profissao', 'introducao_profissao')):
            finding('HUB_DADOS_PENDENTES', 'reprovado', 'Manual 6.3; 12.2', hub)
        for name, category in categories.items():
            route = f'/{profession}/{name}/'
            report['plano'].append(dict(tipo='categoria', rota=route, acao='atualizar' if exists_route(route) else 'criar', ordem=category['ordem']))
            if not category.get('introducao'):
                finding('CATEGORIA_DADOS_PENDENTES', 'reprovado', 'Manual 6.9; solicitação do usuário', route)
            if not exists_route(route):
                finding('CATEGORIA_ROTA_AUSENTE', 'reprovado', 'Manual 6.9; 11.31', route)
        for route in ('/', '/profissoes/', '/empreendedorismo/', hub):
            if not exists_route(route):
                finding('DEPENDENCIA_ROTA_AUSENTE', 'reprovado', 'Manual 1.2; 11.31', route)
        if not local_file(root, 'assets/img/logo-virada-propria.png'):
            finding('LOGO_AUSENTE', 'reprovado', 'Manual 11.32', '/assets/img/logo-virada-propria.png')
        for dest, source in destinations.values():
            present = local_file(root, dest.lstrip('/'))
            if not present and (root / dest.lstrip('/')).exists():
                finding('ASSET_CAMINHO_INSEGURO_OU_CASE', 'reprovado', 'Contrato operacional de caminhos', dest)
            if source and present and (root / dest.lstrip('/')).read_bytes() != files[source]:
                finding('ASSET_SOBRESCRITA', 'reprovado', 'Contrato operacional: preservar assets', dest)
            report['plano'].append(dict(tipo='imagem', caminho=dest, acao='preservar' if present else 'adicionar' if source else 'ausente'))
        from publicacao import configuration_errors
        for detail in configuration_errors(root):
            finding('PAGES_REVALIDAR_ISOLAMENTO', 'reprovado', 'Diagnóstico operacional Pages',
                    detail)
        finding('PAGES_ARTEFATO_PENDENTE', 'pendente', 'Solicitação do usuário: área interna fora do site',
                'Revalidar configuração remota e ausência de _producao/ no artefato antes de publicar; AGENTS.md também precisará de exclusão explícita.')
        def exists_image(image):
            return image['arquivo_zip'] in files if image.get('arquivo_zip') else local_file(root, image['caminho'].lstrip('/'))
        report['qcs'] = dict(editorial=qc.editorial(manifest), comercial=qc.comercial(manifest),
                             tecnico=qc.tecnico(manifest, exists_image, findings))
        for key, status in (('bloqueios', 'reprovado'), ('pendencias', 'pendente')):
            report[key] = sum(i['status'] == status for group in report['qcs'].values() for i in group)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, zlib.error, RuntimeError, subprocess.SubprocessError) as error:
        report['erros_entrada'].append(str(error))
        report['pacote_aceito'] = False
    return report

def simulate(path, root=ROOT, check_git=True, evidence=None, browser=False, online=False):
    from pipeline import process
    return process(path, root, check_git, evidence, browser, online)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path)
    parser.add_argument('--simular', action='store_true', required=True)
    parser.add_argument('--revisoes', type=Path)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--online', action='store_true')
    args = parser.parse_args()
    report = simulate(args.zip, evidence=args.revisoes, browser=args.browser, online=args.online)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('qc_concluido') else 1 if report['pacote_aceito'] else 2

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
