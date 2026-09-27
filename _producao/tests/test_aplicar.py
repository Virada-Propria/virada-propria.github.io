"""All writes and fixture commits are confined to disposable synthetic repositories."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PRODUCTION=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PRODUCTION/'automacao'),str(PRODUCTION/'tests/fixtures')]
import aplicar
import publicacao
import pipeline
from importar import simulate
from lote import site,manifest,write_zip
from html_tools import Renderer,parse,document
from qc import item

def browser_stub(run,routes):
    return {'checks':[dict(route=route,width=width,ok=True) for route in routes for width in (390,1440)]}

def network_stub(urls,online=False):
    return [item('HTTP_EXTERNO','aprovado' if online else 'pendente','Fixture de rede',u) for u in urls]

def fixture_repo(root):
    site(root); publicacao.write_config(root)
    # Approved canonical index fixture, with no invented real profession content.
    source=next((PRODUCTION/'canonico').glob('*.html')).read_text(encoding='utf-8')
    renderer=Renderer(source)
    renderer.templates['fixture-index']='<h1>Profissões sintéticas</h1><h2>Lista sintética</h2><div class="grid"></div>'
    page=renderer.page('fixture-index',{},'/profissoes/','Profissões sintéticas','Índice exclusivo dos testes de software.','CollectionPage')
    tree=parse(page)
    for img in tree.xpath('//img'):
        img.set('width','120'); img.set('height','80')
    (root/'profissoes/index.html').write_text(document(tree),encoding='utf-8')
    # Deliberate internal files: none may enter the publication artifact.
    for name in ('AGENTS.md','_producao/lote.zip','_producao/manifest.json','tests/example.html','reports/draft.html','temp/cache.json'):
        p=root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('fixture interno')
    commands=[['init','-b','automacao-publicacao-v2'],['config','core.autocrlf','false'],
              ['remote','add','origin','https://github.com/Virada-Propria/virada-propria.github.io.git'],
              ['add','.'],['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','synthetic baseline']]
    for args in commands:
        subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)

class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.root=self.base/'repo'; self.root.mkdir()
        fixture_repo(self.root)
        self.m=manifest(); self.zip=self.base/'lote.zip'; self.evidence=self.base/'revisao.json'
        self.browser=patch('browser_qc.verify',side_effect=browser_stub).start()
        self.online=patch('links.inspect_links',side_effect=network_stub).start()
        self.addCleanup(patch.stopall)
        self.runs=[]
        self.addCleanup(self.clean_runs)

    def clean_runs(self):
        for path in self.runs:
            if path.exists(): shutil.rmtree(path)

    def retain(self,r):
        if r.get('diretorio'): self.runs.append(Path(r['diretorio']))
        if r.get('dry_run_revalidado'): self.retain(r['dry_run_revalidado'])
        return r

    def approved(self,mutate=None):
        write_zip(self.zip,self.m,mutate)
        first=self.retain(simulate(self.zip,self.root,True,browser=True,online=True))
        self.assertTrue(first['pacote_aceito'],first)
        request=json.loads((Path(first['diretorio'])/'revisao.json').read_text(encoding='utf-8'))
        request['revisor']='Fixture automatizado; NÃO é revisão editorial real'
        for row in request['avaliacoes']:
            row.update(status='aprovado',evidencia='Dado sintético para testar transporte da aprovação')
        self.evidence.write_text(json.dumps(request),encoding='utf-8')
        return self.retain(simulate(self.zip,self.root,True,self.evidence,True,True))

    def execute(self,r):
        return self.retain(aplicar.apply(self.zip,Path(r['diretorio']),self.evidence,self.root))

    def findings(self,result,stage='qc_pos_gravacao'):
        return {x['codigo'] for rows in result.get(stage,{}).get('qcs',{}).values() for x in rows}

    def test_valid_applies_hub_categories_index_sitemap_and_assets(self):
        approved=self.approved(); self.assertTrue(approved['qc_concluido'],approved)
        head=aplicar.git(self.root,'rev-parse','HEAD')
        result=self.execute(approved)
        self.assertTrue(result['aplicado'],result['erros'])
        for row in approved['plano']:
            self.assertEqual(aplicar.digest((self.root/row['arquivo']).read_bytes()),row['sha256'])
        for slug in ('','a-profissao','formacao','equipamentos','inicio','modelo-a','opcoes','capacitacao'):
            self.assertTrue((self.root/'profissao-teste'/slug/'index.html').is_file())
        self.assertIn('/profissao-teste/',(self.root/'profissoes/index.html').read_text(encoding='utf-8'))
        self.assertIn('/profissao-teste/equipamentos/',(self.root/'sitemap.xml').read_text())
        self.assertEqual(head,aplicar.git(self.root,'rev-parse','HEAD'))
        self.assertFalse(aplicar.git(self.root,'diff','--cached','--name-only'))
        self.assertIn('profissao-teste',result['diff_stat'])
        self.assertFalse(result['publicacao_liberada'])

    def test_complete_post_apply_revalidation_and_exact_preview(self):
        result=self.execute(self.approved()); self.assertTrue(result['aplicado'],result['erros'])
        self.assertTrue(result['qc_pos_gravacao']['qc_concluido'])
        expected={'CANONICAL','TITLE','META_DESCRIPTION','H1','OPEN_GRAPH','JSON_LD','ANALYTICS',
                  'IMAGEM_BYTES_ATRIBUTOS','DESTINO_EXISTE','HTTP_EXTERNO','AFILIADO_APROVADO',
                  'NAVEGACAO_ESTRUTURAL','ROTA_OBRIGATORIA','BROWSER_COBERTURA','SITEMAP_DESTINO',
                  'VOZ_EDITORIAL','CONTEUDO_PRESENTE','ARTEFATO_SEM_INTERNOS'}
        self.assertTrue(expected <= self.findings(result),expected-self.findings(result))
        self.assertEqual(aplicar.snapshot(Path(result['preview'])),aplicar.snapshot(self.root))
        self.assertEqual(set(result['qc_pos_gravacao']['qcs']),{'editorial','comercial','tecnico'})
        self.assertGreaterEqual(self.browser.call_count,5)

    def test_missing_dependency_blocks_without_writes(self):
        self.m['pauta']['categorias']['formacao']['ordem'].append('nao-aprovada')
        before=aplicar.snapshot(self.root); result=self.execute(self.approved())
        self.assertFalse(result['aplicado']); self.assertEqual(before,aplicar.snapshot(self.root))

    def test_missing_required_image_blocks(self):
        # Generate the normal payload first, then remove the declared image in the ZIP/manifest.
        def remove(files):
            data=json.loads(files['manifest.json'])
            for a in data['materias']:
                for img in a['imagens']:
                    if img.get('arquivo_zip')=='imagens/modelo-a-0.png': img.pop('arquivo_zip')
            files['manifest.json']=json.dumps(data).encode(); files.pop('imagens/modelo-a-0.png')
        result=self.execute(self.approved(remove))
        self.assertFalse(result['aplicado']); self.assertFalse((self.root/'profissao-teste').exists())

    def test_broken_link_blocks(self):
        result=self.execute(self.approved(lambda f:f.update({'materias/inicio.html':f['materias/inicio.html']+b'<a href="/inexistente/">Destino quebrado</a>'})))
        self.assertFalse(result['aplicado']); self.assertFalse((self.root/'profissao-teste').exists())

    def test_dry_run_never_changes_public_files(self):
        before=aplicar.snapshot(self.root); self.approved()
        self.assertEqual(before,aplicar.snapshot(self.root)); self.assertFalse(aplicar.git(self.root,'status','--porcelain'))

    def test_internal_files_not_in_preview(self):
        result=self.execute(self.approved()); self.assertTrue(result['aplicado'],result['erros'])
        output=Path(result['preview'])
        self.assertFalse(any(publicacao.internal(p.relative_to(output).as_posix()) for p in output.rglob('*')))
        self.assertFalse((output/'AGENTS.md').exists()); self.assertFalse((output/'_producao').exists())

    def test_reference_to_internal_file_blocks(self):
        r=self.approved(lambda f:f.update({'materias/inicio.html':f['materias/inicio.html']+b'<a href="/_producao/manifest.json">Documento interno</a>'}))
        self.assertFalse(self.execute(r)['aplicado'])

    def test_dirty_tree_and_main_block(self):
        r=self.approved(); (self.root/'note.txt').write_text('alteração do usuário')
        result=self.execute(r); self.assertFalse(result['aplicado']); self.assertIn('limpo',result['erros'][0])
        (self.root/'note.txt').unlink()
        subprocess.run(['git','-C',str(self.root),'branch','-m','main'],check=True,capture_output=True)
        self.assertIn('branch',self.execute(r)['erros'][0])

    def test_changed_zip_and_artifact_block(self):
        r=self.approved(); original=self.zip.read_bytes(); self.zip.write_bytes(original+b'changed')
        self.assertIn('ZIP diferente',self.execute(r)['erros'][0]); self.zip.write_bytes(original)
        (Path(r['diretorio'])/'site/profissao-teste/inicio/index.html').write_text('tampered')
        self.assertIn('Artefato aprovado',self.execute(r)['erros'][0])

    def test_forged_approval_does_not_bypass_revalidation(self):
        r=self.approved(lambda f:f.update({'materias/inicio.html':b'<p>{{PENDENTE}}</p>'}))
        r['qc_concluido']=True
        (Path(r['diretorio'])/'relatorio.json').write_text(json.dumps(r),encoding='utf-8')
        self.assertIn('revalidado bloqueado',self.execute(r)['erros'][0])

    def test_post_write_corruption_rolls_back_and_reports_qc(self):
        r=self.approved(); before=aplicar.snapshot(self.root)
        real_write=aplicar.atomic_write
        def corrupt(path,data):
            if path==self.root/'profissao-teste/inicio/index.html':
                data=data.replace(b'rel="canonical"',b'rel="broken"')
            real_write(path,data)
        with patch('aplicar.atomic_write',side_effect=corrupt): result=self.execute(r)
        self.assertFalse(result['aplicado']); self.assertTrue(result['rollback'])
        self.assertIn('CANONICAL',self.findings(result)); self.assertEqual(before,aplicar.snapshot(self.root))
        self.assertFalse(aplicar.git(self.root,'status','--porcelain'))

    def test_network_pending_after_write_rolls_back(self):
        r=self.approved(); before=aplicar.snapshot(self.root)
        def network(urls,online=False):
            if (self.root/'profissao-teste').exists():
                return [item('HTTP_EXTERNO','pendente','Fixture','HTTP 429')]
            return network_stub(urls,online)
        with patch('links.inspect_links',side_effect=network): result=self.execute(r)
        self.assertFalse(result['aplicado']); self.assertTrue(result['rollback'])
        self.assertEqual(before,aplicar.snapshot(self.root))

    def test_config_inclusion_and_nojekyll_are_rejected(self):
        config=json.loads((self.root/'_config.yml').read_text())
        config['include']=['_producao']
        (self.root/'_config.yml').write_text(json.dumps(config))
        self.assertTrue(publicacao.configuration_errors(self.root,True))
        publicacao.write_config(self.root); (self.root/'.nojekyll').touch()
        self.assertTrue(publicacao.configuration_errors(self.root,True))

    def test_parallel_apply_lock_blocks(self):
        r=self.approved(); (self.root/'.git/vp-apply.lock').write_text('another operation')
        result=self.execute(r)
        self.assertFalse(result['aplicado']); self.assertTrue((self.root/'.git/vp-apply.lock').exists())

    def test_update_existing_hub_categories_and_article_without_duplicates(self):
        first=self.execute(self.approved()); self.assertTrue(first['aplicado'],first['erros'])
        for args in (['add','.'],['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','synthetic first batch']):
            subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True)
        self.m['pauta']['introducao_profissao']='Introdução sintética revisada no segundo lote.'
        self.m['materias'][0]['titulo']='Início sintético revisado'
        self.m['pauta']['categorias']['a-profissao']['introducao']='Categoria sintética revisada.'
        result=self.execute(self.approved()); self.assertTrue(result['aplicado'],result['erros'])
        self.assertIn('Introdução sintética revisada',(self.root/'profissao-teste/index.html').read_text(encoding='utf-8'))
        self.assertIn('Categoria sintética revisada',(self.root/'profissao-teste/a-profissao/index.html').read_text(encoding='utf-8'))
        tree=parse((self.root/'profissoes/index.html').read_text(encoding='utf-8'))
        self.assertEqual(len(tree.xpath('//a[@href="/profissao-teste/"]')),1)
        self.assertEqual((self.root/'sitemap.xml').read_text().count('<loc>https://virada-propria.github.io/profissao-teste/</loc>'),1)

    def test_partial_write_failure_restores_existing_index(self):
        r=self.approved(); before=aplicar.snapshot(self.root); real_write=aplicar.atomic_write
        fired=False
        def fail_once(path,data):
            nonlocal fired
            if path==self.root/'sitemap.xml' and not fired:
                fired=True; raise OSError('Erro de disco sintético')
            real_write(path,data)
        with patch('aplicar.atomic_write',side_effect=fail_once): result=self.execute(r)
        self.assertFalse(result['aplicado']); self.assertTrue(result['rollback'])
        self.assertEqual(before,aplicar.snapshot(self.root)); self.assertFalse(aplicar.git(self.root,'status','--porcelain'))

    def test_missing_browser_coverage_after_write_rolls_back(self):
        r=self.approved()
        def browser(run,routes):
            if (self.root/'profissao-teste').exists(): return {'checks':[]}
            return browser_stub(run,routes)
        with patch('browser_qc.verify',side_effect=browser): result=self.execute(r)
        self.assertFalse(result['aplicado']); self.assertTrue(result['rollback'])
        self.assertFalse(result['qc_pos_gravacao']['qc_concluido'])

    def test_reserved_route_and_internal_image_path_rejected(self):
        self.m['profissao']='profissoes'; write_zip(self.zip,self.m)
        r=self.retain(simulate(self.zip,self.root,True))
        self.assertFalse(r['pacote_aceito']); self.assertIn('reservada',r['erros_entrada'][0])
        self.m=manifest(); self.m['materias'][2]['imagens'][0]['caminho']='/assets/_producao/foto.png'
        write_zip(self.zip,self.m); r=self.retain(simulate(self.zip,self.root,True))
        self.assertFalse(r['pacote_aceito']); self.assertIn('interno',r['erros_entrada'][0])

    def test_ignored_public_file_is_not_silently_published(self):
        (self.root/'.git/info/exclude').write_text('orphan.html\n',encoding='utf-8')
        (self.root/'orphan.html').write_text('<html>arquivo público não aprovado</html>')
        self.assertFalse(aplicar.git(self.root,'status','--porcelain'))
        r=self.execute(self.approved())
        self.assertFalse(r['aplicado']); self.assertIn('fora do plano',r['erros'][0])
        self.assertFalse((self.root/'profissao-teste').exists())

if __name__=='__main__': unittest.main()
