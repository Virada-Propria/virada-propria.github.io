"""Synthetic integration data, never approved editorial content or an official logo."""
from io import BytesIO
import json
from pathlib import Path
import zipfile
from PIL import Image, ImageDraw

def png(seed):
    image = Image.new('RGB',(120,80),(20+seed*20,60,100))
    ImageDraw.Draw(image).text((5,30),f'TESTE {seed}',fill='white')
    stream = BytesIO(); image.save(stream,format='PNG'); return stream.getvalue()

def manifest():
    def article(slug,title,category,kind='informativa',products=None):
        return dict(slug=slug,titulo=title,tipo=kind,categoria=category,intencao='Exercitar o fluxo técnico de '+slug,
                    consulta=slug,conteudo=f'materias/{slug}.html',monetizada=kind!='informativa',produtos=products or [],
                    imagens=[],links_internos=[],descricao='Dados sintéticos para validar a montagem de '+slug+'.',
                    abertura='Exemplo técnico isolado de '+slug+'. Não constitui orientação profissional.',
                    objeto='formacao' if category=='formacao' else 'produto' if kind!='informativa' else 'geral')
    products = [dict(id=f'modelo-{x}',modelo=f'Objeto de teste {x.upper()}',natureza='fisico',
                     links_aprovados=[f'https://example.com/modelo-{x}']) for x in ('a','b')]
    articles = [article('inicio','Início da atividade de teste','a-profissao'),
                article('capacitacao','Capacitação no cenário de teste','formacao'),
                article('modelo-a','Objeto A no cenário de teste','equipamentos','review',[products[0]]),
                article('opcoes','Opções do cenário de teste','equipamentos','comparativo',products)]
    articles[0]['links_internos']=['/profissao-teste/modelo-a/']
    articles[0]['comerciais_relacionados']=['/profissao-teste/modelo-a/']
    articles[3]['produtos'][0]['review']='/profissao-teste/modelo-a/'
    for article_data in articles[2:]:
        for product in article_data['produtos']:
            for angle in (range(3) if article_data['tipo']=='review' else range(1)):
                dest=f'/assets/img/produtos/profissao-teste/{product["id"]}-{angle}.png'
                article_data['imagens'].append(dict(caminho=dest,arquivo_zip=f'imagens/{product["id"]}-{angle}.png',
                    produto=product['id'],origem='Fixture sintético para teste de software; não é fotografia de produto',
                    alt=f'Objeto de teste {product["id"]}, vista {angle}',tipo='representacao-editorial'))
    return dict(id='lote-tecnico-valido',versao_canonica='1.1',profissao='profissao-teste',pauta=dict(
        arquivo='dados/pauta.txt',pesquisa='dados/pesquisa.txt',aprovacao='Fixture técnico, não aprovado para publicação',
        nome_profissao='Profissão de teste',introducao_profissao='Cenário sintético para testar a arquitetura e a navegação.',
        categorias={c:dict(introducao='Conteúdos sintéticos de '+c+' para conferir a automação.',
                          ordem=[a['slug'] for a in articles if a['categoria']==c]) for c in ('a-profissao','formacao','equipamentos')}),materias=articles)

def payload(m):
    result={'manifest.json':json.dumps(m,ensure_ascii=False).encode(),
            'dados/pauta.txt':b'Fixture de software. Nao e pauta editorial aprovada.',
            'dados/pesquisa.txt':b'Fixture de software. Nao e pesquisa de mercado.'}
    for a in m['materias']:
        body='<h2>Aplicação do exemplo</h2><p>Este conteúdo serve apenas para conferir a montagem em ambiente isolado.</p>'
        for link in a['links_internos']:
            body+=f'<p>Consulte o <a href="{link}">objeto A do cenário de teste</a>.</p>'
        for p in a['produtos']:
            body+=f'<h2>{p["modelo"]}</h2><p>O exemplo apresenta um ponto forte e uma limitação para verificar a estrutura. Não descreve um equipamento real.</p>'
            for image in (i for i in a['imagens'] if i.get('produto')==p['id']):
                body+=f'<figure><img src="{image["caminho"]}" alt="{image["alt"]}"><figcaption>Representação editorial — fixture técnico.</figcaption></figure>'
                seed=(1 if p['id']=='modelo-a' else 5)+int(image['arquivo_zip'].split('-')[-1].split('.')[0])
                result[image['arquivo_zip']]=png(seed)
            if p.get('review') and a['tipo']=='comparativo':
                body+=f'<p><a href="{p["review"]}">Análise do objeto A</a></p>'
            for index in range(3 if a['tipo']=='review' else 1):
                body+=f'<h3>Cenário de uso {index+1}</h3><p>O contexto desta etapa antecede a consulta da opção.</p><p><a href="{p["links_aprovados"][0]}" rel="sponsored noopener" target="_blank">Ver opção de teste</a></p>'
        result[a['conteudo']]=body.encode()
    return result

def write_zip(path, m=None, mutate=None):
    m=manifest() if m is None else m
    files=payload(m)
    if mutate:
        mutate(files)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items():
            archive.writestr(name,data)
    return path

def site(root):
    """Minimal existing site fixture; fake logo is confined to the test root."""
    for route in ('','profissoes','empreendedorismo'):
        file=root/route/'index.html'; file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text('<!DOCTYPE html><html lang="pt-BR"><head><title>Fixture '+route+'</title></head>'
                        '<body><header></header><main><h1>Fixture '+route+'</h1><div class="grid"></div></main></body></html>',encoding='utf-8')
    logo=root/'assets/img/logo-virada-propria.png'; logo.parent.mkdir(parents=True,exist_ok=True); logo.write_bytes(png(0))
    (root/'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://virada-propria.github.io/</loc></url></urlset>')
