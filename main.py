import streamlit as st
import pandas as pd
import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_oauth import OAuth2Component
import plotly.express as px
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Habit Master", page_icon="🔥", layout="wide")

# ==============================================================================
# 1. FUNÇÕES DE BACKEND
# ==============================================================================

@st.cache_resource
def get_google_sheet_client():
    creds_dict = dict(st.secrets["connections"]["gsheets"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_allowed_users():
    try:
        client = get_google_sheet_client()
        sheet = client.open("HabitTrackerDB").worksheet("Usuarios")
        return [e.strip() for e in sheet.col_values(1) if "@" in e]
    except:
        return []

def load_data():
    try:
        client = get_google_sheet_client()
        sheet = client.open("HabitTrackerDB").sheet1
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=["Data", "Habito", "Status", "Usuario"])
        df = pd.DataFrame(data)
        df["Data"] = pd.to_datetime(df["Data"]).dt.date
        df["Status"] = df["Status"].astype(str).str.upper() == 'TRUE'
        return df
    except Exception as e:
        st.error(f"Erro DB: {e}")
        return pd.DataFrame(columns=["Data", "Habito", "Status", "Usuario"])

def save_data(df):
    client = get_google_sheet_client()
    sheet = client.open("HabitTrackerDB").sheet1
    df_up = df.copy()
    
    if "Status" in df_up.columns:
        df_up["Status"] = df_up["Status"].fillna(False)
    df_up = df_up.fillna("")
    
    df_up["Data"] = df_up["Data"].astype(str)
    df_up["Status"] = df_up["Status"].astype(str).str.upper()
    
    sheet.clear()
    sheet.update([df_up.columns.values.tolist()] + df_up.values.tolist())

# ==============================================================================
# 2. AUTENTICAÇÃO
# ==============================================================================
def check_auth():
    if "user_email" in st.session_state: return st.session_state.user_email
    
    try:
        oauth2 = OAuth2Component(
            st.secrets["oauth"]["client_id"], 
            st.secrets["oauth"]["client_secret"], 
            "https://accounts.google.com/o/oauth2/v2/auth", 
            "https://oauth2.googleapis.com/token", 
            "https://oauth2.googleapis.com/token", 
            "https://oauth2.googleapis.com/revoke"
        )
        result = oauth2.authorize_button("Login Google", st.secrets["oauth"]["redirect_uri"], "openid email profile", key="goo", extras_params={"prompt": "select_account"})
        
        if result:
            token = result.get("token", {}).get("access_token") or result.get("access_token")
            if token:
                r = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    email = r.json().get("email")
                    st.session_state.user_email = email
                    st.rerun()
    except Exception as e:
        st.error(f"Erro Auth: {e}")
    return None

user_email = check_auth()
if not user_email: st.stop()

whitelist = get_allowed_users()
if whitelist and user_email not in whitelist:
    st.error("Acesso não autorizado."); st.stop()

# ==============================================================================
# 3. LÓGICA DINÂMICA
# ==============================================================================
if "df_habits" not in st.session_state:
    st.session_state.df_habits = load_data()

with st.sidebar:
    st.header(f"👤 {user_email.split('@')[0]}")
    with st.expander("⚙️ Gerenciar Hábitos", expanded=False):
        novo_habito = st.text_input("Novo Hábito")
        if st.button("➕ Adicionar"):
            if novo_habito:
                hoje = datetime.date.today()
                novo_registro = pd.DataFrame([{"Data": hoje, "Habito": novo_habito, "Status": False, "Usuario": user_email}])
                st.session_state.df_habits = pd.concat([st.session_state.df_habits, novo_registro], ignore_index=True)
                save_data(st.session_state.df_habits)
                st.rerun()
        
        st.divider()
        
        df_user = st.session_state.df_habits[st.session_state.df_habits["Usuario"] == user_email]
        lista_habitos = df_user["Habito"].unique().tolist() if not df_user.empty else []
        habito_remover = st.selectbox("Remover Hábito", ["Selecione..."] + lista_habitos)
        if st.button("🗑️ Excluir"):
            if habito_remover != "Selecione...":
                df = st.session_state.df_habits
                st.session_state.df_habits = df[~((df["Usuario"] == user_email) & (df["Habito"] == habito_remover))]
                save_data(st.session_state.df_habits)
                st.rerun()
    
    if st.button("Sair"):
        del st.session_state.user_email
        st.rerun()

def garantir_dados_semana_atual():
    hoje = datetime.date.today()
    inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())
    dias_semana = [inicio_semana + datetime.timedelta(days=i) for i in range(7)]
    
    df = st.session_state.df_habits
    novos = []
    df_user = df[df["Usuario"] == user_email]
    active_habits = df_user["Habito"].unique().tolist()
    
    if not active_habits: return 

    for dia in dias_semana:
        for habito in active_habits:
            filtro = (df["Data"] == dia) & (df["Habito"] == habito) & (df["Usuario"] == user_email)
            if df[filtro].empty:
                novos.append({"Data": dia, "Habito": habito, "Status": False, "Usuario": user_email})
    
    if novos:
        st.session_state.df_habits = pd.concat([df, pd.DataFrame(novos)], ignore_index=True)

garantir_dados_semana_atual()

# ==============================================================================
# 4. INTERFACE DASHBOARD
# ==============================================================================

st.title("🔥 Habit Master")
st.markdown(f"**Semana:** {datetime.date.today().strftime('%W')} | **Ano:** {datetime.date.today().year}")

# --- INPUT SEMANAL ---
hoje = datetime.date.today()
inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())
dias_semana = [inicio_semana + datetime.timedelta(days=i) for i in range(7)]

mask_semana = (st.session_state.df_habits["Data"].isin(dias_semana)) & (st.session_state.df_habits["Usuario"] == user_email)
df_semana = st.session_state.df_habits[mask_semana].copy()

if not df_semana.empty:
    df_semana["DiaStr"] = df_semana["Data"].apply(lambda x: x.strftime("%a %d/%m"))
    df_pivot = df_semana.pivot(index="Habito", columns="DiaStr", values="Status")
    cols_order = [d.strftime("%a %d/%m") for d in dias_semana]
    for c in cols_order:
        if c not in df_pivot.columns: df_pivot[c] = False
    df_pivot = df_pivot[cols_order]

    st.subheader("📝 Check-in Semanal")
    edited_pivot = st.data_editor(df_pivot, use_container_width=True, column_config={c: st.column_config.CheckboxColumn(c) for c in df_pivot.columns})

    if st.button("💾 Salvar Alterações", type="primary"):
        for habito, row in edited_pivot.iterrows():
            for dia_str, status in row.items():
                try:
                    dia_part = dia_str.split()[1]
                    dia_obj = datetime.datetime.strptime(f"{dia_part}/{hoje.year}", "%d/%m/%Y").date()
                    mask = (st.session_state.df_habits["Data"] == dia_obj) & (st.session_state.df_habits["Habito"] == habito) & (st.session_state.df_habits["Usuario"] == user_email)
                    if st.session_state.df_habits[mask].empty:
                         new_row = {"Data": dia_obj, "Habito": habito, "Status": status, "Usuario": user_email}
                         st.session_state.df_habits = pd.concat([st.session_state.df_habits, pd.DataFrame([new_row])], ignore_index=True)
                    else:
                        st.session_state.df_habits.loc[mask, "Status"] = status
                except: pass
        save_data(st.session_state.df_habits)
        st.success("Salvo!")
else:
    st.info("👈 Adicione hábitos na barra lateral.")

st.divider()

# --- ÁREA VISUAL RICA ---
st.subheader("📊 Análise de Performance")

col_f1, col_f2 = st.columns([2, 1])
with col_f1:
    range_datas = st.date_input("Filtrar Período", (hoje - datetime.timedelta(days=30), hoje), format="DD/MM/YYYY")

if isinstance(range_datas, tuple) and len(range_datas) == 2:
    ini, fim = range_datas
    df_filt = st.session_state.df_habits[
        (st.session_state.df_habits["Data"] >= ini) & 
        (st.session_state.df_habits["Data"] <= fim) & 
        (st.session_state.df_habits["Usuario"] == user_email)
    ].copy()
    
    if not df_filt.empty:
        # 1. KPIs
        checks = df_filt[df_filt["Status"]==True].shape[0]
        total = df_filt.shape[0]
        taxa = (checks/total*100) if total > 0 else 0
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Hábitos Concluídos", checks)
        k2.metric("Consistência Global", f"{taxa:.1f}%")
        
        # Melhor hábito
        ranking = df_filt[df_filt["Status"]==True]["Habito"].value_counts()
        best_habit = ranking.index[0] if not ranking.empty else "-"
        k3.metric("Melhor Hábito", best_habit)
        
        # 2. GRÁFICOS LADO A LADO
        g1, g2 = st.columns(2)
        
        with g1:
            st.markdown("##### 📈 Evolução Diária")
            # Agrupa por dia para ver % de conclusao naquele dia
            daily_trend = df_filt.groupby("Data")["Status"].mean().reset_index()
            daily_trend["Status"] = daily_trend["Status"] * 100
            
            fig_line = px.line(daily_trend, x="Data", y="Status", markers=True, labels={"Status": "% Conclusão"})
            fig_line.update_traces(line_color="#00CC96", line_shape="spline") # Linha curva e verde
            fig_line.update_yaxes(range=[0, 110])
            st.plotly_chart(fig_line, use_container_width=True)
            
        with g2:
            st.markdown("##### 🏆 Distribuição por Hábito")
            habit_dist = df_filt[df_filt["Status"]==True]["Habito"].value_counts().reset_index()
            habit_dist.columns = ["Habito", "Count"]
            if not habit_dist.empty:
                fig_pie = px.pie(habit_dist, values="Count", names="Habito", hole=0.4)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.caption("Sem dados suficientes.")

        # 3. HEATMAP GITHUB STYLE (SUPERIOR)
        st.markdown("##### 🔥 Intensidade (Estilo GitHub)")
        
        # Preparação Complexa do Heatmap
        df_heat = df_filt.copy()
        df_heat["SemanaAno"] = pd.to_datetime(df_heat["Data"]).dt.isocalendar().week
        df_heat["DiaSemana"] = pd.to_datetime(df_heat["Data"]).dt.strftime("%a") # Mon, Tue...
        # Mapeamento para ordenar o Eixo Y corretamente (Segunda em cima)
        dias_ordem = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        # Se seu servidor estiver em PT-BR, ajuste para ["Seg", "Ter", ...]
        
        # Calcula intensidade média do dia (0 a 1)
        heat_data = df_heat.groupby(["SemanaAno", "DiaSemana"])["Status"].mean().reset_index()
        
        fig_heat = go.Figure(data=go.Heatmap(
            x=heat_data["SemanaAno"],
            y=heat_data["DiaSemana"],
            z=heat_data["Status"],
            colorscale="Greens",
            showscale=True,
            xgap=3, ygap=3 # Espaçamento estilo tiles
        ))
        
        fig_heat.update_layout(
            height=300,
            yaxis={"categoryorder": "array", "categoryarray": dias_ordem[::-1]}, # Inverte para Seg ficar no topo
            margin=dict(l=20, r=20, t=20, b=20)
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    else:
        st.warning("Sem dados neste período.")