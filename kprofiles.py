import math
import random
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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


def _nome_em_texto_perfil(nome, texto):
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


def _url_perfil(query, esperado):
    html = _buscar_html("https://kprofiles.com/", (("s", query),))
    busca = _BuscaParser()
    busca.feed(html)
    alvo = _normalizar_nome(esperado)
    sufixos = (
        "membersprofileandfactsupdated", "membersprofileandfacts",
        "membersprofileupdated", "membersprofile", "memberprofileandfacts",
        "memberprofile", "profileandfacts", "profile",
    )
    candidatos = []
    for titulo, url in busca.resultados:
        titulo_normalizado = _normalizar_nome(titulo)
        for sufixo in sufixos:
            if not titulo_normalizado.endswith(sufixo):
                continue
            nome_perfil = titulo_normalizado[:-len(sufixo)]
            if alvo and alvo in nome_perfil:
                candidatos.append(
                    (
                        len(nome_perfil) - len(alvo),
                        nome_perfil.find(alvo),
                        nome_perfil != alvo,
                        url,
                    )
                )
                break
    return min(candidatos)[3] if candidatos else None


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
        perfil_url = _url_perfil(consulta, esperado)
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
                pass
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
                _nome_em_texto_perfil(integrante, f"{nome_arquivo} {alt}")
                for integrante in membros_grupo
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
