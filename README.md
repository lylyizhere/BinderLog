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

O botão **Buscar fotos** (aba Fotos) procura imagens em KProfiles e Wikipédia, combina as
candidatas para permitir fotos diferentes do mesmo idol em cards separados. Os termos são
montados automaticamente com grupo + integrante (ex.: `ALLDAY PROJECT Annie`) ou com `Soloist`
(solista) para idols solo. As páginas consultadas ficam em cache por até 24 horas. Se a Wikipédia
limitar a busca, novas tentativas nessa fonte são pausadas por 1 hora. Se a foto vier errada ou
faltar, use **🔄 Trocar por outra foto** ou cole a URL da imagem no campo da aba Fotos.
Para cards de grupo completo, somente são aceitas fotos identificadas com o nome do grupo;
imagens de integrantes são excluídas e, se a lista de membros não puder ser confirmada, a fonte
é ignorada. No KProfiles, a busca prioriza a última foto listada no perfil. A busca e a extração
de dados do KProfiles ficam em `kprofiles.py`, separadas da interface e das demais integrações.
O scraper se identifica no
User-Agent e serializa as requisições, aguardando de 1,5 a 2,5 segundos entre elas. Se o site
responder HTTP 429, o scraper respeita `Retry-After` ou pausa por uma hora; diante de HTTP 403,
pausa por seis horas (ou pelo prazo informado pelo site) e interrompe a busca em lote. O controle
de ritmo e a pausa são compartilhados entre sessões no mesmo processo do Streamlit.
Ao abrir os detalhes de um card, o BinderLog apresenta a imagem ao lado do resumo e consulta o
perfil correspondente no KProfiles. O resumo reúne, quando publicados pela fonte, a apresentação,
os integrantes, os dados de estreia e outras informações factuais do perfil. Nos cards de grupo
completo, os resumos dos integrantes também são carregados e aparecem junto às áreas de eras e
eventos de cada integrante. O texto é traduzido para português brasileiro pelo serviço MyMemory e
salvo no banco; textos longos são enviados em trechos para respeitar o limite por consulta. O texto
público do perfil é enviado ao serviço de tradução. A busca respeita o limitador e as pausas do
KProfiles; em caso de indisponibilidade, o app mostra um aviso e aguarda antes de tentar novamente.

As fotos têm direitos autorais dos respectivos donos: o app só guarda o link para uso pessoal.

## Segurança

Nunca suba para o GitHub o `.streamlit/secrets.toml` (tem a senha do banco). Ele já está no `.gitignore`.
