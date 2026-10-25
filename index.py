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
