from datetime import date, datetime
from uuid import uuid4
from banco import agora,normalizar

ROTULOS={'disponivel':'Disponível','em_uso':'Em uso','baixado':'Baixado','indisponivel':'Indisponível — revisar'}

def ids_validos(valores,limite=500):
    try:
        ids=[int(v) for v in valores]
    except (ValueError,TypeError):
        raise ValueError('Seleção inválida.')
    if not ids or len(ids)>limite or len(ids)!=len(set(ids)) or min(ids)<1:
        raise ValueError('Selecione de 1 a '+str(limite)+' exemplares diferentes.')
    return ids

def aplicar_circulacao(con,ids,acao,turma_id=None,prevista=None):
    ids=ids_validos(ids)
    if acao not in ('retirar','devolver','reservar','cancelar_reserva'):
        raise ValueError('Operação inválida.')
    if prevista:
        try:
            data=date.fromisoformat(prevista)
        except ValueError:
            raise ValueError('Data prevista inválida.')
        prevista=data.isoformat()
        if acao=='retirar' and data<date.today():
            raise ValueError('A previsão não pode ser anterior à retirada.')
    con.execute('BEGIN IMMEDIATE')
    try:
        placeholders=','.join('?' for _ in ids)
        linhas=con.execute('SELECT e.*,l.titulo,l.autor,l.ativo AS livro_ativo FROM exemplares e JOIN livros l ON l.id=e.livro_id WHERE e.id IN ('+placeholders+')',ids).fetchall()
        if len(linhas)!=len(ids):
            raise ValueError('Há exemplar inexistente na seleção.')
        turma=None
        if acao in ('retirar','reservar'):
            try:
                turma_id=int(turma_id)
            except (ValueError,TypeError):
                raise ValueError('Selecione a turma/série.')
            turma=con.execute('SELECT * FROM turmas WHERE id=? AND ativo=1',(turma_id,)).fetchone()
            if not turma:
                raise ValueError('Turma inexistente ou inativa.')
        for e in linhas:
            codigo=e['codigo_interno'] or str(e['id'])
            if not e['livro_ativo']:
                raise ValueError(codigo+': livro arquivado.')
            if acao in ('retirar','reservar') and e['estado']!='disponivel':
                raise ValueError(codigo+': exemplar não disponível.')
            if acao=='reservar' and e['turma_reserva']:
                raise ValueError(codigo+': já possui reserva.')
            if acao=='retirar' and e['turma_reserva'] and e['reserva_turma_id']!=turma_id:
                raise ValueError(codigo+': reservado para outra turma; cancele a reserva antes.')
            if acao=='devolver':
                if e['estado']!='em_uso' or not e['uso_id']:
                    raise ValueError(codigo+': não possui retirada ativa. Revise a migração se necessário.')
                movimento=con.execute('SELECT * FROM circulacoes WHERE id=? AND exemplar_id=? AND devolucao IS NULL',(e['uso_id'],e['id'])).fetchone()
                if not movimento:
                    raise ValueError(codigo+': retirada inconsistente; nenhum item foi alterado.')
            if acao=='cancelar_reserva' and not e['turma_reserva']:
                raise ValueError(codigo+': não possui reserva.')
        lote=uuid4().hex
        instante=agora()
        for e in linhas:
            if acao=='retirar':
                mid=con.execute('INSERT INTO circulacoes(exemplar_id,livro_id,turma_id,codigo,titulo,autor,turma,serie,turno,ano_letivo,retirada,prevista,lote) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (e['id'],e['livro_id'],turma_id,e['codigo_interno'] or '(sem código)',e['titulo'],e['autor'],turma['nome'],turma['serie'],turma['turno'],turma['ano_letivo'],instante,prevista or None,lote)).lastrowid
                con.execute("UPDATE exemplares SET estado='em_uso',turma_id=?,turma_uso=?,data_retirada=?,data_prevista=?,uso_id=?,turma_reserva=NULL,reserva_turma_id=NULL,data_reserva=NULL WHERE id=?",(turma_id,turma['nome'],instante,prevista or None,mid,e['id']))
            elif acao=='devolver':
                con.execute('UPDATE circulacoes SET devolucao=? WHERE id=?',(instante,e['uso_id']))
                con.execute("UPDATE exemplares SET estado='disponivel',turma_id=NULL,turma_uso=NULL,data_retirada=NULL,data_prevista=NULL,uso_id=NULL WHERE id=?",(e['id'],))
            elif acao=='reservar':
                con.execute('UPDATE exemplares SET turma_reserva=?,reserva_turma_id=?,data_reserva=? WHERE id=?',(turma['nome'],turma_id,instante,e['id']))
            else:
                con.execute('UPDATE exemplares SET turma_reserva=NULL,reserva_turma_id=NULL,data_reserva=NULL WHERE id=?',(e['id'],))
        con.commit()
        return len(linhas)
    except Exception:
        con.rollback()
        raise

def criar_inventario(con,nome,local_id=None):
    nome=nome.strip()
    if not nome or len(nome)>150:
        raise ValueError('Informe nome de até 150 caracteres para a conferência.')
    con.execute('BEGIN IMMEDIATE')
    try:
        filtro=''
        argumentos=()
        if local_id:
            try:
                local_id=int(local_id)
            except ValueError:
                raise ValueError('Localização inválida.')
            if not con.execute('SELECT id FROM locais WHERE id=?',(local_id,)).fetchone():
                raise ValueError('Localização inexistente.')
            filtro=' AND e.local_id=?'
            argumentos=(local_id,)
        itens=con.execute("SELECT e.*,l.titulo FROM exemplares e JOIN livros l ON l.id=e.livro_id WHERE l.ativo=1 AND e.estado!='baixado'"+filtro,argumentos).fetchall()
        if not itens:
            raise ValueError('Não há exemplares no escopo escolhido.')
        iid=con.execute('INSERT INTO inventarios(nome,inicio,local_id) VALUES(?,?,?)',(nome,agora(),local_id or None)).lastrowid
        con.executemany('INSERT INTO inventario_itens(inventario_id,exemplar_id,codigo,titulo,local_original,estado_original) VALUES(?,?,?,?,?,?)',[(iid,e['id'],e['codigo_interno'],e['titulo'],e['localizacao'],e['estado']) for e in itens])
        con.commit()
        return iid
    except Exception:
        con.rollback()
        raise

def conferir_inventario(con,iid,ids,local_observado=''):
    ids=ids_validos(ids)
    if len(local_observado)>150:
        raise ValueError('Local observado: máximo de 150 caracteres.')
    con.execute('BEGIN IMMEDIATE')
    try:
        inv=con.execute('SELECT * FROM inventarios WHERE id=?',(iid,)).fetchone()
        if not inv or inv['encerramento']:
            raise ValueError('Inventário inexistente ou encerrado.')
        marcadores=','.join('?' for _ in ids)
        itens=con.execute('SELECT * FROM inventario_itens WHERE inventario_id=? AND id IN ('+marcadores+')',(iid,*ids)).fetchall()
        if len(itens)!=len(ids):
            raise ValueError('Seleção não pertence ao inventário.')
        for item in itens:
            con.execute('UPDATE inventario_itens SET conferido_em=?,local_observado=? WHERE id=?',(agora(),local_observado or item['local_original'],item['id']))
        con.commit()
    except Exception:
        con.rollback()
        raise
