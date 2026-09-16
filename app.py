import streamlit as st
import json
import os
import base64
from datetime import datetime
import requests

# =========================================================
# CONFIGURAÇÃO
# =========================================================
st.set_page_config(
    page_title="Material Operacional",
    page_icon="📦",
    layout="wide"
)

DB_LOCAL = "database_material_operacional.json"

DB_PADRAO = {
    "produtos": []
}

# =========================================================
# VISUAL
# =========================================================
st.markdown("""
<style>
    .block-container {
        max-width: 1100px;
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    #MainMenu, footer, header {
        visibility: hidden;
    }

    .titulo {
        font-size: 2rem;
        font-weight: 800;
        margin-bottom: 0;
    }

    .subtitulo {
        color: #777;
        margin-top: .2rem;
        margin-bottom: 1.4rem;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.20);
        border-radius: 12px;
        padding: 10px 14px;
    }

    .card-alerta {
        border: 1px solid rgba(220,70,70,.35);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }

    .card-ok {
        border: 1px solid rgba(70,170,100,.30);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# LOGIN
# =========================================================
def carregar_usuarios():
    try:
        usuarios = st.secrets.get("usuarios", {})
        if usuarios:
            return dict(usuarios)
    except Exception:
        pass

    # Fallback opcional para teste local.
    return {
        "jessica": "230525",
        "julia": "gds9129"
    }


def login():
    if st.session_state.get("logado"):
        return

    st.markdown("## 📦 Material Operacional")
    st.caption("Acesso restrito")

    with st.form("form_login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)

    if entrar:
        usuarios = carregar_usuarios()

        if not usuarios:
            st.error("Configure os usuários nos Secrets do Streamlit.")
            st.stop()

        if usuario in usuarios and str(usuarios[usuario]) == senha:
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

    st.stop()


login()

# =========================================================
# BANCO DE DADOS - GITHUB + LOCAL
# =========================================================
def config_github():
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_DATA_BRANCH", "main")
        path = st.secrets.get(
            "GITHUB_MATERIAL_DB_PATH",
            "database_material_operacional.json"
        )

        if token and repo:
            return {
                "token": token,
                "repo": repo,
                "branch": branch,
                "path": path
            }
    except Exception:
        pass

    return None


def normalizar_banco(data):
    if not isinstance(data, dict):
        return {"produtos": []}

    # Compatibilidade com versão anterior
    if "itens" in data and "produtos" not in data:
        data["produtos"] = []
        for item in data.get("itens", []):
            data["produtos"].append({
                "id": item.get("id", ""),
                "nome": item.get("nome", ""),
                "quantidade": int(round(float(item.get("quantidade_atual", 0) or 0))),
                "minimo": int(round(float(item.get("estoque_minimo", 0) or 0))),
                "unidade": item.get("unidade", "Unidade"),
                "observacao": item.get("observacao", ""),
                "atualizado_em": item.get("atualizado_em", "")
            })

    data.setdefault("produtos", [])
    return data


def carregar_local():
    if not os.path.exists(DB_LOCAL):
        return {"produtos": []}

    try:
        with open(DB_LOCAL, "r", encoding="utf-8") as f:
            return normalizar_banco(json.load(f))
    except Exception:
        return {"produtos": []}


def salvar_local(data):
    with open(DB_LOCAL, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def carregar_github(cfg):
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Accept": "application/vnd.github+json",
    }

    r = requests.get(
        url,
        headers=headers,
        params={"ref": cfg["branch"]},
        timeout=20
    )

    if r.status_code == 404:
        return {"produtos": []}

    r.raise_for_status()

    conteudo = base64.b64decode(
        r.json()["content"]
    ).decode("utf-8")

    return normalizar_banco(json.loads(conteudo))


def salvar_github(cfg, data, mensagem="Atualiza estoque material operacional"):
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Accept": "application/vnd.github+json",
    }

    sha = None

    r_get = requests.get(
        url,
        headers=headers,
        params={"ref": cfg["branch"]},
        timeout=20
    )

    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
    elif r_get.status_code != 404:
        r_get.raise_for_status()

    conteudo = json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ).encode("utf-8")

    payload = {
        "message": mensagem,
        "content": base64.b64encode(conteudo).decode("utf-8"),
        "branch": cfg["branch"]
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(
        url,
        headers=headers,
        json=payload,
        timeout=25
    )

    r.raise_for_status()


def carregar_banco():
    cfg = config_github()

    if cfg:
        try:
            data = carregar_github(cfg)
            salvar_local(data)
            return data, "GitHub"
        except Exception as e:
            st.warning(
                "Não consegui carregar o banco permanente do GitHub. "
                "Estou usando o arquivo local nesta sessão."
            )

    return carregar_local(), "Local"


def salvar_banco(data, mensagem="Atualiza estoque"):
    salvar_local(data)

    cfg = config_github()

    if cfg:
        try:
            salvar_github(cfg, data, mensagem)
            return True, "Salvo no GitHub."
        except Exception as e:
            return False, f"Salvo localmente, mas não foi possível atualizar o GitHub: {e}"

    return True, "Salvo localmente."


# =========================================================
# FUNÇÕES
# =========================================================
def novo_id():
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def fmt_num(v):
    try:
        return str(int(round(float(v))))
    except Exception:
        return "0"


def precisa_comprar(produto):
    return float(produto.get("quantidade", 0)) <= float(produto.get("minimo", 0))


def qtd_compra(produto):
    qtd = float(produto.get("quantidade", 0))
    minimo = float(produto.get("minimo", 0))
    return max(minimo - qtd, 0)


def unidade_por_extenso(unidade, quantidade):
    unidade = (unidade or "Unidade").strip()
    mapa = {
        "UN": ("Unidade", "Unidades"),
        "Unidade": ("Unidade", "Unidades"),
        "CX": ("Caixa", "Caixas"),
        "Caixa": ("Caixa", "Caixas"),
        "PCT": ("Pacote", "Pacotes"),
        "Pacote": ("Pacote", "Pacotes"),
        "RL": ("Rolo", "Rolos"),
        "Rolo": ("Rolo", "Rolos"),
        "KG": ("Quilograma", "Quilogramas"),
        "Quilograma": ("Quilograma", "Quilogramas"),
        "LT": ("Litro", "Litros"),
        "Litro": ("Litro", "Litros"),
        "PAR": ("Par", "Pares"),
        "Par": ("Par", "Pares"),
        "OUTRO": ("Outro", "Outros"),
        "Outro": ("Outro", "Outros"),
    }
    singular, plural = mapa.get(unidade, (unidade, unidade))
    return singular if int(quantidade) == 1 else plural


def mensagem_wpp(produtos):
    lista = [p for p in produtos if precisa_comprar(p)]

    if not lista:
        return (
            "📦 *MATERIAL OPERACIONAL – SOLICITAÇÃO DE COMPRA*\n\n"
            "✅ No momento, não há materiais para reposição."
        )

    linhas = [
        "📦 *MATERIAL OPERACIONAL – SOLICITAÇÃO DE COMPRA*",
        "",
        "🛒 Segue relação dos materiais para reposição:",
        ""
    ]

    for p in sorted(lista, key=lambda x: x.get("nome", "").lower()):
        comprar = int(qtd_compra(p))
        unidade = unidade_por_extenso(p.get("unidade", "Unidade"), comprar)

        linhas.extend([
            f"🔹 *{p.get('nome','').upper()}*",
            f"Comprar: *{comprar} {unidade}*",
            f"Estoque atual: {fmt_num(p.get('quantidade',0))}",
            f"Estoque mínimo: {fmt_num(p.get('minimo',0))}",
            ""
        ])

    return "\n".join(linhas).rstrip()


# =========================================================
# CARREGAR BANCO
# =========================================================
if "db_material" not in st.session_state:
    db, origem = carregar_banco()
    st.session_state.db_material = db
    st.session_state.origem_banco = origem

db = st.session_state.db_material
for _p in db.get("produtos", []):
    _p.setdefault("unidade_estoque", _p.get("unidade","Unidade"))
    _p.setdefault("unidade_minimo", _p.get("unidade","Unidade"))
    _p.setdefault("quantidade_por_embalagem", 1)


# =========================================================
# CABEÇALHO
# =========================================================
col_titulo, col_sair = st.columns([8, 1])

with col_titulo:
    st.markdown('<div class="titulo">📦 Material Operacional</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitulo">Controle simples do estoque raiz.</div>',
        unsafe_allow_html=True
    )

with col_sair:
    if st.button("Sair", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# =========================================================
# RESUMO
# =========================================================
produtos = db["produtos"]

total = len(produtos)
alertas = len([p for p in produtos if precisa_comprar(p)])
ok = total - alertas

c1, c2, c3 = st.columns(3)
c1.metric("Produtos", total)
c2.metric("Comprar", alertas)
c3.metric("Estoque OK", ok)

st.divider()

# =========================================================
# MENU SIMPLES
# =========================================================
aba1, aba2, aba3, aba4 = st.tabs([
    "📋 Estoque",
    "➕ Novo produto",
    "✏️ Atualizar estoque",
    "💬 Mensagem WhatsApp"
])

# =========================================================
# ESTOQUE
# =========================================================
with aba1:
    st.markdown("### Estoque atual")

    if not produtos:
        st.info("Nenhum produto cadastrado.")
    else:
        busca = st.text_input(
            "Buscar produto",
            placeholder="Digite o nome...",
            key="buscar_produto"
        )

        filtrados = produtos

        if busca:
            filtrados = [
                p for p in produtos
                if busca.lower() in p.get("nome", "").lower()
            ]

        for p in sorted(filtrados, key=lambda x: x.get("nome", "").lower()):
            css = "card-alerta" if precisa_comprar(p) else "card-ok"
            status = "⚠️ COMPRAR" if precisa_comprar(p) else "✅ OK"

            st.markdown(
                f"""
                <div class="{css}">
                    <b>{p.get('nome','')}</b><br>
                    Estoque: <b>{fmt_num(p.get('quantidade',0))} {p.get('unidade','Unidade')}</b>
                    &nbsp;&nbsp;|&nbsp;&nbsp;
                    Mínimo: <b>{fmt_num(p.get('minimo',0))} {p.get('unidade','Unidade')}</b>
                    &nbsp;&nbsp;|&nbsp;&nbsp;
                    {status}
                </div>
                """,
                unsafe_allow_html=True
            )

# =========================================================
# NOVO PRODUTO
# =========================================================
with aba2:
    st.markdown("### Adicionar novo produto")

    with st.form("novo_produto", clear_on_submit=True):
        nome = st.text_input("Produto *", placeholder="Ex.: Fita adesiva")
        unidade = st.selectbox(
            "Unidade",
            ["Unidade", "Caixa", "Pacote", "Rolo", "Quilograma", "Litro", "Par", "Outro"]
        )

        c1, c2 = st.columns(2)

        with c1:
            quantidade = st.number_input(
                "Quantidade atual *",
                min_value=0,
                value=0,
                step=1
            )

        with c2:
            minimo = st.number_input(
                "Estoque mínimo *",
                min_value=0,
                value=0,
                step=1
            )

        observacao = st.text_input(
            "Observação",
            placeholder="Opcional"
        )

        salvar = st.form_submit_button(
            "Salvar produto",
            use_container_width=True
        )

    if salvar:
        if not nome.strip():
            st.error("Informe o nome do produto.")
        elif any(
            p.get("nome", "").strip().lower() == nome.strip().lower()
            for p in produtos
        ):
            st.error("Esse produto já está cadastrado.")
        else:
            produto = {
                "id": novo_id(),
                "nome": nome.strip(),
                "unidade": unidade,
                "unidade_estoque": unidade,
                "unidade_minimo": unidade,
                "quantidade_por_embalagem": 1,
                "quantidade": int(quantidade),
                "minimo": int(minimo),
                "observacao": observacao.strip(),
                "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M")
            }

            db["produtos"].append(produto)

            sucesso, msg = salvar_banco(
                db,
                f"Cadastra produto: {produto['nome']}"
            )

            st.session_state.db_material = db

            if sucesso:
                st.success("✅ Produto cadastrado e informações salvas com sucesso!")
                st.rerun()
            else:
                st.warning(msg)

# =========================================================
# ATUALIZAR ESTOQUE
# =========================================================
with aba3:
    st.markdown("### Atualizar / editar produto")
    if not produtos:
        st.info("Cadastre um produto primeiro.")
    else:
        mapa = {p["nome"]: p for p in sorted(produtos, key=lambda x: x.get("nome","").lower())}
        selecionado = st.selectbox("Produto", list(mapa.keys()), key="produto_atualizar")
        produto = mapa[selecionado]
        opcoes = ["Unidade", "Caixa", "Pacote", "Rolo", "Quilograma", "Litro", "Par", "Outro"]
        ue = produto.get("unidade_estoque", produto.get("unidade","Unidade"))
        um = produto.get("unidade_minimo", produto.get("unidade","Unidade"))

        with st.form("atualizar_estoque"):
            nome_editado = st.text_input("Nome do produto", value=produto.get("nome",""))
            c1,c2=st.columns(2)
            with c1:
                nova_quantidade=st.number_input("Quantidade atual",min_value=0,value=int(produto.get("quantidade",0)),step=1)
                nova_ue=st.selectbox("Unidade do estoque atual",opcoes,index=opcoes.index(ue) if ue in opcoes else 0)
            with c2:
                novo_minimo=st.number_input("Estoque mínimo",min_value=0,value=int(produto.get("minimo",0)),step=1)
                nova_um=st.selectbox("Unidade do estoque mínimo",opcoes,index=opcoes.index(um) if um in opcoes else 0)

            conversao=int(produto.get("quantidade_por_embalagem",1) or 1)
            if nova_ue != nova_um:
                embalagem=nova_um if nova_um!="Unidade" else nova_ue
                st.info("As unidades são diferentes. Informe a conversão para o cálculo da reposição.")
                conversao=st.number_input(f"Quantas Unidades existem em 1 {embalagem}?",min_value=1,value=max(conversao,1),step=1)

            observacao_editada=st.text_input("Observação",value=produto.get("observacao",""))
            salvar_atualizacao=st.form_submit_button("💾 Salvar informações",use_container_width=True,type="primary")

        if salvar_atualizacao:
            duplicado=any(p.get("id")!=produto.get("id") and p.get("nome","").strip().lower()==nome_editado.strip().lower() for p in produtos)
            if not nome_editado.strip():
                st.error("Informe o nome do produto.")
            elif duplicado:
                st.error("Já existe outro produto com esse nome.")
            else:
                produto.update({
                    "nome":nome_editado.strip(),"quantidade":int(nova_quantidade),"minimo":int(novo_minimo),
                    "unidade":nova_ue,"unidade_estoque":nova_ue,"unidade_minimo":nova_um,
                    "quantidade_por_embalagem":int(conversao),"observacao":observacao_editada.strip(),
                    "atualizado_em":datetime.now().strftime("%d/%m/%Y %H:%M")
                })
                sucesso,msg=salvar_banco(db,f"Atualiza produto: {produto['nome']}")
                st.session_state.db_material=db
                if sucesso: st.success("✅ Informações salvas com sucesso!")
                else: st.error(f"❌ Erro ao salvar: {msg}")

        st.divider()
        st.markdown("#### Excluir produto")
        if st.button("🗑️ Excluir produto",key=f"excluir_{produto.get('id','')}"):
            st.session_state["excluir_id"]=produto.get("id")
        if st.session_state.get("excluir_id")==produto.get("id"):
            st.warning(f"Confirma a exclusão de **{produto.get('nome','')}**?")
            x1,x2=st.columns(2)
            if x1.button("Sim, excluir",use_container_width=True,type="primary"):
                db["produtos"]=[p for p in db["produtos"] if p.get("id")!=produto.get("id")]
                sucesso,msg=salvar_banco(db,f"Exclui produto: {produto.get('nome','')}")
                st.session_state.db_material=db
                st.session_state.pop("excluir_id",None)
                if sucesso:
                    st.success("✅ Produto excluído e alteração salva com sucesso!")
                    st.rerun()
                else: st.error(f"❌ Erro ao excluir: {msg}")
            if x2.button("Cancelar",use_container_width=True):
                st.session_state.pop("excluir_id",None); st.rerun()

# =========================================================
# WHATSAPP
# =========================================================
with aba4:
    st.markdown("### 💬 Mensagem para compras")

    lista_compras = [p for p in produtos if precisa_comprar(p)]

    if not lista_compras:
        st.success("Nenhum produto precisa de reposição.")
    else:
        st.warning(
            f"{len(lista_compras)} produto(s) precisam de reposição."
        )

    mensagem = mensagem_wpp(produtos)

    st.text_area(
        "Copie e envie no WhatsApp",
        value=mensagem,
        height=320
    )

# =========================================================
# RODAPÉ
# =========================================================
st.divider()
st.caption(
    f"Banco: {st.session_state.get('origem_banco','Local')} • "
    f"Usuário: {st.session_state.get('usuario','')}"
)
