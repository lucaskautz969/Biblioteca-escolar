# Backup complementar: nao modifica o banco original nem o codigo principal.
import argparse
import base64
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

def porta_ocupada():
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1',8080)) == 0

def log(base, texto):
    pasta=base/'backups';pasta.mkdir(exist_ok=True)
    with (pasta/'registro_backup.log').open('a',encoding='utf-8') as f:
        f.write(datetime.now().isoformat(timespec='seconds')+' '+texto+'\n')

def valor_csv(valor):
    if valor is None: return ''
    if isinstance(valor,bytes): return 'BASE64:'+base64.b64encode(valor).decode('ascii')
    if isinstance(valor,str) and valor.lstrip().startswith(('=','+','-','@')): return "'"+valor
    return valor

def criar_backup(base):
    base=base.resolve();db=base/'instance'/'biblioteca.sqlite'
    if not db.is_file(): raise RuntimeError('Banco nao encontrado. Nenhum banco vazio sera criado: '+str(db))
    if db.is_symlink(): raise RuntimeError('Banco por link simbolico: solicite avaliacao tecnica.')
    if porta_ocupada():
        log(base,'ADIADO: porta 8080 em uso. Encerre o sistema e faca backup manual.')
        print('Backup nao executado: porta 8080 em uso. Encerre o sistema e tente novamente.')
        return 10
    pasta=base/'backups';pasta.mkdir(exist_ok=True);lock=pasta/'.backup_em_execucao.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError: raise RuntimeError('Outro backup em execucao ou trava antiga: '+str(lock))
    os.close(fd)
    nome='backup_'+datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')+'.zip'
    final=pasta/nome;parcial=pasta/(nome+'.partial')
    try:
        with tempfile.TemporaryDirectory(prefix='biblioteca_backup_') as tmp:
            snapshot=Path(tmp)/'biblioteca.sqlite'
            origem=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)
            destino=sqlite3.connect(str(snapshot));limite=time.monotonic()+120
            def progresso(status,restante,total):
                if time.monotonic()>limite: raise TimeoutError('Backup excedeu 120 segundos. Tente com o servidor encerrado.')
            try: origem.backup(destino,pages=256,progress=progresso,sleep=0.1)
            finally: destino.close();origem.close()
            leitura=sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True)
            try:
                if leitura.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]: raise RuntimeError('Copia do banco nao passou na verificacao estrutural.')
                tabelas=[r[0] for r in leitura.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                manifesto={'criado_em':datetime.now().astimezone().isoformat(),'formato':'backup-complementar-1','csv_somente_consulta':True,'tabelas':{},'arquivos_sha256':{}}
                with zipfile.ZipFile(parcial,'w',zipfile.ZIP_DEFLATED) as z:
                    def adicionar(nome,dados):
                        z.writestr(nome,dados);manifesto['arquivos_sha256'][nome]=hashlib.sha256(dados).hexdigest()
                    z.write(snapshot,'instance/biblioteca.sqlite')
                    with snapshot.open('rb') as f:
                        h=hashlib.sha256()
                        for bloco in iter(lambda:f.read(1024*1024),b''): h.update(bloco)
                    manifesto['arquivos_sha256']['instance/biblioteca.sqlite']=h.hexdigest()
                    for i,tabela in enumerate(tabelas,1):
                        ident='"'+tabela.replace('"','""')+'"';cursor=leitura.execute('SELECT * FROM '+ident)
                        buf=io.StringIO(newline='');w=csv.writer(buf,delimiter=';',lineterminator='\n')
                        w.writerow([c[0] for c in cursor.description]);n=0
                        for registro in cursor: w.writerow([valor_csv(v) for v in registro]);n+=1
                        nome_csv='csv_consulta/'+str(i).zfill(2)+'_'+(re.sub(r'[^A-Za-z0-9_-]','_',tabela) or 'tabela')+'.csv'
                        adicionar(nome_csv,buf.getvalue().encode('utf-8-sig'));manifesto['tabelas'][tabela]={'registros':n,'arquivo_csv':nome_csv}
                    capas=base/'static'/'capas'
                    if capas.is_symlink(): raise RuntimeError('Pasta de capas por link simbolico: solicite avaliacao tecnica.')
                    if capas.exists():
                        for arquivo in sorted(capas.rglob('*')):
                            if arquivo.is_symlink(): raise RuntimeError('Link simbolico na pasta de capas: '+str(arquivo))
                            if arquivo.is_file(): adicionar('static/capas/'+arquivo.relative_to(capas).as_posix(),arquivo.read_bytes())
                    instrucoes=('BACKUP DA BIBLIOTECA\n'
                    'O banco instance/biblioteca.sqlite e a fonte para restauracao completa.\n'
                    'static/capas contem as capas presentes no momento do backup.\n'
                    'Os CSVs sao extracoes de TODAS as tabelas para consulta e recuperacao tecnica.\n'
                    'NAO reimporte esses CSVs diretamente pela tela de importacao do sistema.\n'
                    'Eles podem conter IDs, estado atual, historico e colunas internas diferentes dos modelos de importacao.\n'
                    'Campos vazios nao distinguem NULL de texto vazio; binarios usam BASE64:; textos que poderiam virar formulas recebem apostrofo.\n'
                    'Para recuperar com fidelidade use o BANCO, nao os CSVs.\n'
                    'A copia nao inclui codigo, dependencias ou chave de sessao.\n'
                    'Restauracao: solicite apoio tecnico e use pasta de recuperacao separada, com servidor parado.\n'
                    'Preserve a instalacao original. Descompacte o banco em instance e as capas em static/capas da copia.\n'
                    'Use pasta de capas vazia na recuperacao para nao misturar arquivos de datas diferentes.\n'
                    'Nao sobreponha banco com arquivos -wal/-shm remanescentes; use copia separada.\n'
                    'Faca backup da instalacao atual antes de qualquer substituicao.\n'
                    'Depois confira cadastros, imagens, estados e historico na instalacao recuperada.\n'
                    'O programa nao encerra servidores e nao garante consistencia das capas se houver edicao simultanea.\n'
                    'A verificacao de porta considera somente 127.0.0.1:8080. Nao edite durante o backup.\n')
                    adicionar('LEIA-ME.txt',instrucoes.encode('utf-8'))
                    z.writestr('manifesto.json',json.dumps(manifesto,ensure_ascii=False,indent=2).encode('utf-8'))
                with zipfile.ZipFile(parcial) as z:
                    if z.testzip() is not None: raise RuntimeError('Falha ao verificar o ZIP.')
                    for nome_arquivo,digest in manifesto['arquivos_sha256'].items():
                        if hashlib.sha256(z.read(nome_arquivo)).hexdigest()!=digest: raise RuntimeError('Falha de integridade no ZIP.')
            finally: leitura.close()
        os.replace(parcial,final);log(base,'SUCESSO: '+final.name);print('Backup concluido: '+str(final));return 0
    finally:
        if parcial.exists(): parcial.unlink()
        lock.unlink(missing_ok=True)

def agendar(base):
    if os.name!='nt': raise RuntimeError('Agendamento disponivel somente no Windows.')
    hora=input('Horario diario (HH:MM), com PC ligado e sistema encerrado [18:00]: ').strip() or '18:00'
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',hora): raise RuntimeError('Horario invalido.')
    print('Sera criada BibliotecaEscolar_BackupDiario para '+hora+'. Nao encerra servidor nem substitui tarefa existente.')
    if input('Confirma criar a tarefa? Digite SIM: ').strip().upper()!='SIM': print('Cancelado.');return 1
    comando=subprocess.list2cmdline([sys.executable,str(base/'backup_facil.py'),'--automatico'])
    r=subprocess.run(['schtasks','/Create','/TN','BibliotecaEscolar_BackupDiario','/TR',comando,'/SC','DAILY','/ST',hora,'/IT'],check=False)
    if r.returncode: raise RuntimeError('Agendamento nao criado. Consulte a mensagem do Windows. Tarefa ja existente deve ser ajustada no Agendador de Tarefas.')
    print('Tarefa criada. Requer PC ligado e usuario conectado. Execucao perdida nao e recuperada automaticamente.')
    print('Se o sistema estiver aberto, o backup sera adiado. Confira backups e registro_backup.log.')
    return 0

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--automatico',action='store_true');parser.add_argument('--agendar',action='store_true');parser.add_argument('--pasta-base')
    a=parser.parse_args();base=Path(a.pasta_base).resolve() if a.pasta_base else Path(__file__).resolve().parent
    try:
        if a.agendar: return agendar(base)
        if not a.automatico:
            print('Conclua as operacoes e encerre o sistema (Ctrl+C). Nao edite banco ou capas durante a copia.')
            if input('Servidor encerrado? Digite SIM para criar o backup: ').strip().upper()!='SIM': print('Cancelado.');return 1
        return criar_backup(base)
    except Exception as exc:
        print('FALHA no backup/agendamento:',exc)
        try: log(base,'FALHA: '+str(exc))
        except OSError: pass
        return 1

if __name__=='__main__': raise SystemExit(main())
