"""Run real browser geometry/image checks and capture evidence in the isolated run."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from preview import server

def verify(run, routes):
    if not routes:
        return {'error':'Nenhuma página montada para inspecionar'}
    runtime = Path(os.environ.get('USERPROFILE',''))/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    node = runtime/'bin/node.exe'
    if not node.is_file():
        node = shutil.which('node')
    if not node:
        return {'error':'Node não disponível para QC no navegador'}
    request = run/'browser-input.json'
    request.write_text(json.dumps(routes),encoding='utf-8')
    with server(run/'site') as http:
        worker = threading.Thread(target=http.serve_forever,daemon=True); worker.start()
        try:
            env = dict(os.environ, NODE_PATH=str(runtime/'node_modules'))
            result = subprocess.run([str(node),str(Path(__file__).with_name('browser_qc.cjs')),
                        str(run),str(http.server_port)],env=env,capture_output=True,text=True,encoding='utf-8',timeout=180)
            output = run/'browser.json'
            if result.returncode or not output.is_file():
                return {'error':result.stderr[-1500:] or 'Falha no navegador'}
            return json.loads(output.read_text(encoding='utf-8'))
        except Exception as exc:
            return {'error':str(exc)}
        finally:
            http.shutdown(); worker.join(timeout=5)
