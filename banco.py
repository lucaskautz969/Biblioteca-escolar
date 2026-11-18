from pathlib import Path
from datetime import datetime
import sqlite3
import unicodedata

BASE=Path(__file__).resolve().parent
INSTANCE=BASE/'instance'
BANCO=INSTANCE/'biblioteca.sqlite'

def agora():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def normalizar(valor):
    texto=unicodedata.normalize('NFKD',str(valor or '').casefold())
    return ' '.join(''.join(c for c in texto if not unicodedata.combining(c)).split())

def conectar(caminho=BANCO):
    con=sqlite3.connect(caminho,timeout=20)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.create_function('normalizar',1,normalizar,deterministic=True)
    return con

def inicializar():
    INSTANCE.mkdir(exist_ok=True)
    if BANCO.exists():
        destino=INSTANCE/('backup_pre_v3_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite')
        origem=conectar(); copia=sqlite3.connect(destino)
        try:
            origem.backup(copia)
        finally:
            origem.close(); copia.close()
        print('Backup do banco anterior:',destino.name)
    con=conectar()
    try:
        con.executescript((BASE/'schema.sql').read_text(encoding='utf-8'))
        def adicionar(tabela,coluna,definicao):
            if coluna not in {r[1] for r in con.execute('PRAGMA table_info('+tabela+')')}:
                con.execute('ALTER TABLE '+tabela+' ADD COLUMN '+coluna+' '+definicao)
                return True
            return False
        adicionar('livros','capa','TEXT')
        adicionar('livros','ativo','INTEGER NOT NULL DEFAULT 1')
        novo_estado=adicionar('exemplares','estado',"TEXT NOT NULL DEFAULT 'disponivel'")
        for c in ('turma_uso','data_retirada','turma_reserva','data_reserva','motivo_baixa','data_prevista'):
            adicionar('exemplares',c,'TEXT')
        for c in ('turma_id','reserva_turma_id','local_id','uso_id'):
            adicionar('exemplares',c,'INTEGER')
        if novo_estado:
            for e in con.execute('SELECT id,situacao FROM exemplares').fetchall():
                if normalizar(e['situacao']) not in ('','disponivel','no acervo'):
                    con.execute("UPDATE exemplares SET estado='indisponivel' WHERE id=?",(e['id'],))
        for tabela in ('turmas','locais'):
            con.execute('CREATE INDEX IF NOT EXISTS idx_'+tabela+'_ativo ON '+tabela+'(ativo)')
        def referencia(tabela,nome):
            nome=(nome or '').strip()
            if not nome:
                return None
            existe=con.execute('SELECT id FROM '+tabela+' WHERE normalizar(nome)=?',(normalizar(nome),)).fetchone()
            return existe['id'] if existe else con.execute('INSERT INTO '+tabela+'(nome) VALUES(?)',(nome,)).lastrowid
        for e in con.execute('SELECT * FROM exemplares').fetchall():
            local=e['local_id'] or referencia('locais',e['localizacao'])
            turma=e['turma_id']
            reserva=e['reserva_turma_id']
            if e['estado']=='em_uso' and not turma:
                turma=referencia('turmas',e['turma_uso'] or 'Turma não informada — revisar migração')
            if e['turma_reserva'] and not reserva:
                reserva=referencia('turmas',e['turma_reserva'])
            con.execute('UPDATE exemplares SET local_id=?,turma_id=?,reserva_turma_id=? WHERE id=?',(local,turma,reserva,e['id']))
            if e['estado']=='em_uso' and not e['uso_id']:
                l=con.execute('SELECT * FROM livros WHERE id=?',(e['livro_id'],)).fetchone()
                if l:
                    t=con.execute('SELECT * FROM turmas WHERE id=?',(turma,)).fetchone()
                    existente=con.execute('SELECT id FROM circulacoes WHERE exemplar_id=? AND devolucao IS NULL',(e['id'],)).fetchone()
                    movimento=existente['id'] if existente else con.execute('INSERT INTO circulacoes(exemplar_id,livro_id,turma_id,codigo,titulo,autor,turma,serie,turno,ano_letivo,retirada,prevista,lote,migrado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)',
                        (e['id'],e['livro_id'],turma,e['codigo_interno'] or '(sem código)',l['titulo'],l['autor'],t['nome'],t['serie'],t['turno'],t['ano_letivo'],e['data_retirada'] or None,e['data_prevista'],'migracao')).lastrowid
                    con.execute('UPDATE exemplares SET uso_id=? WHERE id=?',(movimento,e['id']))
        con.execute("INSERT OR IGNORE INTO configuracao(chave,valor) VALUES('inicio_historico',?)",(agora(),))
        con.executescript('CREATE INDEX IF NOT EXISTS idx_exemplares_livro ON exemplares(livro_id); CREATE INDEX IF NOT EXISTS idx_exemplares_estado ON exemplares(estado); CREATE INDEX IF NOT EXISTS idx_circulacoes_livro ON circulacoes(livro_id); CREATE INDEX IF NOT EXISTS idx_circulacoes_turma ON circulacoes(turma_id); CREATE UNIQUE INDEX IF NOT EXISTS idx_circulacao_aberta ON circulacoes(exemplar_id) WHERE devolucao IS NULL;')
        con.commit()
        invalidos=con.execute('PRAGMA foreign_key_check').fetchall()
        if invalidos:
            print('ATENÇÃO: relações inválidas preexistentes:',[tuple(r) for r in invalidos])
        print('Banco v3 preparado; confira os dados em uma cópia antes de substituir a instalação anterior.')
    finally:
        con.close()
