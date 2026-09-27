"""Inspect real bytes. Preserve paths and files; never invent/repaint products."""
import hashlib
from io import BytesIO
from pathlib import Path
import warnings
from PIL import Image
from html_tools import serialize

def inspect(data, name):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as image:
            width, height, fmt = image.width, image.height, image.format
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            pixels = hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
    extension = Path(name).suffix.lower()
    expected = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP', '.gif': 'GIF'}
    if expected.get(extension) != fmt:
        raise ValueError('Formato real da imagem não corresponde à extensão (SVG exige revisão/conversão externa)')
    return dict(width=width, height=height, formato=fmt, bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), pixels_sha256=pixels)

def apply(body, declarations, assets):
    by_path = {i['caminho']: i for i in declarations}
    used = set()
    for node in body.xpath('.//img'):
        path = node.get('src')
        if path not in by_path:
            raise ValueError(f'Imagem no HTML não declarada: {path}')
        image, info = by_path[path], assets.get(path)
        used.add(path)
        node.set('alt', image['alt'])
        if info:
            node.set('width', str(info['width'])); node.set('height', str(info['height']))
        node.set('loading', 'eager' if image.get('destaque') else 'lazy')
        if image['tipo'] == 'representacao-editorial':
            parent = node.getparent()
            if parent.tag != 'figure' or 'Representação editorial' not in parent.text_content():
                raise ValueError(f'Representação editorial sem legenda explícita: {path}')
    unused = set(by_path) - used
    if unused:
        raise ValueError(f'Imagens declaradas mas não inseridas no corpo: {sorted(unused)}')
    return used
