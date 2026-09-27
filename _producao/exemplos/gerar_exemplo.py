"""Empacota conteúdo já existente somente para demonstração; não aprova a pauta."""
import json
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / 'automacao'))
from importar import simulate

def main():
    target = HERE / 'lote-exemplo.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(HERE / 'manifest.json', 'manifest.json')
        archive.write(ROOT / 'jardineiro/como-comecar/index.html', 'materias/como-comecar.html')
        archive.writestr('dados/pauta.txt', 'DEMONSTRAÇÃO. Reutiliza uma página existente. Pauta completa e aprovação real pendentes.')
        archive.writestr('dados/pesquisa.txt', 'DEMONSTRAÇÃO. Pesquisa aprovada ainda não fornecida; não constitui fonte editorial.')
    report = simulate(target)
    (HERE / 'relatorio-exemplo.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('pacote_aceito', 'publicacao_liberada', 'erros_entrada', 'bloqueios', 'pendencias')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
