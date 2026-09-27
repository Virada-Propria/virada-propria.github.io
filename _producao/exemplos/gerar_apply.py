"""Synthetic apply in a fresh disposable repository. Never targets the real checkout."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/'automacao'),str(HERE.parent/'tests')]
from test_aplicar import fixture_repo,network_stub,browser_stub
from lote import write_zip
from importar import simulate
from aplicar import apply

def main():
    base=Path(tempfile.mkdtemp(prefix='vp-exemplo-apply-'))
    root=base/'repo'; root.mkdir(); fixture_repo(root)
    package=write_zip(base/'lote.zip')
    # Network destinations and editorial approvals are synthetic fixtures only.
    # Browser can be real; production apply exposes no bypass flags.
    from contextlib import nullcontext
    browser_context=nullcontext() if '--browser' in sys.argv else patch('browser_qc.verify',side_effect=browser_stub)
    with patch('links.inspect_links',side_effect=network_stub),browser_context:
        first=simulate(package,root,True,browser=True,online=True)
        evidence=json.loads((Path(first['diretorio'])/'revisao.json').read_text(encoding='utf-8'))
        evidence['revisor']='Fixture sintético; NÃO é aprovação editorial real'
        for row in evidence['avaliacoes']:
            row.update(status='aprovado',evidencia='Aprovação sintética exclusiva de teste de software')
        review=base/'revisao.json'; review.write_text(json.dumps(evidence),encoding='utf-8')
        approved=simulate(package,root,True,review,True,True)
        result=apply(package,Path(approved['diretorio']),review,root)
        # A second apply without a clean tree must refuse to overwrite the first.
        blocked=apply(package,Path(approved['diretorio']),review,root)
    for name,data in (('apply-sintetico',result),('apply-bloqueado',blocked)):
        data['contexto_exemplo']=dict(somente_dados_sinteticos=True,navegador_real='--browser' in sys.argv,
                                      rede_simulada=True,revisao_sintetica=True,repositorio_temporario=str(root))
        (HERE/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(repo_sintetico=str(root),relatorio=result['diretorio'],aplicado=result['aplicado'],
                 erros=result['erros'],bloqueio_exemplo=blocked['erros'],
                 navegador_real='--browser' in sys.argv,rede_simulada=True,revisao_sintetica=True,
                 arquivos=result['arquivos_publicos_alterados'])
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if result['aplicado'] and not blocked['aplicado'] else 1

if __name__=='__main__': raise SystemExit(main())
