import csv
import io
from banco import normalizar

COLUNAS={'livros':['titulo','autor','isbn','ano_publicacao','editora','assunto','categoria'],
         'exemplares':['livro_id','codigo_interno','localizacao']}

def chave(d):
    return tuple(normalizar(d.get(k)) for k in ('titulo','autor','isbn','ano_publicacao','editora'))

def analisar(con,tipo,texto):
    if tipo not in COLUNAS:
        raise ValueError('Tipo inválido.')
    leitor=csv.DictReader(io.StringIO(texto.lstrip('\ufeff')),delimiter=';',strict=True)
    if leitor.fieldnames!=COLUNAS[tipo]:
        raise ValueError('Cabeçalho diferente do modelo. Use UTF-8 e separador ponto e vírgula.')
    registros=[];erros=[]
    existentes={chave(dict(r)) for r in con.execute('SELECT * FROM livros')}
    codigos={normalizar(r[0]) for r in con.execute('SELECT codigo_interno FROM exemplares') if r[0]}
    categorias={normalizar(r['nome']):r['id'] for r in con.execute('SELECT * FROM categorias')}
    locais={normalizar(r['nome']):r['id'] for r in con.execute('SELECT * FROM locais WHERE ativo=1')}
    for indice,linha in enumerate(leitor,2):
        if indice>501:
            raise ValueError('Máximo de 500 linhas de dados por arquivo.')
        if None in linha or any(v is None for v in linha.values()):
            erros.append(f'Linha {indice}: número de colunas incorreto.');continue
        d={k:v.strip() for k,v in linha.items()}
        if not any(d.values()):
            continue
        problemas=[]
        if any(len(v)>2000 for v in d.values()):
            erros.append(f'Linha {indice}: campo maior que 2.000 caracteres.');continue
        if tipo=='livros':
            if not d['titulo'] or len(d['titulo'])>300:
                problemas.append('título obrigatório, máximo 300 caracteres')
            ano=d['ano_publicacao']
            if ano and (not ano.isascii() or not ano.isdigit() or len(ano)>4 or int(ano)<1):
                problemas.append('ano inválido')
            d['ano_publicacao']=int(ano) if ano.isascii() and ano.isdigit() and len(ano)<=4 else None
            categoria=normalizar(d['categoria'])
            if categoria and categoria not in categorias:
                problemas.append('cadastre a categoria antes de importar')
            d['categoria_id']=categorias.get(categoria)
            k=chave(d)
            if k in existentes:
                problemas.append('possível livro duplicado, inclusive arquivados')
            existentes.add(k)
        else:
            try:
                d['livro_id']=int(d['livro_id'])
            except ValueError:
                d['livro_id']=0
            if not con.execute('SELECT id FROM livros WHERE id=? AND ativo=1',(d['livro_id'],)).fetchone():
                problemas.append('livro inexistente ou arquivado')
            codigo=normalizar(d['codigo_interno'])
            if not codigo or len(d['codigo_interno'])>100 or codigo in codigos:
                problemas.append('código vazio, longo ou repetido')
            codigos.add(codigo)
            loc=normalizar(d['localizacao'])
            if loc and loc not in locais:
                problemas.append('cadastre a localização antes de importar')
            d['local_id']=locais.get(loc)
        registros.append(d)
        if problemas:
            erros.append(f'Linha {indice}: '+ '; '.join(problemas))
    if not registros:
        erros.append('Nenhum registro válido para analisar.')
    return registros,erros

def gravar(con,tipo,registros):
    for d in registros:
        if tipo=='livros':
            con.execute('INSERT INTO livros(titulo,autor,isbn,ano_publicacao,editora,assunto,categoria_id) VALUES(?,?,?,?,?,?,?)',tuple(d[k] for k in ('titulo','autor','isbn','ano_publicacao','editora','assunto','categoria_id')))
        else:
            con.execute('INSERT INTO exemplares(livro_id,codigo_interno,localizacao,local_id) VALUES(?,?,?,?)',(d['livro_id'],d['codigo_interno'],d['localizacao'],d['local_id']))

def celula_segura(valor):
    texto='' if valor is None else str(valor)
    inicio=texto.lstrip(' \t\r\n')
    if inicio.startswith(('=','+','-','@')) or texto.startswith(('\t','\r','\n')):
        return '\t'+texto
    return texto

def exportar_csv(colunas,linhas):
    saida=io.StringIO()
    escritor=csv.writer(saida,delimiter=';',quoting=csv.QUOTE_ALL,lineterminator='\r\n')
    escritor.writerow(colunas)
    for linha in linhas:
        escritor.writerow([celula_segura(v) for v in linha])
    return '\ufeff'+saida.getvalue()
