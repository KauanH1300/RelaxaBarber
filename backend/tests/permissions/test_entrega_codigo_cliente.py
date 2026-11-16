"""Exercita SMTP_SSL real em loopback com CA temporária exclusiva dos testes."""
from email import policy
from email.parser import BytesParser
import shutil
import socketserver
import ssl
import subprocess
from threading import Thread, Event
import pytest


def test_entrega_tls_real_local(isolated_runtime, tmp_path, monkeypatch):
    from app.services.entrega_codigo_cliente import enviar
    openssl=shutil.which('openssl')
    assert openssl, 'OpenSSL necessário para validar entrega TLS real de teste'
    cert,key=tmp_path/'cert.pem',tmp_path/'key.pem'
    subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),
        '-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    recebido=Event();cartas=[]
    class Handler(socketserver.StreamRequestHandler):
        def setup(self):
            self.request=context.wrap_socket(self.request,server_side=True)
            super().setup()
        def handle(self):
            self.wfile.write(b'220 smtp-teste\r\n')
            while True:
                linha=self.rfile.readline()
                if not linha:return
                if linha.upper().startswith(b'EHLO'):self.wfile.write(b'250-smtp-teste\r\n250 SIZE 100000\r\n')
                elif linha.upper().startswith(b'DATA'):
                    self.wfile.write(b'354 enviar\r\n');partes=[]
                    while True:
                        parte=self.rfile.readline()
                        if parte==b'.\r\n' or not parte:break
                        partes.append(parte)
                    cartas.append(BytesParser(policy=policy.default).parsebytes(b''.join(partes)))
                    recebido.set();self.wfile.write(b'250 recebido\r\n')
                elif linha.upper().startswith(b'QUIT'):self.wfile.write(b'221 fim\r\n');return
                else:self.wfile.write(b'250 ok\r\n')
    with socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        for nome,valor in {'HOST':'localhost','PORT':str(server.server_address[1]),'FROM':'remetente@example.test',
                           'TLS':'ssl','CA_FILE':str(cert),'USER':'','PASSWORD':''}.items():
            monkeypatch.setenv('CLIENT_PORTAL_SMTP_'+nome,valor)
        try:
            enviar('destinatario@example.test','123456')
            assert recebido.wait(2) and len(cartas)==1
            assert str(cartas[0]['To'])=='destinatario@example.test'
            assert '123456' in cartas[0].get_body(preferencelist=('plain',)).get_content()
        finally:server.shutdown();thread.join(timeout=3)


@pytest.mark.parametrize('modo',['off','invalido'])
def test_proibe_smtp_sem_tls(isolated_runtime,monkeypatch,modo):
    from app.services.entrega_codigo_cliente import configuracao,EntregaIndisponivel
    monkeypatch.setenv('CLIENT_PORTAL_SMTP_HOST','localhost');monkeypatch.setenv('CLIENT_PORTAL_SMTP_FROM','teste@example.test')
    monkeypatch.setenv('CLIENT_PORTAL_SMTP_TLS',modo)
    with pytest.raises(EntregaIndisponivel):configuracao()
