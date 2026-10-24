# 💿 BinderLog

Acompanhe o progresso da sua coleção de cards de K-pop nos bots do Discord (Garam, Hanbin, Felix, Jisoo, Haewon e Aeri): total de cartas, quantas você tem e a porcentagem de cada idol.

## O que o app faz

- Cadastro de idols por bot, com total de cartas, quantidade que você tem e % de progresso
- Prioridade (Alta/Média/Baixa) e categoria (Grupo/Solo)
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

O botão **Buscar fotos** (aba Galeria) procura imagens na Wikipedia e, se configurado, no Google
(Programmable Search Engine). A Custom Search JSON API do Google está fechada para novos clientes
e será descontinuada em 01/01/2027, então pode não funcionar numa conta nova. Se a foto vier errada
ou faltar, use **🔄 Trocar foto** ou cole a URL na coluna "URL da foto" da aba Progresso.

As fotos têm direitos autorais dos respectivos donos: o app só guarda o link para uso pessoal.

## Segurança

Nunca suba para o GitHub o `.streamlit/secrets.toml` (tem a senha do banco). Ele já está no `.gitignore`.
