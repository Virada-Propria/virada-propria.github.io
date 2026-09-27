"""Publication boundary: explicit Jekyll exclusions and a conservative artifact inventory."""
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from importar import local_file, safe_path

EXCLUDED_NAMES = {'AGENTS.md', 'README.md', 'tests', 'test', 'fixtures', 'exemplos',
                  'manifests', 'relatorios', 'reports', 'tmp', 'temp', 'node_modules', 'vendor'}
INTERNAL_SUFFIXES = {'.zip','.docx','.md','.json','.py','.pyc','.ps1','.cjs','.tmp','.log','.bak','.yml','.yaml'}
PUBLIC_SUFFIXES = {'.html','.htm','.png','.jpg','.jpeg','.webp','.gif','.svg','.css','.js','.woff','.woff2','.ico'}
def caseless(value):
    return ''.join('['+c.lower()+c.upper()+']' if c.isalpha() else c for c in value)

PATTERNS = EXCLUDED_NAMES | {'_producao','Gemfile','Gemfile.lock'} | {'**/' + n for n in EXCLUDED_NAMES} | {
    '*' + s for s in INTERNAL_SUFFIXES} | {'**/*' + s for s in INTERNAL_SUFFIXES}
CONFIG = {'include': [], 'exclude': sorted(PATTERNS | {caseless(p) for p in PATTERNS})}

def internal(name):
    parts = name.replace('\\','/').split('/')
    return any(p.startswith(('.', '_', '#', '~')) or p.casefold() in {n.casefold() for n in EXCLUDED_NAMES}
               for p in parts) or Path(name).suffix.lower() in INTERNAL_SUFFIXES or name.endswith('~')

def public(name):
    return not internal(name) and (Path(name).suffix.lower() in PUBLIC_SUFFIXES or name in ('robots.txt','sitemap.xml'))

def configuration_errors(root, required=False):
    errors = []
    if (root/'.nojekyll').exists() or (root/'.github/workflows').exists():
        errors.append('Mecanismo Pages alterado: .nojekyll ou workflows exigem nova validação')
    file = root/'_config.yml'
    if not file.exists():
        if required:
            errors.append('_config.yml de isolamento obrigatório antes do apply')
    else:
        try:
            if not local_file(root,'_config.yml') or json.loads(file.read_text(encoding='utf-8-sig')) != CONFIG:
                errors.append('_config.yml difere da configuração de isolamento suportada')
        except (ValueError, OSError):
            errors.append('_config.yml inválido; não aceitar include/plugins ou exclusões desconhecidas')
    return errors

def inventory(root):
    """Walk without following reparse points, including new files not yet staged."""
    result = []
    def walk(directory):
        for path in directory.iterdir():
            rel = path.relative_to(root).as_posix()
            if internal(rel):
                continue
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('Link/reparse point na área pública: ' + rel)
            safe_path(rel)
            if path.is_dir():
                walk(path)
            elif public(rel) and local_file(root,rel):
                result.append(rel)
            else:
                raise ValueError('Arquivo fora do inventário público permitido: ' + rel)
    walk(root)
    return sorted(result)

def internal_reference(value):
    path = unquote(urlsplit(value).path).replace('\\','/')
    return internal(path.lstrip('/'))

def write_config(root):
    (root/'_config.yml').write_text(json.dumps(CONFIG,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
