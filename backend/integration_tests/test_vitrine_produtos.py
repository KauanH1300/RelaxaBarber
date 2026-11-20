from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from PIL import Image
from sqlalchemy import text
from test_complementos_agenda import criar_recepcao, requisitar
from test_concorrencia import data
from test_contexto_filiais import duas_filiais
from test_financeiro_http import api
from test_seguranca_horarios import chamar


def criar(api, s, nome, filial=None, **opcoes):
    dados = dict(nome=nome, unidade='un', venda=True, consumo=False, custo='10',
        preco_venda='25', comissao_padrao=10, estoque_minimo='2', visivel_vitrine=True,
        descricao_vitrine='Descrição pública') | opcoes
    codigo, resposta = requisitar(api, '/estoque/produtos', s['admin'], method='POST',
        filial_id=filial or s['filial'], dados=dados)
    assert codigo == 201, resposta
    return resposta


def test_catalogo_filtra_isola_e_pagina(api, pg, duas_filiais):
    s = duas_filiais
    with pg.begin() as conn:
        conn.execute(text("UPDATE filiais SET agenda_publica=true,endereco='Endereço fictício' WHERE id IN (:filial,:second)"),s)
    produto = criar(api, s, 'A ativo')
    criar(api, s, 'B ativo')
    criar(api, s, 'Inativo', ativo=False)
    criar(api, s, 'Oculto', visivel_vitrine=False)
    criar(api, s, 'Interno', venda=False, consumo=True, preco_venda=None, visivel_vitrine=False)
    criar(api, s, 'Dupla finalidade', consumo=True, visivel_vitrine=False)
    criar(api, s, 'Outra filial', s['second'])
    with pg.begin() as conn:
        conn.execute(text('UPDATE produtos_estoque SET saldo=3 WHERE id=:id'), {'id':produto['id']})

    rota = f"/publico/filiais/{s['filial']}/produtos"
    status, cab, _ = chamar(api, rota, resposta_bruta=True)
    assert status == 200 and b'max-age=30' in cab[b'cache-control']
    _, primeira = chamar(api, rota+'?limite=1')
    assert primeira['proxima_pagina'] == 2
    item, = primeira['produtos']
    assert item == {'nome':'A ativo','descricao':'Descrição pública','foto_url':None,'preco':'25.00','disponivel':True}
    _, segunda = chamar(api, rota+'?limite=1&pagina=2')
    assert segunda['proxima_pagina'] is None
    assert segunda['produtos'][0]['nome'] == 'B ativo' and not segunda['produtos'][0]['disponivel']
    assert chamar(api, rota+'?limite=41')[0] == 422

    with pg.begin() as conn:
        conn.execute(text('UPDATE filiais SET agenda_publica=false WHERE id=:id'), {'id':s['filial']})
    assert chamar(api, rota)[0] == 404
    with pg.connect() as conn:
        for papel in ('anon','authenticated'):
            for tabela in ('public.produtos_estoque','public.vitrine_fotos_pendentes'):
                assert not conn.scalar(text("SELECT has_table_privilege(:papel,:tabela,'SELECT,INSERT,UPDATE,DELETE')"),
                                       {'papel':papel,'tabela':tabela})


def upload(api, path, token, formato, conteudo, chave=None, esperada=None):
    async def montar(scope, receive, send):
        scope = dict(scope, headers=[(k,v) for k,v in scope['headers'] if k != b'content-type'] +
                     [(b'content-type', formato.encode())])
        if chave:
            scope['headers'].append((b'idempotency-key', str(chave).encode()))
        if esperada is not None:
            scope['headers'].append((b'x-foto-esperada', esperada.encode()))
        async def bytes_():
            mensagem = await receive()
            return mensagem | {'body':conteudo}
        await api(scope, bytes_, send)
    return chamar(montar,path,method='PUT',token=token)


def jpeg():
    imagem = Image.effect_noise((1600,900), 32).convert('RGB')
    exif = Image.Exif()
    exif[271] = 'Marca fictícia'
    exif[274] = 6
    saida = BytesIO()
    imagem.save(saida, 'JPEG', exif=exif, quality=90)
    return saida.getvalue()


def test_upload_permissao_processamento_troca_e_exclusao(api, pg, duas_filiais, monkeypatch):
    from app.core.security import criar_token
    from app.services import fotos_vitrine as fotos

    s = duas_filiais
    recepcao = criar_recepcao(pg, s)
    produto = criar(api, s, 'Produto de teste')
    caminho = '/estoque/produtos/' + produto['id']
    rota = caminho + '/foto?filial_id=' + str(s['filial'])
    admin = criar_token(s['admin'])
    entrada = jpeg()
    arquivos, exclusoes = {}, []
    monkeypatch.setenv('SUPABASE_URL','https://fixture.supabase.co')
    monkeypatch.setenv('SUPABASE_STORAGE_BUCKET','produtos-vitrine')
    monkeypatch.setattr(fotos, 'enviar', lambda arquivo, bytes_: arquivos.update({arquivo: bytes_}))
    def apagar(nomes):
        for n in nomes:
            exclusoes.append(n)
            arquivos.pop(n, None)
    monkeypatch.setattr(fotos, 'apagar', apagar)
    assert upload(api,rota,None,'image/jpeg',entrada)[0] == 401
    assert upload(api,rota,criar_token(recepcao),'image/jpeg',entrada)[0] == 403
    assert upload(api,rota,admin,'image/gif',b'invalido')[0] == 415
    assert upload(api,rota,admin,'image/jpeg',b'x'*(fotos.LIMITE+1))[0] == 413
    assert upload(api,rota,admin,'image/png',entrada)[0] == 422
    assert upload(api,rota.replace(str(s['filial']),str(s['second'])),admin,'image/jpeg',entrada)[0] == 404
    dados = dict(nome=produto['nome'],unidade='un',venda=True,consumo=False,custo='10',
        preco_venda='25',estoque_minimo='0',visivel_vitrine=False,descricao_vitrine='Nova descrição')
    assert requisitar(api,caminho,recepcao,method='PUT',filial_id=s['filial'],dados=dados)[0] == 403
    assert requisitar(api,caminho,s['admin'],method='PUT',filial_id=s['filial'],dados=dados)[0] == 200

    status, r = upload(api,rota,admin,'image/jpeg',entrada)
    assert status == 200, r
    anterior, = arquivos.keys()
    assert r['foto_url'].endswith('/'+anterior)
    with Image.open(BytesIO(arquivos[anterior])) as foto:
        assert foto.format == 'WEBP' and foto.size == (675,1200)
        assert not foto.getexif() and 'xmp' not in foto.info and 'icc_profile' not in foto.info
    status, r = upload(api,rota,admin,'image/jpeg',entrada)
    assert status == 200, r
    atual, = arquivos.keys()
    assert anterior != atual and exclusoes == [anterior]
    assert chamar(api,rota,method='DELETE',token=admin)[0] == 204
    assert exclusoes == [anterior,atual] and not arquivos
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT foto_vitrine FROM produtos_estoque WHERE id=:id'),{'id':produto['id']}) is None
        assert conn.scalar(text('SELECT count(*) FROM vitrine_fotos_pendentes')) == 0


def test_upload_recibo_replay_e_foto_concorrente(api, pg, duas_filiais, monkeypatch):
    from app.core.security import criar_token
    from app.services import fotos_vitrine as fotos

    s = duas_filiais
    recepcao = criar_recepcao(pg, s)
    item = criar(api, s, 'Foto com recibo')
    base = f"/estoque/produtos/{item['id']}/foto"
    query = f"?filial_id={s['filial']}"
    token = criar_token(s['admin'])
    chave = uuid4()
    envios = []
    monkeypatch.setenv('SUPABASE_URL', 'https://fixture.supabase.co')
    monkeypatch.setenv('SUPABASE_STORAGE_BUCKET', 'produtos-vitrine')
    monkeypatch.setattr(fotos, 'enviar', lambda caminho, _: envios.append(caminho))
    monkeypatch.setattr(fotos, 'apagar', lambda _: None)
    entrada = jpeg()

    def consulta(token=token, filial=s['filial']):
        async def header(scope, receive, send):
            await api(dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave).encode())]), receive, send)
        return chamar(header, base + f'/operacao?filial_id={filial}', token=token)

    assert consulta()[1]['confirmado'] is False
    def publicar(_):
        return upload(api, base + query, token, 'image/jpeg', entrada, chave, '-')
    with ThreadPoolExecutor(max_workers=2) as pool:
        (status, primeiro), outra_resposta = pool.map(publicar, range(2))
    assert status == 200 and primeiro['confirmado']
    assert outra_resposta == (200, primeiro)
    assert consulta() == (200, primeiro)
    assert upload(api, base + query, token, 'image/jpeg', entrada, chave, '-') == (200, primeiro)
    assert upload(api, base + query, token, 'image/jpeg', entrada + b'x', chave, '-')[0] == 409
    assert upload(api, base + query, token, 'image/jpeg', entrada, uuid4(), '-')[0] == 409
    assert len(envios) == 1
    assert consulta(criar_token(recepcao))[0] == 403
    assert consulta(filial=s['second'])[0] == 404
    assert upload(api, base + query, token, 'image/jpeg', entrada, uuid4(), primeiro['foto_url'])[0] == 200
    assert consulta()[1] == {'confirmado': True, 'vigente': False, 'foto_url': fotos.url_publica(envios[-1])}
    assert upload(api, base + query, token, 'image/jpeg', entrada, chave, '-')[1]['vigente'] is False
    assert len(envios) == 2
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM vitrine_uploads_confirmados')) == 2
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.vitrine_uploads_confirmados'::regclass"))
        for papel in ('anon', 'authenticated'):
            assert not conn.scalar(text("SELECT has_table_privilege(:p,'public.vitrine_uploads_confirmados','SELECT,INSERT,UPDATE,DELETE')"), {'p': papel})
        assert not conn.scalar(text("SELECT has_table_privilege('relaxabarber_dev_app','public.vitrine_uploads_confirmados','UPDATE,DELETE')"))


def test_primeira_escrita_desatualizada_e_revisao(api, pg, duas_filiais):
    from app.core.security import criar_token
    from app.models import PerfilEnum, Usuario
    from sqlalchemy.orm import Session

    s = duas_filiais
    with Session(pg, expire_on_commit=False) as db:
        segundo = Usuario(nome='Outro administrador', perfil=PerfilEnum.ADMIN, ativo=True,
                          email='operador-versoes@example.test', senha_hash='fixture')
        db.add(segundo)
        db.commit()
        token_b = criar_token(segundo.id)
    token_a = criar_token(s['admin'])
    item = criar(api, s, 'Insumo', venda=False, consumo=True, preco_venda=None, visivel_vitrine=False)
    produto = dict(nome='Insumo', unidade='un', venda=False, consumo=True, custo='10', estoque_minimo='2')
    query = f"?filial_id={s['filial']}"

    def etag(path, token):
        status, headers, _ = chamar(api, path, token=token, resposta_bruta=True)
        assert status == 200
        return headers[b'etag']

    def alterar(path, token, dados, versao):
        async def header(scope, receive, send):
            await api(dict(scope, headers=[*scope['headers'], (b'if-match', versao)]), receive, send)
        return chamar(header, path, method='PUT', token=token, dados=dados)

    casos = [
        ('/estoque/produtos/' + item['id'], produto | {'nome': 'Operador A'}, produto | {'nome': 'Operador B'}, 'nome', 'Operador A'),
        (f"/comissoes/profissionais/{s['user']}", {'servico_id': str(s['service']), 'percentual': 20},
          {'servico_id': str(s['service']), 'percentual': 40}, 'percentual', '20.00'),
        (f"/servicos/{s['service']}/insumos", [{'produto_id': item['id'], 'quantidade': '1'}],
          [{'produto_id': item['id'], 'quantidade': '2'}], 'quantidade', '1.000'),
    ]
    for rota, entrada_a, entrada_b, campo, esperado in casos:
        path = rota + query
        antiga = etag(path, token_b)
        assert alterar(path, token_a, entrada_a, antiga)[0] == 200
        erro, resposta = alterar(path, token_b, entrada_b, antiga)
        assert erro == 409 and resposta['detail']['codigo'] == 'versao_desatualizada'
        atual = chamar(api, path, token=token_b)[1]
        assert (atual[0] if isinstance(atual, list) else atual)[campo] == esperado
        assert alterar(path, token_b, entrada_b, etag(path, token_b))[0] == 200
