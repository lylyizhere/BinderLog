import os
import random
import re
import time
import tomllib
from html import escape as esc
from contextlib import closing
from pathlib import Path

import pandas as pd
import psycopg2
import requests
import streamlit as st

from kprofiles import (
    KProfilesRateLimited,
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
VERSAO_DESCRICAO = 7

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
    return psycopg2.connect(url)


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
        descricao_versao INTEGER NOT NULL DEFAULT 0,
        UNIQUE (bot, grupo, idol))""")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS image_url TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS descricao_pt TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS descricao_url TEXT")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS descricao_versao "
        "INTEGER NOT NULL DEFAULT 0")
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


init_db()


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


class WikipediaRateLimited(Exception):
    pass


@st.cache_data(ttl=86400, show_spinner=False)
def _imagens_wikipedia(tipo, base, grupo):
    alvo = grupo if tipo == "grupo" else PESSOA_ALIAS_BUSCA.get(base.casefold(), base)
    cabecalhos = {"User-Agent": "BinderLog/1.0 (K-pop collection tracker)"}

    alvo_normalizado = _normalizar_nome_grupo(alvo)
    titulo = None
    for consulta in _termos_busca_imagem(tipo, base, grupo):
        time.sleep(random.uniform(0.0005, 0.0007))
        resposta = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": consulta,
                "srlimit": 5,
                "format": "json",
            },
            headers=cabecalhos,
            timeout=20,
        )
        if resposta.status_code == 429:
            raise WikipediaRateLimited("A API da Wikipédia limitou as buscas (HTTP 429).")
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise ValueError("A API da Wikipédia retornou uma resposta inválida.")
        resultados = (dados.get("query") or {}).get("search", [])
        if not isinstance(resultados, list):
            raise ValueError("A API da Wikipédia retornou resultados em formato inválido.")
        titulos = [
            item.get("title", "")
            for item in resultados
            if isinstance(item, dict)
            and alvo_normalizado
            and alvo_normalizado in _normalizar_nome_grupo(item.get("title", ""))
        ]
        if titulos:
            titulo = min(
                titulos,
                key=lambda item: (
                    len(_normalizar_nome_grupo(item)) - len(alvo_normalizado),
                    _normalizar_nome_grupo(item).find(alvo_normalizado),
                ),
            )
            break
    if not titulo:
        return []

    membros_grupo = []
    if tipo == "grupo":
        try:
            membros_grupo, _ = buscar_integrantes_kprofiles(grupo)
        except KProfilesRateLimited:
            raise
        except (requests.RequestException, ValueError) as erro:
            raise ValueError(
                f"Não foi possível confirmar os integrantes de {grupo}; "
                "a busca não usará fotos que possam ser de uma integrante só."
            ) from erro

    imagens = []
    consultas = (
        {
            "action": "query",
            "titles": titulo,
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": 500,
            "format": "json",
        },
        {
            "action": "query",
            "generator": "images",
            "titles": titulo,
            "gimlimit": 40,
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": 500,
            "format": "json",
        },
    )
    for parametros in consultas:
        time.sleep(random.uniform(0.0005, 0.0007))
        resposta = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params=parametros,
            headers=cabecalhos,
            timeout=20,
        )
        if resposta.status_code == 429:
            raise WikipediaRateLimited("A API da Wikipédia limitou as buscas (HTTP 429).")
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise ValueError("A API da Wikipédia retornou uma resposta inválida.")
        paginas = (dados.get("query") or {}).get("pages") or {}
        for pagina in paginas.values():
            if not isinstance(pagina, dict):
                continue
            thumbnail = pagina.get("thumbnail", {})
            url = thumbnail.get("source") if isinstance(thumbnail, dict) else None
            info = (pagina.get("imageinfo") or [{}])[0]
            if not url and isinstance(info, dict):
                if info.get("mime") not in ("image/jpeg", "image/png"):
                    continue
                url = info.get("thumburl") or info.get("url")
            titulo_imagem = pagina.get("pageimage") or pagina.get("title", "")
            titulo_imagem = str(titulo_imagem).rsplit("/", 1)[-1]
            nome_arquivo = _normalizar_nome_grupo(titulo_imagem)
            if nome_arquivo.endswith(("svg", "logo", "flag", "symbol", "signature", "map")):
                continue
            if tipo == "grupo":
                if alvo_normalizado not in nome_arquivo or any(
                    nome_aparece_em_texto(membro, titulo_imagem)
                    for membro in membros_grupo
                ):
                    continue
            elif alvo_normalizado not in nome_arquivo:
                continue
            if isinstance(url, str) and url.startswith("https://"):
                url = url.split("?", 1)[0]
                if url not in imagens:
                    imagens.append(url)
    return imagens[:12]


def buscar_candidatas(tipo, base, grupo):
    """Combina imagens encontradas no KProfiles e na Wikipedia."""
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
    if time.time() >= st.session_state.get("wikipedia_fotos_cooldown_ate", 0):
        try:
            candidatas.extend(_imagens_wikipedia(tipo, base, grupo))
        except KProfilesRateLimited:
            raise
        except WikipediaRateLimited as erro:
            st.session_state["wikipedia_fotos_cooldown_ate"] = time.time() + 3600
            erros.append(f"Wikipedia: {erro}")
        except (requests.RequestException, ValueError, KeyError, TypeError) as erro:
            erros.append(f"Wikipedia: {erro}")
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
    traducao = traduzir_descricao_ptbr(perfil["descricao"])
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
    traducao = traduzir_descricao_ptbr(perfil["descricao"])
    run(
        "UPDATE colecao_membros SET descricao_pt=?, descricao_url=?, descricao_versao=? "
        "WHERE id=?",
        (traducao, perfil["url"], VERSAO_DESCRICAO, int(membro_id)),
    )
    return traducao, perfil["url"]


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
    ON CONFLICT (bot, grupo, idol) DO UPDATE SET
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


# ---------------------------------------------------------------- Visual (tema escuro roxo)
CSS = """
<style>
:root{--bg:#0a0c14;--card:#121626;--line:rgba(255,255,255,.08);--p:#8b5cf6;--p2:#a78bfa;--g:#14b8a6;--mut:#8b90a8;}
.stApp{background:radial-gradient(1100px 520px at 85% -10%,rgba(139,92,246,.14),transparent),var(--bg);}
#MainMenu,footer{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1200px;padding-top:2rem}
.mut{color:var(--mut);font-size:13px}
.ttl{display:flex;gap:12px;align-items:center;line-height:1.25}
.ttl b{font-size:20px}
.logo{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,#6d4aff,#38bdf8);font-size:22px}
.pill{display:flex;gap:10px;align-items:center;justify-content:center;padding:8px 14px;border-radius:999px;background:var(--card);border:1px solid var(--line);font-size:13px}
.lbl{font-size:12px;letter-spacing:.12em;color:var(--mut);font-weight:600;margin-bottom:8px}
.hero{display:grid;grid-template-columns:1fr auto;gap:14px 24px;align-items:center;padding:28px;margin:8px 0 22px;border-radius:22px;border:1px solid var(--line);background:linear-gradient(135deg,#171b33,#0f2a30)}
.hero .big{font-size:64px;font-weight:800;line-height:1;background:linear-gradient(90deg,#8b5cf6,#a78bfa);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero .sub{color:#b9bdd3;margin-top:10px}
.hero .bar{grid-column:1/-1}
.bar{height:8px;border-radius:99px;background:#1e2338;overflow:hidden}
.bar>span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#8b5cf6,#14b8a6)}
.brow{display:flex;justify-content:space-between;font-size:12px;color:var(--mut);margin:2px 4px 14px}
.brow b{color:var(--p2)}
.ring{--s:96px;width:var(--s);height:var(--s);border-radius:50%;display:grid;place-items:center;position:relative;background:conic-gradient(var(--p) calc(var(--v)*1%),#1e2338 0)}
.ring::before{content:"";position:absolute;inset:9px;border-radius:50%;background:#10142a}
.ring b{position:relative;font-size:16px}
.ring.sm{--s:38px}.ring.sm::before{inset:4px}.ring.sm b{font-size:10px}
.hd{display:flex;justify-content:space-between;align-items:baseline;margin:14px 0 10px}
.hd h3{margin:0;font-size:22px}.hd span{color:var(--mut);font-size:13px}
.st-key-botes button{justify-content:flex-start;text-align:left;padding:14px 16px;border-radius:14px;background:var(--card);border:1px solid var(--line);color:#e8eaf2;font-weight:600}
.st-key-botes button[data-testid="stBaseButton-primary"]{border:1.5px solid var(--p);background:#16132d}
[class*="st-key-card_"]{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;padding:0 0 14px;gap:.55rem}
[class*="st-key-card_"] [data-testid="stMarkdownContainer"] p{margin:0}
[class*="st-key-card_"] [data-testid="stHorizontalBlock"]{padding:0 14px;flex-wrap:nowrap;gap:.3rem}
[class*="st-key-card_"] [data-testid="stColumn"]{min-width:0}
[class*="st-key-card_"] button{width:34px;height:34px;min-height:0;padding:0;border-radius:50%;background:#1b2036;border:1px solid var(--line);color:#e8eaf2}
[class*="st-key-card_"] .card-link{display:block;color:inherit;text-decoration:none;cursor:pointer}
[class*="st-key-card_"] .card-link:hover .nm{text-decoration:underline;text-decoration-color:var(--p2);text-underline-offset:4px}
.ph{position:relative;aspect-ratio:3/4;overflow:hidden;background:#1a1f35}
.ph img{width:100%;height:100%;object-fit:cover;object-position:top}
.ph.empty{display:grid;place-items:center;background:linear-gradient(135deg,var(--c1),var(--c2))}
.ph .ini{font-size:44px;font-weight:800;opacity:.55}
.bg,.bp{position:absolute;top:10px;padding:4px 9px;border-radius:8px;font-size:11px;font-weight:700;background:rgba(10,12,20,.62);backdrop-filter:blur(6px)}
.bg{left:10px;text-transform:uppercase;max-width:62%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bp{right:10px;color:var(--p2)}
.nm{padding:2px 14px 0;font-weight:700;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cnt{text-align:center;font-weight:700;font-size:15px;white-space:nowrap}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


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
    badges = f'<span class="bg">{grupo}</span><span class="bp">{r.progresso:.0f}%</span>'
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

    selecionado = df_all[df_all["id"] == card_selecionado]
    if selecionado.empty:
        st.warning("Este card não está mais na coleção.")
        if st.button("← Voltar ao painel"):
            st.query_params.pop("card", None)
            st.rerun()
        st.stop()

    card = selecionado.iloc[0]
    if st.button("← Voltar ao painel"):
        st.query_params.pop("card", None)
        st.rerun()
    st.title(card["grupo"] if card["idol"] == GRUPO_COMPLETO else card["idol"])
    st.caption(f'{card["grupo"]} · Bot {card["bot"]}')

    descricao_card = card["descricao_pt"]
    fonte_descricao = card["descricao_url"]
    descricao_card_desatualizada = (
        pd.isna(card["descricao_versao"])
        or int(card["descricao_versao"]) < VERSAO_DESCRICAO
    )
    if descricao_card_desatualizada:
        descricao_card = None
        fonte_descricao = None
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
        except KProfilesRateLimited as erro:
            st.warning(str(erro))
            registrar_falha_descricao("card", card_selecionado)
        except (requests.RequestException, ValueError) as erro:
            st.error(f"Não foi possível carregar a descrição: {erro}")
            registrar_falha_descricao("card", card_selecionado)

    coluna_foto, coluna_sobre = st.columns([1, 2], gap="large", vertical_alignment="top")
    with coluna_foto:
        if card["url_foto"]:
            st.image(card["url_foto"], width=260)
        else:
            st.info("Ainda não há uma imagem para este card.")
    with coluna_sobre:
        st.subheader("Sobre")
        if pd.notna(descricao_card) and str(descricao_card).strip():
            st.write(str(descricao_card))
            if pd.notna(fonte_descricao) and fonte_descricao:
                st.caption(f"Fonte: [KProfiles]({fonte_descricao}) · tradução automática")
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
        st.subheader("Membros do grupo")
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

            pausa_descricao_membros = False
            for membro in ordem_membros:
                descricao_membro = membro.descricao_pt
                fonte_membro = membro.descricao_url
                descricao_membro_desatualizada = (
                    pd.isna(membro.descricao_versao)
                    or int(membro.descricao_versao) < VERSAO_DESCRICAO
                )
                if descricao_membro_desatualizada:
                    descricao_membro = None
                    fonte_membro = None
                if (
                    (
                        pd.isna(descricao_membro)
                        or not str(descricao_membro).strip()
                        or descricao_membro_desatualizada
                    )
                    and not pausa_descricao_membros
                    and descricao_pode_carregar("membro", membro.id)
                ):
                    try:
                        with st.spinner(f"Carregando resumo de {membro.nome}..."):
                            descricao_membro, fonte_membro = atualizar_descricao_membro(
                                int(membro.id), membro.nome, card["grupo"]
                            )
                        registrar_sucesso_descricao("membro", membro.id)
                    except KProfilesRateLimited as erro:
                        registrar_falha_descricao("membro", membro.id)
                        pausa_descricao_membros = True
                        st.warning(str(erro))
                    except (requests.RequestException, ValueError) as erro:
                        registrar_falha_descricao("membro", membro.id)
                        st.caption(f"Resumo de {membro.nome} indisponível: {erro}")
                elif pd.notna(descricao_membro) and str(descricao_membro).strip():
                    fonte_membro = membro.descricao_url
                if pd.notna(descricao_membro) and str(descricao_membro).strip():
                    st.markdown(f"**{esc(str(membro.nome))}**")
                    st.markdown(str(descricao_membro))
                    if pd.notna(fonte_membro) and fonte_membro:
                        st.caption(f"Fonte: [KProfiles]({fonte_membro}) · tradução automática")
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
c_tit, c_pill, c_btn = st.columns([5, 2.4, 2.4], vertical_alignment="center")
c_tit.markdown('<div class="ttl"><div class="logo">💿</div><div><b>BinderLog</b><br>'
               '<span class="mut">Coleção de bots do Discord</span></div></div>', unsafe_allow_html=True)
c_pill.markdown(f'<div class="pill">{ring(pct(pos_g, tot_g), sm=True)} Coleção completa</div>',
                unsafe_allow_html=True)
if c_btn.button("＋  Adicionar idol / bot", type="primary", width="stretch"):
    dialog_adicionar()

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
        st.caption("Fontes das fotos: KProfiles e Wikipédia. "
                   "As fontes são combinadas e as buscas ficam em cache por até 24 horas.")
        if time.time() < st.session_state.get("wikipedia_fotos_cooldown_ate", 0):
            st.info("A Wikipédia limitou as buscas recentemente; essa fonte está pausada "
                    "por 1 hora.")
        contagem = df_all["url_foto"].dropna().value_counts()
        repetidas = set(contagem[contagem > 1].index)
        fb2 = st.multiselect("Só estes bots (vazio = todos)", sorted(df_all["bot"].unique()), key="f_bots")
        dff = df_all[df_all["bot"].isin(fb2)] if fb2 else df_all
        dff = ordenar(dff, "Idol (A–Z)")
        falta = dff["url_foto"].isna()
        rep = dff["url_foto"].isin(repetidas)
        modo = st.radio("Buscar fotos para", ["Só as que faltam", "Faltam + repetidas",
                                              "Todas (substituir)"], horizontal=True, key="f_modo")
        alvo = {"Só as que faltam": dff[falta], "Faltam + repetidas": dff[falta | rep],
                "Todas (substituir)": dff}[modo]
        c1, c2 = st.columns([1, 2])
        limite = c1.number_input("Buscar no máximo", min_value=1, max_value=100, value=30, key="f_lim")
        st.caption(f"{int(falta.sum())} sem foto · {int(rep.sum())} com foto repetida")
        if c2.button(f"🔎 Buscar fotos ({len(alvo)} idols)", disabled=alvo.empty):
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
                st.warning("Sem foto nova: " + "; ".join(falhou) + ". Use o ajuste individual abaixo.")
            if not pausa_kprofiles and not falhou:
                st.rerun()

        st.divider()
        st.subheader("Ajustar a foto de um idol")
        rotulo = {int(r.id): f"{r.idol} — {r.grupo} ({r.bot})" for r in ordenar(df_all, "Idol (A–Z)").itertuples()}
        sel_id = st.selectbox("Idol", list(rotulo), format_func=rotulo.get, key="f_idol")
        linha = df_all[df_all["id"] == sel_id].iloc[0]
        atual = _url(linha["url_foto"])
        g1, g2 = st.columns([1, 2])
        if atual:
            g1.image(atual, width=180)
        else:
            g1.caption("sem foto")
        with g2:
            if st.button("🔄 Trocar por outra foto", key="f_troca"):
                try:
                    if trocar_foto(sel_id, linha["idol"], linha["grupo"], atual):
                        st.rerun()
                    else:
                        st.warning("Não achei outra foto. Cole uma URL abaixo.")
                except KProfilesRateLimited as e:
                    st.warning(str(e))
                except Exception as e:
                    st.error(str(e))
            nova = st.text_input("Ou cole a URL da foto", key=f"f_url_{sel_id}")
            if st.button("Salvar URL", key="f_salva") and _url(nova):
                run("UPDATE colecao SET image_url=? WHERE id=?", (_url(nova), int(sel_id)))
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