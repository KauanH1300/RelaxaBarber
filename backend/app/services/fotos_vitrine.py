"""Processamento de fotos e acesso privado ao Supabase Storage."""
import json
import os
import re
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, ImageOps, UnidentifiedImageError

LIMITE = 8 * 1024 * 1024
FORMATOS = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
CAMINHO = re.compile(r'[0-9a-f]{32}[.]webp')


class FotoInvalida(ValueError):
    pass


class StorageIndisponivel(Exception):
    pass


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def processar(conteudo, mime):
    formato = FORMATOS.get(mime)
    if not formato or not conteudo or len(conteudo) > LIMITE:
        raise FotoInvalida('Envie JPEG, PNG ou WebP de até 8 MB')
    try:
        with Image.open(BytesIO(conteudo), formats=[formato]) as original:
            if original.width * original.height > 32_000_000:
                raise FotoInvalida('A resolução da imagem excede o limite de 32 megapixels')
            imagem = ImageOps.exif_transpose(original)
            imagem.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            modo = 'RGBA' if 'A' in imagem.getbands() or 'transparency' in imagem.info else 'RGB'
            imagem = imagem.convert(modo)
            imagem.info.clear()
            saida = BytesIO()
            imagem.save(saida, 'WEBP', quality=80, method=4)
            return saida.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise FotoInvalida('O arquivo não é uma imagem válida do tipo informado') from exc


def origem():
    url = os.getenv('SUPABASE_URL', '').rstrip('/')
    bucket = os.getenv('SUPABASE_STORAGE_BUCKET', '')
    if not re.fullmatch(r'https://[a-z0-9]+[.]supabase[.]co', url) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', bucket):
        raise StorageIndisponivel()
    return url, bucket


def url_publica(caminho):
    if not caminho or not CAMINHO.fullmatch(caminho):
        return None
    try:
        url, bucket = origem()
    except StorageIndisponivel:
        return None
    return f'{url}/storage/v1/object/public/{bucket}/{caminho}'


def enviar(caminho, conteudo):
    if not CAMINHO.fullmatch(caminho):
        raise StorageIndisponivel()
    _operar('POST', '/' + caminho, conteudo, 'image/webp')


def apagar(caminhos):
    if not caminhos or not all(CAMINHO.fullmatch(c) for c in caminhos):
        raise StorageIndisponivel()
    _operar('DELETE', '', json.dumps({'prefixes': caminhos}).encode(), 'application/json')


def pronto():
    try:
        origem()
        return bool(os.getenv('SUPABASE_SERVICE_ROLE_KEY'))
    except StorageIndisponivel:
        return False


def _operar(metodo, sufixo, conteudo, mime):
    url, bucket = origem()
    chave = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    if not chave:
        raise StorageIndisponivel()
    headers = {'apikey': chave, 'Authorization': 'Bearer ' + chave, 'Content-Type': mime}
    if metodo == 'POST':
        headers.update({'cache-control': 'max-age=31536000', 'x-upsert': 'false'})
    req = Request(f'{url}/storage/v1/object/{bucket}{sufixo}', method=metodo, data=conteudo, headers=headers)
    try:
        with build_opener(SemRedirecionamento).open(req, timeout=8):
            pass
    except (HTTPError, OSError, ValueError):
        raise StorageIndisponivel() from None
