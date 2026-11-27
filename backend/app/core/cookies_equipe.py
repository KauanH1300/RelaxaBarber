"""Cookies exclusivos da equipe e proteção CSRF vinculada à sessão."""
import hashlib
import hmac
import json
import os
import secrets
from fastapi import HTTPException
from app.core.security import SECRET_KEY, EXPIRA_MINUTOS

LOCAL = os.getenv("ENV", "production").lower() in {"development", "test"}
SECURE = not LOCAL
SAMESITE = os.getenv("TEAM_COOKIE_SAMESITE", "lax").lower()
if SAMESITE not in {"lax", "strict", "none"} or (SAMESITE == "none" and not SECURE):
    raise RuntimeError("Configuração insegura de cookie da equipe")
COOKIE = "rb_equipe_sessao" if LOCAL else "__Host-rb_equipe_sessao"
ANON = "rb_equipe_csrf" if LOCAL else "__Host-rb_equipe_csrf"
PENDENTE = "rb_equipe_login_pendente" if LOCAL else "__Host-rb_equipe_login_pendente"
DISPOSITIVO = "rb_equipe_dispositivo" if LOCAL else "__Host-rb_equipe_dispositivo"

def assinar(valor):
    return hmac.new(SECRET_KEY.encode(), ("equipe-csrf-v1:" + valor).encode(), hashlib.sha256).hexdigest()

def gravar(response, nome, valor, max_age=EXPIRA_MINUTOS*60):
    response.set_cookie(nome, valor, max_age=max_age, httponly=True,
                        secure=SECURE, samesite=SAMESITE, path="/")
    response.headers["Cache-Control"] = "no-store"

def limpar(response, *nomes):
    for nome in nomes or (COOKIE, ANON, PENDENTE):
        response.delete_cookie(nome, path="/", httponly=True, secure=SECURE, samesite=SAMESITE)
    response.headers["Cache-Control"] = "no-store"

def origem(request):
    permitidas = json.loads(os.getenv("BACKEND_CORS_ORIGINS", '["http://localhost:5173", "http://127.0.0.1:5173"]'))
    if request.headers.get("origin") not in permitidas or request.headers.get("origin") in (None, "*", "null"):
        raise HTTPException(403, "Origem não autorizada.")

def csrf(request):
    origem(request)
    base = request.cookies.get(COOKIE) or request.cookies.get(PENDENTE) or request.cookies.get(ANON)
    recebido = request.headers.get("x-equipe-csrf", "")
    if not base or not hmac.compare_digest(recebido, assinar(base)):
        raise HTTPException(403, "Proteção CSRF inválida. Atualize a página.")

def bootstrap(request, response):
    origem(request)
    autenticacao = request.cookies.get(COOKIE) or request.cookies.get(PENDENTE)
    base = autenticacao or request.cookies.get(ANON) or secrets.token_urlsafe(32)
    if not autenticacao:
        gravar(response, ANON, base)
    response.headers["Cache-Control"] = "no-store"
    return {"csrf": assinar(base)}
