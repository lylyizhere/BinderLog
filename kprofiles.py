import math
import random
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests
import streamlit as st


class KProfilesRateLimited(requests.RequestException):
    def __init__(self, status_code, retry_after):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(
            f"KProfiles respondeu HTTP {status_code}. As buscas dessa fonte foram "
            f"pausadas por pelo menos {math.ceil(retry_after)} segundos."
        )


class _KProfilesRateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._next_request_at = 0
        self._cooldown_until = 0
        self._blocked_status = 429

    @staticmethod
    def _retry_after(headers, default):
        valor = headers.get("Retry-After")
        if valor:
            try:
                segundos = float(valor)
                return max(0, segundos) if math.isfinite(segundos) else default
            except ValueError:
                try:
                    data = parsedate_to_datetime(valor)
                    if data.tzinfo is None:
                        data = data.replace(tzinfo=timezone.utc)
                    return max(0, (data - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        return default

    def get(self, url, params, headers, timeout):
        with self._lock:
            agora = time.monotonic()
            if agora < self._cooldown_until:
                raise KProfilesRateLimited(
                    self._blocked_status, self._cooldown_until - agora
                )
            espera = self._next_request_at - agora
            if espera > 0:
                time.sleep(espera)
            try:
                resposta = requests.get(
                    url, params=params, headers=headers, timeout=timeout
                )
            finally:
                self._next_request_at = time.monotonic() + random.uniform(1.5, 2.5)
            if resposta.status_code in (403, 429):
                padrao = 21600 if resposta.status_code == 403 else 3600
                espera = self._retry_after(resposta.headers, padrao)
                self._blocked_status = resposta.status_code
                self._cooldown_until = time.monotonic() + espera
                raise KProfilesRateLimited(resposta.status_code, espera)
            resposta.raise_for_status()
            return resposta


@st.cache_resource
def _limitador_kprofiles():
    return _KProfilesRateLimiter()


def _normalizar_nome(nome):
    return re.sub(r"[^a-z0-9]", "", str(nome).casefold())


def nome_aparece_em_texto(nome, texto):
    tokens_nome = re.findall(
        r"[a-z0-9]+",
        unicodedata.normalize("NFKD", str(nome).casefold())
        .encode("ascii", "ignore").decode(),
    )
    tokens_texto = re.findall(
        r"[a-z0-9]+",
        unicodedata.normalize("NFKD", str(texto).casefold())
        .encode("ascii", "ignore").decode(),
    )
    if not tokens_nome:
        return False
    tamanho = len(tokens_nome)
    return any(
        tokens_texto[indice:indice + tamanho] == tokens_nome
        for indice in range(len(tokens_texto) - tamanho + 1)
    ) or (tamanho > 1 and "".join(tokens_nome) in tokens_texto)


class _BuscaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resultados = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        atributos = dict(attrs)
        href = atributos.get("href", "")
        titulo = atributos.get("title", "")
        if href.startswith("https://kprofiles.com/") and titulo:
            self.resultados.append((titulo, href))


class _PerfilParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.conteudo_depth = 0
        self.in_paragrafo = False
        self.paragrafo_atual = []
        self.paragrafos = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "div":
            classes = atributos.get("class", "").split()
            if self.conteudo_depth:
                self.conteudo_depth += 1
            elif "entry-content" in classes:
                self.conteudo_depth = 1
        elif tag == "p" and self.conteudo_depth:
            self.in_paragrafo = True
            self.paragrafo_atual = []

    def handle_endtag(self, tag):
        if tag == "p" and self.in_paragrafo:
            texto = " ".join("".join(self.paragrafo_atual).split())
            self.paragrafos.append(texto)
            self.in_paragrafo = False
        elif tag == "div" and self.conteudo_depth:
            self.conteudo_depth -= 1

    def handle_data(self, data):
        if self.in_paragrafo:
            self.paragrafo_atual.append(data)


class _ImagensParser(HTMLParser):
    def __init__(self, content_only=False):
        super().__init__(convert_charrefs=True)
        self.content_only = content_only
        self.content_depth = 0
        self.excluded_depth = 0
        self.images = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "div" and self.content_only:
            classes = atributos.get("class", "").split()
            if self.excluded_depth:
                self.excluded_depth += 1
            elif self.content_depth and any(
                classe == "ad" or classe.startswith("ad-")
                or classe.endswith("-ad")
                or classe in {"ads", "advertisement", "sidebar", "related-posts"}
                for classe in classes
            ):
                self.excluded_depth = 1
            elif self.content_depth:
                self.content_depth += 1
            elif "entry-content" in classes or "profile-content" in classes:
                self.content_depth = 1
        elif tag == "img" and not self.excluded_depth and (
            self.content_depth or not self.content_only
        ):
            src = (atributos.get("data-src") or atributos.get("data-lazy-src")
                   or atributos.get("src", ""))
            srcset = atributos.get("srcset", "")
            if srcset:
                src = srcset.split(",")[-1].strip().split(" ")[0] or src
            if src:
                self.images.append((src, atributos.get("alt", "")))

    def handle_endtag(self, tag):
        if tag == "div":
            if self.excluded_depth:
                self.excluded_depth -= 1
            elif self.content_depth:
                self.content_depth -= 1


@st.cache_data(ttl=86400, show_spinner=False)
def _buscar_html(url, parametros=()):
    resposta = _limitador_kprofiles().get(
        url,
        params=dict(parametros) if parametros else None,
        headers={
            "User-Agent": "BinderLog/1.0 (+https://github.com/lylyizhere/BinderLog)"
        },
        timeout=20,
    )
    return resposta.text


def _url_perfil(query, esperado, grupo_esperado=""):
    html = _buscar_html("https://kprofiles.com/", (("s", query),))
    busca = _BuscaParser()
    busca.feed(html)
    alvo = _normalizar_nome(esperado)
    sufixos = (
        "membersprofileandfactsupdated", "membersprofileandfacts",
        "membersprofileupdated", "membersprofile", "memberprofileandfacts",
        "memberprofile", "profileandfacts", "profile",
    )
    grupo_normalizado = _normalizar_nome(grupo_esperado)
    candidatos = []
    for titulo, url in busca.resultados:
        titulo_normalizado = _normalizar_nome(titulo)
        url_normalizada = _normalizar_nome(url)
        for sufixo in sufixos:
            if not titulo_normalizado.endswith(sufixo):
                continue
            nome_perfil = titulo_normalizado[:-len(sufixo)]
            if alvo and alvo in nome_perfil:
                grupo_corresponde = bool(
                    grupo_normalizado
                    and (
                        grupo_normalizado in titulo_normalizado
                        or grupo_normalizado in url_normalizada
                    )
                )
                candidatos.append(
                    (
                        not grupo_corresponde,
                        len(nome_perfil) - len(alvo),
                        nome_perfil.find(alvo),
                        nome_perfil != alvo,
                        url,
                    )
                )
                break
    return min(candidatos)[4] if candidatos else None


def _extrair_integrantes(html):
    parser = _PerfilParser()
    parser.feed(html)
    padrao = re.compile(
        r"(?:the group consists of|the group is made up of|members are|members include|"
        r"consisting of)"
        r"\s+(.+?)(?:\s+from\b|\s+under\b|[.!?]|$)",
        re.IGNORECASE,
    )
    for paragrafo in parser.paragrafos:
        resultado = padrao.search(paragrafo)
        if not resultado:
            continue
        lista = re.sub(r"^\d+\s+members?\s*:\s*", "", resultado.group(1),
                       flags=re.IGNORECASE)
        integrantes = [
            nome.strip(" .:;")
            for nome in re.split(
                r",\s*(?:and\s+)?|\s+\band\s+|\s+&\s+",
                lista,
                flags=re.IGNORECASE,
            )
        ]
        integrantes = list(dict.fromkeys(nome for nome in integrantes if nome))
        if integrantes and len(integrantes) <= 30:
            return integrantes
    raise ValueError("O perfil encontrado não apresentou uma lista de integrantes reconhecível.")


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_integrantes_kprofiles(grupo):
    perfil_url = _url_perfil(grupo, grupo)
    if not perfil_url:
        raise ValueError(f"Não foi encontrado um perfil de integrantes para {grupo}.")

    integrantes = _extrair_integrantes(_buscar_html(perfil_url))
    return integrantes, perfil_url


def _extrair_info_perfil(html, nomes, tipo):
    parser = _PerfilParser()
    parser.feed(html)
    paragrafos = [paragrafo for paragrafo in parser.paragrafos if paragrafo]
    sentencas = [
        sentenca.strip()
        for paragrafo in paragrafos
        for sentenca in re.split(r"(?<=[.!?])\s+", paragrafo)
        if sentenca.strip()
    ]
    introducao = ""
    for sentenca in sentencas:
        for nome in nomes:
            if not nome:
                continue
            padrao = re.compile(
                rf"(?<!\w){re.escape(nome)}(?!\w)(?:\s*\([^)]*\))?"
                rf"\s+(?:is|are|was|were)\s+[^.!?]+[.!?]?",
                re.IGNORECASE,
            )
            resultado = padrao.search(sentenca)
            if resultado:
                introducao = resultado.group(0).strip()
                break
        if introducao:
            break

    if not introducao:
        raise ValueError("O perfil do KProfiles não apresentou uma descrição curta reconhecível.")

    estreia = next(
        (
            sentenca
            for sentenca in sentencas
            if re.search(r"\bdebut(?:ed|s)?\b", sentenca, re.IGNORECASE)
        ),
        "",
    )
    album = ""
    if estreia:
        resultado_album = re.search(
            r"\b(?:first|debut)\s+"
            r"(?:(?:studio|mini|full[- ]length)\s+)?"
            r"(?:album|single|ep)\s*(?:,|:|-|titled|called)?\s*"
            r"['\"“]?([^,.!?\"”]+)",
            estreia,
            re.IGNORECASE,
        )
        if resultado_album:
            album = resultado_album.group(1).strip()

    integrantes = []
    if tipo == "grupo":
        try:
            integrantes = _extrair_integrantes(html)
        except ValueError:
            pass

    padrao_fato = re.compile(
        r"\b(?:born|birthday|birth name|position|leader|nationality|height|"
        r"zodiac|agency|formed\s+(?:in|on)|debut(?:ed|s)?)\b",
        re.IGNORECASE,
    )
    fatos = []
    for sentenca in sentencas:
        if (
            sentenca != introducao
            and sentenca != estreia
            and padrao_fato.search(sentenca)
            and sentenca not in fatos
        ):
            fatos.append(sentenca)
        if len(fatos) == 4:
            break

    partes = [introducao]
    if integrantes:
        partes.append("Integrantes: " + ", ".join(integrantes) + ".")
    if estreia:
        partes.append("Estreia: " + estreia)
    if album:
        partes.append("Album de estreia: " + album + ".")
    if fatos:
        partes.append("Outras informacoes: " + " ".join(fatos))
    return {
        "descricao": " ".join(partes),
        "estreia": estreia,
        "album": album,
        "membros": integrantes,
        "fatos": fatos,
    }


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_perfil_kprofiles(tipo, base, grupo, nome_busca, termos_busca):
    if tipo == "grupo":
        perfis = [(grupo, grupo)]
    else:
        perfis = [(termo, nome_busca) for termo in termos_busca]
        if grupo and grupo.casefold() != "solo":
            perfis.append((grupo, base))

    consultadas = set()
    for consulta, esperado in perfis:
        chave = (consulta.casefold(), esperado.casefold())
        if chave in consultadas:
            continue
        consultadas.add(chave)
        contexto_grupo = grupo if tipo != "grupo" and grupo.casefold() != "solo" else ""
        perfil_url = _url_perfil(consulta, esperado, contexto_grupo)
        if not perfil_url:
            continue
        try:
            info = _extrair_info_perfil(
                _buscar_html(perfil_url),
                (nome_busca, base, grupo if tipo == "grupo" else ""),
                tipo,
            )
        except ValueError:
            continue
        return {**info, "url": perfil_url}
    raise ValueError(f"Não foi encontrada uma descrição no KProfiles para {base}.")


@st.cache_data(ttl=86400, show_spinner=False)
def traduzir_descricao_ptbr(texto):
    if not texto.strip():
        raise ValueError("A descrição para tradução está vazia.")
    palavras = texto.split()
    trechos = []
    trecho_atual = ""
    for palavra in palavras:
        while len(palavra) > 450:
            if trecho_atual:
                trechos.append(trecho_atual)
                trecho_atual = ""
            trechos.append(palavra[:450])
            palavra = palavra[450:]
        if trecho_atual and len(trecho_atual) + len(palavra) + 1 > 450:
            trechos.append(trecho_atual)
            trecho_atual = ""
        trecho_atual = f"{trecho_atual} {palavra}".strip()
    if trecho_atual:
        trechos.append(trecho_atual)

    traducoes = []
    for trecho in trechos:
        resposta = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": trecho, "langpair": "en|pt-BR"},
            headers={
                "User-Agent": "BinderLog/1.0 (+https://github.com/lylyizhere/BinderLog)"
            },
            timeout=20,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict) or dados.get("responseStatus") != 200:
            detalhe = dados.get("responseDetails", "Resposta de tradução inválida.")
            raise ValueError(f"Não foi possível traduzir a descrição: {detalhe}")
        traducao = dados.get("responseData", {}).get("translatedText", "")
        traducao = unescape(str(traducao)).strip()
        if not traducao:
            raise ValueError("O serviço de tradução retornou uma descrição vazia.")
        traducoes.append(traducao)
    return " ".join(traducoes)


def buscar_imagens_kprofiles(tipo, base, grupo, nome_busca, termos_busca,
                             aliases_busca):
    if tipo == "grupo":
        perfis = [(grupo, grupo, "")]
    else:
        perfis = [(termo, nome_busca, base) for termo in termos_busca]
        if grupo and grupo.casefold() != "solo":
            perfis.append((grupo, grupo, base))

    todas_imagens = []
    consultas_feitas = set()
    for consulta, esperado, membro in perfis:
        chave_consulta = (consulta.casefold(), esperado.casefold(), membro.casefold())
        if chave_consulta in consultas_feitas:
            continue
        consultas_feitas.add(chave_consulta)
        contexto_grupo = grupo if tipo != "grupo" and grupo.casefold() != "solo" else ""
        perfil_url = _url_perfil(consulta, esperado, contexto_grupo)
        if not perfil_url:
            continue
        html = _buscar_html(perfil_url)
        parser = _ImagensParser(content_only=True)
        parser.feed(html)
        membros_grupo = []
        if tipo == "grupo":
            try:
                membros_grupo = _extrair_integrantes(html)
            except ValueError:
                continue
        alvos = {
            _normalizar_nome(membro),
            _normalizar_nome(aliases_busca.get(membro.casefold(), "")),
        }
        alvos.discard("")
        imagens = []
        imagens_com_nome_grupo = []
        for imagem, alt in parser.images:
            url = urljoin(perfil_url, imagem)
            if url.partition("?")[0].casefold().endswith(".svg"):
                continue
            nome_arquivo = _normalizar_nome(url.rsplit("/", 1)[-1])
            texto_alt = _normalizar_nome(alt)
            if tipo == "grupo" and any(
                nome_aparece_em_texto(integrante, f"{nome_arquivo} {alt}")
                for integrante in membros_grupo
            ):
                continue
            if tipo == "grupo" and _normalizar_nome(grupo) not in (
                nome_arquivo + texto_alt
            ):
                continue
            if any(termo in nome_arquivo or termo in texto_alt
                   for termo in ("logo", "flag", "symbol", "signature", "map")):
                continue
            if alvos and not any(
                alvo in nome_arquivo or alvo in texto_alt for alvo in alvos
            ):
                continue
            if url not in imagens:
                imagens.append(url)
                if tipo == "grupo" and texto_alt and (
                    _normalizar_nome(grupo) in texto_alt
                ):
                    imagens_com_nome_grupo.append(url)
        if imagens:
            if imagens_com_nome_grupo:
                todas_imagens.extend(reversed(imagens_com_nome_grupo))
            else:
                todas_imagens.extend(reversed(imagens))
    return list(dict.fromkeys(todas_imagens))[:24]
