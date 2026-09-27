"""Explicit transactional apply. No staging, commit, push, merge or deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import importar
import pipeline
import publicacao
from auditar import audit

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],encoding='utf-8').strip()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def snapshot(root):
    return {name:digest((root/name).read_bytes()) for name in publicacao.inventory(root)}

def target(root,name):
    importar.safe_path(name)
    if not publicacao.public(name):
        raise ValueError('Destino não público: '+name)
    current=root
    for part in name.split('/'):
        if current.exists() and current.is_dir():
            if any(p.name.casefold()==part.casefold() and p.name!=part for p in current.iterdir()):
                raise ValueError('Colisão de capitalização: '+name)
        current=current/part
        if current.is_symlink() or (hasattr(current,'is_junction') and current.is_junction()):
            raise ValueError('Destino com link/reparse point: '+name)
        if not current.resolve().is_relative_to(root):
            raise ValueError('Destino fora do repositório: '+name)
    return current

def atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.vp-write-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as file:
            file.write(data); file.flush(); os.fsync(file.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def diff_report(root,names):
    # git diff omits untracked files; supplement with no-index diffs without staging.
    stat=git(root,'diff','--stat')
    patch=git(root,'diff','--binary')
    tracked=set(git(root,'ls-files').splitlines())
    for name in names:
        if name not in tracked and (root/name).is_file():
            for flag in ('--stat','--binary'):
                result=subprocess.run(['git','-C',str(root),'diff','--no-index',flag,'--',os.devnull,name],
                                      capture_output=True,encoding='utf-8')
                if result.returncode not in (0,1):
                    raise ValueError(result.stderr)
                if flag=='--stat': stat+='\n'+result.stdout
                else: patch+='\n'+result.stdout
    return stat.strip(),patch

def apply(zip_path, approved_run, evidence_path, root=importar.ROOT):
    root=root.resolve(); zip_path=zip_path.resolve(); approved_run=approved_run.resolve()
    run=Path(tempfile.mkdtemp(prefix='vp-apply-'))
    report=dict(modo='apply',aplicado=False,publicacao_liberada=False,diretorio=str(run),
                erros=[],arquivos_publicos_alterados=[],rollback=False)
    (run/'run.json').write_text(json.dumps({'modo':'apply','repo':str(root)}),encoding='utf-8')
    originals={}; created_dirs=[]; written=[]; lock=None; locked=False
    before={}; expected={}
    try:
        state=importar.git_snapshot(root)
        report['git_antes']=state
        if state['branch']!='automacao-publicacao-v2':
            raise ValueError('Apply exige branch automacao-publicacao-v2')
        if state['status']:
            raise ValueError('Apply exige git status limpo; preserve e resolva alterações antes de aplicar')
        if state['origin'].removesuffix('.git') not in ('https://github.com/Virada-Propria/virada-propria.github.io',
                                                       'git@github.com:Virada-Propria/virada-propria.github.io'):
            raise ValueError('Origin inesperado')
        errors=publicacao.configuration_errors(root,required=True)
        if errors:
            raise ValueError('; '.join(errors))
        git_dir=Path(git(root,'rev-parse','--absolute-git-dir'))
        lock=git_dir/'vp-apply.lock'
        with lock.open('x',encoding='utf-8') as f:
            f.write(str(run))
        locked=True
        before=snapshot(root)
        approved=importar.read_json((approved_run/'relatorio.json').read_text(encoding='utf-8'))
        report['dry_run_previo']=dict(diretorio=str(approved_run),fingerprint=approved.get('fingerprint'),
            bloqueios=[x for rows in approved.get('qcs',{}).values() for x in rows if x.get('status')!='aprovado'],
            erros_entrada=approved.get('erros_entrada',[]))
        if approved.get('modo')!='simulacao' or approved.get('qc_concluido') is not True:
            raise ValueError('Dry-run prévio não aprovado ou incompleto')
        if approved.get('zip_sha256')!=digest(zip_path.read_bytes()):
            raise ValueError('ZIP diferente do dry-run aprovado')
        evidence=importar.read_json(evidence_path.read_text(encoding='utf-8'))
        # Replay never trusts a mutable report's booleans or supplied destination list.
        fresh=pipeline.process(zip_path,root,True,evidence_path,True,True)
        report['dry_run_revalidado']=fresh
        if not fresh.get('qc_concluido') or fresh.get('fingerprint')!=approved.get('fingerprint'):
            raise ValueError('Dry-run revalidado bloqueado, revisão inválida ou origem alterada')
        if fresh['plano']!=approved.get('plano'):
            raise ValueError('Plano aprovado não corresponde à reconstrução')
        fresh_run=Path(fresh['diretorio'])
        expected=snapshot(fresh_run/'site')
        if snapshot(approved_run/'site')!=expected:
            raise ValueError('Artefato aprovado foi alterado após a revisão')
        requests=importar.read_json((fresh_run/'revisao.json').read_text(encoding='utf-8'))
        manifest=importar.read_json(importar.inspect_zip(zip_path)['manifest.json'].decode('utf-8-sig'))
        plan=fresh['plano']; names=[r['arquivo'] for r in plan]
        planned=dict(before)
        for row in plan:
            name=row['arquivo']; target(root,name)
            if row['sha256']!=expected.get(name):
                raise ValueError('Hash do destino divergente: '+name)
            planned[name]=row['sha256']
        if planned!=expected:
            raise ValueError('Inventário público contém arquivos fora do plano aprovado (inclusive ignorados pelo Git)')
        # Inspect the complete candidate (including index/sitemap) before any write.
        pre=audit(fresh_run,manifest,fresh['paginas_montadas'],requests,evidence)
        report['qc_pre_gravacao']=pre
        if not pre['qc_concluido']:
            raise ValueError('QC completo do candidato bloqueado antes da gravação')
        if importar.git_snapshot(root)!=state or snapshot(root)!=before:
            raise ValueError('Repositório alterado durante a validação')
        backup=run/'backup'; backup.mkdir()
        for name in names:
            path=target(root,name)
            originals[name]=path.read_bytes() if path.exists() else None
            if originals[name] is not None:
                copy=backup/name; copy.parent.mkdir(parents=True,exist_ok=True); copy.write_bytes(originals[name])
            parent=path.parent
            while parent!=root and not parent.exists():
                if parent not in created_dirs: created_dirs.append(parent)
                parent=parent.parent
        (run/'journal.json').write_text(json.dumps({'root':str(root),'head':state['head'],
            'originais':{n:digest(b) if b is not None else None for n,b in originals.items()},
            'destinos':names},indent=2),encoding='utf-8')
        for name in names:
            data=(fresh_run/'site'/name).read_bytes()
            if digest(data)!=expected[name]:
                raise ValueError('Candidato alterado durante apply: '+name)
            written.append(name)
            atomic_write(target(root,name),data)
        # Build preview strictly from bytes read back from the working tree, not the dry-run.
        actual=snapshot(root)
        site=run/'site'; site.mkdir()
        for name in actual:
            dest=site/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes((root/name).read_bytes())
        post=audit(run,manifest,fresh['paginas_montadas'],requests,evidence)
        report['qc_pos_gravacao']=post
        report['hashes_publicacao']=actual
        if actual!=expected or snapshot(site)!=expected or snapshot(root)!=expected:
            raise ValueError('Bytes publicados divergem do artefato aprovado')
        if not post['qc_concluido']:
            raise ValueError('QC após gravação reprovado ou pendente')
        now=importar.git_snapshot(root)
        if any(now[k]!=state[k] for k in ('branch','head','origin')):
            raise ValueError('Identidade Git mudou durante apply')
        if publicacao.configuration_errors(root,required=True):
            raise ValueError('Configuração de isolamento alterada durante apply')
        report['diff_stat'],patch=diff_report(root,names)
        (run/'git-diff.patch').write_text(patch,encoding='utf-8')
        (run/'git-diff-stat.txt').write_text(report['diff_stat'],encoding='utf-8')
        report.update(aplicado=True,arquivos_publicos_alterados=names,git_depois=now,
                      preview=str(site),fingerprint=fresh['fingerprint'])
    except Exception as exc:
        report['erros'].append(str(exc))
        if written:
            rollback_errors=[]
            for name in reversed(written):
                try:
                    path=target(root,name)
                    if originals[name] is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path,originals[name])
                except Exception as error:
                    rollback_errors.append(name+': '+str(error))
            for directory in sorted(created_dirs,key=lambda p:len(p.parts),reverse=True):
                if directory.exists() and not any(directory.iterdir()): directory.rmdir()
            report['rollback']=not rollback_errors
            report['erros'].extend(rollback_errors)
            if rollback_errors:
                report['recuperacao_manual']=str(run/'journal.json')
        try:
            report['git_depois']=importar.git_snapshot(root)
        except Exception:
            pass
    finally:
        if locked and lock is not None and not report.get('recuperacao_manual'):
            lock.unlink(missing_ok=True)
        (run/'relatorio.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip',type=Path)
    parser.add_argument('--dry-run',type=Path,required=True)
    parser.add_argument('--revisoes',type=Path,required=True)
    args=parser.parse_args()
    result=apply(args.zip,args.dry_run,args.revisoes)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['aplicado'] else 1

if __name__=='__main__':
    raise SystemExit(main())
