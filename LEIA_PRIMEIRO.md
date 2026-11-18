# Biblioteca escolar — versão 3 — pasta completa

## Antes de tudo
Esta é uma pasta NOVA. Não extraia por cima do projeto antigo e não misture os arquivos.
Continue guardando a instalação anterior, sem modificá-la, até validar esta versão.
Use uma cópia do banco e das capas; não compartilhe o mesmo banco entre versões em execução.
Aplicação somente local, sem login, sem estudantes, sem multas, sem etiquetas e sem códigos de barras.
Todas as operações ficam liberadas a quem usa o computador, inclusive exclusão e importação.
Proteja a conta Windows, os arquivos e os backups. Não publique na internet ou na rede.

## O que foi adicionado
- Retirada/devolução individual ou em lote, com prévia e confirmação.
- Operação atômica: conflito em qualquer exemplar bloqueia o lote inteiro.
- Histórico de circulação por exemplar, livro, turma/série, turno e ano letivo quando preenchidos.
- Histórico guarda descrições da data da retirada, previsão e data da devolução.
- Cadastros padronizados de turmas/séries e localizações; podem ser desativados sem apagar passado.
- Data prevista opcional, destaque para previsão ultrapassada, sem multas.
- Filtros por categoria/local, disponibilidade, turma e estado; busca sem distinção de acentos.
- Pesquisa local por ISBN e código; consulta opcional de ISBN na Open Library preservada.
- Exportação CSV e impressão: catálogo, exemplares/uso/reservas/baixados, histórico,
  inventário e avisos de qualidade.
- Inventário com escopo por local ou acervo, marcação de encontrados e encerramento.
- Página de cadastros para revisar; nada é alterado automaticamente por esses avisos.
- Ajuda interna e aviso de alterações não salvas nos formulários de cadastro.
- Remoção opcional da referência à capa, preservando arquivos antigos no disco.

## 1. Transferir os dados existentes
1. Pare o servidor antigo com Ctrl+C.
2. Faça uma cópia completa da pasta antiga em local seguro.
3. Extraia este ZIP como uma pasta separada, por exemplo biblioteca_escolar_v3.
4. Copie da instalação anterior APENAS os dados necessários para esta pasta:
   - instance/biblioteca.sqlite -> instance/biblioteca.sqlite da nova pasta.
   - imagens de static/capas/ -> static/capas/ da nova pasta.
   Crie instance se necessário. Não leve app.py, templates, .venv ou atualizadores antigos.
5. Se não quiser dados antigos, pule a cópia e comece com banco vazio.
O pacote NÃO contém banco, capas reais, turmas reais ou chave de sessão.

## 2. Instalação pelo PowerShell na pasta com app.py
Use Python 3.11 ou superior; prefira a mesma versão que já funciona no seu notebook.
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe init_db.py
A instalação baixa dependências; não é necessário ativar .venv ou alterar ExecutionPolicy.
Não copie .venv de outro computador; recrie-o.
Não execute administrar.py nem o atualizador sem login antigo: eles não fazem parte desta versão.

## 3. Migração
init_db.py cria backup_pre_v3_*.sqlite antes de atualizar um banco existente.
Adiciona tabelas/colunas sem DROP TABLE e preserva contas antigas que possam existir,
mas a aplicação v3 não as utiliza. O backup automático é só do banco, não das capas.
Espera o esquema usado anteriormente nesta conversa. Se você alterou colunas por conta
própria, teste e revise a migração antes de usar. Não apague o banco para 'resolver' erro.
Transforma textos de local e turmas em referências padronizadas, agrupando nomes iguais
após normalização simples (acentos, espaços e maiúsculas). Não entende equivalência
semântica: '4 B' e 'Quarto ano B' podem continuar como cadastros separados. Revise-os.
Situações antigas não reconhecidas ficam indisponíveis para revisão quando o campo
estado ainda não existia. Não força exemplares em uso a ficarem disponíveis.

### Início do histórico
Não é possível recuperar retiradas/devoluções que a versão anterior já apagou.
A versão 3 começa a guardar movimentos novos. Se houver exemplar EM USO na migração,
cria um movimento aberto identificado como migrado, preservando turma e data disponíveis.
Se não houver data antiga, o histórico exibe 'Não informada na migração'; não inventa data.
Se faltar turma, cria uma referência explícita para revisão.
Repetir a migração não deve duplicar movimentos nem zerar a circulação.

## 4. Iniciar
Dê duplo clique em iniciar_biblioteca.bat.
Abra http://127.0.0.1:8080. Não inicia navegador automaticamente.
A janela do servidor precisa ficar aberta e o PC sem suspensão durante o uso.
Para encerrar: espere operações concluírem, Ctrl+C no terminal e confirme o lote se solicitado.
Use uma instância por vez. Se a porta 8080 estiver ocupada pela versão antiga, encerre-a.
Alternativa apenas para teste: .\.venv\Scripts\python.exe app.py e http://127.0.0.1:5000.
O BAT usa Waitress. Não altere host para 0.0.0.0 nem abra portas de rede.
Os únicos hosts aceitos são localhost e 127.0.0.1. O modo não oferece autenticação.

## 5. Turmas, séries e locais
Cadastros e ferramentas > Turmas/séries e Localizações.
Nome da turma deve identificar o grupo; sugerido '4º ano B — manhã — 2026'.
Série, turno e ano letivo são campos complementares opcionais.
Crie uma turma nova para outro ano/grupo; não recicle a identidade de uma turma antiga.
Renomear atualiza o nome de uso/reserva atual, mas NÃO reescreve descrições históricas.
Desativar turma com uso/reserva é bloqueado. Desativar local com exemplares não baixados
vinculados é bloqueado. Histórico/inventário antigo não é apagado.
Não há exclusão nem fusão de turmas/locais pela interface.
Local livre em formulário de exemplar foi substituído por lista; importe/cadastre os locais antes.

## 6. Circulação individual e em lote
Nos detalhes do livro ou em Exemplares/circulação, marque uma ou várias caixas.
Nenhum item vem marcado automaticamente; seleção vale só para a página atual.
Escolha retirar, devolver, reservar ou cancelar reserva. Máximo 500 itens por lote.
Retirada/reserva exige turma ativa. Previsão é opcional, somente na retirada.
Data de previsão igual a hoje é aceita; anterior à data atual não é aceita.
A prévia mostra os códigos e a turma. Na confirmação, o estado é verificado novamente
sob transação. Se um item falhar, nenhum item deste lote muda.
Devolução parcial: selecione só os exemplares que retornaram. Em uso atual, turma/data
são limpas; no histórico a circulação permanece com data de devolução.
Relógio/data do PC precisam estar corretos. Não há prazo obrigatório ou multa.
Reservas só para itens disponíveis, uma por exemplar/turma, sem fila e sem expiração.
Para retirar reservado use a turma da reserva, ou cancele a reserva antes de mudar destino.
Não há renovação, edição ou exclusão de movimentos históricos na interface nesta versão.
Corrija erros operacionais antes de confirmar; se registrar retirada indevida e devolver,
o histórico manterá esse ciclo (não existe marcação de movimento anulado nesta versão).

## 7. Histórico e privacidade
Cada linha representa a circulação de UMA cópia; 20 cópias na mesma operação geram 20
movimentos com o mesmo identificador interno de lote, não 20 leitores ou 20 aulas.
Filtre por livro, turma, período de retirada e estado aberto/devolvido.
As colunas da turma/série/turno/ano são as da retirada. Mudanças posteriores não reescrevem
nome do livro, código do exemplar e turma dos movimentos existentes.
O sistema não armazena nomes de estudantes ou leitores; não digite esses dados nos campos.
O histórico não é apagado automaticamente. Combine finalidade e retenção de banco e backups
com a escola. Sem login, não é possível atribuir alterações a um funcionário específico.
Por preservar histórico, exemplares com circulação não podem ser excluídos: use baixa.
Não há histórico separado de reservas ou auditoria de todas as edições cadastrais.

## 8. Relatórios, CSV e impressão
As páginas de catálogo, exemplares, histórico, inventário e qualidade têm exportação.
Exportar CSV inclui TODOS os resultados dos filtros, não apenas a página visível.
'Abrir impressão de todos os resultados' abre uma página sem paginação.
Use o botão de imprimir nela para imprimir ou salvar PDF pelo navegador, se disponível.
O botão 'Imprimir esta página' imprime somente o conteúdo carregado naquela página.
Arquivos CSV de relatório não são modelos de importação e não devem ser reimportados sem adaptação.
Saídas têm aspas e tratamento de células potencialmente interpretáveis como fórmulas;
confira arquivos no programa de planilhas da escola. ISBN/códigos podem ser reinterpretados
pelo Excel; importe essas colunas como texto se precisar preservar zeros à esquerda.

## 9. Inventário
Cria lista fixa dos exemplares de livros ativos, exceto baixados, no momento da abertura.
Pode incluir disponíveis, em uso e indisponíveis; estado na abertura é exibido.
Itens cadastrados depois não entram automaticamente nessa conferência.
Marque encontrados após conferir fisicamente. Local observado pode ser selecionado;
isso NÃO altera o local cadastral. Corrija o cadastro separadamente após conferir.
Pendente significa 'ainda não conferido', nunca baixa/perda automática.
Pode filtrar pendentes, exportar e imprimir. Encerrar trava novas marcações;
não há reabertura, desmarcação, edição ou exclusão de inventários nesta versão.
Exemplares presentes em inventários não podem ser excluídos, pois há vínculo preservado.

## 10. Qualidade dos dados
Avisos de autor ausente, livro sem exemplares, localização/código ausentes,
capas referenciadas mas não encontradas, situação antiga para revisão e possível duplicidade.
Duplicidade compara combinação título+autor+ISBN+ano+editora com normalização simples.
Não detecta todos os casos; edições diferentes podem parecer iguais. Nada é mesclado/apagado.
Sem ISBN ou sem capa, por si só, não é erro.

## 11. Importação e ISBN
CSV UTF-8 com ;, cabeçalho exatamente igual ao modelo, até 500 linhas e 2 MiB.
Somente livros e exemplares novos; sem capas, histórico ou atualização de registros existentes.
Categorias e locais devem existir antes. Campos opcionais podem ficar vazios.
Duplicados/erros bloqueiam lote. Prévia mostra os primeiros 10 registros e total;
confira todo o arquivo. Confirmação valida novamente e grava tudo ou nada.
Prévias expiram em 30 minutos e são vinculadas à sessão do navegador. Temporários antigos
são limpos ao criar outra prévia; podem ser removidos com servidor parado.
Open Library: consulta manual de ISBN, timeout, precisa internet; dados devem ser revisados.
Valida formato, não checksum. Pode não encontrar o livro. Não baixa capas automaticamente.
Cadastro manual e as demais funções trabalham sem internet depois da instalação.

## 12. Capas e backup
Capas JPG/PNG/WEBP até 16 milhões de pixels; envio total por requisição até 5 MiB.
Servidor regrava em JPEG até 600x900 com nome aleatório. Remover referência não apaga arquivo.
Faça backup de instance/biblioteca.sqlite e static/capas. O banco inclui histórico e inventários.
Com servidor parado:
    .\.venv\Scripts\python.exe backup.py
Digite SIM e copie o ZIP gerado em backups para outro local autorizado.
O ZIP de dados não inclui código nem chave de sessão; guarde este pacote separadamente.
Restauração: servidor parado, cópia da instalação atual, extrair banco/capas do backup em
uma instalação de teste da MESMA versão, executar init_db.py e verificar. Só depois substituir
os dados principais. Não abra banco v3 no app antigo; rollback exige cópia antiga completa.

## 13. Testes
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
Testes usam banco em memória ou pasta temporária, não o banco real.
Núcleo: 28 testes de SQLite, regras, lotes, histórico, inventário, CSV e proteção de exportação.
Migração: 2 testes adicionais de esquemas antigos e repetição segura.
Interface: 10 testes de Flask (requer dependências), incluindo rotas, CSRF, capas e prévias.
Confira VERIFICACOES.txt para o que foi efetivamente executado no ambiente de geração.
Não declare validação com usuários ou desempenho da escola antes do piloto.
No computador real: testar instalação/migração, dados antigos, histórico novo, capas,
lotes parciais, reserva de outra turma, filtros, impressão, CSV, conferência e restauração.
Aviso de saída sem salvar é um recurso do navegador; aparência e exibição podem variar.
A versão não é uma auditoria de segurança nem garantia formal de acessibilidade/desempenho.
Para acervos grandes, meça consultas: algumas telas de relatório carregam todos os resultados
para filtrar/paginar/exportar; otimização adicional pode ser necessária.
