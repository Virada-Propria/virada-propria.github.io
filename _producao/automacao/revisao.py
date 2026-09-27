"""Review requirements are read from the canonical manual, never a second manual."""
import hashlib
import json
import re
import zipfile
from xml.etree import ElementTree as ET

def checklist(manual):
    with zipfile.ZipFile(manual) as archive:
        tree = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    chapter, result = 0, []
    for p in tree.findall('.//w:p', ns):
        text = ''.join(n.text or '' for n in p.findall('.//w:t', ns))
        match = re.match(r'CAPÍTULO (\d+)', text)
        if match:
            chapter = int(match[1])
        if text.startswith('[ ]'):
            group = 'editorial' if chapter in (2,3,4,5,8) else 'comercial' if chapter in (6,7,9) else 'tecnico'
            key = hashlib.sha256(f'{chapter}:{text}'.encode()).hexdigest()[:16]
            result.append(dict(id=key, grupo=group, referencia=f'Manual 1.1, capítulo {chapter}', criterio=text[3:].strip()))
    return result

def template(manual, fingerprint, pages):
    criteria = checklist(manual)
    return dict(fingerprint=fingerprint, revisor='', avaliacoes=[dict(pagina=route, **rule,
                status='pendente', evidencia='') for route in pages for rule in criteria])

def evaluate(requests, evidence):
    if evidence is None:
        return [dict(codigo='REVISAO_CANONICA', status='pendente', referencia='Manual 12.8–12.9',
                     detalhe=f'{len(requests["avaliacoes"])} verificações aguardam evidência na fila integrada')]
    if evidence.get('fingerprint') != requests['fingerprint'] or not evidence.get('revisor', '').strip():
        raise ValueError('Revisão sem revisor ou referente a outro conteúdo/fingerprint')
    expected = {(x['pagina'],x['id']):x for x in requests['avaliacoes']}
    provided = {}
    for row in evidence.get('avaliacoes', []):
        key = (row.get('pagina'), row.get('id'))
        if key not in expected or key in provided:
            raise ValueError('Revisão contém item desconhecido ou duplicado')
        provided[key] = row
    results = []
    for key, criterion in expected.items():
        row = provided.get(key, {})
        status = row.get('status', 'pendente')
        if status not in ('aprovado','reprovado','pendente','nao-aplicavel'):
            raise ValueError('Status de revisão inválido')
        if status != 'pendente' and not row.get('evidencia','').strip():
            raise ValueError('Decisão de revisão sem evidência/justificativa')
        results.append(dict(codigo='REVISAO_' + criterion['id'], status=status, grupo=criterion['grupo'],
                            referencia=criterion['referencia'], detalhe=criterion['pagina'] + ': ' + row.get('evidencia', criterion['criterio'])))
    return results
