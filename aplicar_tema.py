"""Troca as paletas do BinderLog (escuro, claro e automático) por um tema novo.

Uso (na pasta do projeto, onde está o index.py):
    python aplicar_tema.py
Ele faz um backup em index.py.bak e só substitui o bloco final de cores do CSS.
Pode rodar de novo para trocar o tema quantas vezes quiser.
"""
import sys
from pathlib import Path

MARCADORES = (
    "/* BinderLog theme: Holo Pearl */",          # este tema (rodar de novo)
    "/* BinderLog palette: Midnight Holo (dark) */",  # tema anterior
)

TEMA = r'''/* BinderLog theme: Holo Pearl */
:root {
    --brand: #f5f2ff;
    --gold: #f2c35b;
    --bg: #0d0b1a;
    --bg-soft: #120f24;
    --panel: rgba(23, 19, 48, .92);
    --panel-solid: #171330;
    --panel-raised: #201a40;
    --line: #2d2655;
    --line-strong: #463b7d;
    --accent: #8fe9ff;
    --accent-strong: #8fe9ff;
    --accent-soft: rgba(143, 233, 255, .12);
    --text: #cfcbe8;
    --heading: #f5f2ff;
    --muted: #b4afd3;
    --tabs-text: #b4afd3;
    --subtle: #8e89b0;
    --page-glow-one: rgba(154, 134, 255, .16);
    --page-glow-two: rgba(255, 155, 210, .09);
    --page-glow-three: rgba(143, 233, 255, .08);
    --header-bg: rgba(13, 11, 26, .88);
    --pill-bg: rgba(23, 19, 48, .90);
    --hero-bg: linear-gradient(125deg, #1c1544 0%, #241a52 48%, #0f3550 100%);
    --hero-glow: rgba(255, 155, 210, .16);
    --hero-title-gradient: linear-gradient(90deg, #ffffff, #c4b5ff 45%, #8fe9ff);
    --hero-sub: #cfcbe8;
    --grad: linear-gradient(90deg, #ff9bd2, #9a86ff 50%, #6fe3ff);
    --ring-a: #ff9bd2;
    --ring-b: #8fe9ff;
    --logo-bg: linear-gradient(145deg, #ff9bd2, #9a86ff 55%, #6fe3ff);
    --glow: rgba(154, 134, 255, .35);
    --bar-track: rgba(245, 242, 255, .10);
    --ring-track: rgba(245, 242, 255, .10);
    --ring-center: #171330;
    --ring-sm-center: #201a40;
    --tabs-bg: rgba(23, 19, 48, .92);
    --tab-hover-bg: rgba(154, 134, 255, .14);
    --tab-active-bg: linear-gradient(135deg, #9a86ff, #ff9bd2);
    --tab-active-color: #120d27;
    --tab-active-shadow: 0 6px 18px rgba(154, 134, 255, .30);
    --button-secondary-bg: #201a40;
    --button-primary-bg: linear-gradient(135deg, #9a86ff, #ff9bd2);
    --button-primary-text: #120d27;
    --input-bg: #120f24;
    --uploader-bg: rgba(23, 19, 48, .70);
    --uploader-hover-bg: rgba(32, 26, 64, .90);
    --alert-info-bg: rgba(143, 233, 255, .10);
    --alert-success-bg: rgba(105, 214, 170, .12);
    --alert-warning-bg: rgba(242, 195, 91, .13);
    --alert-error-bg: rgba(255, 130, 170, .14);
    --expander-bg: rgba(23, 19, 48, .80);
    --collection-button-bg: rgba(23, 19, 48, .92);
    --card-action-bg: rgba(154, 134, 255, .14);
    --card-bg: linear-gradient(160deg, #1a1538, #130f2b);
    --card-shadow: 0 10px 28px rgba(5, 3, 18, .45);
    --card-shadow-hover: 0 18px 40px rgba(5, 3, 18, .62);
    --photo-bg: #201a40;
    --badge-bg: rgba(13, 11, 26, .88);
    --badge-border: rgba(154, 134, 255, .42);
    color-scheme: dark;
}

@media THEME_LIGHT_QUERY {
    :root {
        --brand: #241d44;
        --gold: #f2c35b;
        --bg: #faf7ff;
        --bg-soft: #f1ecff;
        --panel: rgba(255, 255, 255, .94);
        --panel-solid: #ffffff;
        --panel-raised: #f3eeff;
        --line: #e4dcf7;
        --line-strong: #cdbfee;
        --accent: #6b46f0;
        --accent-strong: #6b46f0;
        --accent-soft: rgba(107, 70, 240, .10);
        --text: #4e4968;
        --heading: #241d44;
        --muted: #5f5a7c;
        --tabs-text: #5f5a7c;
        --subtle: #7b7698;
        --page-glow-one: rgba(154, 134, 255, .22);
        --page-glow-two: rgba(255, 155, 210, .16);
        --page-glow-three: rgba(111, 227, 255, .14);
        --header-bg: rgba(250, 247, 255, .90);
        --pill-bg: rgba(255, 255, 255, .92);
        --hero-bg: linear-gradient(125deg, #ffffff 0%, #f0e9ff 52%, #e2f5ff 100%);
        --hero-glow: rgba(255, 155, 210, .22);
        --hero-title-gradient: linear-gradient(90deg, #2a1f6b, #6b46f0 52%, #c0408f);
        --hero-sub: #5f5a7c;
        --grad: linear-gradient(90deg, #c0408f, #6b46f0 55%, #1fa8d6);
        --ring-a: #c0408f;
        --ring-b: #6b46f0;
        --logo-bg: linear-gradient(145deg, #ff9bd2, #8f78ff 55%, #5fd8ff);
        --glow: rgba(107, 70, 240, .28);
        --bar-track: rgba(36, 29, 68, .10);
        --ring-track: rgba(36, 29, 68, .10);
        --ring-center: #ffffff;
        --ring-sm-center: #f3eeff;
        --tabs-bg: rgba(241, 236, 255, .95);
        --tab-hover-bg: rgba(107, 70, 240, .08);
        --tab-active-bg: linear-gradient(135deg, #6b46f0, #c0408f);
        --tab-active-color: #ffffff;
        --tab-active-shadow: 0 6px 18px rgba(107, 70, 240, .28);
        --button-secondary-bg: rgba(255, 255, 255, .94);
        --button-primary-bg: linear-gradient(135deg, #6b46f0, #c0408f);
        --button-primary-text: #ffffff;
        --input-bg: #ffffff;
        --uploader-bg: rgba(255, 255, 255, .80);
        --uploader-hover-bg: rgba(243, 238, 255, .95);
        --alert-info-bg: rgba(107, 70, 240, .08);
        --alert-success-bg: rgba(31, 150, 104, .10);
        --alert-warning-bg: rgba(242, 170, 40, .14);
        --alert-error-bg: rgba(214, 64, 110, .10);
        --expander-bg: rgba(255, 255, 255, .85);
        --collection-button-bg: rgba(255, 255, 255, .92);
        --card-action-bg: rgba(107, 70, 240, .08);
        --card-bg: linear-gradient(160deg, #ffffff, #f6f1ff);
        --card-shadow: 0 10px 28px rgba(60, 40, 130, .09);
        --card-shadow-hover: 0 18px 40px rgba(60, 40, 130, .17);
        --photo-bg: #ece6fb;
        --badge-bg: rgba(36, 29, 68, .88);
        --badge-border: rgba(255, 255, 255, .40);
        color-scheme: light;
    }
}

/* detalhes do tema: gradientes de progresso, brilho e foco */
.bar > span,
[data-testid="stProgress"] > div > div {background: var(--grad) !important}
.ring {background: conic-gradient(var(--ring-a), var(--ring-b) calc(var(--v) * 1%), var(--ring-track) 0)}
.logo {background: var(--logo-bg); box-shadow: 0 8px 28px var(--glow)}
.hero {position: relative; overflow: hidden}
.hero::after {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 0;
    background: radial-gradient(520px 240px at 94% 0%, var(--hero-glow), transparent 70%);
}
.hero > * {position: relative; z-index: 1}
.bp.complete {color: #241d44 !important; background: var(--gold) !important; border-color: var(--gold) !important}
::selection {background: var(--accent-soft); color: var(--heading)}
* {scrollbar-color: var(--line-strong) transparent}
button:focus-visible, a:focus-visible, input:focus-visible {
    outline: 2px solid var(--accent-strong) !important; outline-offset: 2px;
}
'''


def main():
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "index.py"
    if not alvo.exists():
        sys.exit(f"Não achei {alvo}. Rode este script na pasta do projeto (onde está o index.py).")
    texto = alvo.read_text(encoding="utf-8")
    inicio = next((texto.find(m) for m in MARCADORES if m in texto), -1)
    if inicio < 0:
        sys.exit("Não encontrei o bloco de cores no index.py (comentário '/* BinderLog palette ...'). "
                 "Nada foi alterado.")
    fim = texto.find("</style>", inicio)
    if fim < 0:
        sys.exit("Não encontrei o fim do CSS (</style>). Nada foi alterado.")
    novo = texto[:inicio] + TEMA + texto[fim:]
    Path(str(alvo) + ".bak").write_text(texto, encoding="utf-8")
    alvo.write_text(novo, encoding="utf-8")
    print(f"Tema aplicado em {alvo.name}. Backup salvo em {alvo.name}.bak")


if __name__ == "__main__":
    main()
