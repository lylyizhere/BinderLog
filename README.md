# 💿 BinderLog

Acompanhe o progresso da sua coleção de cards de K-pop nos bots do Discord (Garam, Hanbin, Felix, Jisoo, Haewon e Aeri): total de cartas, quantas você tem e a porcentagem de cada idol.

## O que o app faz

- Cadastro de idols por bot, com total de cartas, quantidade que você tem e % de progresso
- Prioridade (Alta/Média/Baixa) e categoria (Grupo/Solo)
- Cadastro de eras (nome, sigla e 1–3 diamantes) e eventos (nome, sigla automática, marcadores e ícone sugerido pelo nome), com dados independentes por card
- Destaque das três coleções mais avançadas de cada bot na página inicial
- Cards de grupo completo buscam os integrantes no KProfiles e mostram um bloco por pessoa, com eras, eventos e um resumo individual
- Importação dos CSVs da **Garam** (*Bancodedados* e *Priolist*)
- Filtros, busca e ordenação alfabética (ou por progresso, cartas faltando, prioridade)
- Galeria com foto de cada idol, com foto diferente para cada card do mesmo idol
- Exportação em CSV

Nas linhas **SOLO** o idol é tratado como solista. Idol `-` no CSV vira **"Grupo completo"** (você coleciona o grupo todo).

## Como rodar

Requisitos: Python 3.12 ou 3.13 (recomendado) e PostgreSQL com pgAdmin.

1. Crie o ambiente virtual e instale as dependências:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Windows (cmd)  |  source .venv/bin/activate  # Mac/Linux
   python -m pip install -r requirements.txt
   ```
2. No pgAdmin, crie um banco chamado `binderlog` (Databases > Create > Database).
   A tabela é criada sozinha na primeira execução. O arquivo `schema.sql` mostra a estrutura.
3. Edite `.streamlit/secrets.toml` e coloque a senha do seu PostgreSQL em `DATABASE_URL`.
4. Rode:
   ```
   streamlit run index.py
   ```
5. Na aba **Importar CSV**, envie os arquivos da Garam.

## Fotos dos idols

O botão **Buscar fotos** (aba Fotos) procura primeiro no KProfiles e usa kpopping.com como
alternativa quando não encontra imagens. Os termos são montados automaticamente com grupo +
integrante (ex.: `ALLDAY PROJECT Annie`) ou com `Soloist` para idols solo. As páginas consultadas
ficam em cache por até 24 horas. Se o kpopping limitar ou bloquear o acesso, novas tentativas
nessa fonte são pausadas temporariamente, sem contornar a restrição. Se a foto vier errada ou
faltar, use **🔄 Buscar outra foto** ou cole a URL da imagem no campo da aba Fotos.
Para cards de grupo completo, somente são aceitas fotos identificadas com o nome do grupo;
imagens de integrantes são excluídas e, se a lista de membros não puder ser confirmada, a fonte
é ignorada. No KProfiles, a busca prioriza a última foto listada no perfil. A busca e a extração de
dados do KProfiles ficam em `kprofiles.py`, separadas da interface e das demais integrações. O
scraper do KProfiles se identifica no User-Agent e serializa as requisições, aguardando de 1,5 a
2,5 segundos entre elas. Se o site responder HTTP 429, respeita `Retry-After` ou pausa por uma
hora; diante de HTTP 403, pausa por seis horas (ou pelo prazo informado pelo site) e interrompe a
busca em lote. O controle de ritmo e a pausa são compartilhados entre sessões no mesmo processo
do Streamlit.
Ao abrir os detalhes de um card, o BinderLog apresenta a imagem ao lado do resumo e consulta o
perfil correspondente no KProfiles. A busca prioriza o nome e o grupo do card e confere se a
apresentação do perfil confirma esse contexto; se não confirmar, o perfil é descartado em vez de
mostrar uma descrição possivelmente errada. Resumos antigos são atualizados ao abrir o card, e o
texto antigo não é mostrado se a atualização falhar. Os resumos são organizados em parágrafos:
apresentação, integrantes e estreia dos grupos; para idols, a apresentação e fatos biográficos e de
carreira relevantes encontrados no perfil. Nos cards de grupo completo, os resumos dos integrantes
são carregados individualmente pelo botão de cada pessoa, evitando muitas consultas ao abrir um
card. O texto é traduzido para português brasileiro pelo serviço MyMemory e salvo no banco; os
parágrafos são mantidos e textos longos são enviados em trechos para respeitar o limite por consulta.
O texto público do perfil é enviado ao serviço de tradução. As traduções são espaçadas e trechos já
traduzidos são reutilizados; se o serviço responder com código 429, novas traduções aguardam o
prazo informado ou uma hora. Quando a tradução falha após a busca do perfil, o texto original em
inglês continua visível na sessão. A busca respeita o limitador e as pausas do KProfiles; em caso de
indisponibilidade, o app mostra um aviso e aguarda antes de tentar novamente.

As fotos têm direitos autorais dos respectivos donos: o app só guarda o link para uso pessoal.

## Segurança

Nunca suba para o GitHub o `.streamlit/secrets.toml` (tem a senha do banco). Ele já está no `.gitignore`.
