"""Bounded public HTTPS checks; no private addresses, credentials or implicit redirects."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit, urljoin
from qc import item

def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Apenas HTTPS público sem credenciais/porta alternativa')
    addresses = {x[4][0] for x in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise ValueError('Endereço privado/local/reservado não permitido')
    return parsed, sorted(addresses)[0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host,timeout=8,context=ssl.create_default_context())
        self.address = address
    def connect(self):
        # Connect to the validated IP, preserving hostname for TLS/SNI verification.
        sock = socket.create_connection((self.address,443),self.timeout)
        self.sock = self._context.wrap_socket(sock,server_hostname=self.host)

def check(url):
    current = url
    for _ in range(6):
        parsed,address = public_url(current)
        conn = PinnedHTTPS(parsed.hostname,address)
        try:
            target = parsed.path or '/'
            if parsed.query:
                target += '?' + parsed.query
            conn.request('GET',target,headers={'User-Agent':'Virada-Propria-QC/1.0','Range':'bytes=0-1023'})
            response = conn.getresponse()
            status, location = response.status, response.getheader('Location')
            response.read(1024)
        finally:
            conn.close()
        if status in (301,302,303,307,308) and location:
            current = urljoin(current,location); continue
        return status,current
    raise ValueError('Redirecionamentos excedem o limite')

def inspect_links(urls, online=False):
    result = []
    for url in urls:
        if not online:
            result.append(item('HTTP_EXTERNO','pendente','Manual 11.25',url + ': executar --online')); continue
        try:
            status,final = check(url)
            verdict = 'aprovado' if 200 <= status < 300 else 'pendente' if status in (403,429) else 'reprovado'
            result.append(item('HTTP_EXTERNO',verdict,'Manual 11.25',f'{url}: HTTP {status}; destino {final}; correspondência do modelo exige revisão'))
        except Exception as exc:
            result.append(item('HTTP_EXTERNO','pendente','Manual 11.25',f'{url}: {exc}'))
    return result
