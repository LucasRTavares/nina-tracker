import streamlit as st
import pandas as pd
import plotly.express as px
import datetime as dt

# --- 1. CONFIGURAÇÕES GERAIS ---
st.set_page_config(layout="wide", page_title="Nina Tracker: Daily View")

# CONFIGURAÇÕES
# Substitua pelo seu ID real
ID_ARQUIVO = "1ELIud71WxGMp9PskAib_fqVwLOcQNhMV" 
GOOGLE_DRIVE_URL = f"https://drive.google.com/uc?export=download&id={ID_ARQUIVO}"
FUSO_HORARIO = 'America/Sao_Paulo'
CATEGORIAS_PRINCIPAIS = ['Acordada', 'Mamou', 'Dormiu']
DIAS_PADRAO_INICIAL = 15  # Começa mostrando os últimos 15 dias

# --- 2. CAMADA DE DADOS (ETL) ---

@st.cache_data(ttl=3600)
def get_raw_data():
    """Carrega o CSV bruto do Google Drive."""
    try:
        df = pd.read_csv(GOOGLE_DRIVE_URL)
        return df
    except Exception as e:
        st.error(f"Erro no download: {e}")
        return pd.DataFrame()

def process_daily_data(df_raw):
    """
    Processa os dados especificamente para a visão DIÁRIA (00h - 23h59).
    Includes Matutino/Noturno logic based on start time.
    """
    if df_raw.empty: return pd.DataFrame()
    
    df = df_raw.copy()
    
    # Normalização de Colunas
    df.columns = df.columns.str.lower().str.replace(' ', '_')
    
    # Tratamento de Tempo e Fuso Horário
    for col in ['time_started', 'time_ended']:
        df[col] = pd.to_datetime(df[col])
        # Garante que seja tz-aware
        df[col] = df[col].apply(lambda x: x.tz_localize(FUSO_HORARIO) if x.tzinfo is None else x.tz_convert(FUSO_HORARIO))

    # Limpeza básica
    df['duration_minutes'] = pd.to_numeric(df['duration_minutes'], errors='coerce').fillna(0)
    df = df.dropna(subset=['categories'])
    
    # --- ENRIQUECIMENTO DE DADOS ---
    df['date'] = df['time_started'].dt.date
    df['hour'] = df['time_started'].dt.hour
    df['day_name'] = df['time_started'].dt.strftime('%A')
    
    # Lógica Matutino (6h-18h) vs Noturno (18h-6h)
    # Nota: Para visão DIÁRIA civil, consideramos o horário que a atividade COMEÇOU.
    # Se começou às 23h, é Noturno do dia X. Se começou às 01h, é Noturno do dia X+1 (madrugada).
    def definir_periodo(hora):
        if 6 <= hora < 18:
            return "Matutino (06h-18h)"
        else:
            return "Noturno (18h-06h)"
            
    df['periodo_dia'] = df['hour'].apply(definir_periodo)
    
    return df

# --- 3. CARREGAMENTO E FILTROS ---

df_raw = get_raw_data()
if df_raw.empty:
    st.stop()

df_daily = process_daily_data(df_raw)

# --- 3.1 Lógica do Filtro de Data (Últimos 15 dias Padrão) ---
st.sidebar.header("📅 Filtros Diários")

min_date = df_daily['date'].min()
max_date = df_daily['date'].max()

# Calcula a data de início padrão (15 dias atrás a partir do último dado)
default_start_date = max_date - dt.timedelta(days=DIAS_PADRAO_INICIAL)

# Garante que a data padrão não seja anterior à primeira data do dataset
if default_start_date < min_date:
    default_start_date = min_date

date_range = st.sidebar.date_input(
    "Selecione o Período",
    value=(default_start_date, max_date), # O valor inicial agora é dinâmico
    min_value=min_date,
    max_value=max_date
)

# Filtragem do DataFrame
if isinstance(date_range, tuple) and len(date_range) == 2:
    mask = (df_daily['date'] >= date_range[0]) & (df_daily['date'] <= date_range[1])
    df_filtered = df_daily.loc[mask]
else:
    df_filtered = df_daily.copy()
    st.sidebar.warning("Selecione uma data final.")

# --- 4. VISUALIZAÇÃO ---

st.title(f"📊 Análise Diária (0h - 24h)")

# --- 4.1 MÉDIAS DIÁRIAS (Mantido) ---
st.subheader("1. Médias Diárias por Categoria")

daily_sum = df_filtered.groupby(['date', 'categories'])['duration_minutes'].sum().reset_index()
daily_avg = daily_sum.groupby('categories')['duration_minutes'].mean().reset_index()
daily_avg['duration_hours'] = daily_avg['duration_minutes'] / 60

cols = st.columns(len(CATEGORIAS_PRINCIPAIS))
for i, cat in enumerate(CATEGORIAS_PRINCIPAIS):
    if i < len(cols):
        val_df = daily_avg[daily_avg['categories'] == cat]
        if not val_df.empty:
            minutes = val_df['duration_minutes'].values[0]
            hours = val_df['duration_hours'].values[0]
            cols[i].metric(f"Média {cat}/Dia", f"{hours:.1f}h", f"{minutes:.0f} min")

st.divider()

# --- 4.2 GRÁFICO DE BARRAS (Mantido) ---
st.subheader("2. Evolução Diária (Timeline)")
fig_daily_bar = px.bar(
    df_filtered,
    x='date',
    y='duration_minutes',
    color='categories',
    title="Tempo Total por Dia e Categoria",
    barmode='stack'
)
st.plotly_chart(fig_daily_bar, use_container_width=True)

st.divider()

# --- 4.3 MAPA DE CALOR (Atualizado com escala Preto -> Verde) ---
st.subheader("3. Padrão Horário")
hourly_data = df_filtered.groupby(['hour', 'categories']).size().reset_index(name='contagem')
all_hours = pd.DataFrame({'hour': range(24)})
hourly_data = hourly_data.merge(all_hours, on='hour', how='outer').fillna(0)

# Definindo a escala personalizada
escala_matrix = [
    "#050505", # 0% - Quase Preto (Fundo)
    "#003300", # 25% - Verde Muito Escuro
    "#006400", # 50% - Verde Escuro
    "#00cc00", # 75% - Verde Vivo
    "#99ff99"  # 100% - Verde Claro (Picos de atividade)
]

fig_heatmap = px.density_heatmap(
    df_filtered,
    x='hour',
    y='categories',
    title="Heatmap: Concentração de Atividades por Hora",
    nbinsx=24,
    color_continuous_scale=escala_matrix # Aplicando a nova escala
)

fig_heatmap.update_layout(
    xaxis=dict(tickmode='linear', dtick=1),
    # Opcional: Deixar o fundo do gráfico escuro para combinar melhor
    plot_bgcolor='#0e1117' 
)

st.plotly_chart(fig_heatmap, use_container_width=True)

st.divider()

# --- 4.4 BOXPLOT (Atualizado: Dia vs Noite) ---
st.subheader("4. Consistência: Matutino vs Noturno")
st.markdown("""
Esta visualização compara a **dispersão da duração** das atividades entre o dia (06h-18h) e a noite (18h-06h).
* **Caixa pequena:** Duração consistente (previsível).
* **Caixa grande:** Duração muito variável (imprevisível).
""")

# Definindo cores manuais para facilitar a leitura (Dia = Amarelo/Laranja, Noite = Azul Escuro)
color_map = {
    "Matutino (06h-18h)": "#FFA500", # Laranja
    "Noturno (18h-06h)": "#191970"   # Azul Meia-noite
}

fig_box = px.box(
    df_filtered,
    x='categories',
    y='duration_minutes',
    color='periodo_dia', # A mágica acontece aqui: segmenta cada categoria em 2 caixas
    color_discrete_map=color_map,
    points="all",
    title="Distribuição da Duração: Dia vs Noite",
    labels={'categories': 'Categoria', 'duration_minutes': 'Duração (min)', 'periodo_dia': 'Período'}
)

# Ajuste fino visual
fig_box.update_layout(boxmode='group') # Garante que fiquem lado a lado

st.plotly_chart(fig_box, use_container_width=True)
