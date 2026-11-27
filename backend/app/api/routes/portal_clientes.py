import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.ambiente import origens_permitidas, producao
from app.schemas.portal_cliente import CadastroPortal, ContatoPortal, ConfirmarPortal, RedefinirPortal, LoginPortal, PerfilPortal
from app.services import portal_cliente as portal
from app.services.entrega_codigo_cliente import EntregaIndisponivel
from app.services import troca_email_cliente
from app.schemas.portal_cliente import TrocarEmailPortal

COOKIE = 'rb_cliente_sessao'
router = APIRouter(prefix='/portal-clientes', tags=['Portal de clientes'])


def origem_confiavel(request: Request):
    if request.headers.get('origin') not in origens_permitidas():
        raise HTTPException(403, 'Origem não autorizada.')


def executar(function, *args):
    try:
        return function(*args)
    except portal.PortalFalha as exc:
        raise HTTPException(exc.status, exc.detail) from None
    except EntregaIndisponivel:
        raise HTTPException(503, 'O envio de códigos está indisponível. Tente mais tarde ou contate a recepção.') from None


def ip(request):
    # Não confiar em X-Forwarded-For enviado pelo cliente.
    return request.client.host if request.client else 'desconhecido'


def cookie_seguro():
    return producao() or os.getenv('CLIENT_PORTAL_COOKIE_SECURE', 'true').lower() != 'false'


@router.post('/cadastro', status_code=202, dependencies=[Depends(origem_confiavel)])
def cadastro(dados: CadastroPortal, request: Request, db: Session = Depends(get_db)):
    return executar(portal.solicitar, db, dados, ip(request), 'cadastro')


@router.post('/ativar', dependencies=[Depends(origem_confiavel)])
def ativar(dados: ConfirmarPortal, request: Request, db: Session = Depends(get_db)):
    return executar(portal.confirmar, db, dados, ip(request), 'cadastro')


@router.post('/recuperar', status_code=202, dependencies=[Depends(origem_confiavel)])
def recuperar(dados: ContatoPortal, request: Request, db: Session = Depends(get_db)):
    return executar(portal.solicitar, db, dados, ip(request), 'recuperacao')


@router.post('/troca-email', status_code=202, dependencies=[Depends(origem_confiavel)])
def solicitar_troca(dados: TrocarEmailPortal, request: Request, db: Session = Depends(get_db)):
    return executar(troca_email_cliente.solicitar, db, dados, ip(request), request.cookies.get(COOKIE))


@router.post('/troca-email/confirmar-atual', dependencies=[Depends(origem_confiavel)])
def confirmar_email_atual(dados: ConfirmarPortal, request: Request, db: Session = Depends(get_db)):
    return executar(troca_email_cliente.confirmar, db, dados, ip(request), 'atual', request.cookies.get(COOKIE))


@router.post('/troca-email/confirmar-novo', dependencies=[Depends(origem_confiavel)])
def confirmar_email_novo(dados: ConfirmarPortal, request: Request, db: Session = Depends(get_db)):
    return executar(troca_email_cliente.confirmar, db, dados, ip(request), 'novo', request.cookies.get(COOKIE))


@router.post('/redefinir', dependencies=[Depends(origem_confiavel)])
def redefinir(dados: RedefinirPortal, request: Request, db: Session = Depends(get_db)):
    return executar(portal.confirmar, db, dados, ip(request), 'recuperacao')


@router.post('/login', dependencies=[Depends(origem_confiavel)])
def login(dados: LoginPortal, request: Request, response: Response, db: Session = Depends(get_db)):
    token = executar(portal.login, db, dados, ip(request))
    response.set_cookie(COOKIE, token, max_age=8*3600, httponly=True, samesite='strict',
        secure=cookie_seguro(), path='/portal-clientes')
    response.headers['Cache-Control'] = 'no-store'
    return {'mensagem': 'Login realizado.'}


@router.get('/me', response_model=PerfilPortal)
def me(request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return executar(portal.autenticar, db, request.cookies.get(COOKIE))


@router.post('/logout', status_code=204, dependencies=[Depends(origem_confiavel)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    executar(portal.logout, db, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path='/portal-clientes', httponly=True, samesite='strict',
        secure=cookie_seguro())
