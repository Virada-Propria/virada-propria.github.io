import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

PRODUCTION=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCTION/'automacao'))
sys.path.insert(0,str(PRODUCTION/'tests/fixtures'))
from lote import manifest, write_zip, site as fixture_site
from importar import simulate
from html_tools import parse, classes, text_of
from preview import server
import revisao
import links

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); fixture_site(self.root)
        self.m=manifest()

    def run_lote(self, m=None, mutate=None, evidence=None):
        result=simulate(write_zip(self.root/'lote.zip',m or self.m,mutate),self.root,False,evidence=evidence)
        # Temporary run directories are owned by the test and never contain repository paths.
        if result.get('diretorio'):
            import shutil
            self.addCleanup(shutil.rmtree,result['diretorio'])
        return result

    def findings(self,r):
        return [i for group in r['qcs'].values() for i in group]

    def codes(self,r):
        return [i['codigo'] for i in self.findings(r) if i['status']=='reprovado']

    def test_full_build_has_no_automatic_failures(self):
        r=self.run_lote()
        self.assertEqual(self.codes(r),[],json.dumps(self.findings(r),ensure_ascii=False))
        self.assertEqual(len(r['paginas_montadas']),8)
        self.assertFalse(r['publicacao_liberada'])
        self.assertFalse(r['qc_concluido'])  # Semantic review and browser are not forged.
        self.assertTrue(r['pendencias'])
        output=Path(r['diretorio'])/'site'
        self.assertFalse((output/'_producao').exists())
        self.assertFalse((output/'AGENTS.md').exists())

    def test_public_files_unchanged(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.run_lote()
        for name,digest in before.items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),digest)

    def test_unfilled_placeholder_blocks_but_jsonld_braces_do_not(self):
        r=self.run_lote(mutate=lambda f:f.update({'materias/inicio.html':f['materias/inicio.html']+b'<p>{{CAMPO_PENDENTE}}</p>'}))
        self.assertIn('PLACEHOLDERS',self.codes(r))

    def test_review_roundtrip_can_complete_qc_without_releasing_publication(self):
        import shutil
        path=write_zip(self.root/'lote.zip',self.m)
        first=simulate(path,self.root,False); self.addCleanup(shutil.rmtree,first['diretorio'])
        evidence=json.loads((Path(first['diretorio'])/'revisao.json').read_text(encoding='utf-8'))
        evidence['revisor']='Teste automatizado de transporte de evidências'
        for row in evidence['avaliacoes']:
            row.update(status='aprovado',evidencia='Fixture de software; não representa revisão editorial real')
        evidence_path=self.root/'evidence.json'
        evidence_path.write_text(json.dumps(evidence),encoding='utf-8')
        # These mocks test orchestration only; browser/network are separate live checks.
        with patch('browser_qc.verify',return_value={'checks':[{'ok':True}]}), patch('links.inspect_links',return_value=[]):
            result=simulate(path,self.root,False,evidence=evidence_path,browser=True,online=True)
        self.addCleanup(shutil.rmtree,result['diretorio'])
        self.assertTrue(result['qc_concluido'],result)
        self.assertFalse(result['publicacao_liberada'])

    def test_nonphysical_image_adaptation_uses_integrated_review(self):
        self.m['materias'][3]['produtos'][1]['natureza']='curso'
        self.m['materias'][3]['imagens']=[i for i in self.m['materias'][3]['imagens'] if i['produto']!='modelo-b']
        r=self.run_lote(mutate=lambda f:f.pop('imagens/modelo-b-0.png',None))
        self.assertTrue(r['pacote_aceito'],r)
        requests=json.loads((Path(r['diretorio'])/'revisao.json').read_text(encoding='utf-8'))
        self.assertTrue(any(x['id'].startswith('imagem-adaptacao-') for x in requests['avaliacoes']))
        self.assertNotIn('IMAGENS_ADAPTACAO',[x['codigo'] for x in self.findings(r)])

    def test_navigation_and_category_order(self):
        r=self.run_lote(); site=Path(r['diretorio'])/'site'
        tree=parse((site/'profissao-teste/modelo-a/index.html').read_text(encoding='utf-8'))
        nav=classes(tree,'article-nav')[0]
        self.assertEqual(nav.xpath('.//a/@href'),['/profissao-teste/opcoes/','/profissao-teste/equipamentos/','/profissao-teste/'])
        last=parse((site/'profissao-teste/opcoes/index.html').read_text(encoding='utf-8'))
        self.assertFalse(classes(last,'next-article'))
        category=parse((site/'profissao-teste/equipamentos/index.html').read_text(encoding='utf-8'))
        self.assertEqual(classes(category,'category-list')[0].xpath('.//a/@href'),['/profissao-teste/modelo-a/','/profissao-teste/opcoes/'])

    def test_index_sitemap_preserve_and_add_once(self):
        r=self.run_lote(); site=Path(r['diretorio'])/'site'
        tree=parse((site/'profissoes/index.html').read_text(encoding='utf-8'))
        self.assertEqual(len(tree.xpath('//a[@href="/profissao-teste/"]')),1)
        from xml.etree import ElementTree as ET
        urls=[n.text for n in ET.fromstring((site/'sitemap.xml').read_bytes()).iter() if n.tag.endswith('}loc')]
        self.assertEqual(len(urls),len(set(urls)))
        self.assertIn('https://virada-propria.github.io/',urls)
        self.assertIn('https://virada-propria.github.io/profissao-teste/',urls)

    def test_missing_global_dependencies_block(self):
        (self.root/'empreendedorismo/index.html').unlink()
        (self.root/'assets/img/logo-virada-propria.png').unlink()
        r=self.run_lote()
        self.assertIn('LOGO_AUSENTE',self.codes(r))
        self.assertIn('DESTINO_EXISTE',self.codes(r))

    def test_empty_category_requires_approved_intro_without_filler(self):
        self.m['materias']=[a for a in self.m['materias'] if a['categoria']!='formacao']
        self.m['pauta']['categorias']['formacao']={'ordem':[]}
        r=self.run_lote()
        self.assertIn('CATEGORIA_DADOS_PENDENTES',self.codes(r))
        self.assertFalse((Path(r['diretorio'])/'site/profissao-teste/formacao/index.html').exists())

    def test_corrupt_image_blocks(self):
        r=self.run_lote(mutate=lambda f:f.update({'imagens/modelo-a-0.png':b'not an image'}))
        self.assertIn('IMAGEM_INVALIDA',self.codes(r))

    def test_identical_images_do_not_satisfy_review(self):
        def mutate(f):
            f['imagens/modelo-a-1.png']=f['imagens/modelo-a-0.png']
            f['imagens/modelo-a-2.png']=f['imagens/modelo-a-0.png']
        r=self.run_lote(mutate=mutate)
        self.assertIn('IMAGENS_POR_PRODUTO',self.codes(r))

    def test_unapproved_link_blocks(self):
        def mutate(f):
            f['materias/modelo-a.html']=f['materias/modelo-a.html'].replace(b'https://example.com/modelo-a',b'https://example.com/outro')
        r=self.run_lote(mutate=mutate)
        self.assertIn('AFILIADO_APROVADO',self.codes(r))
        self.assertIn('LINKS_POR_PRODUTO',self.codes(r))

    def test_sponsored_noopener_required(self):
        r=self.run_lote(mutate=lambda f:f.update({'materias/modelo-a.html':f['materias/modelo-a.html'].replace(b'rel="sponsored noopener"',b'')}))
        self.assertIn('SPONSORED',self.codes(r)); self.assertIn('NOOPENER',self.codes(r))

    def test_bad_internal_anchor_blocks(self):
        r=self.run_lote(mutate=lambda f:f.update({'materias/inicio.html':f['materias/inicio.html']+b'<p><a href="/profissao-teste/modelo-a/#inexistente">Detalhe inexistente</a></p>'}))
        self.assertIn('DESTINO_EXISTE',self.codes(r))

    def test_editorial_preference_blocks(self):
        r=self.run_lote(mutate=lambda f:f.update({'materias/inicio.html':f['materias/inicio.html']+b'<p>Recomendamos este produto.</p>'}))
        self.assertIn('VOZ_EDITORIAL',self.codes(r))

    def test_scripts_and_event_attributes_block(self):
        for injection in (b'<script>alert(1)</script>',b'<p onclick="alert(1)">Texto</p>',b'<a href="javascript:alert(1)">Texto</a>'):
            r=self.run_lote(mutate=lambda f:f.update({'materias/inicio.html':injection}))
            self.assertIn('MONTAGEM_ARTIGO',self.codes(r))

    def test_review_is_bound_to_fingerprint(self):
        r=self.run_lote(); requests=json.loads((Path(r['diretorio'])/'revisao.json').read_text(encoding='utf-8'))
        self.assertGreater(len(requests['avaliacoes']),100)
        with self.assertRaises(ValueError):
            revisao.evaluate(requests,dict(fingerprint='wrong',revisor='tester',avaliacoes=[]))
        first=requests['avaliacoes'][0]
        evidence=dict(fingerprint=requests['fingerprint'],revisor='tester',avaliacoes=[dict(first,status='aprovado',evidencia='')])
        with self.assertRaises(ValueError):
            revisao.evaluate(requests,evidence)

    def test_repeat_dry_run_same_fingerprint(self):
        path=write_zip(self.root/'lote.zip',self.m)
        import shutil
        first=simulate(path,self.root,False); self.addCleanup(shutil.rmtree,first['diretorio'])
        second=simulate(path,self.root,False); self.addCleanup(shutil.rmtree,second['diretorio'])
        self.assertEqual(first['fingerprint'],second['fingerprint'])
        self.assertEqual(first['plano'],second['plano'])

    def test_preview_does_not_expose_inputs_or_execute_analytics(self):
        r=self.run_lote(); run=Path(r['diretorio'])
        with server(run/'site') as http:
            thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
            try:
                base=f'http://127.0.0.1:{http.server_port}'
                with urlopen(base+'/profissao-teste/') as response:
                    self.assertEqual(response.status,200)
                    self.assertIn("script-src 'none'",response.headers['Content-Security-Policy'])
                for path in ('/_producao/canonico/vigente.json','/../entrada/manifest.json','/assets/','/AGENTS.md'):
                    with self.assertRaises(HTTPError):
                        urlopen(base+path)
            finally:
                http.shutdown(); thread.join()

    def test_network_private_addresses_rejected(self):
        with patch.object(links.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):
                links.public_url('https://example.com/')
        for url in ('http://example.com','https://u:p@example.com','https://example.com:444'):
            with self.assertRaises(ValueError):
                links.public_url(url)

if __name__=='__main__':
    unittest.main()
