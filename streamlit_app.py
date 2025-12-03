import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- 1. CONFIGURAÇÕES GERAIS ---
st.set_page_config(layout="wide", page_title="Nina Tracker: Daily View")

# CONFIGURAÇÕES
# Substitua pelo seu ID real
ID_ARQUIVO = "1ELIud71WxGMp9PskAib_fqVwLOcQNhMV" 
GOOGLE_DRIVE_URL = f"https://drive.google.com/uc?export=download&id={ID_ARQUIVO}"
FUSO_HORARIO = 'America/Sao_Paulo'
CATEGORIAS_PRINCIPAIS = ['Acordada', 'Mamou', 'Dormiu']

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
    """
    if df_raw.empty: return pd.DataFrame()
    
    df = df_raw.copy()
    
    # Normalização de Colunas
    df.columns = df.columns.str.lower().str.replace(' ', '_')
    
    # Tratamento de Tempo e Fuso Horário
    for col in ['time_started', 'time_ended']:
        df[col] = pd.to_datetime(df[col])
        # Garante que seja tz-aware (converte se não for, ajusta se for)
        df[col] = df[col].apply(lambda x: x.tz_localize(FUSO_HORARIO) if x.tzinfo is None else x.tz_convert(FUSO_HORARIO))

    # Limpeza básica
    df['duration_minutes'] = pd.to_numeric(df['duration_minutes'], errors='coerce').fillna(0)
    df = df.dropna(subset=['categories'])
    
    # --- LÓGICA DIÁRIA (CALENDAR DAY) ---
    # Para visão diária, consideramos a data de INÍCIO da atividade.
    df['date'] = df['time_started'].dt.date
    df['hour'] = df['time_started'].dt.hour
    df['day_name'] = df['time_started'].dt.strftime('%A') # Nome do dia (segunda, terça...)
    
    return df

# --- 3. CARREGAMENTO ---

df_raw = get_raw_data()
if df_raw.empty:
    st.stop()

# Cria o DataFrame específico para análise Diária
df_daily = process_daily_data(df_raw)

# Filtro de Data (Sidebar)
st.sidebar.header("📅 Filtros Diários")
min_date = df_daily['date'].min()
max_date = df_daily['date'].max()

date_range = st.sidebar.date_input(
    "Selecione o Período",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Filtragem do DataFrame principal
if len(date_range) == 2:
    mask = (df_daily['date'] >= date_range[0]) & (df_daily['date'] <= date_range[1])
    df_filtered = df_daily.loc[mask]
else:
    df_filtered = df_daily.copy()

# --- 4. VISUALIZAÇÃO ---

st.title(f"📊 Análise Diária (0h - 24h)")
st.markdown("Visão focada no dia civil. Atividades agrupadas pela data de início.")

# --- 4.1 MÉDIAS DIÁRIAS (Solicitado) ---
st.subheader("1. Médias Diárias por Categoria")

# Agrupa por Data e Categoria, depois tira a média
daily_sum = df_filtered.groupby(['date', 'categories'])['duration_minutes'].sum().reset_index()
daily_avg = daily_sum.groupby('categories')['duration_minutes'].mean().reset_index()
daily_avg['duration_hours'] = daily_avg['duration_minutes'] / 60

# Exibição em Colunas (Cards)
cols = st.columns(len(CATEGORIAS_PRINCIPAIS))
for i, cat in enumerate(CATEGORIAS_PRINCIPAIS):
    if i < len(cols):
        val_df = daily_avg[daily_avg['categories'] == cat]
        if not val_df.empty:
            minutes = val_df['duration_minutes'].values[0]
            hours = val_df['duration_hours'].values[0]
            cols[i].metric(f"Média {cat}/Dia", f"{hours:.1f}h", f"{minutes:.0f} min")

st.divider()

# --- 4.2 GRÁFICO POR DIA E CATEGORIA (Solicitado) ---
st.subheader("2. Evolução Diária (Timeline)")

fig_daily_bar = px.bar(
    df_filtered,
    x='date',
    y='duration_minutes',
    color='categories',
    title="Tempo Total por Dia e Categoria",
    labels={'date': 'Data', 'duration_minutes': 'Minutos Totais', 'categories': 'Categoria'},
    barmode='stack'
)
st.plotly_chart(fig_daily_bar, use_container_width=True)

st.divider()

# --- 4.3 NOVO: MAPA DE CALOR HORÁRIO (Sugestão 1) ---
st.subheader("3. Padrão Horário (Concentração de Atividades)")
st.markdown("Em qual hora do dia cada atividade acontece com mais frequência?")

# Agrupa por Hora e Categoria
hourly_data = df_filtered.groupby(['hour', 'categories']).size().reset_index(name='contagem')

# Completa as horas vazias (0 a 23) para o gráfico não ficar buraco
all_hours = pd.DataFrame({'hour': range(24)})
hourly_data = hourly_data.merge(all_hours, on='hour', how='outer').fillna(0)

fig_heatmap = px.density_heatmap(
    df_filtered, # Usamos o DF original filtrado para densidade real
    x='hour',
    y='categories',
    title="Heatmap: Frequência de Início de Atividades por Hora",
    labels={'hour': 'Hora do Dia (0-23h)', 'categories': 'Categoria'},
    color_continuous_scale='Viridis',
    nbinsx=24
)
fig_heatmap.update_layout(xaxis=dict(tickmode='linear', dtick=1))
st.plotly_chart(fig_heatmap, use_container_width=True)

st.divider()

# --- 4.4 NOVO: BOXPLOT DE DURAÇÃO (Sugestão 2) ---
st.subheader("4. Consistência e Duração (Boxplot)")
st.markdown("Análise da variabilidade: As atividades são curtas e picadas ou longas e consistentes?")

fig_box = px.box(
    df_filtered,
    x='categories',
    y='duration_minutes',
    color='categories',
    points="all", # Mostra todos os pontos (outliers e normais)
    title="Distribuição da Duração das Atividades (Minutos)",
    labels={'categories': 'Categoria', 'duration_minutes': 'Duração da Sessão (min)'}
)
st.plotly_chart(fig_box, use_container_width=True)
