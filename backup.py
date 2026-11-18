from pathlib import Path
from datetime import datetime
import tempfile
import sqlite3
import zipfile
from banco import BASE,BANCO,conectar
if not BANCO.exists():
    raise SystemExit('Banco não encontrado.')
print('Pare o servidor para manter banco e capas sincronizados.')
if input('Servidor parado? Digite SIM: ').strip()!='SIM':
    raise SystemExit('Cancelado.')
pasta=BASE/'backups';pasta.mkdir(exist_ok=True)
destino=pasta/('biblioteca_v3_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip')
with tempfile.TemporaryDirectory() as tmp:
    copia=Path(tmp)/'biblioteca.sqlite'
    origem=conectar();alvo=sqlite3.connect(copia)
    try: origem.backup(alvo)
    finally: origem.close();alvo.close()
    with zipfile.ZipFile(destino,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(copia,'instance/biblioteca.sqlite')
        for imagem in (BASE/'static'/'capas').glob('*'):
            if imagem.is_file(): z.write(imagem,'static/capas/'+imagem.name)
print('Backup criado:',destino)
print('Copie para outro local autorizado e teste restauração. Inclui histórico e inventários.')
