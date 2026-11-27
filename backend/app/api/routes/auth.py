from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import exigir_perfil, get_session_user, oauth2
from app.core.security import verificar_senha, autenticar_senha, hash_ficticio
from app.services.limites_senha import admitir
from app.db.database import get_db
from app.models.usuario import PerfilEnum, Usuario
from app.schemas.equipe_auth import DispositivoConfiavelOut, NovaSenhaEquipe, TrocarSenhaEquipe, VerificarLoginAdmin
from app.schemas.portal_cliente import ConfirmarPortal, ContatoPortal
from app.schemas.usuario import UsuarioOut
from app.services.entrega_codigo_cliente import EntregaIndisponivel
from app.services import recuperacao_equipe as recuperacao, sessoes_equipe
from app.services import login_admin
from app.services.persistencia import transacao_escrita

from app.core import cookies_equipe as cookies
router = APIRouter(prefix="/auth", tags=["auth"])
admin_confirmado = exigir_perfil(PerfilEnum.ADMIN)

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
        requer_codigo = usuario.perfil == PerfilEnum.ADMIN and not login_admin.dispositivo_valido(
            db, usuario, request.cookies.get(cookies.DISPOSITIVO),
        )
        if requer_codigo:
            envio = login_admin.iniciar(db, usuario, ip(request))
        else:
            token = sessoes_equipe.emitir(db, usuario.id, admin_verificado=usuario.perfil == PerfilEnum.ADMIN)
    if requer_codigo:
        if envio is None:
            raise HTTPException(429, 'Aguarde antes de solicitar outro código.')
        pendente, *entrega = envio
        entregar_login(db, entrega)
        cookies.limpar(response, cookies.COOKIE)
        cookies.gravar(response, cookies.PENDENTE, pendente, login_admin.PRAZO_LOGIN)
        response.status_code = 202
        return {'verificacao_email': True, **prazos_login()}
    cookies.limpar(response, cookies.PENDENTE)
    cookies.gravar(response, cookies.COOKIE, token)
    return {"mensagem": "Login realizado."}


def prazos_login():
    return {'validade_segundos': login_admin.VALIDADE, 'reenvio_segundos': login_admin.REENVIO}


def entregar_login(db, entrega):
    try:
        entregue = login_admin.entregar(db, *entrega)
    except EntregaIndisponivel as exc:
        raise HTTPException(503, 'Envio indisponível. Tente novamente em instantes.') from exc
    if not entregue:
        raise HTTPException(400, 'Solicitação indisponível. Entre novamente.')


@router.post('/login/email/reenviar')
def reenviar_login(request: Request, response: Response, db: Session = Depends(get_db)):
    cookies.csrf(request)
    codigo_http, entrega = login_admin.reenviar(db, request.cookies.get(cookies.PENDENTE), ip(request))
    if entrega is None:
        mensagem = 'Aguarde antes de solicitar outro código.' if codigo_http == 429 else 'Solicitação indisponível. Entre novamente.'
        raise HTTPException(codigo_http, mensagem)
    entregar_login(db, entrega)
    response.headers['Cache-Control'] = 'no-store'
    return prazos_login()


@router.post('/login/email/verificar')
def verificar_login(dados: VerificarLoginAdmin, request: Request, response: Response, db: Session = Depends(get_db)):
    cookies.csrf(request)
    codigo_http, token, dispositivo = login_admin.verificar(
        db, request.cookies.get(cookies.PENDENTE), dados.codigo, dados.confiar, ip(request),
    )
    if token is None:
        mensagem = 'Aguarde antes de tentar novamente.' if codigo_http == 429 else recuperacao.CODIGO_INVALIDO
        raise HTTPException(codigo_http, mensagem)
    cookies.limpar(response, cookies.PENDENTE)
    cookies.gravar(response, cookies.COOKIE, token)
    if dispositivo:
        cookies.gravar(response, cookies.DISPOSITIVO, dispositivo, login_admin.PRAZO_DISPOSITIVO)
    return {'mensagem': 'Login realizado.'}


@router.get('/dispositivos-confiaveis', response_model=list[DispositivoConfiavelOut])
def dispositivos(request: Request, response: Response, usuario: Usuario = Depends(admin_confirmado),
                 db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return login_admin.listar_dispositivos(db, usuario, request.cookies.get(cookies.DISPOSITIVO))


@router.delete('/dispositivos-confiaveis', status_code=204)
@router.delete('/dispositivos-confiaveis/{dispositivo_id}', status_code=204)
def revogar_dispositivos(request: Request, token: str = Depends(oauth2),
                         usuario: Usuario = Depends(admin_confirmado), db: Session = Depends(get_db),
                         dispositivo_id: UUID | None = None):
    limpar_cookie = login_admin.revogar_dispositivos(
        db, usuario.id, token, request.cookies.get(cookies.DISPOSITIVO), dispositivo_id,
    )
    if limpar_cookie is None:
        raise HTTPException(401, 'Sessão indisponível. Entre novamente.')
    response = Response(status_code=204, headers={'Cache-Control': 'no-store'})
    if limpar_cookie:
        cookies.limpar(response, cookies.DISPOSITIVO)
    return response


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
    cookies.limpar(response, cookies.DISPOSITIVO)
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
    cookies.limpar(response, cookies.DISPOSITIVO)
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
