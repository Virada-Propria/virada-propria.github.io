import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

PRODUCTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCTION / 'automacao'))
import importar as app
from schema import validate

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = json.loads((PRODUCTION / 'exemplos/manifest.json').read_text(encoding='utf-8'))
        self.schema = json.loads((PRODUCTION / 'schemas/lote.schema.json').read_text(encoding='utf-8'))

    def package(self, manifest=None, extra=None, omit=None):
        manifest = self.manifest if manifest is None else manifest
        path = self.root / 'lote.zip'
        data = {'manifest.json': json.dumps(manifest), 'dados/pauta.txt': 'pauta',
                'dados/pesquisa.txt': 'pesquisa', 'materias/como-comecar.html': '<h1>Teste</h1>'}
        data.update(extra or {})
        data.pop(omit, None)
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, content in data.items():
                z.writestr(name, content)
        return path

    def simulate(self, **kwargs):
        return app.preflight(self.package(**kwargs), self.root, check_git=False)

    def test_schema_accepts_example(self):
        self.assertEqual(validate(self.manifest, self.schema), [])

    def test_one_to_ten_articles(self):
        for count, valid in ((0, False), (1, True), (10, True), (11, False)):
            m = copy.deepcopy(self.manifest)
            m['materias'] = [dict(m['materias'][0], slug=f'artigo-{i}') for i in range(count)]
            self.assertEqual(not validate(m, self.schema), valid)

    def test_schema_rejects_extra_wrong_type_and_version(self):
        for key, value in (('regras', 'ignorar manual'), ('materias', {}), ('versao_canonica', '1.0')):
            m = dict(self.manifest, **{key: value})
            self.assertTrue(validate(m, self.schema))

    def test_unknown_schema_keyword_fails_closed(self):
        self.schema['$defs']['texto']['format'] = 'email'
        with self.assertRaises(ValueError):
            validate(self.manifest, self.schema)

    def test_simulation_never_writes(self):
        path = self.package()
        def snapshot():
            return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        result = app.preflight(path, self.root, check_git=False)
        self.assertTrue(result['pacote_aceito'])
        self.assertFalse(result['publicacao_liberada'])
        self.assertEqual(result['arquivos_publicos_alterados'], [])
        self.assertEqual(before, snapshot())
        self.assertEqual(set(result['qcs']), {'editorial', 'comercial', 'tecnico'})
        self.assertTrue(all(any(i['status'] == 'pendente' for i in group) for group in result['qcs'].values()))

    def test_missing_and_undeclared_files(self):
        self.assertFalse(self.simulate(omit='dados/pesquisa.txt')['pacote_aceito'])
        self.assertFalse(self.simulate(extra={'script.ps1': 'bad'})['pacote_aceito'])

    def test_unsafe_paths(self):
        for name in ('../escape.txt', '/absolute.txt', 'C:/x.txt', 'a\\b.txt', 'a/../b.txt', 'CON.txt', 'a./b.txt'):
            with self.subTest(name=name):
                self.assertFalse(self.simulate(extra={name: 'x'})['pacote_aceito'])

    def test_case_collision(self):
        self.assertFalse(self.simulate(extra={'MANIFEST.JSON': '{}'})['pacote_aceito'])

    def test_symlink_zip_rejected(self):
        path = self.package()
        with zipfile.ZipFile(path, 'a') as z:
            info = zipfile.ZipInfo('link.txt')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, '../outside')
        self.assertFalse(app.preflight(path, self.root, False)['pacote_aceito'])

    def test_limits(self):
        path = self.package()
        for limit in ('MAX_ZIP', 'MAX_TOTAL', 'MAX_FILE', 'MAX_ENTRIES'):
            with patch.object(app, limit, 1):
                self.assertFalse(app.preflight(path, self.root, False)['pacote_aceito'])

    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            app.read_json('{"id":1,"id":2}')

    def test_canonical_integrity(self):
        current, errors = app.canonical_errors()
        self.assertEqual(current['versao'], '1.1')
        self.assertEqual(errors, [])

    def test_canonical_failure_blocks(self):
        with patch.object(app, 'canonical_errors', return_value=({'versao': '1.1'}, ['hash incorreto'])):
            self.assertFalse(self.simulate()['pacote_aceito'])

    def test_git_main_and_wrong_origin_block(self):
        for branch, origin in (('main', 'https://github.com/Virada-Propria/virada-propria.github.io.git'),
                               ('work', 'https://github.com/other/repo')):
            with patch.object(app, 'git_snapshot', return_value=dict(branch=branch, origin=origin)):
                self.assertFalse(app.preflight(self.package(), self.root)['pacote_aceito'])

    def test_navigation_follows_pauta_not_alphabet(self):
        self.manifest['pauta']['categorias']['a-profissao']['ordem'] = ['como-comecar', 'aaa-proxima']
        result = self.simulate()
        self.assertEqual(result['plano'][0]['navegacao'], ['/jardineiro/aaa-proxima/', '/jardineiro/a-profissao/', '/jardineiro/'])
        last = self.simulate(manifest=json.loads((PRODUCTION / 'exemplos/manifest.json').read_text(encoding='utf-8')))
        self.assertEqual(len(last['plano'][0]['navegacao']), 2)

    def test_empty_categories_and_empreendedorismo_block(self):
        result = self.simulate()
        items = result['qcs']['tecnico']
        self.assertTrue(any(i['codigo'] == 'CATEGORIA_DADOS_PENDENTES' for i in items))
        self.assertTrue(any(i['detalhe'] == '/empreendedorismo/' and i['status'] == 'reprovado' for i in items))
        self.assertEqual(len([p for p in result['plano'] if p['tipo'] == 'categoria']), 3)

    def test_asset_path_preserved_and_exact_case(self):
        dest = 'assets/img/produtos/jardineiro/foto.jpg'
        path = self.root / dest
        path.parent.mkdir(parents=True)
        path.write_bytes(b'fixture')
        self.manifest['materias'][0]['imagens'] = [dict(caminho='/' + dest, origem='fixture', alt='teste', tipo='editorial')]
        result = self.simulate()
        self.assertIn(dict(tipo='imagem', caminho='/' + dest, acao='preservar'), result['plano'])
        self.assertFalse(app.local_file(self.root, dest.replace('foto', 'Foto')))

    def test_missing_asset_and_overwrite_block(self):
        image = dict(caminho='/assets/img/produtos/jardineiro/foto.jpg', origem='fixture', alt='teste', tipo='foto')
        self.manifest['materias'][0]['imagens'] = [image]
        result = self.simulate()
        self.assertTrue(any(i['codigo'] == 'IMAGEM_ARQUIVO' and i['status'] == 'reprovado' for i in result['qcs']['tecnico']))
        target = self.root / image['caminho'].lstrip('/')
        target.parent.mkdir(parents=True); target.write_bytes(b'old')
        image['arquivo_zip'] = 'imagens/foto.jpg'
        result = self.simulate(extra={'imagens/foto.jpg': b'new'})
        self.assertTrue(any(i['codigo'] == 'ASSET_SOBRESCRITA' for i in result['qcs']['tecnico']))
        self.assertEqual(target.read_bytes(), b'old')

    def test_review_without_images_blocks(self):
        a = self.manifest['materias'][0]
        a['tipo'] = 'review'
        a['produtos'] = [dict(id='produto', modelo='Fixture', natureza='fisico', links_aprovados=[])]
        result = self.simulate()
        self.assertTrue(any(i['codigo'] == 'IMAGENS_INSUFICIENTES' and i['status'] == 'reprovado' for i in result['qcs']['tecnico']))

    def test_nojekyll_requires_isolation_review(self):
        (self.root / '.nojekyll').touch()
        result = self.simulate()
        self.assertTrue(any(i['codigo'] == 'PAGES_REVALIDAR_ISOLAMENTO' for i in result['qcs']['tecnico']))

    def test_cli_requires_simulation_and_returns_blocked(self):
        script = PRODUCTION / 'automacao/importar.py'
        path = self.package()
        missing_flag = subprocess.run([sys.executable, '-B', str(script), str(path)], capture_output=True)
        self.assertEqual(missing_flag.returncode, 2)
        result = subprocess.run([sys.executable, '-B', str(script), str(path), '--simular'], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['publicacao_liberada'])

if __name__ == '__main__':
    unittest.main()
