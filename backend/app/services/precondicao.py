import hashlib
import json

from fastapi import HTTPException


def etag(dados):
    serializado = json.dumps(dados, sort_keys=True, separators=(',', ':'), default=str)
    return '"' + hashlib.sha256(serializado.encode()).hexdigest() + '"'


def verificar(esperada, atual):
    if esperada is not None and esperada != atual:
        raise HTTPException(409, {'codigo': 'versao_desatualizada',
                                  'mensagem': 'Os dados mudaram. Compare a versão atual antes de salvar.'})
