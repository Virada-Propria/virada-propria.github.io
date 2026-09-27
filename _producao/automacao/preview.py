"""Loopback-only preview of one isolated site. Never serve the repository/run root."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import argparse

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if '\\' in path or any(part.startswith(('.', '_')) for part in path.split('/') if part):
            self.send_error(404); return
        target = Path(self.directory) / path.lstrip('/')
        if not target.resolve().is_relative_to(Path(self.directory).resolve()):
            self.send_error(404); return
        super().do_GET()

    def do_HEAD(self):
        self.do_GET()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'")
        super().end_headers()

    def log_message(self, *args):
        pass

def server(site, port=0):
    site = site.resolve()
    if site.name != 'site' or not (site.parent / 'run.json').is_file():
        raise ValueError('Preview exige site isolado com run.json adjacente')
    return ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(site)))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with server(args.run / 'site', args.port) as http:
        print(f'Preview: http://127.0.0.1:{http.server_port}/', flush=True)
        http.serve_forever()

if __name__ == '__main__':
    main()
