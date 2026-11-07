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
    traduzir_descricao,
    traduzir_descricao_ptbr,
)

BOTS = ["Garam", "Hanbin", "Felix", "Jisoo", "Haewon", "Aeri"]
PRIORIDADES = ["Alta", "Média", "Baixa"]
CATEGORIAS = ["Grupo", "Solo", "Outro"]
GRUPO_COMPLETO = "Grupo completo"  # idol "-" no CSV: coleciona o grupo todo
VERSAO_DESCRICAO = 8
IDIOMAS = ("Português (Brasil)", "English", "Español")
TRADUCOES_NAVEGACAO = {
    "label_idioma": {
        "Português (Brasil)": "Idioma",
        "English": "Language",
        "Español": "Idioma",
    },
    "colecao_bots_discord": {
        "Português (Brasil)": "Coleção de bots do Discord",
        "English": "Discord bot collection",
        "Español": "Colección de bots de Discord",
    },
    "colecao_completa": {
        "Português (Brasil)": "Coleção completa",
        "English": "Collection progress",
        "Español": "Progreso de la colección",
    },
    "adicionar_idol_bot": {
        "Português (Brasil)": "＋  Adicionar idol / bot",
        "English": "＋  Add idol / bot",
        "Español": "＋  Añadir ídolo / bot",
    },
    "foto_perfil": {
        "Português (Brasil)": "Foto do perfil",
        "English": "Profile picture",
        "Español": "Foto de perfil",
    },
    "foto_perfil_indisponivel": {
        "Português (Brasil)": "Foto do perfil indisponível",
        "English": "Profile picture unavailable",
        "Español": "Foto de perfil no disponible",
    },
    "conta_conectada": {
        "Português (Brasil)": "Conta conectada",
        "English": "Connected account",
        "Español": "Cuenta conectada",
    },
    "configuracoes_conta": {
        "Português (Brasil)": "Configurações da conta",
        "English": "Account settings",
        "Español": "Configuración de la cuenta",
    },
    "sair_conta": {
        "Português (Brasil)": "Sair da conta",
        "English": "Sign out",
        "Español": "Cerrar sesión",
    },
    "aba_painel": {
        "Português (Brasil)": "Painel",
        "English": "Dashboard",
        "Español": "Panel",
    },
    "aba_tabela": {
        "Português (Brasil)": "Tabela",
        "English": "Table",
        "Español": "Tabla",
    },
    "aba_fotos": {
        "Português (Brasil)": "Fotos",
        "English": "Photos",
        "Español": "Fotos",
    },
    "aba_importar_csv": {
        "Português (Brasil)": "Importar CSV",
        "English": "Import CSV",
        "Español": "Importar CSV",
    },
    "painel_vazio": {
        "Português (Brasil)": "Nada por aqui ainda. Use **Importar CSV** ou o botão **Adicionar idol / bot**.",
        "English": "Nothing here yet. Use **Import CSV** or the **Add idol / bot** button.",
        "Español": "Todavía no hay nada aquí. Usa **Importar CSV** o el botón **Añadir ídolo / bot**.",
    },
    "progresso_geral": {
        "Português (Brasil)": "PROGRESSO GERAL",
        "English": "OVERALL PROGRESS",
        "Español": "PROGRESO GENERAL",
    },
    "cartas_coletadas": {
        "Português (Brasil)": "{possuidas} de {total} cartas coletadas",
        "English": "{possuidas} of {total} cards collected",
        "Español": "{possuidas} de {total} cartas reunidas",
    },
    "colecoes_avancadas": {
        "Português (Brasil)": "Coleções mais avançadas por bot",
        "English": "Most complete collections by bot",
        "Español": "Colecciones más completas por bot",
    },
    "cartas": {
        "Português (Brasil)": "cartas",
        "English": "cards",
        "Español": "cartas",
    },
    "bots": {
        "Português (Brasil)": "BOTS",
        "English": "BOTS",
        "Español": "BOTS",
    },
    "todos": {
        "Português (Brasil)": "Todos",
        "English": "All",
        "Español": "Todos",
    },
    "idols_contagem": {
        "Português (Brasil)": "{quantidade} idols",
        "English": "{quantidade} idols",
        "Español": "{quantidade} ídolos",
    },
    "progresso": {
        "Português (Brasil)": "Progresso",
        "English": "Progress",
        "Español": "Progreso",
    },
    "buscar": {
        "Português (Brasil)": "Buscar",
        "English": "Search",
        "Español": "Buscar",
    },
    "buscar_idol_grupo": {
        "Português (Brasil)": "Buscar idol ou grupo",
        "English": "Search idols or groups",
        "Español": "Buscar ídolos o grupos",
    },
    "ordenar": {
        "Português (Brasil)": "Ordenar",
        "English": "Sort",
        "Español": "Ordenar",
    },
    "prioridade": {
        "Português (Brasil)": "Prioridade",
        "English": "Priority",
        "Español": "Prioridad",
    },
    "todas_colecoes": {
        "Português (Brasil)": "Todas as coleções",
        "English": "All collections",
        "Español": "Todas las colecciones",
    },
    "abrir_detalhes": {
        "Português (Brasil)": "Abrir detalhes de {nome}",
        "English": "Open details for {nome}",
        "Español": "Abrir los detalles de {nome}",
    },
    "mostrar_mais": {
        "Português (Brasil)": "Mostrar mais ({quantidade} restantes)",
        "English": "Show more ({quantidade} remaining)",
        "Español": "Mostrar más ({quantidade} restantes)",
    },
    "ordens": {
        "Português (Brasil)": {
            "Idol (A–Z)": "Idol (A–Z)",
            "Grupo (A–Z)": "Grupo (A–Z)",
            "Menor progresso": "Menor progresso",
            "Maior progresso": "Maior progresso",
            "Mais cartas faltando": "Mais cartas faltando",
            "Prioridade": "Prioridade",
        },
        "English": {
            "Idol (A–Z)": "Idol (A–Z)",
            "Grupo (A–Z)": "Group (A–Z)",
            "Menor progresso": "Least progress",
            "Maior progresso": "Most progress",
            "Mais cartas faltando": "Most cards missing",
            "Prioridade": "Priority",
        },
        "Español": {
            "Idol (A–Z)": "Ídolo (A–Z)",
            "Grupo (A–Z)": "Grupo (A–Z)",
            "Menor progresso": "Menor progreso",
            "Maior progresso": "Mayor progreso",
            "Mais cartas faltando": "Más cartas pendientes",
            "Prioridade": "Prioridad",
        },
    },
    "prioridades": {
        "Português (Brasil)": {"Alta": "Alta", "Média": "Média", "Baixa": "Baixa"},
        "English": {"Alta": "High", "Média": "Medium", "Baixa": "Low"},
        "Español": {"Alta": "Alta", "Média": "Media", "Baixa": "Baja"},
    },
    "detalhe": {
        "Português (Brasil)": {
            "card_url_invalido": "O identificador do card na URL é inválido.",
            "card_removido": "Este card não está mais na coleção.",
            "voltar_painel": "← Voltar ao painel",
            "bot": "Bot",
            "buscando_traduzindo": "Buscando no KProfiles e traduzindo para português...",
            "traducao_pausada": "A tradução está temporariamente pausada por limite de solicitações. Tente novamente mais tarde.",
            "kprofiles_pausado": "O KProfiles limitou as consultas temporariamente. Tente novamente mais tarde.",
            "descricao_indisponivel": "Não foi possível carregar a descrição: {erro}",
            "foto_card": "Foto do card",
            "sem_foto_card": "Ainda não há uma imagem para este card.",
            "sobre": "Sobre",
            "fonte_original_ingles": "texto original em inglês",
            "traducao_automatica": "tradução automática",
            "falha_traduzir_resumo": "Não foi possível traduzir o resumo para o idioma selecionado: {erro}",
            "resumo_indisponivel": "O perfil ainda não tem um resumo disponível.",
            "membros": "Membros",
            "verificando_membros": "Conferindo os integrantes de {grupo} no KProfiles...",
            "membros_indisponiveis": "Não foi possível verificar os integrantes no KProfiles: {erro}",
            "tentar_novamente": "Tentar buscar novamente",
            "fonte_conferida": "Fonte conferida",
            "blocos_membros_indisponiveis": "Os blocos dos integrantes aparecerão quando a lista for encontrada.",
            "membros_adicionais": "Há integrantes salvos que não aparecem na lista atual do KProfiles. Eles e seus dados foram mantidos.",
            "carregar_resumo": "Carregar resumo de {membro}",
            "carregando_resumo": "Carregando resumo de {membro}...",
            "resumo_membro_indisponivel": "Resumo de {membro} indisponível: {erro}",
            "resumo_temporariamente_indisponivel": "Resumo de {membro} temporariamente indisponível. Tente novamente mais tarde.",
            "registros_antigos": "Registros antigos sem integrante",
            "registros_anteriores": "Estes registros foram adicionados antes da divisão por membro.",
            "resumo": "Resumo",
            "eras": "Eras",
            "eventos": "Eventos",
            "marcadores": "marcadores",
            "nome_era": "Nome da era",
            "sigla_era": "Sigla da era",
            "diamantes_era": "Diamantes da era",
            "adicionar_era": "Adicionar era",
            "nome_sigla_era_obrigatorios": "Informe o nome e a sigla da era.",
            "nenhuma_era": "Nenhuma era adicionada ainda.",
            "nome_evento": "Nome do evento",
            "sigla_gerada": "Sigla gerada: {sigla}",
            "marcadores_happy_birthday": "Marcadores do Happy Birthday",
            "um_marcador": "Este evento usa 1 marcador.",
            "nome_evento_obrigatorio": "Informe o nome do evento.",
            "adicionar_evento": "Adicionar evento",
            "nenhum_evento": "Nenhum evento adicionado ainda.",
            "marcadores_evento": "Marcadores: {quantidade}",
            "eras_contagem": "{quantidade} eras",
            "eventos_contagem": "{quantidade} eventos",
            "diamantes_contagem": "{quantidade} 💎",
            "resumo_registros": "{eras} · {diamantes} · {eventos} · {marcadores} {rotulo_marcadores}",
        },
        "English": {
            "card_url_invalido": "The card ID in the URL is invalid.",
            "card_removido": "This card is no longer in the collection.",
            "voltar_painel": "← Back to dashboard",
            "bot": "Bot",
            "buscando_traduzindo": "Checking KProfiles and translating the profile into Portuguese...",
            "traducao_pausada": "Translation is temporarily paused because the service rate limit was reached. Please try again later.",
            "kprofiles_pausado": "KProfiles has temporarily rate-limited requests. Please try again later.",
            "descricao_indisponivel": "Could not load the profile: {erro}",
            "foto_card": "Card image",
            "sem_foto_card": "There is no image for this card yet.",
            "sobre": "About",
            "fonte_original_ingles": "original English text",
            "traducao_automatica": "automatically translated",
            "falha_traduzir_resumo": "Could not translate the summary into the selected language: {erro}",
            "resumo_indisponivel": "No profile summary is available yet.",
            "membros": "Members",
            "verificando_membros": "Checking the KProfiles member list for {grupo}...",
            "membros_indisponiveis": "Could not verify the members on KProfiles: {erro}",
            "tentar_novamente": "Try again",
            "fonte_conferida": "Source checked",
            "blocos_membros_indisponiveis": "Member sections will appear when the list is available.",
            "membros_adicionais": "Some saved members are not on the current KProfiles list. Their entries and data have been kept.",
            "carregar_resumo": "Load {membro}'s profile summary",
            "carregando_resumo": "Loading {membro}'s profile summary...",
            "resumo_membro_indisponivel": "Could not load {membro}'s profile summary: {erro}",
            "resumo_temporariamente_indisponivel": "{membro}'s profile summary is temporarily unavailable. Please try again later.",
            "registros_antigos": "Older entries without a member",
            "registros_anteriores": "These entries were added before records were separated by member.",
            "resumo": "Summary",
            "eras": "Eras",
            "eventos": "Events",
            "marcadores": "markers",
            "nome_era": "Era name",
            "sigla_era": "Era abbreviation",
            "diamantes_era": "Era diamonds",
            "adicionar_era": "Add era",
            "nome_sigla_era_obrigatorios": "Enter both the era name and abbreviation.",
            "nenhuma_era": "No eras added yet.",
            "nome_evento": "Event name",
            "sigla_gerada": "Generated abbreviation: {sigla}",
            "marcadores_happy_birthday": "Happy Birthday markers",
            "um_marcador": "This event uses 1 marker.",
            "nome_evento_obrigatorio": "Enter an event name.",
            "adicionar_evento": "Add event",
            "nenhum_evento": "No events added yet.",
            "marcadores_evento": "Markers: {quantidade}",
            "eras_contagem": "{quantidade} eras",
            "eventos_contagem": "{quantidade} events",
            "diamantes_contagem": "{quantidade} 💎",
            "resumo_registros": "{eras} · {diamantes} · {eventos} · {marcadores} {rotulo_marcadores}",
        },
        "Español": {
            "card_url_invalido": "El identificador de la tarjeta en la URL no es válido.",
            "card_removido": "Esta tarjeta ya no está en la colección.",
            "voltar_painel": "← Volver al panel",
            "bot": "Bot",
            "buscando_traduzindo": "Consultando KProfiles y traduciendo el perfil al portugués...",
            "traducao_pausada": "La traducción está pausada temporalmente porque se alcanzó el límite de solicitudes. Inténtalo de nuevo más tarde.",
            "kprofiles_pausado": "KProfiles ha limitado temporalmente las consultas. Inténtalo de nuevo más tarde.",
            "descricao_indisponivel": "No se pudo cargar la descripción: {erro}",
            "foto_card": "Imagen de la tarjeta",
            "sem_foto_card": "Esta tarjeta aún no tiene imagen.",
            "sobre": "Acerca de",
            "fonte_original_ingles": "texto original en inglés",
            "traducao_automatica": "traducción automática",
            "falha_traduzir_resumo": "No se pudo traducir el resumen al idioma seleccionado: {erro}",
            "resumo_indisponivel": "El perfil aún no tiene un resumen disponible.",
            "membros": "Integrantes",
            "verificando_membros": "Comprobando los integrantes de {grupo} en KProfiles...",
            "membros_indisponiveis": "No se pudieron comprobar los integrantes en KProfiles: {erro}",
            "tentar_novamente": "Volver a intentarlo",
            "fonte_conferida": "Fuente consultada",
            "blocos_membros_indisponiveis": "Las secciones de los integrantes aparecerán cuando se encuentre la lista.",
            "membros_adicionais": "Hay integrantes guardados que no aparecen en la lista actual de KProfiles. Se conservaron sus registros y datos.",
            "carregar_resumo": "Cargar el resumen del perfil de {membro}",
            "carregando_resumo": "Cargando el resumen del perfil de {membro}...",
            "resumo_membro_indisponivel": "No se pudo cargar el resumen del perfil de {membro}: {erro}",
            "resumo_temporariamente_indisponivel": "El resumen del perfil de {membro} no está disponible temporalmente. Inténtalo de nuevo más tarde.",
            "registros_antigos": "Registros anteriores sin integrante",
            "registros_anteriores": "Estos registros se añadieron antes de separar los datos por integrante.",
            "resumo": "Resumen",
            "eras": "Eras",
            "eventos": "Eventos",
            "marcadores": "marcadores",
            "nome_era": "Nombre de la era",
            "sigla_era": "Abreviatura de la era",
            "diamantes_era": "Diamantes de la era",
            "adicionar_era": "Añadir era",
            "nome_sigla_era_obrigatorios": "Escribe el nombre y la abreviatura de la era.",
            "nenhuma_era": "Todavía no se ha añadido ninguna era.",
            "nome_evento": "Nombre del evento",
            "sigla_gerada": "Abreviatura generada: {sigla}",
            "marcadores_happy_birthday": "Marcadores de Happy Birthday",
            "um_marcador": "Este evento usa 1 marcador.",
            "nome_evento_obrigatorio": "Escribe el nombre del evento.",
            "adicionar_evento": "Añadir evento",
            "nenhum_evento": "Todavía no se ha añadido ningún evento.",
            "marcadores_evento": "Marcadores: {quantidade}",
            "eras_contagem": "{quantidade} eras",
            "eventos_contagem": "{quantidade} eventos",
            "diamantes_contagem": "{quantidade} 💎",
            "resumo_registros": "{eras} · {diamantes} · {eventos} · {marcadores} {rotulo_marcadores}",
        },
    },
    "autenticacao": {
        "Português (Brasil)": {
            "entrar_google": "Entrar com Google",
            "login_copy": "Entre com sua conta Google para acessar sua coleção privada.",
            "como_usar": "Como usar o site",
            "titulo_ajuda": "Como usar o site",
            "ajuda_intro": "O **BinderLog** ajuda você a acompanhar sua coleção de cards de K-pop: quais idols e grupos você coleciona, quantos cards já tem e quanto falta. Você também pode organizar eras, eventos e fotos.",
            "ajuda_comecar": "Como começar",
            "ajuda_passo_1": "Entre com sua conta Google.",
            "ajuda_passo_2": "Cadastre seus idols manualmente pelo botão **Adicionar idol / bot**.",
            "ajuda_passo_3": "Atualize a quantidade de cards e organize sua coleção nas abas do app.",
            "ajuda_csv_sem_obrigacao": "Você não precisa criar nem ter um arquivo CSV para usar o BinderLog. O cadastro manual funciona normalmente.",
            "ajuda_csv_titulo": "O que é um arquivo CSV?",
            "ajuda_csv_explicacao": "CSV é um arquivo simples de tabela, parecido com uma planilha: cada linha contém um registro e as colunas guardam informações como grupo, idol e quantidade de cards. No BinderLog, a importação está disponível para os arquivos da Garam **Bancodedados** e **Priolist**.",
            "ajuda_csv_importacao": "Se você já tem esses arquivos, entre no app, abra a aba **Importar CSV** e envie-os. Se não tem, basta cadastrar sua coleção manualmente.",
            "identidade_google_invalida": "Não foi possível verificar sua identidade Google. Tente entrar novamente.",
            "sair": "Sair",
            "owner_email_ausente": "OWNER_EMAIL não está configurado. Defina o e-mail Google da conta proprietária da coleção nos segredos do Streamlit.",
        },
        "English": {
            "entrar_google": "Sign in with Google",
            "login_copy": "Sign in with your Google account to access your private collection.",
            "como_usar": "How to use BinderLog",
            "titulo_ajuda": "How to use BinderLog",
            "ajuda_intro": "**BinderLog** helps you keep track of your K-pop photocards: the idols and groups you collect, how many cards you have, and how many you still need. You can also organize eras, events, and photos.",
            "ajuda_comecar": "Getting started",
            "ajuda_passo_1": "Sign in with your Google account.",
            "ajuda_passo_2": "Add idols manually using the **Add idol / bot** button.",
            "ajuda_passo_3": "Update your card counts and organize your collection in the app's tabs.",
            "ajuda_csv_sem_obrigacao": "You don't need to create or have a CSV file to use BinderLog. You can manage your collection manually.",
            "ajuda_csv_titulo": "What is a CSV file?",
            "ajuda_csv_explicacao": "A CSV is a simple table file, similar to a spreadsheet: each row is a record, and columns hold details such as group, idol, and card count. BinderLog can import Garam's **Bancodedados** and **Priolist** files.",
            "ajuda_csv_importacao": "If you already have these files, sign in, open the **Import CSV** tab, and upload them. Otherwise, you can simply add your collection manually.",
            "identidade_google_invalida": "We couldn't verify your Google identity. Please sign in again.",
            "sair": "Sign out",
            "owner_email_ausente": "OWNER_EMAIL is not configured. Add the Google email address of the collection owner to Streamlit secrets.",
        },
        "Español": {
            "entrar_google": "Iniciar sesión con Google",
            "login_copy": "Inicia sesión con tu cuenta de Google para acceder a tu colección privada.",
            "como_usar": "Cómo usar BinderLog",
            "titulo_ajuda": "Cómo usar BinderLog",
            "ajuda_intro": "**BinderLog** te ayuda a llevar el control de tus tarjetas de K-pop: los ídolos y grupos que coleccionas, cuántas tarjetas tienes y cuántas te faltan. También puedes organizar eras, eventos y fotos.",
            "ajuda_comecar": "Cómo empezar",
            "ajuda_passo_1": "Inicia sesión con tu cuenta de Google.",
            "ajuda_passo_2": "Añade tus ídolos manualmente con el botón **Añadir ídolo / bot**.",
            "ajuda_passo_3": "Actualiza la cantidad de tarjetas y organiza tu colección en las pestañas de la aplicación.",
            "ajuda_csv_sem_obrigacao": "No necesitas crear ni tener un archivo CSV para usar BinderLog. Puedes gestionar tu colección manualmente.",
            "ajuda_csv_titulo": "¿Qué es un archivo CSV?",
            "ajuda_csv_explicacao": "Un CSV es un archivo de tabla sencillo, parecido a una hoja de cálculo: cada fila contiene un registro y las columnas guardan datos como el grupo, el ídolo y la cantidad de tarjetas. BinderLog permite importar los archivos **Bancodedados** y **Priolist** de Garam.",
            "ajuda_csv_importacao": "Si ya tienes esos archivos, inicia sesión, abre la pestaña **Importar CSV** y súbelos. Si no, puedes añadir tu colección manualmente.",
            "identidade_google_invalida": "No se pudo verificar tu identidad de Google. Vuelve a iniciar sesión.",
            "sair": "Cerrar sesión",
            "owner_email_ausente": "OWNER_EMAIL no está configurado. Añade a los secretos de Streamlit la dirección de Google de la cuenta propietaria de la colección.",
        },
    },
    "cadastro": {
        "Português (Brasil)": {
            "titulo": "Adicionar idol / bot",
            "idol_solista": "Idol / Solista",
            "grupo_ou_solo": "Grupo (ou SOLO)",
            "bot": "Bot",
            "categoria": "Categoria",
            "prioridade": "Prioridade",
            "total_cartas": "Total de cartas",
            "quantidade_possuo": "Quantas eu tenho",
            "adicionar": "Adicionar",
            "informe_nome": "Informe o nome.",
            "possuo_maior_total": "Você não pode ter mais cartas do que o total.",
            "ja_existe": "{idol} ({grupo}) já existe no bot {bot}. Edite na aba {aba}.",
            "categorias": {"Grupo": "Grupo", "Solo": "Solo", "Outro": "Outro"},
            "prioridades": {"Alta": "Alta", "Média": "Média", "Baixa": "Baixa"},
        },
        "English": {
            "titulo": "Add idol / bot",
            "idol_solista": "Idol / soloist",
            "grupo_ou_solo": "Group (or SOLO)",
            "bot": "Bot",
            "categoria": "Category",
            "prioridade": "Priority",
            "total_cartas": "Total cards",
            "quantidade_possuo": "Cards I have",
            "adicionar": "Add",
            "informe_nome": "Enter a name.",
            "possuo_maior_total": "The number of cards you have cannot exceed the total.",
            "ja_existe": "{idol} ({grupo}) already exists for bot {bot}. Edit it in the {aba} tab.",
            "categorias": {"Grupo": "Group", "Solo": "Soloist", "Outro": "Other"},
            "prioridades": {"Alta": "High", "Média": "Medium", "Baixa": "Low"},
        },
        "Español": {
            "titulo": "Añadir ídolo / bot",
            "idol_solista": "Ídolo / solista",
            "grupo_ou_solo": "Grupo (o SOLO)",
            "bot": "Bot",
            "categoria": "Categoría",
            "prioridade": "Prioridad",
            "total_cartas": "Total de tarjetas",
            "quantidade_possuo": "Tarjetas que tengo",
            "adicionar": "Añadir",
            "informe_nome": "Escribe un nombre.",
            "possuo_maior_total": "No puedes tener más tarjetas que el total.",
            "ja_existe": "{idol} ({grupo}) ya existe en el bot {bot}. Edítalo en la pestaña {aba}.",
            "categorias": {"Grupo": "Grupo", "Solo": "Solista", "Outro": "Otro"},
            "prioridades": {"Alta": "Alta", "Média": "Media", "Baixa": "Baja"},
        },
    },
    "tabela": {
        "Português (Brasil)": {
            "vazio": "Nada por aqui ainda.",
            "instrucoes": "Edite direto na tabela e clique em **Salvar alterações**. O total geral soma cada linha; cartas compartilhadas entre membros do mesmo grupo podem ser contadas mais de uma vez.",
            "bot": "Bot",
            "grupo": "Grupo",
            "prioridade": "Prioridade",
            "categoria": "Categoria",
            "buscar_idol": "Buscar idol",
            "ordenar_por": "Ordenar por",
            "idol": "Idol",
            "total": "Total",
            "possuo": "Tenho",
            "faltam": "Faltam",
            "progresso": "Progresso",
            "url_foto": "URL da foto",
            "excluir": "Excluir",
            "salvar": "💾 Salvar alterações",
            "valores_negativos": "{idol} ({bot}): os valores não podem ser negativos.",
            "possuo_maior_total": "{idol} ({bot}): 'Tenho' não pode ser maior que 'Total'.",
            "duplicado": "{idol} ({grupo}) já existe no bot {bot}.",
            "baixar_csv": "⬇️ Baixar CSV",
            "colunas_exportadas": {
                "bot": "Bot", "grupo": "Grupo", "idol": "Idol",
                "categoria": "Categoria", "prioridade": "Prioridade",
                "total": "Total", "possuo": "Tenho", "image_url": "URL da foto",
                "descricao_pt": "Descrição (português)", "descricao_url": "URL da descrição",
                "descricao_versao": "Versão da descrição",
            },
        },
        "English": {
            "vazio": "Nothing here yet.",
            "instrucoes": "Edit the table directly, then click **Save changes**. The overall total adds up every row; cards shared by members of the same group may be counted more than once.",
            "bot": "Bot",
            "grupo": "Group",
            "prioridade": "Priority",
            "categoria": "Category",
            "buscar_idol": "Search idols",
            "ordenar_por": "Sort by",
            "idol": "Idol",
            "total": "Total",
            "possuo": "Owned",
            "faltam": "Remaining",
            "progresso": "Progress",
            "url_foto": "Image URL",
            "excluir": "Delete",
            "salvar": "💾 Save changes",
            "valores_negativos": "{idol} ({bot}): values cannot be negative.",
            "possuo_maior_total": "{idol} ({bot}): owned cards cannot exceed the total.",
            "duplicado": "{idol} ({grupo}) already exists for bot {bot}.",
            "baixar_csv": "⬇️ Download CSV",
            "colunas_exportadas": {
                "bot": "Bot", "grupo": "Group", "idol": "Idol",
                "categoria": "Category", "prioridade": "Priority",
                "total": "Total", "possuo": "Owned", "image_url": "Image URL",
                "descricao_pt": "Description (Portuguese)", "descricao_url": "Description URL",
                "descricao_versao": "Description version",
            },
        },
        "Español": {
            "vazio": "Todavía no hay nada aquí.",
            "instrucoes": "Edita la tabla directamente y luego pulsa **Guardar cambios**. El total general suma todas las filas; las tarjetas compartidas entre integrantes de un mismo grupo pueden contarse más de una vez.",
            "bot": "Bot",
            "grupo": "Grupo",
            "prioridade": "Prioridad",
            "categoria": "Categoría",
            "buscar_idol": "Buscar ídolos",
            "ordenar_por": "Ordenar por",
            "idol": "Ídolo",
            "total": "Total",
            "possuo": "Tengo",
            "faltam": "Pendientes",
            "progresso": "Progreso",
            "url_foto": "URL de la imagen",
            "excluir": "Eliminar",
            "salvar": "💾 Guardar cambios",
            "valores_negativos": "{idol} ({bot}): los valores no pueden ser negativos.",
            "possuo_maior_total": "{idol} ({bot}): las tarjetas que tienes no pueden superar el total.",
            "duplicado": "{idol} ({grupo}) ya existe en el bot {bot}.",
            "baixar_csv": "⬇️ Descargar CSV",
            "colunas_exportadas": {
                "bot": "Bot", "grupo": "Grupo", "idol": "Ídolo",
                "categoria": "Categoría", "prioridade": "Prioridad",
                "total": "Total", "possuo": "Tengo", "image_url": "URL de la imagen",
                "descricao_pt": "Descripción (portugués)", "descricao_url": "URL de la descripción",
                "descricao_versao": "Versión de la descripción",
            },
        },
    },
    "fotos": {
        "Português (Brasil)": {
            "vazio": "Importe ou adicione idols primeiro.",
            "descricao_busca": "As buscas usam KProfiles primeiro e kpopping.com como alternativa. Os resultados ficam em cache por até 24 horas.",
            "kpopping_pausado": "O kpopping.com está temporariamente pausado após limitar uma busca. O KProfiles continua disponível.",
            "buscar_lote": "Buscar fotos em lote",
            "filtrar_bot": "Filtrar por bot (vazio = todos)",
            "escolher_bots": "Escolha os bots",
            "buscar_para": "Buscar fotos para",
            "so_faltantes": "Só as que faltam",
            "faltantes_repetidas": "Faltam + repetidas",
            "todas_substituir": "Todas (substituir)",
            "limite": "Limite por busca",
            "buscar_contagem": "🔎 Buscar fotos ({quantidade} idols)",
            "atualizadas": "{quantidade} fotos atualizadas.",
            "lote_interrompido": "{erro} O restante da busca em lote foi interrompido.",
            "sem_novas": "Sem foto nova: {itens}. Use o ajuste individual abaixo.",
            "sem_foto_contagem": "{quantidade} sem foto",
            "repetidas_contagem": "{quantidade} repetidas",
            "ajuste_individual": "Ajustar foto individual",
            "idol": "Idol",
            "card_sem_foto": "Este card ainda não tem foto.",
            "buscar_outra": "🔄 Buscar outra foto",
            "outra_nao_encontrada": "Não achei outra foto. Cole uma URL abaixo.",
            "url_direta": "URL direta da foto",
            "salvar_url": "Salvar URL",
        },
        "English": {
            "vazio": "Import or add idols first.",
            "descricao_busca": "Photos are searched on KProfiles first, with kpopping.com as a backup. Results are cached for up to 24 hours.",
            "kpopping_pausado": "kpopping.com is temporarily paused after rate-limiting a request. KProfiles is still available.",
            "buscar_lote": "Search for photos in bulk",
            "filtrar_bot": "Filter by bot (leave empty for all)",
            "escolher_bots": "Choose bots",
            "buscar_para": "Find photos for",
            "so_faltantes": "Missing photos only",
            "faltantes_repetidas": "Missing and duplicate photos",
            "todas_substituir": "All photos (replace)",
            "limite": "Maximum photos per search",
            "buscar_contagem": "🔎 Search for photos ({quantidade} idols)",
            "atualizadas": "Photos updated: {quantidade}.",
            "lote_interrompido": "{erro} The rest of the bulk search was stopped.",
            "sem_novas": "No new photo found for: {itens}. Use the individual photo controls below.",
            "sem_foto_contagem": "{quantidade} without a photo",
            "repetidas_contagem": "{quantidade} duplicates",
            "ajuste_individual": "Update an individual photo",
            "idol": "Idol",
            "card_sem_foto": "This card does not have a photo yet.",
            "buscar_outra": "🔄 Find another photo",
            "outra_nao_encontrada": "Couldn't find another photo. Paste an image URL below.",
            "url_direta": "Direct image URL",
            "salvar_url": "Save URL",
        },
        "Español": {
            "vazio": "Primero, importa o añade ídolos.",
            "descricao_busca": "Primero se buscan fotos en KProfiles y, como alternativa, en kpopping.com. Los resultados se guardan en caché hasta 24 horas.",
            "kpopping_pausado": "kpopping.com está en pausa temporalmente porque limitó una solicitud. KProfiles sigue disponible.",
            "buscar_lote": "Buscar fotos en lote",
            "filtrar_bot": "Filtrar por bot (vacío = todos)",
            "escolher_bots": "Elige los bots",
            "buscar_para": "Buscar fotos para",
            "so_faltantes": "Solo las que faltan",
            "faltantes_repetidas": "Faltantes y repetidas",
            "todas_substituir": "Todas (reemplazar)",
            "limite": "Límite de fotos por búsqueda",
            "buscar_contagem": "🔎 Buscar fotos ({quantidade} ídolos)",
            "atualizadas": "Fotos actualizadas: {quantidade}.",
            "lote_interrompido": "{erro} Se detuvo el resto de la búsqueda en lote.",
            "sem_novas": "No se encontró una foto nueva para: {itens}. Usa los controles individuales de abajo.",
            "sem_foto_contagem": "{quantidade} sin foto",
            "repetidas_contagem": "{quantidade} repetidas",
            "ajuste_individual": "Cambiar una foto individual",
            "idol": "Ídolo",
            "card_sem_foto": "Esta tarjeta aún no tiene foto.",
            "buscar_outra": "🔄 Buscar otra foto",
            "outra_nao_encontrada": "No se encontró otra foto. Pega una URL de imagen abajo.",
            "url_direta": "URL directa de la imagen",
            "salvar_url": "Guardar URL",
        },
    },
    "importacao": {
        "Português (Brasil)": {
            "titulo": "Importar coleção da Garam",
            "descricao": "O arquivo Bancodedados é obrigatório e contém o total e a quantidade adquirida. Priolist é opcional e preenche prioridade e categoria. Idols já existentes serão atualizados.",
            "bot": "Bot",
            "bancodedados": "Bancodedados (.csv)",
            "priolist": "Priolist (.csv) — opcional",
            "previa": "Prévia da importação",
            "linhas_prontas": "{quantidade} linhas prontas para importar",
            "avisos_csv": "⚠️ {quantidade} aviso(s) na leitura do CSV",
            "col_grupo": "Grupo",
            "col_idol": "Idol",
            "col_total": "Total",
            "col_possuo": "Tenho",
            "col_categoria": "Categoria",
            "col_prioridade": "Prioridade",
            "importar": "Importar CSV",
            "importados": "{quantidade} linhas importadas para {bot}!",
            "erro_colunas_banco": "O arquivo Bancodedados precisa conter estas colunas: {colunas}",
            "erro_colunas_priolist": "A Priolist precisa conter: Group, Idol, Priority, Category",
            "linha_invalida": "{grupo} / {idol}: quantidade vazia, inválida ou negativa — linha ignorada.",
            "acima_total": "{grupo} / {idol}: a quantidade adquirida ({possuo}) excede o total ({total}) — ajustada para o total.",
        },
        "English": {
            "titulo": "Import a collection from Garam",
            "descricao": "The Bancodedados file is required and contains the total and owned card counts. Priolist is optional and supplies priority and category. Existing idols will be updated.",
            "bot": "Bot",
            "bancodedados": "Bancodedados (.csv)",
            "priolist": "Priolist (.csv) — optional",
            "previa": "Import preview",
            "linhas_prontas": "{quantidade} rows ready to import",
            "avisos_csv": "⚠️ {quantidade} CSV warning(s)",
            "col_grupo": "Group",
            "col_idol": "Idol",
            "col_total": "Total",
            "col_possuo": "Owned",
            "col_categoria": "Category",
            "col_prioridade": "Priority",
            "importar": "Import CSV",
            "importados": "Imported {quantidade} rows into {bot}!",
            "erro_colunas_banco": "The Bancodedados file must contain these columns: {colunas}",
            "erro_colunas_priolist": "Priolist must contain: Group, Idol, Priority, Category",
            "linha_invalida": "{grupo} / {idol}: card count is missing, invalid, or negative; row skipped.",
            "acima_total": "{grupo} / {idol}: owned count ({possuo}) exceeds the total ({total}); adjusted to the total.",
        },
        "Español": {
            "titulo": "Importar una colección de Garam",
            "descricao": "El archivo Bancodedados es obligatorio y contiene el total y la cantidad de tarjetas que tienes. Priolist es opcional y aporta la prioridad y la categoría. Se actualizarán los ídolos que ya existan.",
            "bot": "Bot",
            "bancodedados": "Bancodedados (.csv)",
            "priolist": "Priolist (.csv) — opcional",
            "previa": "Vista previa de la importación",
            "linhas_prontas": "{quantidade} filas listas para importar",
            "avisos_csv": "⚠️ {quantidade} aviso(s) en el CSV",
            "col_grupo": "Grupo",
            "col_idol": "Ídolo",
            "col_total": "Total",
            "col_possuo": "Tengo",
            "col_categoria": "Categoría",
            "col_prioridade": "Prioridad",
            "importar": "Importar CSV",
            "importados": "Se importaron {quantidade} filas a {bot}.",
            "erro_colunas_banco": "El archivo Bancodedados debe contener estas columnas: {colunas}",
            "erro_colunas_priolist": "Priolist debe contener: Group, Idol, Priority, Category",
            "linha_invalida": "{grupo} / {idol}: la cantidad de tarjetas está vacía, no es válida o es negativa; se omitió la fila.",
            "acima_total": "{grupo} / {idol}: la cantidad que tienes ({possuo}) supera el total ({total}); se ajustó al total.",
        },
    },
    "sistema": {
        "Português (Brasil)": {
            "erro_secrets_sintaxe": "Erro de sintaxe no arquivo de segredos {arquivo}: {erro}",
            "database_ausente": "DATABASE_URL não encontrada. Crie o arquivo indicado abaixo e adicione a URL de conexão do PostgreSQL.",
            "arquivo_contexto": "Arquivo existe? {existe} · Pasta atual do terminal: {pasta}",
            "login_necessario": "Entre com uma conta Google para conectar sua coleção.",
            "role_insegura": "A conexão do banco usa uma conta que ignora as regras de privacidade do PostgreSQL. Configure DATABASE_URL com um usuário sem SUPERUSER e sem BYPASSRLS.",
        },
        "English": {
            "erro_secrets_sintaxe": "Syntax error in secrets file {arquivo}: {erro}",
            "database_ausente": "DATABASE_URL was not found. Create the file shown below and add the PostgreSQL connection URL.",
            "arquivo_contexto": "File exists? {existe} · Current working directory: {pasta}",
            "login_necessario": "Sign in with a Google account to connect to your collection.",
            "role_insegura": "The database connection uses an account that can bypass PostgreSQL privacy policies. Set DATABASE_URL to a user without SUPERUSER or BYPASSRLS privileges.",
        },
        "Español": {
            "erro_secrets_sintaxe": "Error de sintaxis en el archivo de secretos {arquivo}: {erro}",
            "database_ausente": "No se encontró DATABASE_URL. Crea el archivo indicado abajo y añade la URL de conexión de PostgreSQL.",
            "arquivo_contexto": "¿Existe el archivo? {existe} · Directorio actual de la terminal: {pasta}",
            "login_necessario": "Inicia sesión con una cuenta de Google para conectar tu colección.",
            "role_insegura": "La conexión a la base de datos usa una cuenta que puede omitir las políticas de privacidad de PostgreSQL. Configura DATABASE_URL con un usuario sin privilegios SUPERUSER ni BYPASSRLS.",
        },
    },
}

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
        st.error(
            texto_sistema(
                "erro_secrets_sintaxe", arquivo=SECRETS_FILE, erro=e
            )
        )
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
        st.error(texto_sistema("login_necessario"))
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
            st.error(texto_sistema("role_insegura"))
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


def texto_navegacao(chave):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO[chave][idioma]


def texto_painel(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO[chave][idioma].format(**valores)


def texto_detalhe(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["detalhe"][idioma][chave].format(**valores)


def descricao_para_idioma(texto, original_ingles=None):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    if idioma == IDIOMAS[0]:
        if original_ingles:
            return traduzir_descricao_ptbr(original_ingles), False
        return texto, False
    if idioma == "English":
        if original_ingles:
            return original_ingles, True
        return traduzir_descricao(texto, "pt-BR|en"), False
    if original_ingles:
        return traduzir_descricao(original_ingles, "en|es"), False
    return traduzir_descricao(texto, "pt-BR|es"), False


def texto_autenticacao(chave):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["autenticacao"][idioma][chave]


def texto_cadastro(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["cadastro"][idioma][chave].format(**valores)


def texto_tabela(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["tabela"][idioma][chave].format(**valores)


def texto_fotos(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["fotos"][idioma][chave].format(**valores)


def texto_importacao(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["importacao"][idioma][chave].format(**valores)


def texto_sistema(chave, **valores):
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    return TRADUCOES_NAVEGACAO["sistema"][idioma][chave].format(**valores)


def seletor_idioma():
    st.session_state.setdefault("idioma_interface", IDIOMAS[0])
    nomes_idiomas = {
        IDIOMAS[0]: "Português",
        IDIOMAS[1]: "English",
        IDIOMAS[2]: "Español",
    }
    st.segmented_control(
        texto_navegacao("label_idioma"),
        options=IDIOMAS,
        format_func=nomes_idiomas.get,
        selection_mode="single",
        key="idioma_interface",
        label_visibility="collapsed",
        width="stretch",
        wrap=True,
    )


def mostrar_como_usar():
    @st.dialog(texto_autenticacao("titulo_ajuda"))
    def dialog_ajuda():
        st.markdown(texto_autenticacao("ajuda_intro"))
        st.markdown(f"### {texto_autenticacao('ajuda_comecar')}")
        st.markdown(
            f"1. {texto_autenticacao('ajuda_passo_1')}\n"
            f"2. {texto_autenticacao('ajuda_passo_2')}\n"
            f"3. {texto_autenticacao('ajuda_passo_3')}"
        )
        st.info(texto_autenticacao("ajuda_csv_sem_obrigacao"))
        st.markdown(f"### {texto_autenticacao('ajuda_csv_titulo')}")
        st.markdown(texto_autenticacao("ajuda_csv_explicacao"))
        st.markdown(texto_autenticacao("ajuda_csv_importacao"))

    dialog_ajuda()


def mostrar_configuracoes_conta(nome, email, avatar_html):
    @st.dialog(
        texto_navegacao("configuracoes_conta"),
        width="small",
        position="center",
    )
    def dialog_configuracoes():
        st.markdown(
            '<div class="account-menu__identity">'
            f'{avatar_html}<div><strong>{esc(nome)}</strong>'
            f'<span>{esc(email)}</span></div></div>',
            unsafe_allow_html=True,
        )
        st.caption(texto_navegacao("label_idioma"))
        seletor_idioma()
        st.divider()
        if st.button(
            texto_navegacao("sair_conta"),
            key="account_dialog_logout",
            width="stretch",
        ):
            st.logout()

    dialog_configuracoes()


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
            }
            .st-key-login_screen .st-key-login_google button {
                min-height: 2.8rem;
                padding: .5rem 1.35rem;
                font-size: 1rem;
            }
            .st-key-login_screen .st-key-como_usar_site button {
                min-height: 2.3rem;
                padding: .35rem 1rem;
                font-size: .92rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="login_screen"):
            seletor_idioma()
            st.markdown(
                '<h1 class="login-title">BinderLog</h1>'
                f'<p class="login-copy">{esc(texto_autenticacao("login_copy"))}</p>',
                unsafe_allow_html=True,
            )
            if st.button(
                texto_autenticacao("entrar_google"),
                type="primary",
                width="content",
                key="login_google",
            ):
                st.login()
            if st.button(
                texto_autenticacao("como_usar"),
                width="content",
                key="como_usar_site",
            ):
                mostrar_como_usar()
        st.stop()

    email = str(st.user.get("email", "")).strip().casefold()
    user_sub = str(st.user.get("sub", "")).strip()
    if not email or not user_sub or st.user.get("email_verified") is not True:
        st.error(texto_autenticacao("identidade_google_invalida"))
        if st.button(texto_autenticacao("sair")):
            st.logout()
        st.stop()

    owner_email = str(_secret("OWNER_EMAIL") or "").strip().casefold()
    if not owner_email:
        st.error(texto_autenticacao("owner_email_ausente"))
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
    idol = "" if idol is None or pd.isna(idol) else str(idol).strip()
    grupo = "" if grupo is None or pd.isna(grupo) else str(grupo).strip()
    if idol in (GRUPO_COMPLETO, "Todos os membros", "-"):
        return "grupo", grupo, ALIAS_GRUPO.get(grupo.casefold(), grupo)
    base = re.sub(r"\s+\d+$", "", idol).strip()
    solo = grupo.casefold() == "solo"
    g = PESSOA_GRUPO.get(base.casefold(), "") if solo else (
        ALIAS_GRUPO.get(grupo.casefold(), grupo) or PESSOA_GRUPO.get(base.casefold(), "")
    )
    return ("solista" if solo else "pessoa"), base, g or ""


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
    guardar_descricao_original("card", card_id, perfil["descricao"], perfil["url"])
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
    guardar_descricao_original("membro", membro_id, perfil["descricao"], perfil["url"])
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
        raise ValueError(
            texto_importacao("erro_colunas_banco", colunas=", ".join(obrig))
        )
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
        avisos.append(
            texto_importacao("linha_invalida", grupo=r.Grupo, idol=r.Idol)
        )
    b = b[~invalido].copy()
    for r in b[b["n_possuo"] > b["n_total"]].itertuples():
        avisos.append(
            texto_importacao(
                "acima_total",
                grupo=r.Grupo,
                idol=r.Idol,
                possuo=int(r.n_possuo),
                total=int(r.n_total),
            )
        )
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
            raise ValueError(texto_importacao("erro_colunas_priolist"))

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
CSS_DIR = Path(__file__).resolve().parent / "css"
app_css = (CSS_DIR / "app.css").read_text(encoding="utf-8")
st.markdown(
    f"<style>{app_css}</style>",
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
        st.session_state[chave_erro] = "nome_evento_obrigatorio"
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
    resumo = texto_detalhe(
        "resumo_registros",
        eras=texto_detalhe("eras_contagem", quantidade=len(eras)),
        diamantes=texto_detalhe("diamantes_contagem", quantidade=total_diamantes),
        eventos=texto_detalhe("eventos_contagem", quantidade=len(eventos)),
        marcadores=total_marcadores,
        rotulo_marcadores=texto_detalhe("marcadores"),
    )
    titulo = f"👤 {nome_membro} · {resumo}" if nome_membro else resumo

    if nome_membro:
        with st.expander(titulo, expanded=False):
            _renderizar_formularios_card(card_id, membro_id, sufixo, eras, eventos, resumo)
    else:
        _renderizar_formularios_card(card_id, membro_id, sufixo, eras, eventos, resumo)


def _renderizar_formularios_card(card_id, membro_id, sufixo, eras, eventos, resumo):
    st.caption(f"{texto_detalhe('resumo')}: {resumo}")
    col_eras, col_eventos = st.columns(2, gap="large")
    with col_eras:
        st.subheader(texto_detalhe("eras"))
        with st.form(f"form_era_{card_id}_{sufixo}", clear_on_submit=True):
            nome_era = st.text_input(texto_detalhe("nome_era"))
            sigla_era = st.text_input(texto_detalhe("sigla_era"))
            diamantes_era = st.selectbox(
                texto_detalhe("diamantes_era"), [1, 2, 3],
                format_func=lambda n: "💎" * n,
                key=f"diamantes_era_{card_id}_{sufixo}",
            )
            enviar_era = st.form_submit_button(
                texto_detalhe("adicionar_era"), type="primary"
            )
        if enviar_era:
            if not nome_era.strip() or not sigla_era.strip():
                st.error(texto_detalhe("nome_sigla_era_obrigatorios"))
            else:
                run("INSERT INTO colecao_eras "
                    "(colecao_id, membro_id, nome, sigla, diamantes) VALUES (?,?,?,?,?)",
                    (int(card_id), membro_id, nome_era.strip(), sigla_era.strip(),
                     int(diamantes_era)))
                st.rerun()

        if eras.empty:
            st.info(texto_detalhe("nenhuma_era"))
        else:
            for era in eras.itertuples():
                diamantes = "💎" * int(era.diamantes)
                st.markdown(f"**{esc(era.nome)}** · `{esc(era.sigla)}` · {diamantes}")

    with col_eventos:
        st.subheader(texto_detalhe("eventos"))
        chave_membro = membro_id if membro_id is not None else "card"
        prefixo_evento = f"evento_{card_id}_{chave_membro}"
        chave_nome_evento = f"{prefixo_evento}_nome"
        nome_evento = st.text_input(
            texto_detalhe("nome_evento"), key=chave_nome_evento
        )
        sigla_gerada = sigla_evento(nome_evento)
        st.caption(texto_detalhe("sigla_gerada", sigla=sigla_gerada or "—"))
        chave_marcadores = f"{prefixo_evento}_marcadores"
        if eh_happy_birthday(nome_evento):
            st.selectbox(
                texto_detalhe("marcadores_happy_birthday"),
                [1, 2],
                key=chave_marcadores,
            )
        else:
            st.caption(texto_detalhe("um_marcador"))
        chave_erro = f"{prefixo_evento}_erro"
        if st.session_state.get(chave_erro):
            st.error(texto_detalhe(st.session_state[chave_erro]))
        st.button(
            texto_detalhe("adicionar_evento"),
            key=f"adicionar_{prefixo_evento}",
            type="primary",
            on_click=adicionar_evento,
            args=(int(card_id), membro_id),
        )

        if eventos.empty:
            st.info(texto_detalhe("nenhum_evento"))
        else:
            for evento in eventos.itertuples():
                st.markdown(
                    f"{icone_evento(evento.nome)} **{esc(evento.nome)}** · "
                    f"`{esc(evento.sigla)}` · "
                    f"{texto_detalhe('marcadores_evento', quantidade=int(evento.marcadores))}"
                )


def dialog_adicionar():
    @st.dialog(texto_cadastro("titulo"))
    def dialog_formulario():
        idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
        traducoes = TRADUCOES_NAVEGACAO["cadastro"][idioma]
        with st.form("novo", clear_on_submit=True):
            idol = st.text_input(texto_cadastro("idol_solista"))
            grupo = st.text_input(texto_cadastro("grupo_ou_solo"))
            bot = st.selectbox(texto_cadastro("bot"), BOTS)
            c4, c5 = st.columns(2)
            cat = c4.selectbox(
                texto_cadastro("categoria"),
                CATEGORIAS,
                format_func=traducoes["categorias"].get,
            )
            prio = c5.selectbox(
                texto_cadastro("prioridade"),
                PRIORIDADES,
                index=1,
                format_func=traducoes["prioridades"].get,
            )
            c6, c7 = st.columns(2)
            total = c6.number_input(
                texto_cadastro("total_cartas"), min_value=0, value=0
            )
            possuo = c7.number_input(
                texto_cadastro("quantidade_possuo"), min_value=0, value=0
            )
            if st.form_submit_button(texto_cadastro("adicionar"), type="primary"):
                if not idol.strip():
                    st.error(texto_cadastro("informe_nome"))
                elif possuo > total:
                    st.error(texto_cadastro("possuo_maior_total"))
                else:
                    try:
                        run("INSERT INTO colecao (bot, grupo, idol, categoria, prioridade, total, possuo) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (bot, grupo.strip(), idol.strip(), cat, prio, int(total), int(possuo)))
                        st.rerun()
                    except psycopg2.IntegrityError:
                        st.error(
                            texto_cadastro(
                                "ja_existe",
                                idol=idol,
                                grupo=grupo,
                                bot=bot,
                                aba=texto_navegacao("aba_tabela"),
                            )
                        )

    dialog_formulario()


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
        st.error(texto_detalhe("card_url_invalido"))
        st.query_params.pop("card", None)
        st.stop()

    selecionado = df_all[df_all["id"] == card_selecionado]
    if selecionado.empty:
        st.warning(texto_detalhe("card_removido"))
        if st.button(texto_detalhe("voltar_painel")):
            st.query_params.pop("card", None)
            st.rerun()
        st.stop()

    card = selecionado.iloc[0]
    if st.button(texto_detalhe("voltar_painel")):
        st.query_params.pop("card", None)
        st.rerun()
    st.title(card["grupo"] if card["idol"] == GRUPO_COMPLETO else card["idol"])
    st.caption(f'{card["grupo"]} · {texto_detalhe("bot")} {card["bot"]}')

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
            with st.spinner(texto_detalhe("buscando_traduzindo")):
                descricao_card, fonte_descricao = atualizar_descricao_card(
                    int(card_selecionado), card["idol"], card["grupo"]
                )
            registrar_sucesso_descricao("card", card_selecionado)
        except MyMemoryRateLimited as erro:
            st.warning(texto_detalhe("traducao_pausada"))
            registrar_falha_descricao("card", card_selecionado)
        except KProfilesRateLimited as erro:
            st.warning(texto_detalhe("kprofiles_pausado"))
            registrar_falha_descricao("card", card_selecionado)
        except (requests.RequestException, ValueError) as erro:
            st.error(texto_detalhe("descricao_indisponivel", erro=erro))
            registrar_falha_descricao("card", card_selecionado)
        original_card = descricao_original("card", card_selecionado)
        if (
            original_card
            and (pd.isna(descricao_card) or not str(descricao_card).strip())
        ):
            descricao_card, fonte_descricao = original_card
            descricao_card_em_ingles = True

    if pd.notna(descricao_card) and str(descricao_card).strip():
        try:
            descricao_card, descricao_card_em_ingles = descricao_para_idioma(
                str(descricao_card),
                original_card[0] if original_card else None,
            )
        except MyMemoryRateLimited as erro:
            st.warning(texto_detalhe("traducao_pausada"))
        except (requests.RequestException, ValueError) as erro:
            st.warning(texto_detalhe("falha_traduzir_resumo", erro=erro))

    coluna_foto, coluna_sobre = st.columns([1, 2], gap="large", vertical_alignment="top")
    with coluna_foto:
        if card["url_foto"]:
            st.markdown(
                f'<div class="detail-photo"><img src="{esc(card["url_foto"], quote=True)}" '
                f'alt="{esc(texto_detalhe("foto_card"), quote=True)}" '
                'referrerpolicy="no-referrer" loading="lazy"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info(texto_detalhe("sem_foto_card"))
    with coluna_sobre:
        st.subheader(texto_detalhe("sobre"))
        if pd.notna(descricao_card) and str(descricao_card).strip():
            st.write(str(descricao_card))
            if pd.notna(fonte_descricao) and fonte_descricao:
                texto_fonte = (
                    texto_detalhe("fonte_original_ingles")
                    if descricao_card_em_ingles
                    else texto_detalhe("traducao_automatica")
                )
                st.caption(f"Fonte: [KProfiles]({fonte_descricao}) · {texto_fonte}")
        else:
            st.caption(texto_detalhe("resumo_indisponivel"))

    grupo_completo = card["idol"] == GRUPO_COMPLETO
    if grupo_completo:
        membros = q("SELECT id, nome, descricao_pt, descricao_url, descricao_versao "
                    "FROM colecao_membros "
                    "WHERE colecao_id=? ORDER BY nome",
                    (int(card_selecionado),))
        roster_url = None
        roster = None
        st.subheader(texto_detalhe("membros"))
        try:
            with st.spinner(
                texto_detalhe("verificando_membros", grupo=card["grupo"])
            ):
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
            st.warning(texto_detalhe("membros_indisponiveis", erro=erro))
            if st.button(
                texto_detalhe("tentar_novamente"),
                key=f"buscar_membros_{card_selecionado}",
            ):
                st.rerun()

        if roster_url:
            st.markdown(
                f'{texto_detalhe("fonte_conferida")}: [KProfiles]({roster_url})'
            )

        if membros.empty:
            st.info(texto_detalhe("blocos_membros_indisponiveis"))
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
                    st.warning(texto_detalhe("membros_adicionais"))
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
                        texto_detalhe(
                            "carregar_resumo", membro=str(membro.nome)
                        ),
                        key=f"carregar_resumo_membro_{membro.id}",
                    ):
                        try:
                            with st.spinner(
                                texto_detalhe(
                                    "carregando_resumo", membro=str(membro.nome)
                                )
                            ):
                                descricao_membro, fonte_membro = atualizar_descricao_membro(
                                    int(membro.id), membro.nome, card["grupo"]
                                )
                            registrar_sucesso_descricao("membro", membro.id)
                        except MyMemoryRateLimited as erro:
                            registrar_falha_descricao("membro", membro.id)
                            st.warning(texto_detalhe("traducao_pausada"))
                        except KProfilesRateLimited as erro:
                            registrar_falha_descricao("membro", membro.id)
                            st.warning(texto_detalhe("kprofiles_pausado"))
                        except (requests.RequestException, ValueError) as erro:
                            registrar_falha_descricao("membro", membro.id)
                            st.caption(
                                texto_detalhe(
                                    "resumo_membro_indisponivel",
                                    membro=str(membro.nome),
                                    erro=erro,
                                )
                            )
                        original_membro = descricao_original("membro", membro.id)
                        if (
                            original_membro
                            and (
                                pd.isna(descricao_membro)
                                or not str(descricao_membro).strip()
                            )
                        ):
                            descricao_membro, fonte_membro = original_membro
                            descricao_membro_em_ingles = True
                elif resumo_vazio:
                    st.caption(
                        texto_detalhe(
                            "resumo_temporariamente_indisponivel",
                            membro=str(membro.nome),
                        )
                    )
                if pd.notna(descricao_membro) and str(descricao_membro).strip():
                    try:
                        descricao_membro, descricao_membro_em_ingles = (
                            descricao_para_idioma(
                                str(descricao_membro),
                                original_membro[0] if original_membro else None,
                            )
                        )
                    except MyMemoryRateLimited as erro:
                        st.warning(texto_detalhe("traducao_pausada"))
                    except (requests.RequestException, ValueError) as erro:
                        st.warning(
                            texto_detalhe("falha_traduzir_resumo", erro=erro)
                        )
                if pd.notna(descricao_membro) and str(descricao_membro).strip():
                    st.markdown(str(descricao_membro))
                    if pd.notna(fonte_membro) and fonte_membro:
                        texto_fonte = (
                            texto_detalhe("fonte_original_ingles")
                            if descricao_membro_em_ingles
                            else texto_detalhe("traducao_automatica")
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
            with st.expander(texto_detalhe("registros_antigos"), expanded=False):
                st.caption(texto_detalhe("registros_anteriores"))
                for era in eras_sem_membro.itertuples():
                    diamantes = "💎" * int(era.diamantes)
                    st.markdown(f"**{esc(era.nome)}** · `{esc(era.sigla)}` · {diamantes}")
                for evento in eventos_sem_membro.itertuples():
                    st.markdown(
                        f"{icone_evento(evento.nome)} **{esc(evento.nome)}** · "
                        f"`{esc(evento.sigla)}` · "
                        f"{texto_detalhe('marcadores_evento', quantidade=int(evento.marcadores))}"
                    )
    else:
        renderizar_eras_eventos(int(card_selecionado))
    st.stop()

# ---------------------------------------------------------------- Cabeçalho
tot_g, pos_g = int(df_all["total"].sum()), int(df_all["possuo"].sum())
with st.container(key="app_header"):
    c_tit, c_pill, c_btn, c_user = st.columns(
        [4.2, 2.4, 2.4, 1.6], vertical_alignment="center"
    )
    c_tit.markdown(
        '<div class="ttl"><div class="logo">💿</div><div><b>BinderLog</b><br>'
        f'<span class="mut">{esc(texto_navegacao("colecao_bots_discord"))}</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    c_pill.markdown(
        f'<div class="pill">{ring(pct(pos_g, tot_g), sm=True)} '
        f'{esc(texto_navegacao("colecao_completa"))}</div>',
                    unsafe_allow_html=True)
    if c_btn.button(
        texto_navegacao("adicionar_idol_bot"), type="primary", width="stretch"
    ):
        dialog_adicionar()
    nome_conta = st.session_state["authenticated_user_name"]
    email_conta = st.session_state["authenticated_user_email"]
    foto_conta = st.session_state.get("authenticated_user_picture", "")
    if foto_conta.startswith("https://"):
        avatar_html = (
            f'<img src="{esc(foto_conta, quote=True)}" '
            f'alt="{esc(texto_navegacao("foto_perfil"), quote=True)}" '
            'style="width:42px;height:42px;border-radius:50%;object-fit:cover;'
            'display:block;">'
        )
    else:
        iniciais = esc("".join(parte[0] for parte in nome_conta.split()[:2]).upper())
        avatar_html = (
            f'<div aria-label="{esc(texto_navegacao("foto_perfil_indisponivel"), quote=True)}" '
            'style="width:42px;height:42px;border-radius:50%;background:#dbeafe;'
            'color:#1e3a8a;display:flex;align-items:center;justify-content:center;'
            'font-weight:700;">'
            f'{iniciais}</div>'
        )
    with c_user:
        c_foto, c_menu = st.columns([1.1, 0.9], vertical_alignment="center")
        c_foto.markdown(avatar_html, unsafe_allow_html=True)
        if c_menu.button(
            "⋮",
            help=texto_navegacao("configuracoes_conta"),
            key="account_settings_open",
            width="stretch",
        ):
            mostrar_configuracoes_conta(nome_conta, email_conta, avatar_html)

tab_painel, tab_tabela, tab_fotos, tab_imp = st.tabs(
    [
        texto_navegacao("aba_painel"),
        texto_navegacao("aba_tabela"),
        texto_navegacao("aba_fotos"),
        texto_navegacao("aba_importar_csv"),
    ]
)

# ---------------------------------------------------------------- Painel
with tab_painel:
    if df_all.empty:
        st.info(texto_painel("painel_vazio"))
    else:
        bots_ord = [texto_painel("todos")] + sorted(df_all["bot"].unique())
        if st.session_state.get("bot_sel") not in bots_ord:
            st.session_state["bot_sel"] = texto_painel("todos")
        sel = st.session_state["bot_sel"]
        bot_todos = texto_painel("todos")
        base_df = df_all if sel == bot_todos else df_all[df_all["bot"] == sel]
        t, p = int(base_df["total"].sum()), int(base_df["possuo"].sum())
        v = pct(p, t)
        st.markdown(
            f'<div class="hero"><div><div class="lbl">{texto_painel("progresso_geral")}</div>'
            f'<div class="big">{v:.0f}%</div>'
            f'<div class="sub">{texto_painel("cartas_coletadas", possuidas=p, total=t)}'
            f'</div></div>{ring(v)}{barra(v)}</div>',
            unsafe_allow_html=True,
        )

        st.subheader(texto_painel("colecoes_avancadas"))
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
                            f"{int(destaque.total)} {texto_painel('cartas')}"
                        )

        esq, dir_ = st.columns([1, 3], gap="large")
        with esq:
            st.markdown(
                f'<div class="lbl">{texto_painel("bots")}</div>',
                unsafe_allow_html=True,
            )
            with st.container(key="botes"):
                for b in bots_ord:
                    sub = df_all if b == bot_todos else df_all[df_all["bot"] == b]
                    vb = pct(sub["possuo"].sum(), sub["total"].sum())
                    st.button(
                        f"{b}  ·  {texto_painel('idols_contagem', quantidade=len(sub))}",
                        key=f"bot_{b}",
                        width="stretch",
                        type="primary" if b == sel else "secondary",
                        on_click=selecionar_bot,
                        args=(b,),
                    )
                    st.markdown(
                        f'<div>{barra(vb)}<div class="brow"><span>'
                        f'{texto_painel("progresso")}</span><b>{vb:.0f}%</b></div></div>',
                        unsafe_allow_html=True,
                    )
        with dir_:
            f1, f2, f3 = st.columns([3, 2, 2])
            busca = f1.text_input(
                texto_painel("buscar"),
                placeholder=texto_painel("buscar_idol_grupo"),
                label_visibility="collapsed",
                key="p_busca",
            )
            idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
            ordem = f2.selectbox(
                texto_painel("ordenar"),
                ORDENS,
                format_func=TRADUCOES_NAVEGACAO["ordens"][idioma].get,
                label_visibility="collapsed",
                key="p_ordem",
            )
            prios = f3.multiselect(
                texto_painel("prioridade"),
                PRIORIDADES,
                format_func=TRADUCOES_NAVEGACAO["prioridades"][idioma].get,
                placeholder=texto_painel("prioridade"),
                label_visibility="collapsed",
                key="p_prio",
            )
            vis = base_df
            if busca:
                vis = vis[vis["idol"].str.contains(busca, case=False, regex=False)
                          | vis["grupo"].str.contains(busca, case=False, regex=False)]
            if prios:
                vis = vis[vis["prioridade"].isin(prios)]
            vis = ordenar(vis, ordem)
            vis = vis.copy()
            n = st.session_state.setdefault("n_cards", 12)
            titulo_colecoes = (
                texto_painel("todas_colecoes") if sel == bot_todos else esc(sel)
            )
            st.markdown(
                f'<div class="hd"><h3>{titulo_colecoes}</h3>'
                f'<span>{texto_painel("idols_contagem", quantidade=len(vis))}'
                '</span></div>',
                unsafe_allow_html=True,
            )

            cards_visiveis = list(vis.head(n).itertuples())
            for inicio in range(0, len(cards_visiveis), 4):
                with st.container(key=f"cards_row_{inicio}"):
                    colunas_cards = st.columns(4)
                    for coluna, r in zip(colunas_cards, cards_visiveis[inicio:inicio + 4]):
                        with coluna:
                            with st.container(key=f"card_{r.id}"):
                                nome_card = r.grupo if r.idol == GRUPO_COMPLETO else r.idol
                                st.markdown(
                                    f'<a class="card-link" href="?card={int(r.id)}" target="_self" '
                                    f'aria-label="{esc(texto_painel("abrir_detalhes", nome=nome_card), quote=True)}">'
                                    f'{card_html(r)}</a>',
                                    unsafe_allow_html=True)
                                c1, c2, c3, c4 = st.columns(
                                    4, gap="small", vertical_alignment="center"
                                )
                                c1.button("−", key=f"m_{r.id}", on_click=ajustar, args=(r.id, -1),
                                          disabled=bool(r.possuo <= 0))
                                c2.markdown(
                                    f'<div class="cnt">{r.possuo}/{r.total}</div>',
                                    unsafe_allow_html=True,
                                )
                                c3.button("+", key=f"a_{r.id}", on_click=ajustar, args=(r.id, 1),
                                          disabled=bool(r.possuo >= r.total))
                                c4.markdown(ring(r.progresso, sm=True), unsafe_allow_html=True)
            if len(vis) > n:
                st.button(
                    texto_painel("mostrar_mais", quantidade=len(vis) - n),
                    on_click=mostrar_mais,
                    width="stretch",
                )

# ---------------------------------------------------------------- Tabela (edição em massa)
with tab_tabela:
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    traducoes_tabela = TRADUCOES_NAVEGACAO["tabela"][idioma]
    traducoes_cadastro = TRADUCOES_NAVEGACAO["cadastro"][idioma]
    if df_all.empty:
        st.info(texto_tabela("vazio"))
    else:
        st.caption(texto_tabela("instrucoes"))
        f1, f2, f3, f4, f5 = st.columns(5)
        fb = f1.multiselect(texto_tabela("bot"), sorted(df_all["bot"].unique()), key="t_bot")
        fg = f2.multiselect(texto_tabela("grupo"), sorted(df_all["grupo"].unique(), key=str.casefold), key="t_grupo")
        fp = f3.multiselect(
            texto_tabela("prioridade"),
            PRIORIDADES,
            format_func=traducoes_cadastro["prioridades"].get,
            key="t_prio",
        )
        fc = f4.multiselect(
            texto_tabela("categoria"),
            CATEGORIAS,
            format_func=traducoes_cadastro["categorias"].get,
            key="t_cat",
        )
        busca_t = f5.text_input(texto_tabela("buscar_idol"), key="t_busca")
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
        df = ordenar(
            df,
            st.selectbox(
                texto_tabela("ordenar_por"),
                ORDENS,
                format_func=TRADUCOES_NAVEGACAO["ordens"][idioma].get,
                key="t_ordem",
            ),
        ).copy()
        df["excluir"] = False
        df["categoria"] = df["categoria"].map(traducoes_cadastro["categorias"].get)
        df["prioridade"] = df["prioridade"].map(traducoes_cadastro["prioridades"].get)

        edited = st.data_editor(
            df, hide_index=True, width="stretch",
            disabled=["id", "progresso", "faltam"],
            column_order=["bot", "grupo", "idol", "categoria", "prioridade",
                          "total", "possuo", "faltam", "progresso", "image_url", "excluir"],
            column_config={
                "bot": st.column_config.SelectboxColumn(texto_tabela("bot"), options=BOTS),
                "grupo": texto_tabela("grupo"),
                "idol": texto_tabela("idol"),
                "categoria": st.column_config.SelectboxColumn(
                    texto_tabela("categoria"),
                    options=list(traducoes_cadastro["categorias"].values()),
                ),
                "prioridade": st.column_config.SelectboxColumn(
                    texto_tabela("prioridade"),
                    options=list(traducoes_cadastro["prioridades"].values()),
                ),
                "total": st.column_config.NumberColumn(texto_tabela("total"), min_value=0, step=1),
                "possuo": st.column_config.NumberColumn(texto_tabela("possuo"), min_value=0, step=1),
                "faltam": st.column_config.NumberColumn(texto_tabela("faltam")),
                "progresso": st.column_config.ProgressColumn(
                    texto_tabela("progresso"), min_value=0, max_value=100, format="%.0f%%"),
                "image_url": st.column_config.TextColumn(texto_tabela("url_foto")),
                "excluir": st.column_config.CheckboxColumn(texto_tabela("excluir")),
            },
        )
        if st.button(texto_tabela("salvar"), type="primary"):
            erros = []
            for r in edited.itertuples():
                if r.excluir:
                    run("DELETE FROM colecao WHERE id=?", (int(r.id),))
                elif r.total < 0 or r.possuo < 0:
                    erros.append(
                        texto_tabela(
                            "valores_negativos", idol=r.idol, bot=r.bot
                        )
                    )
                elif r.possuo > r.total:
                    erros.append(
                        texto_tabela(
                            "possuo_maior_total", idol=r.idol, bot=r.bot
                        )
                    )
                else:
                    try:
                        run("UPDATE colecao SET bot=?, grupo=?, idol=?, categoria=?, prioridade=?, "
                            "total=?, possuo=?, image_url=? WHERE id=?",
                            (r.bot, r.grupo, r.idol,
                             traducoes_cadastro["categorias"].get(r.categoria, r.categoria),
                             traducoes_cadastro["prioridades"].get(r.prioridade, r.prioridade),
                             int(r.total), int(r.possuo), _url(r.image_url), int(r.id)))
                    except psycopg2.IntegrityError:
                        erros.append(
                            texto_tabela(
                                "duplicado", idol=r.idol, grupo=r.grupo, bot=r.bot
                            )
                        )
            if erros:
                for e in erros:
                    st.error(e)
            else:
                st.rerun()
        exportacao = q("SELECT * FROM colecao").rename(
            columns=traducoes_tabela["colunas_exportadas"]
        )
        st.download_button(
            texto_tabela("baixar_csv"),
            exportacao.to_csv(index=False),
            "binderlog.csv",
            "text/csv",
        )

# ---------------------------------------------------------------- Fotos
with tab_fotos:
    if df_all.empty:
        st.info(texto_fotos("vazio"))
    else:
        st.caption(texto_fotos("descricao_busca"))
        if time.time() < st.session_state.get("kpopping_fotos_cooldown_ate", 0):
            st.info(texto_fotos("kpopping_pausado"))

        with st.container(border=True):
            st.subheader(texto_fotos("buscar_lote"))
            fb2 = st.multiselect(
                texto_fotos("filtrar_bot"),
                sorted(df_all["bot"].unique()),
                placeholder=texto_fotos("escolher_bots"),
                key="f_bots",
            )
            dff = df_all[df_all["bot"].isin(fb2)] if fb2 else df_all
            dff = ordenar(dff, "Idol (A–Z)")
            contagem = dff["url_foto"].dropna().value_counts()
            repetidas = set(contagem[contagem > 1].index)
            falta = dff["url_foto"].isna()
            rep = dff["url_foto"].isin(repetidas)
            idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
            modos_fotos = {
                "Só as que faltam": "so_faltantes",
                "Faltam + repetidas": "faltantes_repetidas",
                "Todas (substituir)": "todas_substituir",
            }
            modo = st.radio(
                texto_fotos("buscar_para"),
                list(modos_fotos),
                format_func=lambda value: texto_fotos(modos_fotos[value]),
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
                texto_fotos("limite"),
                min_value=1,
                max_value=100,
                value=30,
                key="f_lim",
            )
            if c_busca.button(
                texto_fotos("buscar_contagem", quantidade=len(alvo)),
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
                st.success(texto_fotos("atualizadas", quantidade=achou))
                if pausa_kprofiles:
                    st.warning(
                        texto_fotos("lote_interrompido", erro=pausa_kprofiles)
                    )
                if falhou:
                    st.warning(
                        texto_fotos("sem_novas", itens="; ".join(falhou))
                    )
                if not pausa_kprofiles and not falhou:
                    st.rerun()
            st.caption(
                f'{texto_fotos("sem_foto_contagem", quantidade=int(falta.sum()))} · '
                f'{texto_fotos("repetidas_contagem", quantidade=int(rep.sum()))}'
            )

        with st.container(border=True):
            st.subheader(texto_fotos("ajuste_individual"))
            rotulo = {
                int(r.id): f"{r.idol} — {r.grupo} ({r.bot})"
                for r in ordenar(df_all, "Idol (A–Z)").itertuples()
            }
            sel_id = st.selectbox(
                texto_fotos("idol"),
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
                    st.info(texto_fotos("card_sem_foto"))
            with g2:
                if st.button(
                    texto_fotos("buscar_outra"),
                    key="f_troca",
                    width="stretch",
                ):
                    try:
                        if trocar_foto(sel_id, linha["idol"], linha["grupo"], atual):
                            st.rerun()
                        else:
                            st.warning(texto_fotos("outra_nao_encontrada"))
                    except KProfilesRateLimited as e:
                        st.warning(str(e))
                    except Exception as e:
                        st.error(str(e))
                nova = st.text_input(
                    texto_fotos("url_direta"), key=f"f_url_{sel_id}"
                )
                if st.button(
                    texto_fotos("salvar_url"),
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
    idioma = st.session_state.get("idioma_interface", IDIOMAS[0])
    traducoes_importacao = TRADUCOES_NAVEGACAO["importacao"][idioma]
    traducoes_cadastro = TRADUCOES_NAVEGACAO["cadastro"][idioma]
    st.subheader(texto_importacao("titulo"))
    st.caption(texto_importacao("descricao"))
    bot_imp = st.selectbox(texto_importacao("bot"), BOTS, key="bot_imp")
    f_banco = st.file_uploader(
        texto_importacao("bancodedados"), type="csv", key="f_banco"
    )
    f_prio = st.file_uploader(
        texto_importacao("priolist"), type="csv", key="f_prio"
    )
    if f_banco:
        try:
            prev, avisos = parse_garam(f_banco, f_prio)
            st.divider()
            st.subheader(texto_importacao("previa"))
            st.caption(
                texto_importacao("linhas_prontas", quantidade=len(prev))
            )
            if avisos:
                with st.expander(
                    texto_importacao("avisos_csv", quantidade=len(avisos))
                ):
                    for a in avisos:
                        st.write("• " + a)
            previa_exibicao = prev.copy()
            previa_exibicao["categoria"] = previa_exibicao["categoria"].map(
                traducoes_cadastro["categorias"].get
            )
            previa_exibicao["prioridade"] = previa_exibicao["prioridade"].map(
                traducoes_cadastro["prioridades"].get
            )
            st.dataframe(
                previa_exibicao,
                hide_index=True,
                width="stretch",
                height=520,
                column_config={
                    "grupo": st.column_config.TextColumn(
                        texto_importacao("col_grupo"), width="medium"
                    ),
                    "idol": st.column_config.TextColumn(
                        texto_importacao("col_idol"), width="medium"
                    ),
                    "total": st.column_config.NumberColumn(
                        texto_importacao("col_total"), width="small"
                    ),
                    "possuo": st.column_config.NumberColumn(
                        texto_importacao("col_possuo"), width="small"
                    ),
                    "categoria": st.column_config.TextColumn(
                        texto_importacao("col_categoria"), width="small"
                    ),
                    "prioridade": st.column_config.TextColumn(
                        texto_importacao("col_prioridade"), width="small"
                    ),
                },
            )
            if st.button(
                texto_importacao("importar"), type="primary", width="stretch"
            ):
                run_many(
                    UPSERT,
                    [
                        (
                            bot_imp,
                            r.grupo,
                            r.idol,
                            traducoes_cadastro["categorias"].get(
                                r.categoria, r.categoria
                            ),
                            traducoes_cadastro["prioridades"].get(
                                r.prioridade, r.prioridade
                            ),
                            int(r.total),
                            int(r.possuo),
                        )
                        for r in previa_exibicao.itertuples()
                    ],
                )
                st.success(
                    texto_importacao(
                        "importados", quantidade=len(prev), bot=bot_imp
                    )
                )
        except Exception as e:
            st.error(str(e))
