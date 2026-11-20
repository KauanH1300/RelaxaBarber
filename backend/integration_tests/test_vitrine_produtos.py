from io import BytesIO

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


def upload(api, path, token, formato, conteudo):
    async def montar(scope, receive, send):
        scope = dict(scope, headers=[(k,v) for k,v in scope['headers'] if k != b'content-type'] +
                     [(b'content-type', formato.encode())])
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
