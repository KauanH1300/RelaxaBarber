from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session_user, oauth2
from app.core.security import verificar_senha, autenticar_senha, hash_ficticio
from app.services.limites_senha import admitir
from app.db.database import get_db
from app.models.usuario import Usuario
from app.schemas.equipe_auth import NovaSenhaEquipe, TrocarSenhaEquipe
from app.schemas.portal_cliente import ConfirmarPortal, ContatoPortal
from app.schemas.usuario import UsuarioOut
from app.services.entrega_codigo_cliente import EntregaIndisponivel
from app.services import recuperacao_equipe as recuperacao, sessoes_equipe
from app.services.persistencia import transacao_escrita

from app.core import cookies_equipe as cookies
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post('/csrf')
def csrf_bootstrap(request: Request, response: Response):
    return cookies.bootstrap(request, response)



def ip(request):
    return request.client.host if request.client else 'desconhecido'


@router.post("/login")
def login(request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    cookies.csrf(request)
    admitir(db, "login", ip(request), form.username)
    with transacao_escrita(db):
        usuario = db.scalar(select(Usuario).where(Usuario.email == form.username)
                            .with_for_update().execution_options(populate_existing=True))
        correta, atualizado = autenticar_senha(form.password, usuario.senha_hash if usuario else hash_ficticio())
        if not usuario or not correta or not usuario.ativo:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
        if atualizado:
            usuario.senha_hash = atualizado
        token = sessoes_equipe.emitir(db, usuario.id)
    cookies.gravar(response, cookies.COOKIE, token)
    return {"mensagem": "Login realizado."}


@router.get("/me", response_model=UsuarioOut)
def me(response: Response, usuario: Usuario = Depends(get_session_user)):
    response.headers["Cache-Control"] = "no-store"
    return usuario


@router.post('/logout', status_code=204)
def logout(token: str = Depends(oauth2), usuario: Usuario = Depends(get_session_user), db: Session = Depends(get_db)):
    with transacao_escrita(db):
        sessoes_equipe.revogar(db, token, usuario.id)
    response = Response(status_code=204)
    cookies.limpar(response)
    return response


@router.post('/recuperar', status_code=202)
def recuperar(dados: ContatoPortal, request: Request, tarefas: BackgroundTasks, db: Session = Depends(get_db)):
    cookies.csrf(request)
    id_ = uuid4()
    if recuperacao.admitir(db, dados.email, ip(request)):
        tarefas.add_task(recuperacao.enviar_codigo, db.get_bind(), id_, dados.email)
    return {'solicitacao_id': id_, 'mensagem': recuperacao.MENSAGEM}


@router.post('/redefinir', status_code=204)
def redefinir(dados: NovaSenhaEquipe, request: Request, db: Session = Depends(get_db)):
    cookies.csrf(request)
    if not recuperacao.redefinir(db, dados, ip(request)):
        raise HTTPException(400, recuperacao.CODIGO_INVALIDO)
    response = Response(status_code=204)
    cookies.limpar(response)
    return response


@router.post('/trocar-senha', status_code=204)
def trocar_senha(dados: TrocarSenhaEquipe, request: Request, token: str = Depends(oauth2),
                 usuario: Usuario = Depends(get_session_user), db: Session = Depends(get_db)):
    admitir(db, "troca-senha", ip(request), str(usuario.id))
    with transacao_escrita(db):
        atual = db.scalar(select(Usuario).where(Usuario.id == usuario.id)
                          .with_for_update().execution_options(populate_existing=True))
        if not atual or not sessoes_equipe.validar(db, token):
            raise HTTPException(401, 'Não autenticado')
        if not verificar_senha(dados.senha_atual, atual.senha_hash):
            raise HTTPException(400, 'Senha atual inválida')
        recuperacao.alterar_senha(db, atual, dados.senha)
    response = Response(status_code=204)
    cookies.limpar(response)
    return response

@router.post('/confirmacao-email')
def solicitar_confirmacao_email(request: Request, token: str = Depends(oauth2),
                               usuario: Usuario = Depends(get_session_user), db: Session = Depends(get_db)):
    try:
        id_ = recuperacao.solicitar_confirmacao(db, usuario.id, token, ip(request))
    except EntregaIndisponivel as exc:
        raise HTTPException(503, 'Envio indisponível. Tente novamente em instantes.') from exc
    if id_ is None:
        raise HTTPException(429, 'Aguarde antes de solicitar outro código.')
    return {'solicitacao_id': id_, 'validade_segundos': 600, 'reenvio_segundos': 60}


@router.post('/confirmacao-email/confirmar', response_model=UsuarioOut)
def confirmar_email(dados: ConfirmarPortal, request: Request, token: str = Depends(oauth2),
                    usuario: Usuario = Depends(get_session_user), db: Session = Depends(get_db)):
    if not recuperacao.redefinir(db, dados, ip(request), 'confirmacao', usuario.id, token):
        raise HTTPException(400, recuperacao.CODIGO_INVALIDO)
    return usuario
