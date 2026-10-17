"""Sanitização central antes de qualquer handler de logging.

Não registrar configurações completas, mensagens de drivers ou secrets. O filtro
é defesa adicional; entradas privadas continuam fora de argumentos e imagens.
"""
import logging
import os
import re
import sys
import threading
import traceback
from urllib.parse import quote, quote_plus, unquote, urlsplit


_URL = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|mssql|oracle|sqlite)"
    r"(?:\+[\w]+)?://[^\s\"'<>]+", re.IGNORECASE,
)
_FIELD = re.compile(
    r"([\"']?\b(?:password|passwd|senha|pgpassword|database_url|secret_key)"
    r"[\"']?\s*[:=]\s*)(?:'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"|[^\s;,]+)",
    re.IGNORECASE,
)


def sanitize(value: str) -> str:
    secrets = {os.environ.get(key, "") for key in ("PGPASSWORD", "SECRET_KEY")}
    raw_url = os.environ.get("DATABASE_URL", "")
    if raw_url:
        secrets.add(raw_url)
        try:
            password = urlsplit(raw_url).password
            if password:
                secrets.update((password, unquote(password)))
        except ValueError:
            pass
    variants = {
        variant for secret in secrets - {""}
        for variant in (secret, quote(secret, safe=""), quote_plus(secret))
    }
    # Remover primeiro os valores integrais: uma regex de URL pode parar num
    # espaço e deixar parte de uma senha mal codificada. Variantes longas vêm
    # antes de prefixos para não deixar sufixos de percent-encoding.
    for variant in sorted(variants, key=len, reverse=True):
        value = value.replace(variant, "[OMITIDO]")
    value = _URL.sub("[CONEXAO OMITIDA]", value)
    return _FIELD.sub(lambda m: m.group(1) + "[OMITIDO]", value)


def _exception_locations(exc_info) -> str:
    kind, _, tb = exc_info
    locations = [f"{f.filename}:{f.lineno} ({f.name})" for f in traceback.extract_tb(tb)]
    # Nunca formatar a mensagem da exceção, seu repr, código-fonte ou variáveis.
    return sanitize("\n".join(["Exceção: " + kind.__name__, *locations]))


def install_safe_logging() -> None:
    previous = logging.getLogRecordFactory()
    if not getattr(previous, "_relaxabarber_safe", False):
        def factory(*args, **kwargs):
            record = previous(*args, **kwargs)
            try:
                record.msg = sanitize(record.getMessage())
            except Exception:
                record.msg = "Mensagem de log omitida por segurança"
            record.args = ()
            if record.exc_info:
                record.exc_text = _exception_locations(record.exc_info)
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = sanitize(record.exc_text)
            record.stack_info = None
            return record

        factory._relaxabarber_safe = True
        logging.setLogRecordFactory(factory)

    # Cobre falhas de import/configuração anteriores aos handlers HTTP, inclusive
    # quando a aplicação é iniciada pela CLI do Uvicorn ou Alembic.
    def exception_hook(kind, value, tb):
        sys.stderr.write(_exception_locations((kind, value, tb)) + "\n")

    sys.excepthook = exception_hook
    threading.excepthook = lambda args: exception_hook(
        args.exc_type, args.exc_value, args.exc_traceback,
    )
    sys.unraisablehook = lambda args: exception_hook(
        args.exc_type, args.exc_value, args.exc_traceback,
    )
    logging.captureWarnings(True)
