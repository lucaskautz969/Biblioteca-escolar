from pathlib import Path
from datetime import date, datetime
from uuid import uuid4
import io
import csv
import json
import re
import secrets
import sqlite3
import time
import warnings
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import URLError
from flask import Flask,render_template,request,redirect,url_for,flash,abort,session,g,Response  # pyright: ignore[reportMissingImports]
from PIL import Image,ImageOps,UnidentifiedImageError  # pyright: ignore[reportMissingImports]
from banco import BASE,INSTANCE,BANCO,conectar,agora,normalizar
from servicos import ROTULOS,ids_validos,aplicar_circulacao,criar_inventario,conferir_inventario
from importacao import COLUNAS,analisar,gravar,exportar_csv,chave

INSTANCE.mkdir(exist_ok=True)
CAPAS=BASE/'static'/'capas'; CAPAS.mkdir(parents=True,exist_ok=True)
TEMP=INSTANCE/'previas'; TEMP.mkdir(exist_ok=True)
CHAVE=INSTANCE/'chave.txt'
if not CHAVE.exists():
    CHAVE.write_text(secrets.token_hex(32),encoding='utf-8')
app=Flask(__name__)
app.config.update(SECRET_KEY=CHAVE.read_text(encoding='utf-8').strip(),MAX_CONTENT_LENGTH=5*1024*1024,
    SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',TRUSTED_HOSTS=['127.0.0.1','localhost'])

def db():
    if 'db' not in g:
        g.db=conectar()
    return g.db

@app.teardown_appcontext
def fechar(erro=None):
    con=g.pop('db',None)
    if con is not None:
        con.close()

@app.before_request
def preparar():
    session.setdefault('csrf',secrets.token_hex(32))
    session.setdefault('cliente',secrets.token_hex(16))
    if request.endpoint=='static':
        return
    if not BANCO.exists():
        return 'Execute init_db.py na pasta desta versão antes de iniciar.',503
    if request.method=='POST':
        if not secrets.compare_digest(session['csrf'],request.form.get('csrf_token','')):
            abort(400,description='Formulário expirado. Atualize a página e tente novamente.')

def url_com(**mudancas):
    args={k:v for k,v in request.args.items() if not k.startswith('_')}
    args.update(request.view_args or {})
    args.update(mudancas)
    args={k:v for k,v in args.items() if v is not None}
    return url_for(request.endpoint,**args)

@app.context_processor
def contexto():
    return {'csrf_token':session.get('csrf',''),'rotulos':ROTULOS,'hoje':date.today().isoformat(),'url_com':url_com}

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(413)
def erro_http(erro):
    mensagem='Envio maior que 5 MiB.' if erro.code==413 else erro.description
    return render_template('erro.html',mensagem=mensagem),erro.code

@app.errorhandler(sqlite3.OperationalError)
def erro_banco(erro):
    con=g.get('db')
    if con is not None:
        con.rollback()
    app.logger.exception('Falha no banco')
    return render_template('erro.html',mensagem='Não foi possível acessar o banco. Confira o terminal e se init_db.py da versão 3 foi executado. Não apague o banco.'),503

def ler_id(nome,opcional=True):
    valor=request.values.get(nome,'').strip()
    if not valor and opcional:
        return None
    try:
        n=int(valor)
        if n<1: raise ValueError()
        return n
    except ValueError:
        raise ValueError('Identificador inválido: '+nome)

def opcoes(tabela,ativos=True):
    return db().execute('SELECT * FROM '+tabela+(' WHERE ativo=1' if ativos and tabela in ('turmas','locais') else '')+' ORDER BY nome COLLATE NOCASE').fetchall()

def paginar(itens,tamanho=24):
    total=len(itens)
    paginas=max(1,(total+tamanho-1)//tamanho)
    pagina=min(max(1,request.args.get('pagina',1,type=int) or 1),paginas)
    if request.args.get('imprimir')=='1':
        return itens,pagina,paginas,total
    return itens[(pagina-1)*tamanho:pagina*tamanho],pagina,paginas,total

def responder_tabela(titulo,colunas,linhas,nome='relatorio',extras=None):
    if request.args.get('formato')=='csv':
        return Response(exportar_csv(colunas,linhas),content_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename={nome}.csv'})
    parte,pagina,paginas,total=paginar(linhas,50)
    return render_template('relatorio.html',titulo=titulo,colunas=colunas,linhas=parte,pagina=pagina,paginas=paginas,total=total,extras=extras or {})

def previa_salvar(tipo,dados):
    for arquivo in TEMP.glob('*.json'):
        if time.time()-arquivo.stat().st_mtime>3600:
            arquivo.unlink(missing_ok=True)
    token=uuid4().hex
    (TEMP/(token+'.json')).write_text(json.dumps({'tipo':tipo,'dados':dados,'cliente':session['cliente'],'criado':time.time()},ensure_ascii=False),encoding='utf-8')
    return token

def previa_ler(token,tipo):
    if not re.fullmatch('[a-f0-9]{32}',token or ''):
        raise ValueError('Prévia inválida.')
    caminho=TEMP/(token+'.json')
    if not caminho.exists():
        raise ValueError('Prévia inexistente ou já usada.')
    p=json.loads(caminho.read_text(encoding='utf-8'))
    if p['tipo']!=tipo or p['cliente']!=session['cliente'] or time.time()-p['criado']>1800:
        raise ValueError('Prévia expirada ou de outra sessão. Recomece a operação.')
    return p['dados'],caminho

@app.route('/')
def inicio():
    con=db()
    dados={'livros':con.execute('SELECT count(*) FROM livros WHERE ativo=1').fetchone()[0],
        'uso':con.execute("SELECT count(*) FROM exemplares WHERE estado='em_uso'").fetchone()[0],
        'reservas':con.execute('SELECT count(*) FROM exemplares WHERE turma_reserva IS NOT NULL').fetchone()[0],
        'atrasados':con.execute("SELECT count(*) FROM exemplares WHERE estado='em_uso' AND data_prevista<?",(date.today().isoformat(),)).fetchone()[0]}
    return render_template('inicio.html',dados=dados)

@app.route('/categorias',methods=['GET','POST'])
def categorias():
    erro=None
    if request.method=='POST':
        nome=request.form.get('nome','').strip()
        if not nome or len(nome)>100:
            erro='Informe um nome com até 100 caracteres.'
        elif db().execute('SELECT id FROM categorias WHERE normalizar(nome)=?',(normalizar(nome),)).fetchone():
            erro='Categoria já cadastrada.'
        else:
            db().execute('INSERT INTO categorias(nome) VALUES(?)',(nome,)); db().commit()
            return redirect(url_for('categorias'))
    return render_template('categorias.html',categorias=opcoes('categorias'),erro=erro)

@app.route('/cadastros/<tipo>',methods=['GET','POST'])
@app.route('/cadastros/<tipo>/<int:rid>/editar',methods=['GET','POST'])
def referencias(tipo,rid=None):
    if tipo not in ('turmas','locais'): abort(404)
    registro=db().execute('SELECT * FROM '+tipo+' WHERE id=?',(rid,)).fetchone() if rid else None
    if rid and not registro: abort(404)
    dados=dict(registro) if registro else {}
    erro=None
    if request.method=='POST':
        dados={k:request.form.get(k,'').strip() for k in ('nome','serie','turno','ano_letivo')}
        dados['ativo']=1 if request.form.get('ativo')=='1' else 0
        try:
            if not dados['nome'] or len(dados['nome'])>100:
                raise ValueError('Nome obrigatório de até 100 caracteres. Inclua turma, turno e ano no nome quando necessário.')
            if db().execute('SELECT id FROM '+tipo+' WHERE normalizar(nome)=? AND id!=?',(normalizar(dados['nome']),rid or 0)).fetchone():
                raise ValueError('Nome já cadastrado.')
            ano=None
            if tipo=='turmas' and dados['ano_letivo']:
                if not re.fullmatch('[0-9]{4}',dados['ano_letivo']):
                    raise ValueError('Ano letivo deve ter quatro dígitos.')
                ano=int(dados['ano_letivo'])
            if rid and not dados['ativo']:
                filtro="(turma_id=? AND estado='em_uso') OR reserva_turma_id=?" if tipo=='turmas' else "local_id=? AND estado!='baixado'"
                valores=(rid,rid) if tipo=='turmas' else (rid,)
                if db().execute('SELECT id FROM exemplares WHERE '+filtro,valores).fetchone():
                    raise ValueError('Há exemplares vinculados em uso/reserva ou no acervo deste local. Resolva as vinculações antes de desativar.')
            if tipo=='turmas':
                valores=(dados['nome'],dados['serie'],dados['turno'],ano,dados['ativo'])
                if rid:
                    db().execute('UPDATE turmas SET nome=?,serie=?,turno=?,ano_letivo=?,ativo=? WHERE id=?',valores+(rid,))
                    db().execute('UPDATE exemplares SET turma_uso=? WHERE turma_id=?',(dados['nome'],rid))
                    db().execute('UPDATE exemplares SET turma_reserva=? WHERE reserva_turma_id=?',(dados['nome'],rid))
                else:
                    db().execute('INSERT INTO turmas(nome,serie,turno,ano_letivo,ativo) VALUES(?,?,?,?,?)',valores)
            else:
                if rid:
                    db().execute('UPDATE locais SET nome=?,ativo=? WHERE id=?',(dados['nome'],dados['ativo'],rid))
                    db().execute('UPDATE exemplares SET localizacao=? WHERE local_id=?',(dados['nome'],rid))
                else:
                    db().execute('INSERT INTO locais(nome,ativo) VALUES(?,?)',(dados['nome'],dados['ativo']))
            db().commit()
        except ValueError as exc:
            db().rollback(); erro=str(exc)
        except sqlite3.IntegrityError:
            db().rollback(); erro='Cadastro duplicado ou vinculação inválida.'
        else:
            flash('Cadastro salvo. Registros históricos anteriores mantêm a descrição original.')
            return redirect(url_for('referencias',tipo=tipo))
    return render_template('referencias.html',tipo=tipo,registros=opcoes(tipo,False),dados=dados,editando=bool(registro),erro=erro)

SQL_LIVROS="""SELECT l.*,c.nome AS categoria,
 (SELECT count(*) FROM exemplares e WHERE e.livro_id=l.id AND e.estado!='baixado') AS quantidade,
 (SELECT count(*) FROM exemplares e WHERE e.livro_id=l.id AND e.estado='disponivel' AND e.turma_reserva IS NULL) AS livres
 FROM livros l LEFT JOIN categorias c ON c.id=l.categoria_id"""

def filtrar_livros():
    where=['l.ativo=?'];valores=[0 if request.args.get('arquivo')=='1' else 1]
    busca=normalizar(request.args.get('busca',''))
    if busca:
        where.append('(normalizar(l.titulo) LIKE ? OR normalizar(l.autor) LIKE ? OR normalizar(l.assunto) LIKE ? OR normalizar(l.isbn) LIKE ? OR EXISTS(SELECT 1 FROM exemplares x WHERE x.livro_id=l.id AND normalizar(x.codigo_interno) LIKE ?))')
        valores += ['%'+busca+'%']*5
    for chave_http,campo in (('categoria','l.categoria_id'),):
        valor=request.args.get(chave_http,'')
        if valor:
            where.append(campo+'=?');valores.append(valor)
    filtros_exemplar=['x.livro_id=l.id']
    if request.args.get('local'):
        filtros_exemplar.append('x.local_id=?');valores.append(request.args['local'])
    if request.args.get('livres')=='1':
        filtros_exemplar.append("x.estado='disponivel' AND x.turma_reserva IS NULL")
    if len(filtros_exemplar)>1:
        where.append('EXISTS(SELECT 1 FROM exemplares x WHERE '+' AND '.join(filtros_exemplar)+')')
    ordem={'titulo':'l.titulo COLLATE NOCASE','autor':'l.autor COLLATE NOCASE,l.titulo COLLATE NOCASE','recentes':'l.id DESC'}.get(request.args.get('ordem'),'l.titulo COLLATE NOCASE')
    return db().execute(SQL_LIVROS+' WHERE '+' AND '.join(where)+' ORDER BY '+ordem,valores).fetchall()

@app.route('/catalogo')
def catalogo():
    livros=filtrar_livros()
    if request.args.get('formato')=='csv':
        return responder_tabela('Catálogo',['ID','Título','Autor','ISBN','Categoria','Exemplares não baixados','Livres'],[(l['id'],l['titulo'],l['autor'],l['isbn'],l['categoria'],l['quantidade'],l['livres']) for l in livros],'catalogo')
    parte,pagina,paginas,total=paginar(livros)
    vista=request.args.get('vista','cartoes')
    return render_template('catalogo.html',livros=parte,pagina=pagina,paginas=paginas,total=total,vista=vista,categorias=opcoes('categorias'),locais=opcoes('locais',False))

def salvar_capa(arquivo):
    if not arquivo or not arquivo.filename: return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(arquivo.stream) as imagem:
                if imagem.format not in ('JPEG','PNG','WEBP') or imagem.width*imagem.height>16000000:
                    raise ValueError('Use JPG, PNG ou WEBP de até 16 milhões de pixels.')
                imagem.load()
                img=ImageOps.exif_transpose(imagem).convert('RGB');img.thumbnail((600,900))
                nome=uuid4().hex+'.jpg';img.save(CAPAS/nome,'JPEG',quality=85)
                return nome
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('Imagem inválida ou grande demais.')

@app.route('/livros/novo',methods=['GET','POST'])
@app.route('/livros/<int:livro_id>/editar',methods=['GET','POST'])
def novo_livro(livro_id=None):
    livro=db().execute('SELECT * FROM livros WHERE id=?',(livro_id,)).fetchone() if livro_id else None
    if livro_id and not livro: abort(404)
    if livro and not livro['ativo']: abort(409,description='Restaure o livro antes de editar.')
    dados=dict(livro) if livro else session.pop('isbn_dados',{})
    erro=None
    if request.method=='POST':
        dados={k:request.form.get(k,'').strip() for k in ('titulo','autor','isbn','ano_publicacao','editora','assunto','categoria_id')}
        dados['capa']=livro['capa'] if livro else None
        nova=None
        try:
            if not dados['titulo'] or len(dados['titulo'])>300: raise ValueError('Título obrigatório, até 300 caracteres.')
            ano=None
            if dados['ano_publicacao']:
                if not re.fullmatch('[0-9]{1,4}',dados['ano_publicacao']) or int(dados['ano_publicacao'])<1: raise ValueError('Ano inválido.')
                ano=int(dados['ano_publicacao'])
            cid=ler_id('categoria_id')
            if cid and not db().execute('SELECT id FROM categorias WHERE id=?',(cid,)).fetchone(): raise ValueError('Categoria inexistente.')
            nova=salvar_capa(request.files.get('capa'))
            capa=None if request.form.get('remover_capa')=='1' else dados['capa']
            capa=nova or capa
            valores=(dados['titulo'],dados['autor'],dados['isbn'],ano,dados['editora'],dados['assunto'],cid,capa)
            if livro:
                db().execute('UPDATE livros SET titulo=?,autor=?,isbn=?,ano_publicacao=?,editora=?,assunto=?,categoria_id=?,capa=? WHERE id=?',valores+(livro_id,))
            else:
                livro_id=db().execute('INSERT INTO livros(titulo,autor,isbn,ano_publicacao,editora,assunto,categoria_id,capa) VALUES(?,?,?,?,?,?,?,?)',valores).lastrowid
            db().commit()
        except ValueError as exc:
            erro=str(exc)
        except sqlite3.Error:
            db().rollback()
            if nova: (CAPAS/nova).unlink(missing_ok=True)
            raise
        else:
            flash('Livro salvo.');return redirect(url_for('detalhe_livro',livro_id=livro_id))
    return render_template('livro_formulario.html',dados=dados,categorias=opcoes('categorias'),erro=erro,editando=bool(livro))

@app.route('/livros/<int:livro_id>')
def detalhe_livro(livro_id):
    livro=db().execute(SQL_LIVROS+' WHERE l.id=?',(livro_id,)).fetchone()
    if not livro: abort(404)
    exemplares=db().execute('SELECT * FROM exemplares WHERE livro_id=? ORDER BY codigo_interno',(livro_id,)).fetchall()
    return render_template('livro_detalhe.html',livro=livro,exemplares=exemplares,turmas=opcoes('turmas'))

@app.route('/livros/<int:livro_id>/gestao',methods=['POST'])
def gestao_livro(livro_id):
    con=db();con.execute('BEGIN IMMEDIATE')
    l=con.execute('SELECT * FROM livros WHERE id=?',(livro_id,)).fetchone()
    if not l: abort(404)
    acao=request.form.get('acao')
    if acao=='excluir':
        if con.execute('SELECT id FROM exemplares WHERE livro_id=?',(livro_id,)).fetchone() or con.execute('SELECT id FROM circulacoes WHERE livro_id=?',(livro_id,)).fetchone():
            abort(409,description='Livro com exemplares ou histórico não pode ser excluído. Prefira arquivar.')
        con.execute('DELETE FROM livros WHERE id=?',(livro_id,))
    elif acao=='arquivar':
        if con.execute("SELECT id FROM exemplares WHERE livro_id=? AND (estado='em_uso' OR turma_reserva IS NOT NULL)",(livro_id,)).fetchone():
            abort(409,description='Devolva exemplares e cancele reservas antes de arquivar.')
        con.execute('UPDATE livros SET ativo=0 WHERE id=?',(livro_id,))
    elif acao=='restaurar': con.execute('UPDATE livros SET ativo=1 WHERE id=?',(livro_id,))
    else: abort(400)
    con.commit();flash('Operação concluída.')
    return redirect(url_for('catalogo'))

@app.route('/livros/<int:livro_id>/exemplares/novo',methods=['GET','POST'])
@app.route('/exemplares/<int:exemplar_id>/editar',methods=['GET','POST'])
def novo_exemplar(livro_id=None,exemplar_id=None):
    e=db().execute('SELECT * FROM exemplares WHERE id=?',(exemplar_id,)).fetchone() if exemplar_id else None
    if exemplar_id and not e: abort(404)
    if e: livro_id=e['livro_id']
    livro=db().execute('SELECT * FROM livros WHERE id=? AND ativo=1',(livro_id,)).fetchone()
    if not livro: abort(404)
    dados=dict(e) if e else {};erro=None
    if request.method=='POST':
        dados={'codigo_interno':request.form.get('codigo_interno','').strip(),'local_id':request.form.get('local_id','')}
        try:
            codigo=dados['codigo_interno']
            if not codigo or len(codigo)>100: raise ValueError('Código obrigatório, até 100 caracteres.')
            if db().execute('SELECT id FROM exemplares WHERE normalizar(codigo_interno)=? AND id!=?',(normalizar(codigo),exemplar_id or 0)).fetchone(): raise ValueError('Código já cadastrado.')
            local_id=ler_id('local_id');local=None
            if local_id:
                local=db().execute('SELECT * FROM locais WHERE id=? AND ativo=1',(local_id,)).fetchone()
                if not local: raise ValueError('Localização inválida ou inativa.')
            if e:
                db().execute('UPDATE exemplares SET codigo_interno=?,local_id=?,localizacao=? WHERE id=?',(codigo,local_id,local['nome'] if local else None,exemplar_id))
            else:
                db().execute('INSERT INTO exemplares(livro_id,codigo_interno,local_id,localizacao) VALUES(?,?,?,?)',(livro_id,codigo,local_id,local['nome'] if local else None))
            db().commit()
        except ValueError as exc: erro=str(exc)
        except sqlite3.IntegrityError:
            db().rollback();erro='Código duplicado ou vínculo inválido.'
        else: return redirect(url_for('detalhe_livro',livro_id=livro_id))
    return render_template('exemplar_formulario.html',livro=livro,dados=dados,locais=opcoes('locais'),editando=bool(e),erro=erro)

@app.route('/exemplares/<int:eid>/gestao',methods=['GET','POST'])
def gestao_exemplar(eid):
    con=db()
    if request.method=='POST': con.execute('BEGIN IMMEDIATE')
    e=con.execute('SELECT e.*,l.titulo FROM exemplares e JOIN livros l ON l.id=e.livro_id WHERE e.id=?',(eid,)).fetchone()
    if not e: abort(404)
    acao=request.values.get('acao','')
    if acao not in ('baixar','reativar','excluir'): abort(400)
    erro=None
    if request.method=='POST':
        try:
            if e['estado']=='em_uso' or e['turma_reserva']: raise ValueError('Devolva e cancele reservas antes da operação.')
            if acao=='excluir':
                if con.execute('SELECT id FROM circulacoes WHERE exemplar_id=?',(eid,)).fetchone() or con.execute('SELECT id FROM inventario_itens WHERE exemplar_id=?',(eid,)).fetchone():
                    raise ValueError('Exemplar com histórico ou inventário não pode ser excluído. Use baixa.')
                con.execute('DELETE FROM exemplares WHERE id=?',(eid,))
            elif acao=='baixar':
                motivo=request.form.get('motivo','').strip()
                if not motivo or len(motivo)>300: raise ValueError('Informe motivo da baixa com até 300 caracteres.')
                con.execute("UPDATE exemplares SET estado='baixado',motivo_baixa=? WHERE id=?",(motivo,eid))
            else:
                if e['estado'] not in ('baixado','indisponivel'): raise ValueError('O exemplar não está baixado ou indisponível.')
                con.execute("UPDATE exemplares SET estado='disponivel',motivo_baixa=NULL WHERE id=?",(eid,))
            con.commit()
        except ValueError as exc: con.rollback();erro=str(exc)
        else: flash('Operação concluída.');return redirect(url_for('detalhe_livro',livro_id=e['livro_id']))
    return render_template('gestao_exemplar.html',e=e,acao=acao,erro=erro)


def consulta_exemplares():
    where=['l.ativo=1'];valores=[]
    busca=normalizar(request.args.get('busca',''))
    if busca:
        where.append('(normalizar(e.codigo_interno) LIKE ? OR normalizar(l.titulo) LIKE ? OR normalizar(l.autor) LIKE ?)');valores+=['%'+busca+'%']*3
    for chave_http,campo in (('local','e.local_id'),('livro','e.livro_id')):
        if request.args.get(chave_http): where.append(campo+'=?');valores.append(request.args[chave_http])
    turma=request.args.get('turma')
    if turma: where.append('(e.turma_id=? OR e.reserva_turma_id=?)');valores += [turma,turma]
    estado=request.args.get('estado','')
    if estado in ROTULOS: where.append('e.estado=?');valores.append(estado)
    elif estado=='livre': where.append("e.estado='disponivel' AND e.turma_reserva IS NULL")
    elif estado=='reservado': where.append('e.turma_reserva IS NOT NULL')
    elif estado=='atrasado': where.append("e.estado='em_uso' AND e.data_prevista<?");valores.append(date.today().isoformat())
    return db().execute('SELECT e.*,l.titulo,l.autor FROM exemplares e JOIN livros l ON l.id=e.livro_id WHERE '+' AND '.join(where)+' ORDER BY l.titulo COLLATE NOCASE,e.codigo_interno',valores).fetchall()

@app.route('/exemplares')
def exemplares():
    linhas=consulta_exemplares()
    if request.args.get('formato')=='csv':
        colunas=['Código','Livro','Localização','Estado','Turma em uso','Retirada','Previsão','Reserva','Motivo baixa']
        return responder_tabela('Exemplares',colunas,[(e['codigo_interno'],e['titulo'],e['localizacao'],ROTULOS.get(e['estado']),e['turma_uso'],e['data_retirada'],e['data_prevista'],e['turma_reserva'],e['motivo_baixa']) for e in linhas],'exemplares')
    parte,pagina,paginas,total=paginar(linhas,50)
    return render_template('exemplares.html',linhas=parte,pagina=pagina,paginas=paginas,total=total,turmas=opcoes('turmas'),todas_turmas=opcoes('turmas',False),locais=opcoes('locais',False))

@app.route('/lote',methods=['POST'])
def lote():
    erro=None
    try:
        if request.form.get('confirmar'):
            p,caminho=previa_ler(request.form.get('token'),'circulacao')
            n=aplicar_circulacao(db(),p['ids'],p['acao'],p.get('turma_id'),p.get('prevista'))
            caminho.unlink(missing_ok=True)
            flash(f'Operação concluída em {n} exemplar(es).')
            return redirect(url_for('exemplares',estado='em_uso' if p['acao']=='retirar' else ''))
        ids=ids_validos(request.form.getlist('ids'))
        acao=request.form.get('acao')
        if acao not in ('retirar','devolver','reservar','cancelar_reserva'): raise ValueError('Selecione uma operação.')
        turma_id=ler_id('turma_id')
        turma=db().execute('SELECT * FROM turmas WHERE id=?',(turma_id,)).fetchone() if turma_id else None
        if acao in ('retirar','reservar') and not turma: raise ValueError('Selecione uma turma.')
        linhas=db().execute('SELECT e.*,l.titulo FROM exemplares e JOIN livros l ON l.id=e.livro_id WHERE e.id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()
        if len(linhas)!=len(ids): raise ValueError('Seleção inválida.')
        prevista=request.form.get('prevista','').strip() if acao=='retirar' else None
        token=previa_salvar('circulacao',{'ids':ids,'acao':acao,'turma_id':turma_id,'prevista':prevista})
        return render_template('confirmar_lote.html',linhas=linhas,acao=acao,turma=turma,prevista=prevista,token=token)
    except ValueError as exc:
        erro=str(exc)
    return render_template('erro.html',mensagem=erro),400

@app.route('/historico')
def historico():
    filtros=[];valores=[]
    for chave_http,campo in (('livro','livro_id'),('turma','turma_id')):
        if request.args.get(chave_http): filtros.append(campo+'=?');valores.append(request.args[chave_http])
    for chave_http,op in (('inicio','>='),('fim','<=')):
        if request.args.get(chave_http):
            try: data=date.fromisoformat(request.args[chave_http]).isoformat()
            except ValueError: abort(400,description='Data de filtro inválida.')
            filtros.append('substr(retirada,1,10)'+op+'?');valores.append(data)
    estado=request.args.get('estado','')
    if estado=='aberto': filtros.append('devolucao IS NULL')
    if estado=='devolvido': filtros.append('devolucao IS NOT NULL')
    where=' WHERE '+' AND '.join(filtros) if filtros else ''
    registros=db().execute('SELECT * FROM circulacoes'+where+' ORDER BY id DESC',valores).fetchall()
    linhas=[(r['id'],r['titulo'],r['codigo'],r['turma'],r['serie'],r['turno'],r['ano_letivo'],r['retirada'] or 'Não informada na migração',r['prevista'],r['devolucao'] or 'Em uso','Uso existente na migração' if r['migrado'] else 'Registrado nesta versão') for r in registros]
    inicio_hist=db().execute("SELECT valor FROM configuracao WHERE chave='inicio_historico'").fetchone()
    extras={'historico':True,'turmas':opcoes('turmas',False),'livros':db().execute('SELECT id,titulo FROM livros ORDER BY titulo').fetchall(),'inicio_historico':inicio_hist[0] if inicio_hist else ''}
    return responder_tabela('Histórico por livro e turma',['Movimento','Livro','Exemplar','Turma','Série','Turno','Ano letivo','Retirada','Previsão','Devolução','Origem'],linhas,'historico',extras)

@app.route('/inventarios',methods=['GET','POST'])
def inventarios():
    erro=None
    if request.method=='POST':
        try:
            iid=criar_inventario(db(),request.form.get('nome',''),request.form.get('local_id') or None)
        except ValueError as exc: erro=str(exc)
        else: return redirect(url_for('inventario',iid=iid))
    linhas=db().execute('SELECT i.*, (SELECT count(*) FROM inventario_itens x WHERE x.inventario_id=i.id) AS total,(SELECT count(*) FROM inventario_itens x WHERE x.inventario_id=i.id AND x.conferido_em IS NOT NULL) AS encontrados FROM inventarios i ORDER BY i.id DESC').fetchall()
    return render_template('inventarios.html',linhas=linhas,locais=opcoes('locais',False),erro=erro)

@app.route('/inventarios/<int:iid>',methods=['GET','POST'])
def inventario(iid):
    inv=db().execute('SELECT * FROM inventarios WHERE id=?',(iid,)).fetchone()
    if not inv: abort(404)
    erro=None
    if request.method=='POST':
        try:
            if request.form.get('encerrar'):
                if not inv['encerramento']:
                    db().execute('UPDATE inventarios SET encerramento=? WHERE id=?',(agora(),iid));db().commit()
            else:
                local_id=ler_id('local_observado')
                local=db().execute('SELECT * FROM locais WHERE id=?',(local_id,)).fetchone() if local_id else None
                if local_id and not local: raise ValueError('Local observado inválido.')
                conferir_inventario(db(),iid,request.form.getlist('ids'),local['nome'] if local else '')
        except ValueError as exc: erro=str(exc)
        else: return redirect(url_for('inventario',iid=iid))
    linhas=db().execute('SELECT * FROM inventario_itens WHERE inventario_id=? ORDER BY titulo,codigo',(iid,)).fetchall()
    if request.args.get('pendentes')=='1': linhas=[r for r in linhas if not r['conferido_em']]
    if request.args.get('formato')=='csv':
        return responder_tabela('Inventário',['Código','Livro','Local cadastrado na abertura','Estado na abertura','Conferido em','Local observado'],[(r['codigo'],r['titulo'],r['local_original'],ROTULOS.get(r['estado_original']),r['conferido_em'],r['local_observado']) for r in linhas],'inventario')
    parte,pagina,paginas,total=paginar(linhas,50)
    return render_template('inventario.html',inv=inv,linhas=parte,pagina=pagina,paginas=paginas,total=total,locais=opcoes('locais',False),erro=erro)

@app.route('/qualidade')
def qualidade():
    con=db();problemas=[]
    for l in con.execute('SELECT * FROM livros WHERE ativo=1'):
        ls=dict(l);motivos=[]
        if not (l['autor'] or '').strip(): motivos.append('Autor não informado')
        if not con.execute('SELECT id FROM exemplares WHERE livro_id=?',(l['id'],)).fetchone(): motivos.append('Sem exemplares cadastrados')
        if l['capa'] and (Path(l['capa']).name!=l['capa'] or not (CAPAS/l['capa']).is_file()): motivos.append('Arquivo da capa não encontrado ou referência inválida')
        for motivo in motivos: problemas.append(('Livro',l['id'],l['titulo'],motivo,url_for('detalhe_livro',livro_id=l['id'])))
    grupos={}
    for l in con.execute('SELECT * FROM livros'):
        grupos.setdefault(chave(dict(l)),[]).append(l)
    for grupo in grupos.values():
        if len(grupo)>1:
            for l in grupo: problemas.append(('Livro',l['id'],l['titulo'],'Possível duplicidade: IDs '+', '.join(str(x['id']) for x in grupo),url_for('detalhe_livro',livro_id=l['id'])))
    for e in con.execute("SELECT e.*,l.titulo FROM exemplares e JOIN livros l ON l.id=e.livro_id WHERE e.estado!='baixado'"):
        motivos=[]
        if not e['local_id']: motivos.append('Sem localização padronizada')
        if not (e['codigo_interno'] or '').strip(): motivos.append('Código não informado')
        if e['estado']=='indisponivel': motivos.append('Situação antiga precisa de revisão física')
        if e['estado']=='em_uso' and not e['uso_id']: motivos.append('Uso sem movimento vinculado: revisar migração')
        for motivo in motivos: problemas.append(('Exemplar',e['id'],e['titulo']+' / '+(e['codigo_interno'] or '?'),motivo,url_for('detalhe_livro',livro_id=e['livro_id'])))
    if request.args.get('formato')=='csv':
        return responder_tabela('Cadastros para revisar',['Tipo','ID','Descrição','Aviso'],[p[:4] for p in problemas],'qualidade')
    parte,pagina,paginas,total=paginar(problemas,50)
    return render_template('qualidade.html',problemas=parte,pagina=pagina,paginas=paginas,total=total)

@app.route('/modelos/<tipo>.csv')
def modelo_csv(tipo):
    if tipo not in COLUNAS: abort(404)
    return Response(exportar_csv(COLUNAS[tipo],[]),content_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename=modelo_{tipo}.csv'})

@app.route('/importar',methods=['GET','POST'])
def importar():
    erro=None;previa=None
    if request.method=='POST':
        try:
            if request.form.get('confirmar'):
                p,caminho=previa_ler(request.form.get('token'),'csv')
                con=db();con.execute('BEGIN IMMEDIATE')
                registros,erros=analisar(con,p['tipo'],p['texto'])
                if erros: con.rollback();raise ValueError('Arquivo ou cadastro mudou. Reenvie: '+' / '.join(erros[:5]))
                gravar(con,p['tipo'],registros);con.commit();caminho.unlink(missing_ok=True)
                flash(f'{len(registros)} registros importados.');return redirect(url_for('catalogo'))
            tipo=request.form.get('tipo')
            arquivo=request.files.get('arquivo')
            if not arquivo or not arquivo.filename.lower().endswith('.csv'): raise ValueError('Envie CSV em UTF-8.')
            conteudo=arquivo.read(2*1024*1024+1)
            if len(conteudo)>2*1024*1024: raise ValueError('CSV acima de 2 MiB.')
            try: texto=conteudo.decode('utf-8-sig')
            except UnicodeDecodeError: raise ValueError('Salve o arquivo em UTF-8.')
            registros,erros=analisar(db(),tipo,texto)
            token=previa_salvar('csv',{'tipo':tipo,'texto':texto}) if not erros else None
            previa={'linhas':registros[:10],'total':len(registros),'erros':erros,'token':token,'tipo':tipo}
        except (ValueError,csv.Error) as exc:
            db().rollback();erro=str(exc)
        except sqlite3.IntegrityError:
            db().rollback();erro='Conflito ao importar; o lote não foi gravado.'
    return render_template('importar.html',erro=erro,previa=previa)

@app.route('/isbn',methods=['GET','POST'])
def isbn_consulta():
    erro=None;resultado=None
    isbn=request.form.get('isbn','').strip()
    if request.method=='POST':
        if request.form.get('usar'):
            dados=session.pop('isbn_previa',None)
            if dados:
                session['isbn_dados']=dados;return redirect(url_for('novo_livro'))
            erro='Faça a consulta novamente.'
        else:
            session.pop('isbn_previa',None)
            codigo=re.sub(r'[\s-]','',isbn).upper()
            if not re.fullmatch(r'(?:[0-9]{13}|[0-9]{9}[0-9X])',codigo): erro='Informe ISBN de 10 ou 13 caracteres.'
            elif time.time()-session.get('ultimo_isbn',0)<3: erro='Aguarde alguns segundos antes de consultar novamente.'
            else:
                session['ultimo_isbn']=time.time()
                try:
                    chave_isbn='ISBN:'+codigo
                    url='https://openlibrary.org/api/books?'+urlencode({'bibkeys':chave_isbn,'format':'json','jscmd':'data'})
                    req=Request(url,headers={'User-Agent':'BibliotecaEscolarLocal/3.0 (consulta manual ISBN)'})
                    with urlopen(req,timeout=8) as resposta: bruto=resposta.read(1000001)
                    if len(bruto)>1000000: raise ValueError('Resposta grande demais.')
                    item=json.loads(bruto).get(chave_isbn)
                    if not item: erro='Não encontrado. Você pode cadastrar manualmente.'
                    else:
                        anos=re.findall(r'\b[0-9]{4}\b',str(item.get('publish_date','')))
                        resultado={'titulo':str(item.get('title',''))[:300],'autor':'; '.join(str(a.get('name','')) for a in item.get('authors',[]) if isinstance(a,dict))[:250],'editora':'; '.join(str(p.get('name','')) for p in item.get('publishers',[]) if isinstance(p,dict))[:250],'isbn':codigo,'ano_publicacao':anos[-1] if anos else ''}
                        session['isbn_previa']=resultado
                except (URLError,OSError,ValueError,TypeError,AttributeError): erro='Consulta indisponível. Confira a internet ou cadastre manualmente.'
    return render_template('isbn.html',erro=erro,resultado=resultado,isbn=isbn)

@app.route('/ajuda')
def ajuda():
    return render_template('ajuda.html')

if __name__=='__main__':
    app.run(host='127.0.0.1',port=5000,debug=False)
