import os
import re
import time
import tomllib
from contextlib import closing
from html import escape as esc
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin

import pandas as pd
import psycopg2
import requests
import streamlit as st

from kprofiles import (
    KProfilesRateLimited,
    MyMemoryRateLimited,
    VERSAO_CACHE_PERFIL,
    buscar_imagens_kprofiles,
    buscar_integrantes_kprofiles,
    buscar_perfil_kprofiles,
    nome_aparece_em_texto,
    traduzir_descricao_ptbr,
)

BOTS = ["Garam", "Hanbin", "Felix", "Jisoo", "Haewon", "Aeri"]
PRIORIDADES = ["Alta", "Média", "Baixa"]
CATEGORIAS = ["Grupo", "Solo", "Outro"]
GRUPO_COMPLETO = "Grupo completo"  # idol "-" no CSV: coleciona o grupo todo
VERSAO_DESCRICAO = 8

st.set_page_config(page_title="BinderLog", page_icon="💿", layout="wide")


SECRETS_FILE = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"


def _secret(name):
    """Lê uma configuração: st.secrets, variável de ambiente ou o secrets.toml
    que fica ao lado deste arquivo (não depende da pasta onde o terminal está)."""
    try:
        v = st.secrets.get(name)
        if v:
            return v
    except Exception:
        pass
    v = os.environ.get(name)
    if v:
        return v
    try:
        with open(SECRETS_FILE, "rb") as f:
            return tomllib.load(f).get(name)
    except FileNotFoundError:
        return None
    except tomllib.TOMLDecodeError as e:
        st.error(f"Erro de sintaxe no {SECRETS_FILE}: {e}")
        return None


# ---------------------------------------------------------------- Banco (PostgreSQL)
def conn():
    url = _secret("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL não encontrada. Crie o arquivo abaixo com a linha "
                 'DATABASE_URL = "postgresql://usuario:senha@localhost:5432/binderlog"')
        st.code(str(SECRETS_FILE))
        st.caption(f"Arquivo existe? {SECRETS_FILE.exists()} · Pasta atual do terminal: {Path.cwd()}")
        st.stop()
    user_sub = st.session_state.get("authenticated_user_sub")
    user_email = st.session_state.get("authenticated_user_email")
    owner_email = st.session_state.get("owner_email")
    if not user_sub or not user_email or not owner_email:
        st.error("Entre com uma conta Google para conectar sua coleção.")
        st.stop()
    connection = psycopg2.connect(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('binderlog.user_sub', %s, false), "
                "set_config('binderlog.user_email', %s, false), "
                "set_config('binderlog.owner_email', %s, false)",
                (user_sub, user_email, owner_email),
            )
            cursor.execute(
                "SELECT COALESCE(bool_or(rolsuper OR rolbypassrls), false) "
                "FROM pg_roles WHERE rolname = current_user "
                "OR pg_has_role(current_user, oid, 'MEMBER')"
            )
            bypasses_policies = cursor.fetchone()[0]
        if bypasses_policies:
            connection.close()
            st.error(
                "A conexão do banco usa uma conta que ignora as regras de privacidade "
                "do PostgreSQL. Configure DATABASE_URL com um usuário sem SUPERUSER "
                "e sem BYPASSRLS."
            )
            st.stop()
        return connection
    except Exception:
        connection.close()
        raise


def _sql(sql):
    return sql.replace("?", "%s")  # o código usa ? como marcador; o psycopg2 usa %s


def q(sql, params=()):
    with closing(conn()) as c, c.cursor() as cur:
        cur.execute(_sql(sql), params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def run(sql, params=()):
    with closing(conn()) as c:
        with c, c.cursor() as cur:  # "with c" confirma (commit) a transação
            cur.execute(_sql(sql), params)


def run_many(sql, linhas):
    with closing(conn()) as c:
        with c, c.cursor() as cur:
            for linha in linhas:
                cur.execute(_sql(sql), linha)


@st.dialog("Como usar o site")
def mostrar_como_usar():
    st.markdown(
        "O **BinderLog** ajuda você a acompanhar sua coleção de cards de K-pop: "
        "quais idols e grupos você coleciona, quantos cards já tem e quanto falta. "
        "Você também pode organizar eras, eventos e fotos."
    )
    st.markdown("### Como começar")
    st.markdown(
        "1. Entre com sua conta Google.\n"
        "2. Cadastre seus idols manualmente pelo botão **Adicionar idol / bot**.\n"
        "3. Atualize a quantidade de cards e organize sua coleção nas abas do app."
    )
    st.info(
        "Você não precisa criar nem ter um arquivo CSV para usar o BinderLog. "
        "O cadastro manual funciona normalmente."
    )
    st.markdown("### O que é um arquivo CSV?")
    st.markdown(
        "CSV é um arquivo simples de tabela, parecido com uma planilha: cada linha "
        "contém um registro e as colunas guardam informações como grupo, idol e "
        "quantidade de cards. No BinderLog, a importação está disponível para os "
        "arquivos da Garam **Bancodedados** e **Priolist**."
    )
    st.markdown(
        "Se você já tem esses arquivos, entre no app, abra a aba **Importar CSV** "
        "e envie-os. Se não tem, basta cadastrar sua coleção manualmente."
    )


def autenticar_usuario():
    if not st.user.is_logged_in:
        st.markdown(
            """
            <style>
            .st-key-login_screen {
                min-height: calc(100vh - 5rem);
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                padding: 2rem 1rem;
            }
            .st-key-login_screen [data-testid="stMarkdownContainer"] {
                text-align: center;
            }
            .st-key-login_screen .login-title {
                margin: 0 0 1rem;
                color: var(--heading, #102A43);
                font-size: clamp(2.5rem, 6vw, 4rem);
                font-weight: 780;
                letter-spacing: -.045em;
                line-height: 1.1;
            }
            .st-key-login_screen .login-copy {
                max-width: 38rem;
                margin: 0 auto 2rem;
                color: var(--text, #263746);
                font-size: clamp(1.15rem, 2.5vw, 1.5rem);
                line-height: 1.6;
            }
            .st-key-login_screen .stButton {
                display: flex;
                justify-content: center;
                width: 100%;
            }
            .st-key-login_screen .stButton button {
                min-height: 3.5rem;
                padding: .7rem 2rem;
                font-size: 1.1rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="login_screen"):
            st.markdown(
                '<h1 class="login-title">BinderLog</h1>'
                '<p class="login-copy">Entre com sua conta Google para acessar '
                'sua coleção privada.</p>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Entrar com Google", type="primary", width="stretch", key="login_google"
            ):
                st.login()
            if st.button("Como usar o site", width="stretch", key="como_usar_site"):
                mostrar_como_usar()
        st.stop()

    email = str(st.user.get("email", "")).strip().casefold()
    user_sub = str(st.user.get("sub", "")).strip()
    if not email or not user_sub or st.user.get("email_verified") is not True:
        st.error("Não foi possível verificar sua identidade Google. Tente entrar novamente.")
        if st.button("Sair"):
            st.logout()
        st.stop()

    owner_email = str(_secret("OWNER_EMAIL") or "").strip().casefold()
    if not owner_email:
        st.error(
            "OWNER_EMAIL não está configurado. Defina o e-mail Google da conta "
            "proprietária da coleção nos segredos do Streamlit."
        )
        st.stop()

    st.session_state["authenticated_user_sub"] = user_sub
    st.session_state["authenticated_user_email"] = email
    st.session_state["owner_email"] = owner_email
    st.session_state["authenticated_user_name"] = (
        str(st.user.get("name", "")).strip() or email.split("@", 1)[0]
    )
    st.session_state["authenticated_user_picture"] = str(
        st.user.get("picture", "")
    ).strip()


def sigla_evento(nome):
    palavras = re.findall(r"\w+", str(nome), flags=re.UNICODE)
    return "".join(palavra[0] for palavra in palavras).upper()


def eh_happy_birthday(nome):
    return re.sub(r"[^a-z]", "", str(nome).casefold()) == "happybirthday"


def icone_evento(nome):
    termo = re.sub(r"[^a-z0-9]", "", str(nome).casefold())
    icones = (
        (("birthday", "aniversario"), "🎂"),
        (("fansign", "signing", "autograph"), "✍️"),
        (("fanmeeting", "meetandgreet"), "🫶"),
        (("concert", "worldtour", "tour"), "🎤"),
        (("showcase", "premiere"), "🎬"),
        (("award", "awards"), "🏆"),
        (("festival",), "🎪"),
        (("anniversary",), "🎉"),
        (("comeback", "release", "album"), "🎵"),
        (("livestream", "onlineconcert", "broadcast"), "📹"),
        (("popup", "popupevent"), "🛍️"),
        (("christmas", "xmas"), "🎄"),
        (("halloween",), "🎃"),
        (("seasonsgreetings",), "🎁"),
    )
    return next((icone for termos, icone in icones
                 if any(termo_evento in termo for termo_evento in termos)), "📅")


def _normalizar_nome_grupo(nome):
    return re.sub(r"[^a-z0-9]", "", str(nome).casefold())


@st.cache_resource
def init_db():
    run("""CREATE TABLE IF NOT EXISTS colecao (
        id SERIAL PRIMARY KEY,
        owner_id TEXT,
        bot TEXT NOT NULL,
        grupo TEXT NOT NULL DEFAULT '',
        idol TEXT NOT NULL,
        categoria TEXT DEFAULT 'Grupo',
        prioridade TEXT DEFAULT 'Média',
        total INTEGER NOT NULL DEFAULT 0,
        possuo INTEGER NOT NULL DEFAULT 0,
        image_url TEXT,
        descricao_pt TEXT,
        descricao_url TEXT,
        descricao_versao INTEGER NOT NULL DEFAULT 0)""")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS owner_id TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS image_url TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS descricao_pt TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS descricao_url TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS descricao_versao "
        "INTEGER NOT NULL DEFAULT 0")
    run(
        "ALTER TABLE colecao ALTER COLUMN owner_id "
        "SET DEFAULT current_setting('binderlog.user_sub')"
    )
    run(
        "ALTER TABLE colecao DROP CONSTRAINT IF EXISTS "
        "colecao_bot_grupo_idol_key"
    )
    run(
        "CREATE UNIQUE INDEX IF NOT EXISTS colecao_owner_bot_grupo_idol_idx "
        "ON colecao (owner_id, bot, grupo, idol)"
    )
    run("""CREATE TABLE IF NOT EXISTS colecao_membros (
        id SERIAL PRIMARY KEY,
        colecao_id INTEGER NOT NULL REFERENCES colecao(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        descricao_pt TEXT,
        descricao_url TEXT,
        descricao_versao INTEGER NOT NULL DEFAULT 0)""")
    run("ALTER TABLE colecao_membros ADD COLUMN IF NOT EXISTS descricao_pt TEXT")
    run("ALTER TABLE colecao_membros ADD COLUMN IF NOT EXISTS descricao_url TEXT")
    run("ALTER TABLE colecao_membros ADD COLUMN IF NOT EXISTS descricao_versao "
        "INTEGER NOT NULL DEFAULT 0")
    run("""CREATE TABLE IF NOT EXISTS colecao_eras (
        id SERIAL PRIMARY KEY,
        colecao_id INTEGER NOT NULL REFERENCES colecao(id) ON DELETE CASCADE,
        membro_id INTEGER REFERENCES colecao_membros(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        sigla TEXT NOT NULL DEFAULT '',
        diamantes INTEGER NOT NULL DEFAULT 1,
        descricao TEXT NOT NULL DEFAULT '')""")
    run("ALTER TABLE colecao_eras ADD COLUMN IF NOT EXISTS membro_id "
        "INTEGER REFERENCES colecao_membros(id) ON DELETE CASCADE")
    run("ALTER TABLE colecao_eras ADD COLUMN IF NOT EXISTS sigla TEXT NOT NULL DEFAULT ''")
    run("ALTER TABLE colecao_eras ADD COLUMN IF NOT EXISTS diamantes INTEGER NOT NULL DEFAULT 1")
    run("""CREATE TABLE IF NOT EXISTS colecao_eventos (
        id SERIAL PRIMARY KEY,
        colecao_id INTEGER NOT NULL REFERENCES colecao(id) ON DELETE CASCADE,
        membro_id INTEGER REFERENCES colecao_membros(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        sigla TEXT NOT NULL DEFAULT '',
        marcadores INTEGER NOT NULL DEFAULT 1,
        descricao TEXT NOT NULL DEFAULT '')""")
    run("ALTER TABLE colecao_eventos ADD COLUMN IF NOT EXISTS membro_id "
        "INTEGER REFERENCES colecao_membros(id) ON DELETE CASCADE")
    run("ALTER TABLE colecao_eventos ADD COLUMN IF NOT EXISTS sigla TEXT NOT NULL DEFAULT ''")
    run("ALTER TABLE colecao_eventos ADD COLUMN IF NOT EXISTS marcadores INTEGER NOT NULL DEFAULT 1")

    politica_colecao = (
        "owner_id = current_setting('binderlog.user_sub', true) OR "
        "(owner_id IS NULL AND "
        "current_setting('binderlog.user_email', true) = "
        "current_setting('binderlog.owner_email', true))"
    )
    for tabela in (
        "colecao",
        "colecao_membros",
        "colecao_eras",
        "colecao_eventos",
    ):
        run(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        run(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        run(f"DROP POLICY IF EXISTS binderlog_user_isolation ON {tabela}")
        condicao = (
            politica_colecao
            if tabela == "colecao"
            else "EXISTS (SELECT 1 FROM colecao c WHERE c.id = colecao_id)"
        )
        run(
            f"CREATE POLICY binderlog_user_isolation ON {tabela} "
            f"USING ({condicao}) WITH CHECK ({condicao})"
        )

    eventos = q("SELECT id, nome, sigla FROM colecao_eventos")
    siglas_atualizadas = [
        (sigla_evento(evento.nome), int(evento.id))
        for evento in eventos.itertuples()
        if evento.sigla != sigla_evento(evento.nome)
    ]
    if siglas_atualizadas:
        run_many("UPDATE colecao_eventos SET sigla=? WHERE id=?", siglas_atualizadas)
    try:
        run("UPDATE colecao SET idol=? WHERE idol IN ('Todos os membros', '-')",
            (GRUPO_COMPLETO,))
    except psycopg2.IntegrityError:
        pass
    return True


def reivindicar_colecao_existente():
    email = st.session_state["authenticated_user_email"]
    if email == st.session_state["owner_email"]:
        run(
            "UPDATE colecao SET owner_id=? WHERE owner_id IS NULL",
            (st.session_state["authenticated_user_sub"],),
        )


autenticar_usuario()
init_db()
reivindicar_colecao_existente()


# ---------------------------------------------------------------- Busca de imagens
# Idols que aparecem como "Solo" ou em subunidades: grupo principal usado na busca
PESSOA_GRUPO = {
    "miyeon": "(G)I-DLE", "chungha": "I.O.I", "eunbi": "IZ*ONE", "yiren": "EVERGLOW",
    "taeyeon": "Girls' Generation", "yoona": "Girls' Generation",
    "taeyong": "NCT", "seulgi": "Red Velvet", "wendy": "Red Velvet",
    "irene": "Red Velvet", "joy": "Red Velvet", "jiwoo": "KARD", "somin": "KARD",
    "jonghyun": "SHINee", "yeji": "ITZY", "jurin asaya": "XG",
}
PESSOA_ALIAS_BUSCA = {"eunbi": "Kwon Eunbi", "jurin asaya": "Jurin"}
ALIAS_GRUPO = {
    "snsd": "Girls' Generation", "(g)i-dle": "(G)I-DLE", "i-dle": "(G)I-DLE",
    "nct u": "NCT U", "nct127": "NCT 127", "tts": "Girls' Generation-TTS",
    "triples": "tripleS", "got the beat": "GOT the Beat",
}
def _url(x):
    return x.strip() if isinstance(x, str) and x.strip() else None


def contexto(idol, grupo):
    """Devolve (tipo, nome, grupo_para_busca).
    grupo   -> idol "-" (coleção do grupo todo): busca a foto do grupo
    solista -> linhas SOLO: busca o idol como solista (grupo de origem só ajuda a achar a pessoa)
    pessoa  -> membro dentro do próprio grupo"""
    if idol in (GRUPO_COMPLETO, "Todos os membros", "-"):
        return "grupo", grupo, ALIAS_GRUPO.get(grupo.casefold(), grupo)
    base = re.sub(r"\s+\d+$", "", idol).strip()
    solo = grupo.casefold() == "solo"
    g = PESSOA_GRUPO.get(base.casefold()) if solo else (
        ALIAS_GRUPO.get(grupo.casefold(), grupo) or PESSOA_GRUPO.get(base.casefold(), "")
    )
    return ("solista" if solo else "pessoa"), base, g


def _termos_busca_imagem(tipo, base, grupo):
    if tipo == "grupo":
        return [grupo]
    nomes = list(dict.fromkeys(
        (base, PESSOA_ALIAS_BUSCA.get(base.casefold(), base))
    ))
    termos = []
    for nome in nomes:
        if tipo == "solista":
            termos.append(f"{nome} Soloist")
        if grupo and grupo.casefold() != "solo":
            termos.extend((f"{grupo} {nome}", f"{nome} {grupo}"))
        termos.append(nome)
    return list(dict.fromkeys(termo.strip() for termo in termos if termo.strip()))


class KpoppingUnavailable(requests.RequestException):
    def __init__(self, status_code):
        self.status_code = status_code
        self.cooldown = 86400 if status_code == 403 else 3600
        super().__init__(
            f"kpopping.com respondeu HTTP {status_code}; essa fonte foi pausada."
        )


class _KpoppingImageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        atributos = dict(attrs)
        src = (atributos.get("data-src") or atributos.get("data-lazy-src")
               or atributos.get("src", ""))
        srcset = atributos.get("srcset", "")
        if srcset:
            src = srcset.split(",")[-1].strip().split(" ")[0] or src
        if src:
            self.images.append((src, atributos.get("alt", "")))


@st.cache_data(ttl=86400, show_spinner=False)
def _imagens_kpopping(tipo, base, grupo):
    alvo = grupo if tipo == "grupo" else PESSOA_ALIAS_BUSCA.get(base.casefold(), base)
    alvo_normalizado = _normalizar_nome_grupo(alvo)
    membros_grupo = []
    if tipo == "grupo":
        membros_grupo, _ = buscar_integrantes_kprofiles(grupo)

    paginas = []
    if tipo == "grupo":
        slug = quote(grupo, safe="")
        paginas.append(("https://kpopping.com/profiles/group/" + slug, None))
    paginas.extend(
        ("https://kpopping.com/search", {"query": termo})
        for termo in _termos_busca_imagem(tipo, base, grupo)[:3]
    )

    imagens = []
    for url, parametros in paginas:
        resposta = requests.get(
            url,
            params=parametros,
            headers={
                "User-Agent": "BinderLog/1.0 (+https://github.com/lylyizhere/BinderLog)"
            },
            timeout=20,
        )
        if resposta.status_code in (403, 429):
            raise KpoppingUnavailable(resposta.status_code)
        if resposta.status_code == 404:
            continue
        resposta.raise_for_status()
        parser = _KpoppingImageParser()
        parser.feed(resposta.text)
        for src, alt in parser.images:
            imagem_url = urljoin(resposta.url, src)
            contexto_imagem = f"{alt} {imagem_url}"
            nome_normalizado = _normalizar_nome_grupo(contexto_imagem)
            if (
                not imagem_url.startswith("https://")
                or alvo_normalizado not in nome_normalizado
            ):
                continue
            if tipo == "grupo" and any(
                nome_aparece_em_texto(membro, contexto_imagem)
                for membro in membros_grupo
            ):
                continue
            if any(
                termo in nome_normalizado
                for termo in ("logo", "flag", "symbol", "signature", "map", "avatar")
            ):
                continue
            if imagem_url not in imagens:
                imagens.append(imagem_url)
        if imagens:
            break
    return imagens[:12]


def buscar_candidatas(tipo, base, grupo):
    """Busca primeiro no KProfiles e usa kpopping.com como alternativa."""
    candidatas = []
    erros = []
    try:
        candidatas.extend(buscar_imagens_kprofiles(
            tipo,
            base,
            grupo,
            PESSOA_ALIAS_BUSCA.get(base.casefold(), base),
            _termos_busca_imagem(tipo, base, grupo),
            PESSOA_ALIAS_BUSCA,
        ))
    except KProfilesRateLimited:
        raise
    except (requests.RequestException, ValueError) as erro:
        erros.append(f"KProfiles: {erro}")
    if not candidatas and time.time() >= st.session_state.get(
        "kpopping_fotos_cooldown_ate", 0
    ):
        try:
            candidatas.extend(_imagens_kpopping(tipo, base, grupo))
        except KpoppingUnavailable as erro:
            st.session_state["kpopping_fotos_cooldown_ate"] = (
                time.time() + erro.cooldown
            )
            erros.append(f"kpopping.com: {erro}")
        except KProfilesRateLimited:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError) as erro:
            erros.append(f"kpopping.com: {erro}")
    if candidatas:
        return list(dict.fromkeys(candidatas))
    if erros:
        raise RuntimeError("Não foi possível pesquisar imagens. " + " | ".join(erros))
    return []


def atualizar_descricao_card(card_id, idol, grupo):
    tipo, base, grupo_busca = contexto(idol, grupo)
    perfil = buscar_perfil_kprofiles(
        tipo,
        base,
        grupo_busca,
        PESSOA_ALIAS_BUSCA.get(base.casefold(), base),
        _termos_busca_imagem(tipo, base, grupo_busca),
        VERSAO_CACHE_PERFIL,
    )
    try:
        traducao = traduzir_descricao_ptbr(perfil["descricao"])
    except (requests.RequestException, ValueError):
        guardar_descricao_original("card", card_id, perfil["descricao"], perfil["url"])
        raise
    run(
        "UPDATE colecao SET descricao_pt=?, descricao_url=?, descricao_versao=? WHERE id=?",
        (traducao, perfil["url"], VERSAO_DESCRICAO, int(card_id)),
    )
    return traducao, perfil["url"]


def atualizar_descricao_membro(membro_id, nome, grupo):
    tipo, base, grupo_busca = contexto(nome, grupo)
    perfil = buscar_perfil_kprofiles(
        tipo,
        base,
        grupo_busca,
        PESSOA_ALIAS_BUSCA.get(base.casefold(), base),
        _termos_busca_imagem(tipo, base, grupo_busca),
        VERSAO_CACHE_PERFIL,
    )
    try:
        traducao = traduzir_descricao_ptbr(perfil["descricao"])
    except (requests.RequestException, ValueError):
        guardar_descricao_original(
            "membro", membro_id, perfil["descricao"], perfil["url"]
        )
        raise
    run(
        "UPDATE colecao_membros SET descricao_pt=?, descricao_url=?, descricao_versao=? "
        "WHERE id=?",
        (traducao, perfil["url"], VERSAO_DESCRICAO, int(membro_id)),
    )
    return traducao, perfil["url"]


def guardar_descricao_original(tipo, id_, descricao, url):
    descricoes = st.session_state.setdefault("descricoes_originais", {})
    descricoes[(tipo, int(id_))] = (descricao, url)


def descricao_original(tipo, id_):
    descricoes = st.session_state.setdefault("descricoes_originais", {})
    return descricoes.get((tipo, int(id_)))


def _tentativas_descricao():
    return st.session_state.setdefault("tentativas_descricoes", {})


def _chave_tentativa_descricao(tipo, id_):
    return tipo, int(id_), VERSAO_DESCRICAO


def descricao_pode_carregar(tipo, id_):
    tentativas = _tentativas_descricao()
    chave = _chave_tentativa_descricao(tipo, id_)
    agora = time.time()
    if tentativas.get(chave, 0) > agora:
        return False
    tentativas.pop(chave, None)
    return True


def registrar_falha_descricao(tipo, id_):
    _tentativas_descricao()[_chave_tentativa_descricao(tipo, id_)] = time.time() + 900


def registrar_sucesso_descricao(tipo, id_):
    _tentativas_descricao().pop(_chave_tentativa_descricao(tipo, id_), None)


def escolher(cands, usadas, atual=None):
    """Próxima candidata (depois da atual) que nenhum outro card está usando."""
    if not cands:
        return None
    i = cands.index(atual) if atual in cands else -1
    for u in cands[i + 1:] + cands[:i + 1]:
        if u not in usadas and u != atual:
            return u
    return None


def trocar_foto(id_, idol, grupo, atual=None):
    """Busca e salva uma foto diferente das já usadas em outros cards."""
    tipo, base, g = contexto(idol, grupo)
    cands = buscar_candidatas(tipo, base, g)
    outras = q("SELECT image_url FROM colecao WHERE id != ? AND image_url IS NOT NULL", (int(id_),))
    nova = escolher(cands, set(outras["image_url"]), atual)
    if nova:
        run("UPDATE colecao SET image_url=? WHERE id=?", (nova, int(id_)))
    return nova


UPSERT = """INSERT INTO colecao (bot, grupo, idol, categoria, prioridade, total, possuo)
    VALUES (?,?,?,?,?,?,?)
    ON CONFLICT (owner_id, bot, grupo, idol) DO UPDATE SET
        categoria=excluded.categoria, prioridade=excluded.prioridade,
        total=excluded.total, possuo=excluded.possuo"""


# ---------------------------------------------------------------- Importação Garam
def _norm(s):
    return " ".join(str(s).split())


def parse_garam(banco, prio=None):
    """banco: CSV 'Bancodedados' (Grupo, Idol, Quantidade Total, Quantidade adquirida).
    prio: CSV 'Priolist' (Group, Idol, Priority, Category), opcional."""
    b = pd.read_csv(banco)
    b.columns = [str(c).strip() for c in b.columns]
    obrig = ["Grupo", "Idol", "Quantidade Total", "Quantidade adquirida"]
    if not set(obrig) <= set(b.columns):
        raise ValueError("O arquivo de banco de dados precisa ter as colunas: " + ", ".join(obrig))
    b = b[obrig].dropna(subset=["Grupo", "Idol"]).copy()
    b["Grupo"] = b["Grupo"].map(_norm)
    b["Idol"] = b["Idol"].map(_norm)

    # valida os números: linhas com valor vazio, texto ou negativo são ignoradas (e avisadas)
    avisos = []
    b["n_total"] = pd.to_numeric(b["Quantidade Total"], errors="coerce")
    b["n_possuo"] = pd.to_numeric(b["Quantidade adquirida"], errors="coerce")
    invalido = (b["n_total"].isna() | b["n_possuo"].isna()
                | (b["n_total"] < 0) | (b["n_possuo"] < 0))
    for r in b[invalido].itertuples():
        avisos.append(f"{r.Grupo} / {r.Idol}: quantidade vazia, inválida ou negativa — linha ignorada.")
    b = b[~invalido].copy()
    for r in b[b["n_possuo"] > b["n_total"]].itertuples():
        avisos.append(f"{r.Grupo} / {r.Idol}: 'adquirida' ({int(r.n_possuo)}) maior que o total "
                      f"({int(r.n_total)}) — ajustada para o total.")
    b["k"] = (b["Grupo"] + "|" + b["Idol"]).str.casefold()

    out = pd.DataFrame({
        "grupo": b["Grupo"],
        "idol": b["Idol"].replace("-", GRUPO_COMPLETO),
        "total": b["n_total"].astype(int),
        "possuo": b["n_possuo"].astype(int),
        "categoria": b["Grupo"].map(lambda g: "Solo" if g.casefold() == "solo" else "Grupo"),
        "prioridade": "Média",
        "k": b["k"],
    })

    if prio is not None:
        p = pd.read_csv(prio)
        p.columns = [str(c).strip() for c in p.columns]
        if {"Group", "Idol", "Priority", "Category"} <= set(p.columns):
            p["k"] = (p["Group"].map(_norm) + "|" + p["Idol"].map(_norm)).str.casefold()
            pr = dict(zip(p["k"], p["Priority"].map(
                {"High": "Alta", "Medium": "Média", "Low": "Baixa"})))
            ca = dict(zip(p["k"], p["Category"].map(
                {"Group only": "Grupo", "Solo only": "Solo"})))
            out["prioridade"] = out["k"].map(pr).fillna(out["prioridade"])
            out["categoria"] = out["k"].map(ca).fillna(out["categoria"])
        else:
            raise ValueError("A Priolist precisa ter: Group, Idol, Priority, Category")

    out["possuo"] = out[["possuo", "total"]].min(axis=1)
    return out.drop(columns="k").reset_index(drop=True), avisos


def ordenar(df, ordem):
    df = df.copy()
    # "Grupo completo" é ordenado pelo nome do grupo
    df["_nome"] = df.apply(lambda r: r["grupo"] if r["idol"] == GRUPO_COMPLETO else r["idol"], axis=1)
    df["_nome"] = df["_nome"].str.casefold()
    df["_grupo"] = df["grupo"].str.casefold()
    if ordem == "Idol (A–Z)":
        df = df.sort_values(["_nome", "_grupo"])
    elif ordem == "Grupo (A–Z)":
        df = df.sort_values(["_grupo", "_nome"])
    elif ordem == "Menor progresso":
        df = df.sort_values(["progresso", "_nome"])
    elif ordem == "Maior progresso":
        df = df.sort_values(["progresso", "_nome"], ascending=[False, True])
    elif ordem == "Mais cartas faltando":
        df = df.sort_values(["faltam", "_nome"], ascending=[False, True])
    else:
        ordem_p = {p: i for i, p in enumerate(PRIORIDADES)}
        df["_p"] = df["prioridade"].map(ordem_p)
        df = df.sort_values(["_p", "_nome"])
    return df.drop(columns=[c for c in ["_nome", "_grupo", "_p"] if c in df.columns])


# ---------------------------------------------------------------- Visual
THEME_MODES = ("system", "light", "dark")
THEME_LABELS = {"system": "🖥️ Auto", "light": "☀️ Claro", "dark": "🌙 Escuro"}
THEME_MEDIA_QUERIES = {
    "system": "(prefers-color-scheme: light)",
    "light": "all",
    "dark": "(prefers-color-scheme: no-preference)",
}
theme_mode = st.session_state.setdefault("theme_mode", "system")
theme_media_query = THEME_MEDIA_QUERIES.get(
    theme_mode, THEME_MEDIA_QUERIES["system"]
)


def botao_tema(container):
    tema_atual = st.session_state.get("theme_mode", "system")
    if tema_atual not in THEME_MODES:
        tema_atual = "system"
    with container.popover(
        THEME_LABELS[tema_atual],
        help="Escolha a aparência do BinderLog.",
        width="stretch",
    ):
        st.radio(
            "Tema",
            options=THEME_MODES,
            format_func=THEME_LABELS.__getitem__,
            key="theme_mode",
            label_visibility="collapsed",
        )


CSS = """
<style>
:root {
    --brand: #102A43;
    --gold: #D8B56D;
    --bg: #091925;
    --bg-soft: #0c2030;
    --panel: rgba(16, 42, 67, .88);
    --panel-solid: #102A43;
    --panel-raised: #173954;
    --line: rgba(66, 217, 245, .14);
    --line-strong: rgba(66, 217, 245, .28);
    --accent: #42D9F5;
    --accent-strong: #42D9F5;
    --accent-soft: rgba(66, 217, 245, .14);
    --text: #eaf6fa;
    --heading: #eaf6fa;
    --muted: #afc5d2;
    --tabs-text: #afc5d2;
    --subtle: #7f9aaa;
    --page-glow-one: rgba(66, 217, 245, .12);
    --page-glow-two: rgba(16, 42, 67, .42);
    --header-bg: rgba(9, 25, 37, .82);
    --pill-bg: rgba(16, 42, 67, .82);
    --hero-bg: linear-gradient(125deg,rgba(16,42,67,.98),rgba(13,58,75,.96));
    --hero-title-gradient: linear-gradient(90deg,#eaf6fa,#42D9F5 72%);
    --hero-sub: #c4d8e2;
    --bar-track: rgba(234,246,250,.12);
    --ring-track: rgba(234,246,250,.12);
    --ring-center: #102A43;
    --ring-sm-center: #173954;
    --tabs-bg: rgba(16, 42, 67, .86);
    --tab-hover-bg: rgba(66, 217, 245, .1);
    --tab-active-bg: linear-gradient(135deg,#42D9F5,#27b9d4);
    --tab-active-color: #102A43;
    --tab-active-shadow: 0 5px 16px rgba(0,0,0,.24);
    --button-secondary-bg: rgba(16,42,67,.8);
    --button-primary-bg: linear-gradient(135deg,#42D9F5,#24b8d3);
    --button-primary-text: #102A43;
    --input-bg: rgba(10,29,44,.9);
    --uploader-bg: rgba(16,42,67,.56);
    --uploader-hover-bg: rgba(20,67,88,.72);
    --alert-info-bg: rgba(66,217,245,.1);
    --alert-success-bg: rgba(105,202,165,.12);
    --alert-warning-bg: rgba(216,181,109,.14);
    --alert-error-bg: rgba(232,113,142,.13);
    --expander-bg: rgba(16,42,67,.62);
    --collection-button-bg: rgba(16,42,67,.84);
    --card-action-bg: rgba(66,217,245,.1);
    --card-bg: linear-gradient(160deg,rgba(16,42,67,.98),rgba(12,32,48,.98));
    --card-shadow: 0 10px 28px rgba(0,0,0,.2);
    --card-shadow-hover: 0 16px 35px rgba(0,0,0,.3);
    --photo-bg: #102A43;
    --badge-bg: rgba(7,22,34,.8);
    --badge-border: rgba(66,217,245,.25);
    --radius: 18px;
    color-scheme: dark;
}

@media THEME_LIGHT_QUERY {
    :root {
        --bg: #f3f8fb;
        --bg-soft: #eaf3f7;
        --panel: rgba(255, 255, 255, .9);
        --panel-solid: #fff;
        --panel-raised: #eaf3f7;
        --line: rgba(16, 42, 67, .12);
        --line-strong: rgba(16, 42, 67, .22);
        --accent: #087F9C;
        --accent-strong: #087F9C;
        --accent-soft: rgba(8, 127, 156, .12);
        --text: #263f53;
        --heading: #102A43;
        --muted: #526b7c;
        --tabs-text: #526b7c;
        --subtle: #758b99;
        --page-glow-one: rgba(66, 217, 245, .3);
        --page-glow-two: rgba(8, 127, 156, .12);
        --page-glow-three: rgba(216, 181, 109, .08);
        --header-bg: rgba(243, 248, 251, .88);
        --pill-bg: rgba(255, 255, 255, .84);
        --hero-bg: linear-gradient(125deg,rgba(225,239,247,.98),rgba(220,245,247,.96));
        --hero-title-gradient: linear-gradient(90deg,#102A43,#087F9C 72%);
        --hero-sub: #405a6e;
        --bar-track: rgba(16, 42, 67, .12);
        --ring-track: rgba(16, 42, 67, .12);
        --ring-center: #fff;
        --ring-sm-center: #eaf3f7;
        --tabs-bg: rgba(234, 243, 247, .92);
        --tab-hover-bg: rgba(8, 127, 156, .1);
        --tab-active-bg: linear-gradient(135deg,#42D9F5,#24b8d3);
        --tab-active-color: #102A43;
        --tab-active-shadow: 0 5px 16px rgba(16, 42, 67, .16);
        --button-secondary-bg: rgba(255, 255, 255, .86);
        --button-primary-bg: linear-gradient(135deg,#087F9C,#066b84);
        --button-primary-text: #fff;
        --input-bg: rgba(255, 255, 255, .96);
        --uploader-bg: rgba(255, 255, 255, .62);
        --uploader-hover-bg: rgba(220, 245, 247, .84);
        --alert-info-bg: rgba(8, 127, 156, .08);
        --alert-success-bg: rgba(36, 143, 102, .09);
        --alert-warning-bg: rgba(216, 181, 109, .15);
        --alert-error-bg: rgba(190, 62, 91, .09);
        --expander-bg: rgba(255, 255, 255, .72);
        --collection-button-bg: rgba(255, 255, 255, .84);
        --card-action-bg: rgba(8, 127, 156, .08);
        --card-bg: linear-gradient(160deg,rgba(255,255,255,.98),rgba(239,247,250,.98));
        --card-shadow: 0 10px 28px rgba(16, 42, 67, .09);
        --card-shadow-hover: 0 16px 35px rgba(16, 42, 67, .15);
        --photo-bg: #e5eff4;
        --badge-bg: rgba(16, 42, 67, .84);
        --badge-border: rgba(255,255,255,.32);
        color-scheme: light;
    }
}

.stApp {
    color: var(--text);
    background:
        radial-gradient(ellipse at 12% 0%, var(--page-glow-one), transparent 34rem),
        radial-gradient(ellipse at 94% 15%, var(--page-glow-two), transparent 32rem),
        radial-gradient(ellipse at 52% -12%, var(--page-glow-three, transparent), transparent 38rem),
        var(--bg);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
[data-testid="stHorizontalBlock"]:has(.ttl) button {
    min-height:48px; position:relative; top:8px;
}
body {background:var(--bg); color:var(--text)}
#MainMenu, footer {visibility: hidden}
[data-testid="stDialog"] [role="dialog"] {
    border:1px solid var(--line-strong) !important;
    border-radius:16px !important;
    background:var(--panel-solid) !important;
    color:var(--text) !important;
    box-shadow:0 18px 50px rgba(16,42,67,.24) !important;
}
[data-testid="stDialog"] [aria-label="Close"] {color:var(--text) !important}
header[data-testid="stHeader"] {background: var(--header-bg)}
.block-container {max-width: 1440px; padding: 2.1rem 3rem 4rem}

h1, h2, h3, h4 {color: var(--heading); letter-spacing: -.035em}
h1 p, h2 p, h3 p, h4 p {color:inherit !important}
h1 {font-weight: 760}
h2, h3 {font-weight: 690}
p, label, [data-testid="stCaptionContainer"] {color: var(--muted)}
hr {border-color: var(--line); margin: 1.4rem 0}
a {color: var(--accent)}

.ttl {display:flex; gap:14px; align-items:center; line-height:1.2}
.ttl b {font-size:23px; letter-spacing:-.04em; color:var(--heading)}
.ttl .mut {color:var(--muted); font-size:12px; letter-spacing:.02em}
.logo {
    display:grid; place-items:center; width:48px; height:48px; border-radius:16px;
    background:linear-gradient(145deg,#42D9F5,#102A43 72%);
    box-shadow:0 8px 28px rgba(66,217,245,.22);
    font-size:23px;
}
.pill {
    display:flex; gap:11px; align-items:center; justify-content:center;
    min-height:48px; padding:8px 16px; border-radius:999px;
    background:var(--pill-bg); border:1px solid var(--line);
    color:var(--text); font-size:13px; font-weight:650;
    box-shadow:inset 0 1px rgba(255,255,255,.04);
}
.lbl {font-size:11px; letter-spacing:.17em; color:var(--muted); font-weight:750; margin-bottom:10px}

.hero {
    display:grid; grid-template-columns:1fr auto; gap:18px 26px; align-items:center;
    padding:30px 34px; margin:10px 0 30px; border-radius:26px;
    border:1px solid var(--line-strong);
    background:var(--hero-bg);
    box-shadow:0 20px 60px rgba(0,0,0,.2), inset 0 1px rgba(255,255,255,.05);
}
.hero .big {
    font-size:clamp(52px,7vw,76px); font-weight:820; line-height:.95;
    background:var(--hero-title-gradient);
    -webkit-background-clip:text; background-clip:text; color:transparent;
}
.hero .sub {color:var(--hero-sub); margin-top:12px; font-size:14px}
.hero .bar {grid-column:1/-1}
.bar {height:7px; border-radius:99px; background:var(--bar-track); overflow:hidden}
.bar>span {display:block; height:100%; border-radius:99px; background:linear-gradient(90deg,var(--accent),#24b8d3)}
.brow {display:flex; justify-content:space-between; font-size:11px; color:var(--subtle); margin:5px 4px 17px}
.brow b {color:var(--accent)}
.ring {
    --s:96px; width:var(--s); height:var(--s); border-radius:50%; display:grid; place-items:center;
    position:relative; background:conic-gradient(var(--accent) calc(var(--v)*1%),var(--ring-track) 0);
    box-shadow:0 0 34px rgba(66,217,245,.12);
}
.ring::before {content:""; position:absolute; inset:8px; border-radius:50%; background:var(--ring-center)}
.ring b {position:relative; color:var(--text); font-size:16px}
.ring.sm {--s:36px; box-shadow:none}
.ring.sm::before {inset:4px; background:var(--ring-sm-center)}
.ring.sm b {font-size:9px}

.hd {display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin:16px 0 14px}
.hd h3 {margin:0; font-size:23px}
.hd span {color:var(--muted); font-size:12px}

[data-testid="stTabs"] [role="tablist"] {
    width:fit-content; max-width:100%; gap:7px; padding:6px;
    border:1px solid var(--line); border-radius:16px; background:var(--tabs-bg);
}
[data-testid="stTabs"] [role="tab"] {
    height:42px; padding:0 17px; border-radius:11px; box-sizing:border-box;
    color:var(--tabs-text); font-weight:650; background:transparent;
}
[data-testid="stTabs"] [role="tab"]:hover {color:var(--text); background:var(--tab-hover-bg)}
[data-testid="stTabs"] .react-aria-SelectionIndicator {display:none !important}
[data-testid="stTabs"] [aria-selected="true"] {
    color:var(--tab-active-color) !important; background:var(--tab-active-bg) !important;
    box-shadow:var(--tab-active-shadow);
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {
    color:var(--tab-active-color) !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {display:none}

[data-testid="stRadioGroup"] [data-testid="stRadioOption"] > div > div:first-child {
    background:var(--panel-solid) !important;
    border-color:var(--line-strong) !important;
}
[data-testid="stRadioGroup"] [data-testid="stRadioOption"][data-selected="true"]
> div > div:first-child {
    background:var(--accent) !important;
    border-color:var(--accent) !important;
}
[data-testid="stRadioGroup"] [data-testid="stRadioOption"] > div > div:first-child > div {
    background:var(--panel-solid) !important;
}
[data-testid="stMultiSelectTagsContainer"] [data-tag] {
    background:var(--accent-soft) !important;
    border:1px solid var(--line-strong) !important;
    border-radius:8px !important;
    color:var(--text) !important;
}
[data-testid="stMultiSelectTagsContainer"] [data-tag] button {
    color:var(--muted) !important;
}
[data-testid="stMultiSelectTagsContainer"] [data-tag] button:hover {
    background:var(--accent-soft) !important;
    color:var(--heading) !important;
}

button[kind="primary"], [data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] button {
    border:1px solid var(--line-strong) !important;
    border-radius:12px !important;
    background:var(--button-primary-bg) !important;
    color:var(--button-primary-text) !important; font-weight:680 !important;
    box-shadow:0 6px 18px rgba(8,127,156,.18);
    transition:transform .16s ease, filter .16s ease, box-shadow .16s ease;
}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover,
[data-testid="stFormSubmitButton"] button:hover {
    filter:brightness(1.1); transform:translateY(-1px);
    box-shadow:0 9px 22px rgba(8,127,156,.28);
}
button[kind="secondary"] {
    border:1px solid var(--line) !important; border-radius:12px !important;
    background:var(--button-secondary-bg) !important; color:var(--text) !important;
    transition:background .15s ease, border-color .15s ease;
}
button[kind="secondary"]:hover {border-color:var(--line-strong) !important; background:var(--panel-raised) !important}
button:disabled {opacity:.42 !important}
button p {color:inherit !important}

[data-testid="stSelectbox"] [role="group"] {
    border:1px solid var(--line-strong) !important;
    border-radius:11px !important;
    background:var(--input-bg) !important;
    color:var(--text) !important;
}
[data-testid="stSelectbox"] [role="group"]:focus-within {
    border-color:var(--accent-strong) !important;
    box-shadow:0 0 0 1px var(--accent-strong) !important;
}
[data-testid="stSelectbox"] input,
[data-testid="stSelectbox"] button {
    color:var(--text) !important;
}
[data-testid="stSelectbox"] button:hover {background:var(--accent-soft) !important}
[data-testid="stSelectboxVirtualDropdown"] {
    border:1px solid var(--line-strong) !important;
    border-radius:11px !important;
    background:var(--panel-solid) !important;
    box-shadow:0 12px 30px rgba(16,42,67,.18) !important;
}
[data-testid="stSelectboxVirtualDropdown"] [role="listbox"] {
    background:var(--panel-solid) !important;
    color:var(--text) !important;
}
[data-testid="stSelectboxVirtualDropdown"] [role="option"] {
    color:var(--text) !important;
}
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
[data-testid="stSelectboxVirtualDropdown"] [role="option"][data-selected="true"] {
    background:var(--accent-soft) !important;
}

[data-testid="stPopoverBody"] {
    border:1px solid var(--line-strong) !important;
    border-radius:14px !important;
    background:var(--panel-solid) !important;
    color:var(--text) !important;
    box-shadow:0 14px 36px rgba(16,42,67,.2) !important;
}
[data-testid="stPopoverBody"] [data-testid="stRadioOption"] {
    border-radius:9px;
    color:var(--text) !important;
}
[data-testid="stPopoverBody"] [data-testid="stRadioOption"] p {
    color:var(--text) !important;
}
[data-testid="stPopoverBody"] [data-testid="stRadioOption"]:hover,
[data-testid="stPopoverBody"] [data-testid="stRadioOption"]:has(input:checked) {
    background:var(--accent-soft) !important;
}
[data-testid="stPopoverBody"] [data-testid="stRadioOption"] > div > div:first-child {
    background:var(--panel-solid) !important;
    border-color:var(--line-strong) !important;
}
[data-testid="stPopoverBody"] [data-testid="stRadioOption"][data-selected="true"]
> div > div:first-child {
    background:var(--accent) !important;
    border-color:var(--accent) !important;
}
[data-testid="stPopoverBody"] [data-testid="stRadioOption"] > div > div:first-child > div {
    background:var(--panel-solid) !important;
}

[data-testid="stTextInputRootElement"],
[data-testid="stNumberInputContainer"] {
    border:1px solid var(--line-strong) !important;
    border-radius:11px !important;
    background:var(--input-bg) !important;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within {
    border-color:var(--accent-strong) !important;
    box-shadow:0 0 0 1px var(--accent-strong) !important;
}
.stTextInput input, .stNumberInput input, .stTextArea textarea,
[data-baseweb="select"] > div, [data-baseweb="input"] > div {
    border-color:var(--line-strong) !important; border-radius:11px !important;
    background:var(--input-bg) !important; color:var(--text) !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
    border-color:var(--accent-strong) !important;
    box-shadow:0 0 0 1px var(--accent-strong) !important;
}
[data-testid="stNumberInputStepUp"],
[data-testid="stNumberInputStepDown"] {
    color:var(--text) !important;
    background:var(--panel-raised) !important;
}
[data-baseweb="select"] span, [data-baseweb="input"] input {color:var(--text) !important}
[data-baseweb="tag"] {background:var(--accent-soft) !important; color:var(--text) !important}
[data-baseweb="popover"], [data-baseweb="menu"] {background:var(--panel-solid) !important}
[role="option"]:hover {background:var(--accent-soft) !important}

[data-testid="stFileUploader"] section {
    border:1px dashed var(--line-strong); border-radius:16px;
    background:var(--uploader-bg); transition:border-color .15s ease, background .15s ease;
}
[data-testid="stFileUploader"] section:hover {
    border-color:var(--accent); background:var(--uploader-hover-bg);
}
[data-testid="stFileUploader"] button {
    border-radius:10px !important; border-color:var(--line-strong) !important;
    background:var(--panel-raised) !important; color:var(--text) !important;
}

[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border:1px solid var(--line); border-radius:15px; overflow:hidden;
}
[data-testid="stProgress"] > div > div {background:linear-gradient(90deg,var(--accent),#24b8d3)}
[data-testid="stAlert"] {border-radius:13px; border:0}
[data-testid="stAlertContainer"] {
    border-radius:13px; border:1px solid var(--line);
    background:var(--alert-info-bg) !important;
}
[data-testid="stAlertContentInfo"] {
    background:var(--alert-info-bg) !important; color:var(--accent) !important;
}
[data-testid="stAlertContentSuccess"] {background:var(--alert-success-bg) !important}
[data-testid="stAlertContentWarning"] {background:var(--alert-warning-bg) !important}
[data-testid="stAlertContentError"] {background:var(--alert-error-bg) !important}
[data-testid="stExpander"] {
    border:1px solid var(--line); border-radius:14px; background:var(--expander-bg);
}
[data-testid="stExpander"] summary {color:var(--text); font-weight:620}

.st-key-botes button {
    justify-content:flex-start; text-align:left; min-height:44px; padding:11px 14px;
    border-radius:12px; background:var(--collection-button-bg);
    border:1px solid var(--line); color:var(--text); font-weight:620;
}
.st-key-botes button[data-testid="stBaseButton-primary"] {
    border-color:var(--line-strong); background:linear-gradient(115deg,#102A43,#174763);
}
[class*="st-key-card_"] {
    background:var(--card-bg);
    border:1px solid var(--line); border-radius:18px; overflow:hidden;
    padding:0 0 13px; gap:.55rem;
    box-shadow:var(--card-shadow);
    transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
[class*="st-key-card_"]:hover {
    transform:translateY(-3px); border-color:var(--line-strong);
    box-shadow:var(--card-shadow-hover);
}
[class*="st-key-card_"] [data-testid="stMarkdownContainer"] p {margin:0}
[class*="st-key-card_"] [data-testid="stHorizontalBlock"] {padding:0 12px; flex-wrap:nowrap; gap:.25rem}
[class*="st-key-card_"] [data-testid="stColumn"] {min-width:0}
[class*="st-key-card_"] button {
    width:34px; height:34px; min-height:0; padding:0; border-radius:50%;
    background:var(--card-action-bg); border:1px solid var(--line); color:var(--text);
}
[class*="st-key-card_"] .card-link {display:block; color:inherit; text-decoration:none; cursor:pointer}
[class*="st-key-card_"] .card-link:hover .nm {color:var(--accent); text-decoration:underline; text-underline-offset:4px}
.ph {position:relative; width:100%; height:260px; overflow:hidden; background:var(--photo-bg)}
.ph img {display:block; width:100%; height:100%; object-fit:cover; object-position:top; transition:transform .35s ease}
.detail-photo {width:100%; max-width:260px; height:340px; overflow:hidden; border-radius:14px; background:var(--photo-bg)}
.detail-photo img {display:block; width:100%; height:100%; object-fit:cover; object-position:top}
.card-link:hover .ph img {transform:scale(1.035)}
.ph.empty {display:grid; place-items:center; background:linear-gradient(145deg,var(--c1),var(--c2))}
.ph .ini {font-size:46px; font-weight:800; opacity:.62; color:#fff}
.bg,.bp {
    position:absolute; top:10px; padding:5px 9px; border-radius:9px;
    font-size:10px; font-weight:750; letter-spacing:.045em;
    background:var(--badge-bg); border:1px solid var(--badge-border);
    backdrop-filter:blur(8px);
}
.bg {left:10px; text-transform:uppercase; max-width:62%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.bp {right:10px; color:var(--accent)}
.bp.complete {color:#102A43; background:var(--gold); border-color:var(--gold)}
.nm {padding:7px 14px 2px; font-weight:730; font-size:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.cnt {text-align:center; font-weight:700; font-size:14px; white-space:nowrap; color:var(--text)}

@media (max-width: 900px) {
    .block-container {padding:1.5rem 1.25rem 3rem}
    .hero {padding:24px}
}
@media (max-width: 600px) {
    .block-container {padding:1.2rem .8rem 2.5rem}
    .ttl b {font-size:19px}
    .hero {padding:20px; border-radius:20px}
    .ring:not(.sm) {--s:72px}
    [data-testid="stTabs"] [role="tab"] {padding:0 10px; font-size:12px}
}
</style>
"""
st.markdown(
    CSS.replace("THEME_LIGHT_QUERY", theme_media_query, 1),
    unsafe_allow_html=True,
)


def pct(parte, total):
    return float(parte) / float(total) * 100 if total else 0.0


def ring(v, sm=False):
    v = max(0, min(100, v))
    return f'<div class="ring{" sm" if sm else ""}" style="--v:{v:.0f}"><b>{v:.0f}%</b></div>'


def barra(v):
    return f'<div class="bar"><span style="width:{max(0, min(100, v)):.0f}%"></span></div>'


def card_html(r):
    nome = r.grupo if r.idol == GRUPO_COMPLETO else r.idol
    grupo = esc(r.grupo or "—")
    conclusao = " complete" if r.progresso >= 100 else ""
    badges = (f'<span class="bg">{grupo}</span>'
              f'<span class="bp{conclusao}">{r.progresso:.0f}%</span>')
    foto = _url(r.url_foto)
    if foto:
        ph = f'<div class="ph"><img src="{esc(foto, quote=True)}" referrerpolicy="no-referrer" loading="lazy">{badges}</div>'
    else:
        h = sum(map(ord, r.grupo or "x")) % 360
        ini = "".join(w[0] for w in nome.replace("-", " ").split()[:2]).upper() or "?"
        ph = (f'<div class="ph empty" style="--c1:hsl({h} 55% 32%);--c2:hsl({(h + 50) % 360} 55% 16%)">'
              f'<span class="ini">{esc(ini)}</span>{badges}</div>')
    return ph + f'<div class="nm">{esc(nome)}</div>'


# ---------------------------------------------------------------- Ações
def ajustar(id_, delta):
    run("UPDATE colecao SET possuo = GREATEST(0, LEAST(total, possuo + ?)) WHERE id = ?",
        (int(delta), int(id_)))


def selecionar_bot(nome):
    st.session_state["bot_sel"] = nome
    st.session_state["n_cards"] = 12


def mostrar_mais():
    st.session_state["n_cards"] = st.session_state.get("n_cards", 12) + 12


def adicionar_evento(card_id, membro_id=None):
    chave_membro = membro_id if membro_id is not None else "card"
    prefixo = f"evento_{card_id}_{chave_membro}"
    chave_nome = f"{prefixo}_nome"
    nome = st.session_state.get(chave_nome, "").strip()
    chave_erro = f"{prefixo}_erro"
    if not nome:
        st.session_state[chave_erro] = "Informe o nome do evento."
        return

    marcador = 1
    if eh_happy_birthday(nome):
        marcador = int(st.session_state.get(f"{prefixo}_marcadores", 1))
    run("INSERT INTO colecao_eventos "
        "(colecao_id, membro_id, nome, sigla, marcadores) VALUES (?,?,?,?,?)",
        (int(card_id), membro_id, nome, sigla_evento(nome), marcador))
    st.session_state[chave_nome] = ""
    st.session_state[f"{prefixo}_marcadores"] = 1
    st.session_state.pop(chave_erro, None)


def renderizar_eras_eventos(card_id, membro_id=None, nome_membro=None):
    sufixo = membro_id if membro_id is not None else "card"
    filtro_membro = "AND membro_id IS NOT DISTINCT FROM ?"
    parametros = (int(card_id), membro_id)
    eras = q("SELECT nome, sigla, diamantes FROM colecao_eras "
             f"WHERE colecao_id=? {filtro_membro} ORDER BY id", parametros)
    eventos = q("SELECT nome, sigla, marcadores FROM colecao_eventos "
                f"WHERE colecao_id=? {filtro_membro} ORDER BY id", parametros)
    total_diamantes = sum(int(era.diamantes) for era in eras.itertuples())
    total_marcadores = sum(int(evento.marcadores) for evento in eventos.itertuples())
    resumo = (f"{len(eras)} eras · {total_diamantes} 💎 · "
              f"{len(eventos)} eventos · {total_marcadores} marcadores")
    titulo = f"👤 {nome_membro} · {resumo}" if nome_membro else resumo

    if nome_membro:
        with st.expander(titulo, expanded=False):
            _renderizar_formularios_card(card_id, membro_id, sufixo, eras, eventos, resumo)
    else:
        _renderizar_formularios_card(card_id, membro_id, sufixo, eras, eventos, resumo)


def _renderizar_formularios_card(card_id, membro_id, sufixo, eras, eventos, resumo):
    st.caption(f"Resumo: {resumo}")
    col_eras, col_eventos = st.columns(2, gap="large")
    with col_eras:
        st.subheader("Eras")
        with st.form(f"form_era_{card_id}_{sufixo}", clear_on_submit=True):
            nome_era = st.text_input("Nome da era")
            sigla_era = st.text_input("Sigla da era")
            diamantes_era = st.selectbox(
                "Diamantes da era", [1, 2, 3], format_func=lambda n: "💎" * n,
                key=f"diamantes_era_{card_id}_{sufixo}",
            )
            enviar_era = st.form_submit_button("Adicionar era", type="primary")
        if enviar_era:
            if not nome_era.strip() or not sigla_era.strip():
                st.error("Informe o nome e a sigla da era.")
            else:
                run("INSERT INTO colecao_eras "
                    "(colecao_id, membro_id, nome, sigla, diamantes) VALUES (?,?,?,?,?)",
                    (int(card_id), membro_id, nome_era.strip(), sigla_era.strip(),
                     int(diamantes_era)))
                st.rerun()

        if eras.empty:
            st.info("Nenhuma era adicionada ainda.")
        else:
            for era in eras.itertuples():
                diamantes = "💎" * int(era.diamantes)
                st.markdown(f"**{esc(era.nome)}** · `{esc(era.sigla)}` · {diamantes}")

    with col_eventos:
        st.subheader("Eventos")
        chave_membro = membro_id if membro_id is not None else "card"
        prefixo_evento = f"evento_{card_id}_{chave_membro}"
        chave_nome_evento = f"{prefixo_evento}_nome"
        nome_evento = st.text_input("Nome do evento", key=chave_nome_evento)
        sigla_gerada = sigla_evento(nome_evento)
        st.caption(f"Sigla gerada: {sigla_gerada or '—'}")
        chave_marcadores = f"{prefixo_evento}_marcadores"
        if eh_happy_birthday(nome_evento):
            st.selectbox("Marcadores do Happy Birthday", [1, 2], key=chave_marcadores)
        else:
            st.caption("Este evento usa 1 marcador.")
        chave_erro = f"{prefixo_evento}_erro"
        if st.session_state.get(chave_erro):
            st.error(st.session_state[chave_erro])
        st.button("Adicionar evento", key=f"adicionar_{prefixo_evento}",
                  type="primary", on_click=adicionar_evento,
                  args=(int(card_id), membro_id))

        if eventos.empty:
            st.info("Nenhum evento adicionado ainda.")
        else:
            for evento in eventos.itertuples():
                st.markdown(
                    f"{icone_evento(evento.nome)} **{esc(evento.nome)}** · "
                    f"`{esc(evento.sigla)}` · Marcadores: {int(evento.marcadores)}"
                )


@st.dialog("Adicionar idol / bot")
def dialog_adicionar():
    with st.form("novo", clear_on_submit=True):
        idol = st.text_input("Idol / Solista")
        grupo = st.text_input("Grupo (ou SOLO)")
        bot = st.selectbox("Bot", BOTS)
        c4, c5 = st.columns(2)
        cat = c4.selectbox("Categoria", CATEGORIAS)
        prio = c5.selectbox("Prioridade", PRIORIDADES, index=1)
        c6, c7 = st.columns(2)
        total = c6.number_input("Total de cartas", min_value=0, value=0)
        possuo = c7.number_input("Quantas eu tenho", min_value=0, value=0)
        if st.form_submit_button("Adicionar", type="primary"):
            if not idol.strip():
                st.error("Informe o nome.")
            elif possuo > total:
                st.error("Você não pode ter mais cartas do que o total.")
            else:
                try:
                    run("INSERT INTO colecao (bot, grupo, idol, categoria, prioridade, total, possuo) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (bot, grupo.strip(), idol.strip(), cat, prio, int(total), int(possuo)))
                    st.rerun()
                except psycopg2.IntegrityError:
                    st.error(f"{idol} ({grupo}) já existe no bot {bot}. Edite na aba Tabela.")


# ---------------------------------------------------------------- Dados
df_all = q(
    "SELECT id, bot, grupo, idol, categoria, prioridade, total, possuo, image_url, "
    "descricao_pt, descricao_url, descricao_versao FROM colecao"
)
df_all["progresso"] = (df_all["possuo"] / df_all["total"].where(df_all["total"] > 0) * 100).fillna(0)
df_all["faltam"] = df_all["total"] - df_all["possuo"]
df_all["url_foto"] = df_all["image_url"].map(_url)
ORDENS = ["Idol (A–Z)", "Grupo (A–Z)", "Menor progresso", "Maior progresso",
          "Mais cartas faltando", "Prioridade"]

# ---------------------------------------------------------------- Detalhes do card
card_selecionado = st.query_params.get("card")
if card_selecionado:
    try:
        card_selecionado = int(card_selecionado)
    except ValueError:
        st.error("O identificador do card na URL é inválido.")
        st.query_params.pop("card", None)
        st.stop()

    c_voltar, c_tema = st.columns([6, 2], vertical_alignment="center")
    botao_tema(c_tema)
    selecionado = df_all[df_all["id"] == card_selecionado]
    if selecionado.empty:
        st.warning("Este card não está mais na coleção.")
        if c_voltar.button("← Voltar ao painel"):
            st.query_params.pop("card", None)
            st.rerun()
        st.stop()

    card = selecionado.iloc[0]
    if c_voltar.button("← Voltar ao painel"):
        st.query_params.pop("card", None)
        st.rerun()
    st.title(card["grupo"] if card["idol"] == GRUPO_COMPLETO else card["idol"])
    st.caption(f'{card["grupo"]} · Bot {card["bot"]}')

    descricao_card = card["descricao_pt"]
    fonte_descricao = card["descricao_url"]
    descricao_card_em_ingles = False
    descricao_card_desatualizada = (
        pd.isna(card["descricao_versao"])
        or int(card["descricao_versao"]) < VERSAO_DESCRICAO
    )
    if descricao_card_desatualizada:
        descricao_card = None
        fonte_descricao = None
    original_card = descricao_original("card", card_selecionado)
    if (
        (pd.isna(descricao_card) or not str(descricao_card).strip())
        and original_card
    ):
        descricao_card, fonte_descricao = original_card
        descricao_card_em_ingles = True
    if (
        pd.isna(descricao_card) or not str(descricao_card).strip()
        or descricao_card_desatualizada
    ) and descricao_pode_carregar("card", card_selecionado):
        try:
            with st.spinner("Buscando no KProfiles e traduzindo para português..."):
                descricao_card, fonte_descricao = atualizar_descricao_card(
                    int(card_selecionado), card["idol"], card["grupo"]
                )
            registrar_sucesso_descricao("card", card_selecionado)
        except MyMemoryRateLimited as erro:
            st.warning(f"A tradução está temporariamente pausada: {erro}")
            registrar_falha_descricao("card", card_selecionado)
        except KProfilesRateLimited as erro:
            st.warning(str(erro))
            registrar_falha_descricao("card", card_selecionado)
        except (requests.RequestException, ValueError) as erro:
            st.error(f"Não foi possível carregar a descrição: {erro}")
            registrar_falha_descricao("card", card_selecionado)
        original_card = descricao_original("card", card_selecionado)
        if original_card:
            descricao_card, fonte_descricao = original_card
            descricao_card_em_ingles = True

    coluna_foto, coluna_sobre = st.columns([1, 2], gap="large", vertical_alignment="top")
    with coluna_foto:
        if card["url_foto"]:
            st.markdown(
                f'<div class="detail-photo"><img src="{esc(card["url_foto"], quote=True)}" '
                'alt="Foto do card" referrerpolicy="no-referrer" loading="lazy"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Ainda não há uma imagem para este card.")
    with coluna_sobre:
        st.subheader("Sobre")
        if pd.notna(descricao_card) and str(descricao_card).strip():
            st.write(str(descricao_card))
            if pd.notna(fonte_descricao) and fonte_descricao:
                texto_fonte = (
                    "texto original em inglês"
                    if descricao_card_em_ingles
                    else "tradução automática"
                )
                st.caption(f"Fonte: [KProfiles]({fonte_descricao}) · {texto_fonte}")
        else:
            st.caption("O perfil ainda não tem um resumo disponível.")

    grupo_completo = card["idol"] == GRUPO_COMPLETO
    if grupo_completo:
        membros = q("SELECT id, nome, descricao_pt, descricao_url, descricao_versao "
                    "FROM colecao_membros "
                    "WHERE colecao_id=? ORDER BY nome",
                    (int(card_selecionado),))
        roster_url = None
        roster = None
        st.subheader("Membros")
        try:
            with st.spinner(f"Conferindo os integrantes de {card['grupo']} no KProfiles..."):
                roster, roster_url = buscar_integrantes_kprofiles(card["grupo"])
            existentes = {
                str(membro.nome).strip().casefold()
                for membro in membros.itertuples()
            }
            novos = [
                nome for nome in roster
                if nome.strip().casefold() not in existentes
            ]
            if novos:
                run_many(
                    "INSERT INTO colecao_membros (colecao_id, nome) VALUES (?,?)",
                    [(int(card_selecionado), nome) for nome in novos],
                )
                membros = q("SELECT id, nome, descricao_pt, descricao_url, descricao_versao "
                            "FROM colecao_membros "
                            "WHERE colecao_id=? ORDER BY nome",
                            (int(card_selecionado),))
        except (requests.RequestException, ValueError) as erro:
            st.warning(f"Não foi possível verificar os integrantes no KProfiles: {erro}")
            if st.button("Tentar buscar novamente", key=f"buscar_membros_{card_selecionado}"):
                st.rerun()

        if roster_url:
            st.markdown(f"Fonte conferida: [KProfiles]({roster_url})")

        if membros.empty:
            st.info("Os blocos dos integrantes aparecerão quando a lista for encontrada.")
        else:
            membros_por_nome = {
                str(membro.nome).strip().casefold(): membro
                for membro in membros.itertuples()
            }
            ordem_membros = []
            if roster:
                ordem_membros.extend(
                    membros_por_nome[nome.strip().casefold()]
                    for nome in roster
                    if nome.strip().casefold() in membros_por_nome
                )
                nomes_fonte = {nome.strip().casefold() for nome in roster}
                adicionais = [
                    membro for chave, membro in membros_por_nome.items()
                    if chave not in nomes_fonte
                ]
                if adicionais:
                    st.warning(
                        "Há integrantes salvos que não aparecem na lista atual do KProfiles. "
                        "Eles e seus dados foram mantidos."
                    )
                    ordem_membros.extend(adicionais)
            else:
                ordem_membros = list(membros.itertuples())

            for membro in ordem_membros:
                descricao_membro = membro.descricao_pt
                fonte_membro = membro.descricao_url
                descricao_membro_em_ingles = False
                descricao_membro_desatualizada = (
                    pd.isna(membro.descricao_versao)
                    or int(membro.descricao_versao) < VERSAO_DESCRICAO
                )
                if descricao_membro_desatualizada:
                    descricao_membro = None
                    fonte_membro = None
                original_membro = descricao_original("membro", membro.id)
                if (
                    (pd.isna(descricao_membro) or not str(descricao_membro).strip())
                    and original_membro
                ):
                    descricao_membro, fonte_membro = original_membro
                    descricao_membro_em_ingles = True
                st.markdown(f"**{esc(str(membro.nome))}**")
                resumo_vazio = (
                    pd.isna(descricao_membro) or not str(descricao_membro).strip()
                )
                pode_buscar = descricao_pode_carregar("membro", membro.id)
                if resumo_vazio and pode_buscar:
                    if st.button(
                        f"Carregar resumo de {membro.nome}",
                        key=f"carregar_resumo_membro_{membro.id}",
                    ):
                        try:
                            with st.spinner(f"Carregando resumo de {membro.nome}..."):
                                descricao_membro, fonte_membro = atualizar_descricao_membro(
                                    int(membro.id), membro.nome, card["grupo"]
                                )
                            registrar_sucesso_descricao("membro", membro.id)
                        except MyMemoryRateLimited as erro:
                            registrar_falha_descricao("membro", membro.id)
                            st.warning(f"A tradução está temporariamente pausada: {erro}")
                        except KProfilesRateLimited as erro:
                            registrar_falha_descricao("membro", membro.id)
                            st.warning(str(erro))
                        except (requests.RequestException, ValueError) as erro:
                            registrar_falha_descricao("membro", membro.id)
                            st.caption(f"Resumo de {membro.nome} indisponível: {erro}")
                        original_membro = descricao_original("membro", membro.id)
                        if original_membro:
                            descricao_membro, fonte_membro = original_membro
                            descricao_membro_em_ingles = True
                elif resumo_vazio:
                    st.caption(
                        f"Resumo de {membro.nome} temporariamente indisponível. "
                        "Tente novamente mais tarde."
                    )
                if pd.notna(descricao_membro) and str(descricao_membro).strip():
                    st.markdown(str(descricao_membro))
                    if pd.notna(fonte_membro) and fonte_membro:
                        texto_fonte = (
                            "texto original em inglês"
                            if descricao_membro_em_ingles
                            else "tradução automática"
                        )
                        st.caption(f"Fonte: [KProfiles]({fonte_membro}) · {texto_fonte}")
                renderizar_eras_eventos(
                    int(card_selecionado), int(membro.id), membro.nome
                )
        eras_sem_membro = q(
            "SELECT nome, sigla, diamantes FROM colecao_eras "
            "WHERE colecao_id=? AND membro_id IS NULL ORDER BY id",
            (int(card_selecionado),),
        )
        eventos_sem_membro = q(
            "SELECT nome, sigla, marcadores FROM colecao_eventos "
            "WHERE colecao_id=? AND membro_id IS NULL ORDER BY id",
            (int(card_selecionado),),
        )
        if not eras_sem_membro.empty or not eventos_sem_membro.empty:
            with st.expander("Registros antigos sem integrante", expanded=False):
                st.caption("Estes registros foram adicionados antes da divisão por membro.")
                for era in eras_sem_membro.itertuples():
                    diamantes = "💎" * int(era.diamantes)
                    st.markdown(f"**{esc(era.nome)}** · `{esc(era.sigla)}` · {diamantes}")
                for evento in eventos_sem_membro.itertuples():
                    st.markdown(
                        f"{icone_evento(evento.nome)} **{esc(evento.nome)}** · "
                        f"`{esc(evento.sigla)}` · Marcadores: {int(evento.marcadores)}"
                    )
    else:
        renderizar_eras_eventos(int(card_selecionado))
    st.stop()

# ---------------------------------------------------------------- Cabeçalho
tot_g, pos_g = int(df_all["total"].sum()), int(df_all["possuo"].sum())
c_tit, c_pill, c_tema, c_btn, c_user = st.columns(
    [4.2, 2.4, 1.8, 2.4, 1.0], vertical_alignment="center"
)
c_tit.markdown('<div class="ttl"><div class="logo">💿</div><div><b>BinderLog</b><br>'
               '<span class="mut">Coleção de bots do Discord</span></div></div>', unsafe_allow_html=True)
c_pill.markdown(f'<div class="pill">{ring(pct(pos_g, tot_g), sm=True)} Coleção completa</div>',
                unsafe_allow_html=True)
botao_tema(c_tema)
if c_btn.button("＋  Adicionar idol / bot", type="primary", width="stretch"):
    dialog_adicionar()
nome_conta = st.session_state["authenticated_user_name"]
email_conta = st.session_state["authenticated_user_email"]
foto_conta = st.session_state.get("authenticated_user_picture", "")
if foto_conta.startswith("https://"):
    avatar_html = (
        f'<img src="{esc(foto_conta, quote=True)}" alt="Foto do perfil" '
        'style="width:42px;height:42px;border-radius:50%;object-fit:cover;'
        'display:block;">'
    )
else:
    iniciais = esc("".join(parte[0] for parte in nome_conta.split()[:2]).upper())
    avatar_html = (
        '<div aria-label="Foto do perfil indisponível" '
        'style="width:42px;height:42px;border-radius:50%;background:#dbeafe;'
        'color:#1e3a8a;display:flex;align-items:center;justify-content:center;'
        'font-weight:700;">'
        f'{iniciais}</div>'
    )
with c_user:
    c_foto, c_menu = st.columns([1.1, 0.9], vertical_alignment="center")
    c_foto.markdown(avatar_html, unsafe_allow_html=True)
    with c_menu.popover("⋮", help="Conta conectada"):
        st.markdown(f"**{esc(nome_conta)}**")
        st.caption(email_conta)
        if st.button("Sair da conta", key="logout_button", width="stretch"):
            st.logout()

tab_painel, tab_tabela, tab_fotos, tab_imp = st.tabs(["Painel", "Tabela", "Fotos", "Importar CSV"])

# ---------------------------------------------------------------- Painel
with tab_painel:
    if df_all.empty:
        st.info("Nada por aqui ainda. Use **Importar CSV** ou o botão **Adicionar idol / bot**.")
    else:
        bots_ord = ["Todos"] + sorted(df_all["bot"].unique())
        if st.session_state.get("bot_sel") not in bots_ord:
            st.session_state["bot_sel"] = "Todos"
        sel = st.session_state["bot_sel"]
        base_df = df_all if sel == "Todos" else df_all[df_all["bot"] == sel]
        t, p = int(base_df["total"].sum()), int(base_df["possuo"].sum())
        v = pct(p, t)
        st.markdown(
            f'<div class="hero"><div><div class="lbl">PROGRESSO GERAL</div><div class="big">{v:.0f}%</div>'
            f'<div class="sub">{p} de {t} cartas coletadas</div></div>{ring(v)}{barra(v)}</div>',
            unsafe_allow_html=True)

        st.subheader("Coleções mais avançadas por bot")
        bots_com_colecao = sorted(df_all["bot"].dropna().unique())
        for bot in bots_com_colecao:
            st.markdown(f"### {esc(bot)}")
            destaques = (
                df_all[df_all["bot"] == bot]
                .sort_values(
                    ["progresso", "faltam", "idol"],
                    ascending=[False, True, True],
                    kind="stable",
                )
                .head(3)
            )
            colunas_colecoes = st.columns(3, gap="medium")
            for coluna, destaque in zip(colunas_colecoes, destaques.itertuples()):
                with coluna:
                    with st.container(border=True):
                        nome = (
                            destaque.grupo
                            if destaque.idol == GRUPO_COMPLETO
                            else destaque.idol
                        )
                        if destaque.idol != GRUPO_COMPLETO and destaque.grupo:
                            nome = f"{nome} · {destaque.grupo}"
                        progresso = max(0.0, min(100.0, float(destaque.progresso)))
                        st.markdown(f"**{esc(nome)}**")
                        st.progress(progresso / 100)
                        st.caption(
                            f"{progresso:.0f}% · {int(destaque.possuo)} / "
                            f"{int(destaque.total)} cartas"
                        )

        esq, dir_ = st.columns([1, 3], gap="large")
        with esq:
            st.markdown('<div class="lbl">BOTS</div>', unsafe_allow_html=True)
            with st.container(key="botes"):
                for b in bots_ord:
                    sub = df_all if b == "Todos" else df_all[df_all["bot"] == b]
                    vb = pct(sub["possuo"].sum(), sub["total"].sum())
                    st.button(f"{b}  ·  {len(sub)} idols", key=f"bot_{b}", width="stretch",
                              type="primary" if b == sel else "secondary",
                              on_click=selecionar_bot, args=(b,))
                    st.markdown(f'{barra(vb)}<div class="brow"><span>Progresso</span><b>{vb:.0f}%</b></div>',
                                unsafe_allow_html=True)
        with dir_:
            f1, f2, f3 = st.columns([3, 2, 2])
            busca = f1.text_input("Buscar", placeholder="Buscar idol ou grupo",
                                  label_visibility="collapsed", key="p_busca")
            ordem = f2.selectbox("Ordenar", ORDENS, label_visibility="collapsed", key="p_ordem")
            prios = f3.multiselect("Prioridade", PRIORIDADES, placeholder="Prioridade",
                                   label_visibility="collapsed", key="p_prio")
            vis = base_df
            if busca:
                vis = vis[vis["idol"].str.contains(busca, case=False, regex=False)
                          | vis["grupo"].str.contains(busca, case=False, regex=False)]
            if prios:
                vis = vis[vis["prioridade"].isin(prios)]
            vis = ordenar(vis, ordem)
            vis = vis.copy()
            n = st.session_state.setdefault("n_cards", 12)
            st.markdown(f'<div class="hd"><h3>{"Todas as idols" if sel == "Todos" else esc(sel)}</h3>'
                        f'<span>{len(vis)} idols</span></div>', unsafe_allow_html=True)

            cols = st.columns(4)
            for i, r in enumerate(vis.head(n).itertuples()):
                with cols[i % 4]:
                    with st.container(key=f"card_{r.id}"):
                        nome_card = r.grupo if r.idol == GRUPO_COMPLETO else r.idol
                        st.markdown(
                            f'<a class="card-link" href="?card={int(r.id)}" target="_self" '
                            f'aria-label="Abrir detalhes de {esc(nome_card, quote=True)}">'
                            f'{card_html(r)}</a>',
                            unsafe_allow_html=True)
                        c1, c2, c3, c4 = st.columns([1, 1.7, 1, 1.1], vertical_alignment="center")
                        c1.button("−", key=f"m_{r.id}", on_click=ajustar, args=(r.id, -1),
                                  disabled=bool(r.possuo <= 0))
                        c2.markdown(f'<div class="cnt">{r.possuo}/{r.total}</div>', unsafe_allow_html=True)
                        c3.button("+", key=f"a_{r.id}", on_click=ajustar, args=(r.id, 1),
                                  disabled=bool(r.possuo >= r.total))
                        c4.markdown(ring(r.progresso, sm=True), unsafe_allow_html=True)
            if len(vis) > n:
                st.button(f"Mostrar mais ({len(vis) - n} restantes)", on_click=mostrar_mais,
                          width="stretch")

# ---------------------------------------------------------------- Tabela (edição em massa)
with tab_tabela:
    if df_all.empty:
        st.info("Nada por aqui ainda.")
    else:
        st.caption("Edite direto na tabela e clique em **Salvar alterações**. O total geral soma cada linha; "
                   "cartas compartilhadas entre membros do mesmo grupo podem ser contadas mais de uma vez.")
        f1, f2, f3, f4, f5 = st.columns(5)
        fb = f1.multiselect("Bot", sorted(df_all["bot"].unique()), key="t_bot")
        fg = f2.multiselect("Grupo", sorted(df_all["grupo"].unique(), key=str.casefold), key="t_grupo")
        fp = f3.multiselect("Prioridade", PRIORIDADES, key="t_prio")
        fc = f4.multiselect("Categoria", CATEGORIAS, key="t_cat")
        busca_t = f5.text_input("Buscar idol", key="t_busca")
        df = df_all
        if fb:
            df = df[df["bot"].isin(fb)]
        if fg:
            df = df[df["grupo"].isin(fg)]
        if fp:
            df = df[df["prioridade"].isin(fp)]
        if fc:
            df = df[df["categoria"].isin(fc)]
        if busca_t:
            df = df[df["idol"].str.contains(busca_t, case=False, regex=False)
                    | df["grupo"].str.contains(busca_t, case=False, regex=False)]
        df = ordenar(df, st.selectbox("Ordenar por", ORDENS, key="t_ordem")).copy()
        df["excluir"] = False

        edited = st.data_editor(
            df, hide_index=True, width="stretch",
            disabled=["id", "progresso", "faltam"],
            column_order=["bot", "grupo", "idol", "categoria", "prioridade",
                          "total", "possuo", "faltam", "progresso", "image_url", "excluir"],
            column_config={
                "bot": st.column_config.SelectboxColumn("Bot", options=BOTS),
                "grupo": "Grupo",
                "idol": "Idol",
                "categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS),
                "prioridade": st.column_config.SelectboxColumn("Prioridade", options=PRIORIDADES),
                "total": st.column_config.NumberColumn("Total", min_value=0, step=1),
                "possuo": st.column_config.NumberColumn("Tenho", min_value=0, step=1),
                "faltam": st.column_config.NumberColumn("Faltam"),
                "progresso": st.column_config.ProgressColumn(
                    "Progresso", min_value=0, max_value=100, format="%.0f%%"),
                "image_url": st.column_config.TextColumn("URL da foto"),
                "excluir": st.column_config.CheckboxColumn("Excluir"),
            },
        )
        if st.button("💾 Salvar alterações", type="primary"):
            erros = []
            for r in edited.itertuples():
                if r.excluir:
                    run("DELETE FROM colecao WHERE id=?", (int(r.id),))
                elif r.total < 0 or r.possuo < 0:
                    erros.append(f"{r.idol} ({r.bot}): valores não podem ser negativos.")
                elif r.possuo > r.total:
                    erros.append(f"{r.idol} ({r.bot}): 'Tenho' maior que 'Total'.")
                else:
                    try:
                        run("UPDATE colecao SET bot=?, grupo=?, idol=?, categoria=?, prioridade=?, "
                            "total=?, possuo=?, image_url=? WHERE id=?",
                            (r.bot, r.grupo, r.idol, r.categoria, r.prioridade,
                             int(r.total), int(r.possuo), _url(r.image_url), int(r.id)))
                    except psycopg2.IntegrityError:
                        erros.append(f"{r.idol} ({r.grupo}) já existe no bot {r.bot}.")
            if erros:
                for e in erros:
                    st.error(e)
            else:
                st.rerun()
        st.download_button("⬇️ Baixar CSV", q("SELECT * FROM colecao").to_csv(index=False),
                           "binderlog.csv", "text/csv")

# ---------------------------------------------------------------- Fotos
with tab_fotos:
    if df_all.empty:
        st.info("Importe ou adicione idols primeiro.")
    else:
        st.caption(
            "As buscas usam KProfiles primeiro e kpopping.com como alternativa. "
            "Os resultados ficam em cache por até 24 horas."
        )
        if time.time() < st.session_state.get("kpopping_fotos_cooldown_ate", 0):
            st.info(
                "kpopping.com está temporariamente pausado após limitar uma busca. "
                "O KProfiles continua disponível."
            )

        with st.container(border=True):
            st.subheader("Buscar fotos em lote")
            fb2 = st.multiselect(
                "Filtrar por bot (vazio = todos)",
                sorted(df_all["bot"].unique()),
                placeholder="Escolha os bots",
                key="f_bots",
            )
            dff = df_all[df_all["bot"].isin(fb2)] if fb2 else df_all
            dff = ordenar(dff, "Idol (A–Z)")
            contagem = dff["url_foto"].dropna().value_counts()
            repetidas = set(contagem[contagem > 1].index)
            falta = dff["url_foto"].isna()
            rep = dff["url_foto"].isin(repetidas)
            modo = st.radio(
                "Buscar fotos para",
                ["Só as que faltam", "Faltam + repetidas", "Todas (substituir)"],
                horizontal=True,
                key="f_modo",
            )
            alvo = {
                "Só as que faltam": dff[falta],
                "Faltam + repetidas": dff[falta | rep],
                "Todas (substituir)": dff,
            }[modo]
            c_limite, c_busca = st.columns(
                [1, 2], vertical_alignment="bottom"
            )
            limite = c_limite.number_input(
                "Limite por busca",
                min_value=1,
                max_value=100,
                value=30,
                key="f_lim",
            )
            if c_busca.button(
                f"🔎 Buscar fotos ({len(alvo)} idols)",
                disabled=alvo.empty,
                width="stretch",
            ):
                barra_p = st.progress(0.0)
                achou, falhou = 0, []
                pausa_kprofiles = None
                alvo = alvo.head(int(limite))
                for i, r in enumerate(alvo.itertuples(), 1):
                    try:
                        atual = _url(r.url_foto) if modo != "Só as que faltam" else None
                        if trocar_foto(r.id, r.idol, r.grupo, atual):
                            achou += 1
                        else:
                            falhou.append(f"{r.idol} ({r.grupo})")
                    except KProfilesRateLimited as e:
                        pausa_kprofiles = str(e)
                        barra_p.progress(i / len(alvo))
                        break
                    except Exception as e:
                        falhou.append(f"{r.idol} ({r.grupo}): {e}")
                    barra_p.progress(i / len(alvo))
                    time.sleep(0.2)
                st.success(f"{achou} fotos atualizadas.")
                if pausa_kprofiles:
                    st.warning(
                        f"{pausa_kprofiles} O restante da busca em lote foi interrompido."
                    )
                if falhou:
                    st.warning(
                        "Sem foto nova: " + "; ".join(falhou)
                        + ". Use o ajuste individual abaixo."
                    )
                if not pausa_kprofiles and not falhou:
                    st.rerun()
            st.caption(f"{int(falta.sum())} sem foto · {int(rep.sum())} repetidas")

        with st.container(border=True):
            st.subheader("Ajustar foto individual")
            rotulo = {
                int(r.id): f"{r.idol} — {r.grupo} ({r.bot})"
                for r in ordenar(df_all, "Idol (A–Z)").itertuples()
            }
            sel_id = st.selectbox(
                "Idol",
                list(rotulo),
                format_func=rotulo.get,
                key="f_idol",
            )
            linha = df_all[df_all["id"] == sel_id].iloc[0]
            atual = _url(linha["url_foto"])
            g1, g2 = st.columns([1, 2], gap="large", vertical_alignment="center")
            with g1:
                if atual:
                    st.image(atual, width=220)
                else:
                    st.info("Este card ainda não tem foto.")
            with g2:
                if st.button(
                    "🔄 Buscar outra foto",
                    key="f_troca",
                    width="stretch",
                ):
                    try:
                        if trocar_foto(sel_id, linha["idol"], linha["grupo"], atual):
                            st.rerun()
                        else:
                            st.warning("Não achei outra foto. Cole uma URL abaixo.")
                    except KProfilesRateLimited as e:
                        st.warning(str(e))
                    except Exception as e:
                        st.error(str(e))
                nova = st.text_input("URL direta da foto", key=f"f_url_{sel_id}")
                if st.button(
                    "Salvar URL",
                    key="f_salva",
                    disabled=not _url(nova),
                    width="stretch",
                ):
                    run(
                        "UPDATE colecao SET image_url=? WHERE id=?",
                        (_url(nova), int(sel_id)),
                    )
                    st.rerun()

# ---------------------------------------------------------------- Importar CSV
with tab_imp:
    st.subheader("Importar coleção da Garam")
    st.caption("O arquivo Bancodedados é obrigatório e contém o total e a quantidade adquirida. "
               "Priolist é opcional e preenche prioridade e categoria. "
               "Idols já existentes serão atualizados.")
    bot_imp = st.selectbox("Bot", BOTS, key="bot_imp")
    f_banco = st.file_uploader("Bancodedados (.csv)", type="csv", key="f_banco")
    f_prio = st.file_uploader("Priolist (.csv) — opcional", type="csv", key="f_prio")
    if f_banco:
        try:
            prev, avisos = parse_garam(f_banco, f_prio)
            st.divider()
            st.subheader("Prévia da importação")
            st.caption(f"{len(prev)} linhas prontas para importar")
            if avisos:
                with st.expander(f"⚠️ {len(avisos)} aviso(s) na leitura do CSV"):
                    for a in avisos:
                        st.write("• " + a)
            st.dataframe(
                prev,
                hide_index=True,
                width="stretch",
                height=520,
                column_config={
                    "grupo": st.column_config.TextColumn("Grupo", width="medium"),
                    "idol": st.column_config.TextColumn("Idol", width="medium"),
                    "total": st.column_config.NumberColumn("Total", width="small"),
                    "possuo": st.column_config.NumberColumn("Tenho", width="small"),
                    "categoria": st.column_config.TextColumn("Categoria", width="small"),
                    "prioridade": st.column_config.TextColumn("Prioridade", width="small"),
                },
            )
            if st.button("Importar CSV", type="primary", width="stretch"):
                run_many(UPSERT, [(bot_imp, r.grupo, r.idol, r.categoria, r.prioridade,
                                   int(r.total), int(r.possuo)) for r in prev.itertuples()])
                st.success(f"{len(prev)} linhas importadas para {bot_imp}!")
        except Exception as e:
            st.error(str(e))
