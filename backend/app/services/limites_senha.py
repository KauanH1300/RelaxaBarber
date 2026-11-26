"""Admissão persistida, confirmada antes da verificação da senha."""
from fastapi import HTTPException
from app.services.portal_cliente import _bucket
from app.services.persistencia import transacao_escrita


def admitir(db, finalidade, ip, conta):
    with transacao_escrita(db):
        # Ordem fixa entre buckets. Contar inclusive quando o outro já esgotou.
        por_ip = _bucket(db, f"equipe:{finalidade}:ip:{ip}", 30, 900)
        por_conta = _bucket(db, f"equipe:{finalidade}:conta:{conta.strip().casefold()}", 5, 900)
    if not por_ip or not por_conta:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.",
                            headers={"Retry-After": "900"})
