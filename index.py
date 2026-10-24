import os
import re
import time
from contextlib import closing

import pandas as pd
import psycopg2
import requests
import streamlit as st

BOTS = ["Garam", "Hanbin", "Felix", "Jisoo", "Haewon", "Aeri"]
PRIORIDADES = ["Alta", "Média", "Baixa"]
CATEGORIAS = ["Grupo", "Solo", "Outro"]
GRUPO_COMPLETO = "Grupo completo"  # idol "-" no CSV: coleciona o grupo todo

st.set_page_config(page_title="Progresso da coleção", page_icon="💿", layout="wide")


def _secret(name):
    try:
        return st.secrets.get(name) or os.environ.get(name)
    except Exception:
        return os.environ.get(name)


# ---------------------------------------------------------------- Banco (PostgreSQL)
def conn():
    url = _secret("DATABASE_URL")
    if not url:
        st.error("Configure a variável DATABASE_URL (veja o README / secrets.toml), "
                 "por exemplo: postgresql://usuario:senha@localhost:5432/binderlog")
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
        UNIQUE (bot, grupo, idol))""")
    run("ALTER TABLE colecao ADD COLUMN IF NOT EXISTS image_url TEXT")
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
    "jonghyun": "SHINee", "yeji": "ITZY",
}
ALIAS_GRUPO = {
    "snsd": "Girls' Generation", "(g)i-dle": "(G)I-DLE", "i-dle": "(G)I-DLE",
    "nct u": "NCT", "nct127": "NCT 127", "tts": "Girls' Generation-TTS",
    "triples": "tripleS", "got the beat": "GOT the Beat",
}
WIKI = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "kpop-progresso/1.0"}


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
    g = PESSOA_GRUPO.get(base.casefold())
    if not g:
        g = "" if solo else ALIAS_GRUPO.get(grupo.casefold(), grupo)
    return ("solista" if solo else "pessoa"), base, g


def _google(consulta, exato, face):
    key, cx = _secret("GOOGLE_API_KEY"), _secret("GOOGLE_CSE_ID")
    if not (key and cx):
        return []
    params = {"key": key, "cx": cx, "q": consulta, "searchType": "image",
              "num": 10, "safe": "active", "exactTerms": exato}
    if face:
        params["imgType"] = "face"
    r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=15)
    r.raise_for_status()
    out = []
    for it in r.json().get("items") or []:
        # a miniatura hospedada pelo Google costuma carregar melhor que o link original
        u = it.get("image", {}).get("thumbnailLink") or it.get("link")
        if u:
            out.append(u)
    return out


def _wiki(params):
    r = requests.get(WIKI, params={**params, "format": "json"}, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def _wikipedia(tipo, base, grupo, n=8):
    alvo = (grupo if tipo == "grupo" else base).casefold()
    termo = grupo if tipo == "grupo" else f"{base} {grupo}".strip()
    achados = _wiki({"action": "query", "list": "search", "srsearch": termo,
                     "srlimit": 5})["query"]["search"]
    # só aceita o artigo se o título contém o nome procurado (evita idol errado)
    titulo = next((x["title"] for x in achados if alvo in x["title"].casefold()), None)
    if not titulo:
        return []
    out = []
    d = _wiki({"action": "query", "titles": titulo, "prop": "pageimages",
               "piprop": "thumbnail", "pithumbsize": 500})
    for pg in d["query"]["pages"].values():
        if "thumbnail" in pg:
            out.append(pg["thumbnail"]["source"])
    d = _wiki({"action": "query", "generator": "images", "titles": titulo, "gimlimit": 40,
               "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 500})
    for pg in ((d.get("query") or {}).get("pages") or {}).values():
        info = (pg.get("imageinfo") or [{}])[0]
        nome = pg.get("title", "").casefold()
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if any(w in nome for w in ("logo", "flag", "icon", "symbol", "signature", "map")):
            continue
        if tipo != "grupo" and base.casefold() not in nome:
            continue  # em artigos de grupo, só fotos com o nome do idol no arquivo
        u = info.get("thumburl") or info.get("url")
        if u and u not in out:
            out.append(u)
    return out[:n]


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_candidatas(tipo, base, grupo):
    """Lista de URLs candidatas (Google primeiro, depois Wikipedia), sem repetição."""
    if tipo == "grupo":
        consulta, exato, face = f"{grupo} kpop group", grupo, False
    else:
        extra = "solo singer" if tipo == "solista" else "kpop idol"
        consulta, exato, face = f"{base} {grupo} {extra}".replace("  ", " "), base, True
    urls, erro = [], None
    try:
        urls += _google(consulta, exato, face)
    except Exception as e:
        erro = e
    try:
        urls += _wikipedia(tipo, base, grupo)
    except Exception as e:
        erro = erro or e
    urls = list(dict.fromkeys(urls))
    if not urls and erro:
        raise erro
    return urls


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


# ---------------------------------------------------------------- Interface
st.title("💿 Progresso da coleção")
tab_prog, tab_gal, tab_add, tab_imp = st.tabs(["Progresso", "Galeria", "Adicionar", "Importar CSV"])

with tab_add:
    with st.form("novo", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        idol = c1.text_input("Idol / Solista")
        grupo = c2.text_input("Grupo")
        bot = c3.selectbox("Bot", BOTS)
        c4, c5, c6, c7 = st.columns(4)
        cat = c4.selectbox("Categoria", CATEGORIAS)
        prio = c5.selectbox("Prioridade", PRIORIDADES, index=1)
        total = c6.number_input("Total de cartas", min_value=0, value=0)
        possuo = c7.number_input("Quantas eu tenho", min_value=0, value=0)
        if st.form_submit_button("Adicionar"):
            if not idol.strip():
                st.error("Informe o nome.")
            elif possuo > total:
                st.error("Você não pode ter mais cartas do que o total.")
            else:
                try:
                    run("INSERT INTO colecao (bot, grupo, idol, categoria, prioridade, total, possuo) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (bot, grupo.strip(), idol.strip(), cat, prio, int(total), int(possuo)))
                    st.success("Adicionado!")
                except psycopg2.IntegrityError:
                    st.error(f"{idol} ({grupo}) já existe no bot {bot}. Edite na aba Progresso.")

with tab_imp:
    st.write("Importa o formato da **Garam**. O arquivo *Bancodedados* é obrigatório "
             "(traz total e quantidade adquirida); a *Priolist* é opcional e preenche "
             "prioridade e categoria. Idols já existentes são atualizados.")
    bot_imp = st.selectbox("Bot", BOTS, key="bot_imp")
    f_banco = st.file_uploader("Bancodedados (.csv)", type="csv", key="f_banco")
    f_prio = st.file_uploader("Priolist (.csv) — opcional", type="csv", key="f_prio")
    if f_banco:
        try:
            prev, avisos = parse_garam(f_banco, f_prio)
            st.caption(f"{len(prev)} linhas prontas para importar")
            if avisos:
                with st.expander(f"⚠️ {len(avisos)} aviso(s) na leitura do CSV"):
                    for a in avisos:
                        st.write("• " + a)
            st.dataframe(prev, hide_index=True, use_container_width=True)
            if st.button("Importar", type="primary"):
                run_many(UPSERT, [(bot_imp, r.grupo, r.idol, r.categoria, r.prioridade,
                                   int(r.total), int(r.possuo)) for r in prev.itertuples()])
                st.success(f"{len(prev)} linhas importadas para {bot_imp}!")
        except Exception as e:
            st.error(str(e))

with tab_prog:
    df = q("SELECT id, bot, grupo, idol, categoria, prioridade, total, possuo, image_url "
           "FROM colecao")
    if df.empty:
        st.info("Nada por aqui ainda. Use a aba **Importar CSV** ou **Adicionar**.")
        st.stop()

    tot, pos = int(df["total"].sum()), int(df["possuo"].sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Cartas no total", tot)
    m2.metric("Cartas que tenho", pos)
    m3.metric("Progresso geral", f"{pos / tot * 100:.1f}%" if tot else "0%")
    st.caption("Obs.: o total é a soma de cada linha; cartas compartilhadas entre "
               "membros do mesmo grupo podem ser contadas mais de uma vez.")

    resumo = df.groupby("bot")[["total", "possuo"]].sum().reset_index()
    resumo["progresso"] = (resumo["possuo"] / resumo["total"].where(resumo["total"] > 0) * 100).fillna(0)
    st.subheader("Por bot")
    st.dataframe(
        resumo, hide_index=True, use_container_width=True,
        column_config={"progresso": st.column_config.ProgressColumn(
            "Progresso", min_value=0, max_value=100, format="%.0f%%")})

    st.subheader("Idols")
    f1, f2, f3, f4, f5 = st.columns(5)
    fb = f1.multiselect("Bot", sorted(df["bot"].unique()))
    fg = f2.multiselect("Grupo", sorted(df["grupo"].unique(), key=str.casefold))
    fp = f3.multiselect("Prioridade", PRIORIDADES)
    fc = f4.multiselect("Categoria", CATEGORIAS)
    busca = f5.text_input("Buscar idol")
    if fb:
        df = df[df["bot"].isin(fb)]
    if fg:
        df = df[df["grupo"].isin(fg)]
    if fp:
        df = df[df["prioridade"].isin(fp)]
    if fc:
        df = df[df["categoria"].isin(fc)]
    if busca:
        df = df[df["idol"].str.contains(busca, case=False, regex=False)
                | df["grupo"].str.contains(busca, case=False, regex=False)]

    df = df.copy()
    df["progresso"] = (df["possuo"] / df["total"].where(df["total"] > 0) * 100).fillna(0)
    df["faltam"] = df["total"] - df["possuo"]
    ordem = st.selectbox("Ordenar por", ["Idol (A–Z)", "Grupo (A–Z)", "Menor progresso",
                                         "Maior progresso", "Mais cartas faltando", "Prioridade"])
    df = ordenar(df, ordem)
    df["excluir"] = False

    edited = st.data_editor(
        df, hide_index=True, use_container_width=True,
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
                       "progresso.csv", "text/csv")


# ---------------------------------------------------------------- Galeria
with tab_gal:
    st.write("A galeria usa os filtros e a ordenação da aba **Progresso**. "
             "Cada card do mesmo idol (ex.: Miyeon 1, 2, 3) recebe uma foto diferente.")
    tem_google = bool(_secret("GOOGLE_API_KEY") and _secret("GOOGLE_CSE_ID"))
    st.caption("Fonte das fotos: " + ("Google (Custom Search, filtro de rosto) + Wikipedia."
               if tem_google else "Wikipedia (configure as chaves do Google para buscar lá)."))

    todas = q("SELECT image_url FROM colecao")["image_url"].map(_url).dropna()
    contagem = todas.value_counts()
    repetidas = set(contagem[contagem > 1].index)
    df["url_foto"] = df["image_url"].map(_url)
    falta = df["url_foto"].isna()
    rep = df["url_foto"].isin(repetidas)

    modo = st.radio("Buscar fotos para", ["Só as que faltam", "Faltam + repetidas",
                                          "Todas nos filtros (substituir)"], horizontal=True)
    alvo = {"Só as que faltam": df[falta],
            "Faltam + repetidas": df[falta | rep],
            "Todas nos filtros (substituir)": df}[modo]
    c1, c2 = st.columns([1, 2])
    limite = c1.number_input("Buscar no máximo", min_value=1, max_value=100, value=30)
    st.caption(f"{int(falta.sum())} sem foto · {int(rep.sum())} com foto repetida nos filtros atuais")
    if c2.button(f"🔎 Buscar fotos ({len(alvo)} cards)", disabled=alvo.empty):
        barra = st.progress(0.0)
        achou, falhou = 0, []
        alvo = alvo.head(int(limite))
        for i, r in enumerate(alvo.itertuples(), 1):
            try:
                if trocar_foto(r.id, r.idol, r.grupo, _url(r.url_foto) if modo != "Só as que faltam" else None):
                    achou += 1
                else:
                    falhou.append(f"{r.idol} ({r.grupo})")
            except Exception as e:
                falhou.append(f"{r.idol} ({r.grupo}): {e}")
            barra.progress(i / len(alvo))
            time.sleep(0.2)
        st.success(f"{achou} fotos atualizadas.")
        if falhou:
            st.warning("Sem foto nova: " + "; ".join(falhou)
                       + ". Cole a URL manualmente na coluna 'URL da foto' da aba Progresso.")
        else:
            st.rerun()

    st.divider()
    cols = st.columns(5)
    for i, r in enumerate(df.itertuples()):
        with cols[i % 5]:
            foto = _url(r.url_foto)
            if foto:
                st.image(foto, use_container_width=True)
            else:
                st.markdown("🖼️ *sem foto*")
            aviso = " ⚠️ repetida" if foto in repetidas else ""
            st.markdown(f"**{r.idol}**{aviso}  \n{r.grupo} · {r.bot}")
            st.progress(max(0.0, min(r.progresso / 100, 1.0)), text=f"{r.possuo}/{r.total} · {r.progresso:.0f}%")
            if st.button("🔄 Trocar foto", key=f"troca_{r.id}"):
                try:
                    if trocar_foto(r.id, r.idol, r.grupo, foto):
                        st.rerun()
                    else:
                        st.warning("Não achei outra foto. Cole a URL na aba Progresso.")
                except Exception as e:
                    st.error(str(e))