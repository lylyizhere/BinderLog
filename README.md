# 💿 BinderLog

Acompanhe o progresso da sua coleção de cards de K-pop nos bots do Discord **Garam, Hanbin, Felix, Jisoo, Haewon e Aeri**: total de cartas, quantas você tem e a porcentagem de cada idol.

## O que o app faz

- Cadastro de idols por bot, com total de cartas, quantidade que você tem e percentual de progresso.
- Prioridade (Alta, Média ou Baixa) e categoria (Grupo, Solo ou Outro).
- Cadastro de eras com nome, sigla e de 1 a 3 diamantes.
- Cadastro de eventos com sigla automática, marcadores e ícone sugerido pelo nome.
- Dados de eras e eventos independentes para cada card.
- Destaque das três coleções mais avançadas de cada bot na página inicial.
- Cards de grupo completo que buscam integrantes no KProfiles e mostram um bloco por pessoa, com eras, eventos e resumo individual.
- Importação dos CSVs da **Garam** (*Bancodedados* e *Priolist*).
- Filtros, busca e ordenação alfabética ou por progresso, cartas faltando e prioridade.
- Galeria com foto de cada idol, incluindo uma foto diferente para cada card do mesmo idol.
- Exportação em CSV.
- Login com Google e coleções separadas por conta.

Nas linhas **SOLO**, o idol é tratado como solista. Um idol indicado como `-` no CSV vira **Grupo completo**, para quando você coleciona o grupo todo.

## Como rodar

### Requisitos

- Python 3.12 ou 3.13 (recomendado).
- PostgreSQL.
- Uma conta Google e credenciais OAuth para o aplicativo.

### 1. Baixe o projeto e instale as dependências

```bash
git clone https://github.com/lylyizhere/BinderLog.git
cd BinderLog
python -m venv .venv
```

No Windows (Prompt de Comando):

```bat
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

No Mac ou Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Crie o banco de dados

No PostgreSQL, crie um banco chamado `binderlog` (por exemplo, no pgAdmin em **Databases > Create > Database**).

As tabelas, os índices e as políticas de isolamento por usuário são criados e atualizados automaticamente pelo app na primeira execução. Este repositório não contém um arquivo `schema.sql` separado.

### 3. Configure o login com Google

No Google Cloud, configure um cliente OAuth para um aplicativo Web. Cadastre como URI de redirecionamento:

```text
http://localhost:8501/oauth2callback
```

Quando publicar o app, cadastre também a URL pública do BinderLog terminada em `/oauth2callback`. Essa URL também deve ser informada na configuração do app.

Se a tela de consentimento OAuth estiver em modo de teste, adicione como usuários de teste as contas Google que usarão o app.

### 4. Configure os segredos

Crie ou edite o arquivo `.streamlit/secrets.toml` na raiz do projeto:

```toml
DATABASE_URL = "postgresql://USUARIO:SENHA@HOST:5432/binderlog"
OWNER_EMAIL = "seu-email-google@exemplo.com"

[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "COLE_AQUI_UM_SEGREDO_ALEATORIO_LONGO"
client_id = "CLIENT_ID_DO_GOOGLE"
client_secret = "CLIENT_SECRET_DO_GOOGLE"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Gere um valor aleatório para `cookie_secret` com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

No Streamlit Community Cloud, cadastre os mesmos valores em **App settings > Secrets** e use a URL pública do app em `redirect_uri`. Essa URL também precisa estar cadastrada no Google Cloud.

`OWNER_EMAIL` identifica a conta Google proprietária da coleção. Os dados que já estavam no banco são associados a essa conta quando ela entrar pela primeira vez. As demais contas começam com coleções vazias.

### 5. Configure uma role PostgreSQL segura

O BinderLog exige uma role PostgreSQL proprietária das tabelas, mas que não tenha `SUPERUSER` nem herde uma role com `BYPASSRLS`. O app interrompe a conexão se detectar uma role que possa ignorar as regras de isolamento dos dados.

**No Neon, crie a role de aplicação pelo SQL Editor, não pela tela de Roles.** Roles criadas pelo Console/API do Neon podem ser associadas a `neon_superuser`, que inclui `BYPASSRLS`.

Use a role proprietária atual para executar o SQL abaixo e substitua o texto da senha por uma senha forte:

```sql
CREATE ROLE binderlog_app LOGIN PASSWORD 'DEFINA_UMA_SENHA_FORTE'
    NOSUPERUSER NOBYPASSRLS;

GRANT binderlog_app TO CURRENT_USER;
GRANT CONNECT ON DATABASE binderlog TO binderlog_app;
GRANT USAGE, CREATE ON SCHEMA public TO binderlog_app;

ALTER TABLE public.colecao OWNER TO binderlog_app;
ALTER TABLE public.colecao_membros OWNER TO binderlog_app;
ALTER TABLE public.colecao_eras OWNER TO binderlog_app;
ALTER TABLE public.colecao_eventos OWNER TO binderlog_app;

ALTER SEQUENCE public.colecao_id_seq OWNER TO binderlog_app;
ALTER SEQUENCE public.colecao_membros_id_seq OWNER TO binderlog_app;
ALTER SEQUENCE public.colecao_eras_id_seq OWNER TO binderlog_app;
ALTER SEQUENCE public.colecao_eventos_id_seq OWNER TO binderlog_app;
```

Se as tabelas ainda não existirem, omita os comandos `ALTER TABLE` e `ALTER SEQUENCE`; o app as criará na primeira execução. Atualize `DATABASE_URL` para usar `binderlog_app` e a senha definida para essa role. Não compartilhe nem faça commit da senha.

### 6. Inicie o app

Com o ambiente virtual ativado e as configurações prontas, execute:

```bash
streamlit run index.py
```

Abra no navegador o endereço indicado pelo Streamlit, normalmente `http://localhost:8501`, e entre com sua conta Google.

### 7. Importe os CSVs

Na aba **Importar CSV**, envie os arquivos da Garam (*Bancodedados* e *Priolist*).

Cada pessoa deve entrar com sua própria conta Google para manter a coleção isolada. Não compartilhe a mesma conta Google entre usuários.

## Fotos dos idols

O botão **Buscar fotos**, na aba **Fotos**, procura primeiro no KProfiles e usa kpopping.com como alternativa quando não encontra imagens. Os termos são montados automaticamente com grupo e integrante (por exemplo, `ALLDAY PROJECT Annie`) ou com `Soloist` para idols solo.

As páginas consultadas ficam em cache por até 24 horas. Se o kpopping limitar ou bloquear o acesso, novas tentativas nessa fonte são pausadas temporariamente, sem contornar a restrição. Se a foto vier errada ou não for encontrada, use **Buscar outra foto** ou cole a URL da imagem no campo da aba **Fotos**.

Para cards de grupo completo, somente são aceitas fotos identificadas com o nome do grupo. Imagens de integrantes são excluídas e, se a lista de membros não puder ser confirmada, a fonte é ignorada. No KProfiles, a busca prioriza a última foto listada no perfil.

A busca e a extração de dados do KProfiles ficam em `kprofiles.py`, separadas da interface e das demais integrações. O scraper se identifica no User-Agent e serializa as requisições, aguardando de 1,5 a 2,5 segundos entre elas. Se o site responder HTTP 429, respeita `Retry-After` ou pausa por uma hora. Diante de HTTP 403, pausa por seis horas (ou pelo prazo informado pelo site) e interrompe a busca em lote. O controle de ritmo e as pausas são compartilhados entre sessões no mesmo processo do Streamlit.

Ao abrir os detalhes de um card, o BinderLog apresenta a imagem ao lado do resumo e consulta o perfil correspondente no KProfiles. A busca considera o nome e o grupo do card e verifica se a apresentação do perfil confirma esse contexto. Se não confirmar, o perfil é descartado para evitar mostrar uma descrição possivelmente errada.

Resumos antigos são atualizados ao abrir o card. Se a atualização falhar, o texto antigo não é mostrado. Os resumos são organizados em parágrafos: apresentação, integrantes e estreia dos grupos; para idols, apresentação e fatos biográficos ou de carreira relevantes encontrados no perfil.

Nos cards de grupo completo, os resumos dos integrantes são carregados individualmente pelo botão de cada pessoa, evitando muitas consultas ao abrir um card. O texto público do perfil é enviado ao serviço MyMemory para tradução para português brasileiro e salvo no banco. Os parágrafos são mantidos, e textos longos são enviados em trechos para respeitar o limite por consulta.

As traduções são espaçadas e trechos já traduzidos são reutilizados. Se o serviço responder com HTTP 429, novas traduções aguardam o prazo informado ou uma hora. Quando a tradução falha após a busca do perfil, o texto original em inglês continua visível na sessão. A busca respeita o limitador e as pausas do KProfiles; em caso de indisponibilidade, o app mostra um aviso e aguarda antes de tentar novamente.

As fotos têm direitos autorais dos respectivos donos. O app só guarda o link para uso pessoal.

## Testes e validação

Este projeto ainda não inclui uma suíte de testes automatizados nem uma rotina de validação contínua no GitHub Actions.

Para verificar a sintaxe dos arquivos Python, com o ambiente virtual ativado, execute:

```bash
python -m compileall -q index.py kprofiles.py
```

Esse comando verifica apenas a sintaxe. Ele não testa o login com Google, a conexão e as permissões do PostgreSQL, o isolamento entre contas nem os fluxos de importação, exportação ou busca de fotos. Para validar esses recursos, configure o OAuth e o banco conforme as instruções acima e teste o app em execução.

## Segurança

- Nunca envie `.streamlit/secrets.toml` ao GitHub. Ele contém a senha do banco e as credenciais OAuth, e já está no `.gitignore`.
- Use uma senha forte para o PostgreSQL e não a compartilhe.
- Configure `DATABASE_URL` com uma role que não tenha `SUPERUSER` nem `BYPASSRLS`.
- Cada pessoa deve entrar com sua própria conta Google para manter as coleções isoladas.
