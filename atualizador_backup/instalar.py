# Instalador local conservador dos arquivos complementares.
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

def executar():
    pasta=Path(__file__).resolve().parent;candidato=pasta.parent
    if (candidato/'app.py').is_file(): destino=candidato
    else:
        try:
            import tkinter as tk
            from tkinter import filedialog
            janela=tk.Tk();janela.withdraw()
            escolha=filedialog.askdirectory(title='Selecione a pasta do sistema (contem app.py e .venv)');janela.destroy()
            if not escolha: print('Instalacao cancelada.');return 1
        except ImportError:
            escolha=input('Caminho completo da pasta do sistema: ').strip().strip('"')
            if not escolha: return 1
        destino=Path(escolha).resolve()
    for relativo in ['app.py','instance/biblioteca.sqlite','.venv/Scripts/python.exe']:
        if not (destino/relativo).is_file(): raise RuntimeError('Instalacao nao identificada: falta '+relativo+'. Nada sera instalado.')
    with socket.socket() as s:
        s.settimeout(1)
        if s.connect_ex(('127.0.0.1',8080))==0: raise RuntimeError('Porta 8080 em uso. Encerre o sistema antes de atualizar.')
    arquivos=pasta/'arquivos';manifesto=json.loads((pasta/'manifesto_instalador.json').read_text(encoding='utf-8'))
    for nome,digest in manifesto.items():
        if Path(nome).name!=nome: raise RuntimeError('Nome invalido no pacote.')
        if hashlib.sha256((arquivos/nome).read_bytes()).hexdigest()!=digest: raise RuntimeError('Pacote corrompido: '+nome)
        if (destino/nome).is_symlink(): raise RuntimeError('Arquivo de destino e link: '+nome)
    print('Pasta selecionada:',destino)
    print('Serao adicionados/atualizados SOMENTE:',', '.join(manifesto))
    print('Banco, capas, app.py, backup.py e inicializacao original NAO serao substituidos.')
    print('Sera criado backup previo. O agendamento nao sera ativado nesta instalacao.')
    if input('Com o servidor encerrado, digite ATUALIZAR para continuar: ').strip()!='ATUALIZAR': print('Cancelado.');return 1
    python=destino/'.venv'/'Scripts'/'python.exe'
    r=subprocess.run([str(python),str(arquivos/'backup_facil.py'),'--automatico','--pasta-base',str(destino)])
    if r.returncode: raise RuntimeError('Backup previo nao concluido. Atualizacao abortada sem substituir arquivos de programa.')
    anterior=destino/'_atualizacoes_backup'/datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f');anterior.mkdir(parents=True)
    existentes=[];copiados=[]
    try:
        for nome in manifesto:
            if (destino/nome).exists():
                if not (destino/nome).is_file(): raise RuntimeError('Destino nao e arquivo: '+nome)
                shutil.copy2(destino/nome,anterior/nome);existentes.append(nome)
        (anterior/'registro.json').write_text(json.dumps({'arquivos_previos':existentes,'arquivos_pacote':list(manifesto)},indent=2),encoding='utf-8')
        for nome in manifesto:
            copiados.append(nome);shutil.copy2(arquivos/nome,destino/nome)
            if hashlib.sha256((destino/nome).read_bytes()).hexdigest()!=manifesto[nome]: raise RuntimeError('Falha ao conferir copia: '+nome)
    except Exception:
        for nome in copiados:
            if nome in existentes: shutil.copy2(anterior/nome,destino/nome)
            else: (destino/nome).unlink(missing_ok=True)
        raise
    print('ATUALIZACAO CONCLUIDA.')
    print('Use FAZER_BACKUP.bat. Para agendamento opcional: AGENDAR_BACKUP.bat.')
    print('Manual: Manual_do_usuario_escola.pdf. Copias anteriores:',anterior)
    print('O programa principal permanece inalterado. Nao foi criada tarefa agendada.')
    return 0

if __name__=='__main__':
    try: raise SystemExit(executar())
    except Exception as exc:
        print('Atualizacao nao concluida:',exc);raise SystemExit(1)
