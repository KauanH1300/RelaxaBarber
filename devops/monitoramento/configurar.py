"""Provisiona apenas a instância Zabbix do Compose acadêmico."""
import json
import os
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

URL = "http://zabbix-web:8080/api_jsonrpc.php"
NOME = "RelaxaBarber acadêmico"
LEITOR = "grafana_leitura"


class ErroZabbix(RuntimeError):
    pass


def chamar(metodo, parametros, sessao=None):
    headers = {"Content-Type": "application/json-rpc"}
    if sessao:
        headers["Authorization"] = f"Bearer {sessao}"
    payload = {"jsonrpc": "2.0", "id": 1, "method": metodo, "params": parametros}
    with urlopen(Request(URL, json.dumps(payload).encode(), headers), timeout=5) as resposta:
        dados = json.load(resposta)
    if "error" in dados:
        # Mensagens da API podem conter parâmetros privados.
        raise ErroZabbix(f"{metodo}: código {dados['error']['code']}")
    return dados["result"]


def aguardar_api():
    prazo = time.monotonic() + 150
    while time.monotonic() < prazo:
        try:
            chamar("apiinfo.version", {})
            return
        except (URLError, TimeoutError, ErroZabbix, ValueError):
            time.sleep(3)
    raise SystemExit("A API interna do Zabbix não ficou disponível em 150 segundos.")


def login(senha):
    return chamar("user.login", {"username": "Admin", "password": senha})


def provisionar(sessao):
    def api(metodo, parametros):
        return chamar(metodo, parametros, sessao)

    grupos = api("hostgroup.get", {"filter": {"name": [NOME]}, "output": ["groupid"]})
    grupo = grupos[0]["groupid"] if grupos else api("hostgroup.create", {"name": NOME})["groupids"][0]
    hosts = api("host.get", {"filter": {"host": ["relaxabarber-api"]}, "output": ["hostid"]})
    host = hosts[0]["hostid"] if hosts else api("host.create", {
        "host": "relaxabarber-api", "name": "RelaxaBarber API", "groups": [{"groupid": grupo}],
    })["hostids"][0]

    for nome in ("health", "ready"):
        cenarios = api("httptest.get", {"hostids": [host], "filter": {"name": [nome]}, "output": ["httptestid"]})
        if cenarios:
            continue
        api("httptest.create", {
            "name": nome, "hostid": host, "delay": "15s",
            "steps": [{"name": "GET", "no": 1, "timeout": "5s", "status_codes": "200",
                       "url": f"http://api:8000/{nome}"}],
        })

    grupos_leitor = api("usergroup.get", {"filter": {"name": ["Grafana acadêmico"]}, "output": ["usrgrpid"]})
    grupo_leitor = grupos_leitor[0]["usrgrpid"] if grupos_leitor else api("usergroup.create", {
        "name": "Grafana acadêmico", "hostgroup_rights": [{"id": grupo, "permission": 2}],
    })["usrgrpids"][0]

    usuarios = api("user.get", {"filter": {"username": [LEITOR]}, "output": ["userid"]})
    if not usuarios:
        papeis = api("role.get", {"filter": {"name": ["User role"], "type": 1}, "output": ["roleid"]})
        if len(papeis) != 1:
            raise ErroZabbix("Papel de usuário padrão não encontrado.")
        api("user.create", {"username": LEITOR, "passwd": os.environ["MON_ZABBIX_READER_PASSWORD"],
                            "roleid": papeis[0]["roleid"], "usrgrps": [{"usrgrpid": grupo_leitor}]})


def main():
    aguardar_api()
    senha = os.environ["MON_ZABBIX_ADMIN_PASSWORD"]
    try:
        sessao = login(senha)
    except ErroZabbix:
        inicial = os.environ.get("MON_ZABBIX_INITIAL_PASSWORD")
        if not inicial or inicial == senha:
            raise
        sessao = login(inicial)
        usuario = chamar("user.get", {"filter": {"username": ["Admin"]}, "output": ["userid"]}, sessao)
        chamar("user.update", {"userid": usuario[0]["userid"], "passwd": senha, "current_passwd": inicial}, sessao)
        sessao = login(senha)
    try:
        provisionar(sessao)
    finally:
        chamar("user.logout", [], sessao)
    print("Sondas e acesso de leitura do Grafana configurados.")


if __name__ == "__main__":
    try:
        main()
    except ErroZabbix as erro:
        raise SystemExit(f"Falha no provisionamento do Zabbix: {erro}.") from None
    except (URLError, TimeoutError, ValueError) as erro:
        raise SystemExit(f"Falha no provisionamento do Zabbix ({type(erro).__name__}).") from None
