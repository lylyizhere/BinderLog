# 💿 BinderLog

Acompanhe o progresso da sua coleção de cards de K-pop nos bots do Discord (Garam, Hanbin, Felix, Jisoo, Haewon e Aeri): total de cartas, quantas você tem e a porcentagem de cada idol.

## O que o app faz

- Cadastro de idols por bot, com total de cartas, quantidade que você tem e % de progresso
- Prioridade (Alta/Média/Baixa) e categoria (Grupo/Solo)
- Cadastro de eras (nome, sigla e 1–3 diamantes) e eventos (nome, sigla automática, marcadores e ícone sugerido pelo nome), com dados independentes por card
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

O botão **Buscar fotos** (aba Fotos) procura imagens em KProfiles, kpopping.com e Wikipédia,
combina as candidatas para permitir fotos diferentes do mesmo idol em cards separados e mantém
as páginas consultadas em cache por até 24 horas para reduzir requisições.
Se o kpopping.com recusar o acesso, novas tentativas nessa fonte são pausadas por 24 horas. Se a
Wikipédia limitar a busca, novas tentativas nessa fonte são pausadas por 1 hora. Se a foto vier
errada ou faltar, use **🔄 Trocar por outra foto** ou cole a URL da imagem no campo da aba Fotos.

As fotos têm direitos autorais dos respectivos donos: o app só guarda o link para uso pessoal.

## Segurança

Nunca suba para o GitHub o `.streamlit/secrets.toml` (tem a senha do banco). Ele já está no `.gitignore`.
