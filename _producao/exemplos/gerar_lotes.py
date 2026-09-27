"""Generate valid/invalid technical examples; never real profession content."""
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'tests/fixtures'))
sys.path.insert(0,str(HERE.parent/'automacao'))
from lote import manifest, write_zip
from importar import simulate

def main():
    write_zip(HERE/'lote-valido.zip')
    write_zip(HERE/'lote-invalido.zip',mutate=lambda files: files.update({'../escape.txt':b'blocked'}))
    (HERE/'manifest-valido.json').write_text(json.dumps(manifest(),ensure_ascii=False,indent=2),encoding='utf-8')
    for kind in ('valido','invalido'):
        report=simulate(HERE/f'lote-{kind}.zip',browser='--browser' in sys.argv)
        (HERE/f'dry-run-{kind}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:report.get(k) for k in ('lote','pacote_aceito','diretorio','bloqueios','pendencias','erros_entrada')},ensure_ascii=False))

if __name__=='__main__':
    main()
