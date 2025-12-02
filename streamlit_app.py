import streamlit as st
import pandas as pd
import plotly.express as px
import datetime as dt
from dateutil import tz
import numpy as np

# --- 1. CONFIGURAÇÃO E CARREGAMENTO DE DADOS (6H às 6H) ---

st.set_page_config(layout="wide", page_title="Ciclos da Bebê: Análise e Projeção")

# **ATENÇÃO: SUBSTITUA ESTE LINK PELO SEU URL DE DOWNLOAD DIRETO DO GOOGLE DRIVE!**
# Lembre-se de definir as permissões do seu CSV no Drive para "Qualquer pessoa com o link".
GOOGLE_DRIVE_URL = "https://drive.google.com/uc?export=download&id=1ELIud71WxGMp9PskAib_fqVwLOcQNhMV"
N_DIAS_HISTORICO = 15
FUSO_HORARIO = 'America/Sao_Paulo' # Ajuste conforme seu fuso

@st.cache_data(ttl=3600) # Recarrega os dados a cada 1 hora
def load_and_preprocess_data():
    """Carrega dados, limpa colunas e define o 'cycle_date' (6h às 6h)."""
    
    # 1. Carregamento dos dados (usando o link do Drive ou o arquivo local)
    try:
        df = pd.read_csv(GOOGLE_DRIVE_URL)
        # Se for usar um arquivo local para testes:
        # df = pd.read_csv('simulated_baby_data.csv') 
    except Exception as e:
        st.error(f"Erro ao carregar os dados. Verifique a URL do Google Drive e as permissões. Erro: {e}")
        return pd.DataFrame()

    df.columns = df.columns.str.lower().str.replace(' ', '_')
    
    # 2. Limpeza e Conversão de Tipos
    df['time_started'] = pd.to_datetime(df['time_started']).dt.tz_localize(FUSO_HORARIO, nonexistent='shift_forward', ambiguous='NaT')
    df['time_ended'] = pd.to_datetime(df['time_ended']).dt.tz_localize(FUSO_HORARIO, nonexistent='shift_forward', ambiguous='NaT')
    df['duration_minutes'] = pd.to_numeric(df['duration_minutes'], errors='coerce').fillna(0)
    
    # 3. Definição do Ciclo Diário (6h AM a 6h AM do dia seguinte)
    df['cycle_date'] = df['time_started'].dt.tz_convert(None).dt.date
    is_early_morning = df['time_started'].dt.tz_convert(None).dt.hour < 6
    
    # Se a atividade começou antes das 6h, ela pertence ao ciclo do dia anterior.
    df.loc[is_early_morning, 'cycle_date'] = (pd.to_datetime(df.loc[is_early_morning, 'cycle_date']) - pd.Timedelta(days=1)).dt.date
    
    df['cycle_date'] = pd.to_datetime(df['cycle_date']).dt.date
    
    return df

# --- 2. EXECUÇÃO DO SCRIPT ---

df_raw = load_and_preprocess_data()

if df_raw.empty:
    st.stop()

# Filtra para os últimos N dias (excluindo o dia atual para a maioria das análises)
all_cycle_dates = sorted(df_raw['cycle_date'].unique())

# O dia mais recente é o "Dia de Hoje"
today_cycle_date = all_cycle_dates[-1]

# Selecionar o histórico (últimos N dias)
historical_cycles = all_cycle_dates[-N_DIAS_HISTORICO:-1] # Exclui o dia atual (o último)

# Cria uma cópia do DF com os últimos N dias para processamento rápido
df_history = df_raw[df_raw['cycle_date'].isin(historical_cycles + [today_cycle_date])].copy()
df_today = df_raw[df_raw['cycle_date'] == today_cycle_date].copy()

# --- 3. BARRA LATERAL (FILTROS) ---

st.sidebar.header("🗓️ Configurações da Análise")
st.sidebar.markdown(f"**Ciclo Atual:** {today_cycle_date.strftime('%d/%m/%Y')} (6h às 6h)")

# Filtro de Similaridade
st.sidebar.subheader("Filtro de Dias Similares")
similarity_category = st.sidebar.selectbox(
    "Categoria Chave para Comparação",
    options=df_raw['categories'].unique(),
    index=0 # Ex: 'Mamou'
)
similarity_threshold = st.sidebar.slider(
    "Tolerância (minutos)",
    min_value=30,
    max_value=120,
    value=60, # 60 minutos = 1 hora
    step=10
)

# --- 4. ANÁLISE DO DIA ATUAL E DO HISTÓRICO ---

st.title(f"Acompanhamento do Ciclo: {today_cycle_date.strftime('%d/%m/%Y')}")
st.markdown("---")

col1, col2, col3 = st.columns(3)

# 4.1 KPIs do Dia Atual (Até o momento)
current_time = pd.Timestamp.now(tz=FUSO_HORARIO).tz_convert(None).to_datetime64()

df_today_so_far = df_today[df_today['time_ended'] < current_time]
totals_today = df_today_so_far.groupby('categories')['duration_minutes'].sum()

# Calcula a duração total do ciclo (em minutos) para o dia atual (6h de 'today_cycle_date' até o `current_time`)
start_of_cycle = pd.Timestamp(today_cycle_date) + pd.Timedelta(hours=6)
total_time_passed_minutes = (current_time - start_of_cycle) / np.timedelta64(1, 'm')

# Exibe os KPIs
for i, cat in enumerate(df_raw['categories'].unique()):
    total_min = totals_today.get(cat, 0)
    total_h = total_min / 60
    
    col = [col1, col2, col3][i % 3]
    col.metric(
        label=f"Tempo Total **{cat}** (Hoje)",
        value=f"{total_min} min ({total_h:.1f} h)",
        delta=None # Sem delta, pois a comparação é complexa
    )

st.markdown("---")

# 4.2 Histórico Diário (Timeline de Bar)

st.subheader("Histórico dos Últimos Dias (6h às 6h)")

# Agrega os dados históricos por dia e categoria
daily_totals = df_history.groupby(['cycle_date', 'categories'])['duration_minutes'].sum().reset_index()

fig_history = px.bar(
    daily_totals,
    x='cycle_date',
    y='duration_minutes',
    color='categories',
    title='Tempo Total por Categoria (Timeline dos Dias)',
    labels={'cycle_date': 'Dia do Ciclo (6h)', 'duration_minutes': 'Duração (Minutos)', 'categories': 'Categoria'},
    height=400
)
fig_history.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig_history, use_container_width=True)

st.markdown("---")

# --- 5. ANÁLISE DE SIMILARIDADE E PROJEÇÃO ---

st.header("🔍 Análise de Similaridade e Projeção")

# 5.1 Encontrando Dias Similares
# 1. Calcular o total da categoria chave para o dia atual (até o momento)
today_key_value = totals_today.get(similarity_category, 0)

# 2. Calcular o total da categoria chave para todos os dias históricos (até o mesmo ponto do ciclo)
def calculate_historical_value(df_hist, key_category, cycle_start_time_of_day):
    """Calcula o valor da categoria chave em dias históricos até a mesma hora do dia."""
    
    # Cria uma cópia para evitar SettingWithCopyWarning
    df_temp = df_hist.copy()
    
    # Ponto de corte no ciclo de 24h
    df_temp['time_started_TOD'] = (df_temp['time_started'] - pd.to_datetime(df_temp['cycle_date'])).dt.total_seconds() / 60
    
    # Calcula a hora de corte (em minutos desde o início do ciclo às 6h)
    cut_off_minutes = (cycle_start_time_of_day - start_of_cycle) / np.timedelta64(1, 'm')
    
    # Filtra atividades que terminaram antes do ponto de corte
    df_filtered = df_temp[df_temp['time_ended'] < pd.Timestamp(df_temp['cycle_date']) + pd.Timedelta(hours=6) + pd.Timedelta(minutes=cut_off_minutes)]
    
    historical_key_totals = df_filtered.groupby('cycle_date')['duration_minutes'].sum().reset_index()
    
    # Filtra apenas a categoria chave
    historical_key_totals = df_filtered[df_filtered['categories'] == key_category].groupby('cycle_date')['duration_minutes'].sum().reset_index()
    historical_key_totals = historical_key_totals.rename(columns={'duration_minutes': 'key_category_total'})
    
    return historical_key_totals

# Ponto de corte é o 'current_time'
historical_key_totals_df = calculate_historical_value(df_history, similarity_category, current_time)

# 3. Encontrar dias similares
historical_key_totals_df['difference'] = abs(historical_key_totals_df['key_category_total'] - today_key_value)
similar_days_df = historical_key_totals_df[historical_key_totals_df['difference'] <= similarity_threshold]

similar_days = similar_days_df['cycle_date'].tolist()

st.info(f"O dia atual (até o momento) tem **{today_key_value:.0f} minutos** de **{similarity_category}**. Encontrados **{len(similar_days)}** dias similares (tolerância de $\pm {similarity_threshold}$ minutos).")
st.dataframe(similar_days_df[['cycle_date', 'key_category_total', 'difference']].sort_values('difference'), use_container_width=True)


# 5.2 Projeção do Restante do Dia

if similar_days:
    st.subheader("Projeção Baseada em Dias Similares (Restante do Ciclo)")
    
    # Dados apenas dos dias similares
    df_similar_days = df_raw[df_raw['cycle_date'].isin(similar_days)].copy()
    
    # Atividades que aconteceram DEPOIS do ponto de corte (current_time)
    df_projection = df_similar_days[df_similar_days['time_started'] >= current_time].copy()
    
    # Calcula a hora relativa no ciclo de 24h (0h = 6h da manhã do cycle_date)
    def calculate_relative_time(row):
        # Início do ciclo é 6h do cycle_date
        cycle_start = pd.Timestamp(row['cycle_date']) + pd.Timedelta(hours=6)
        
        # O tempo '0' do gráfico é o cycle_start.
        relative_minutes_start = (row['time_started'] - cycle_start) / np.timedelta64(1, 'm')
        
        # Plota como se o dia tivesse 24h * 60 min = 1440 min
        return relative_minutes_start % 1440

    df_projection['relative_minutes_start'] = df_projection.apply(calculate_relative_time, axis=1)

    # Agrega a média de duração por categoria para cada hora do ciclo
    df_projection['relative_hour'] = (df_projection['relative_minutes_start'] / 60).astype(int)
    
    # Filtra para o período relevante (depois do tempo atual, arredondando para baixo)
    current_hour_of_cycle = int((current_time - start_of_cycle) / np.timedelta64(1, 'm') / 60)
    df_projection_relevant = df_projection[df_projection['relative_hour'] >= current_hour_of_cycle]

    # Calcula o total MÍNIMO, MÉDIO e MÁXIMO restante por categoria (por dia similar)
    projection_summary = df_projection_relevant.groupby(['cycle_date', 'categories'])['duration_minutes'].sum().reset_index()
    
    projection_final = projection_summary.groupby('categories')['duration_minutes'].agg(['min', 'mean', 'max']).reset_index()
    projection_final.columns = ['Categoria', 'Min. Restante (min)', 'Média Restante (min)', 'Max. Restante (min)']

    st.markdown("##### ⏳ Tempo Total de Atividade Projetado (Restante do Ciclo)")
    st.dataframe(projection_final.set_index('Categoria').astype(int), use_container_width=True)
    
    
    # 5.3 Gráfico de Timeline dos Dias Similares (Projeção)
    st.markdown("##### 📈 Timeline de Atividades dos Dias Similares (A partir de agora)")

    # Cria o gráfico de Gantt/Timeline
    fig_timeline = px.timeline(
        df_projection_relevant,
        x_start="time_started", 
        x_end="time_ended", 
        y="cycle_date", 
        color="categories",
        title="Atividades Restantes nos Dias Similares",
        labels={"cycle_date": "Dia Similar"},
        hover_name="activity_name"
    )

    # Adiciona uma linha vertical para o tempo atual de hoje
    fig_timeline.add_vline(x=current_time, line_dash="dash", line_color="Red", annotation_text="Tempo Atual")
    
    fig_timeline.update_yaxes(autorange="reversed") 
    st.plotly_chart(fig_timeline, use_container_width=True)

else:
    st.warning("Nenhum dia similar encontrado com os critérios atuais. Tente aumentar a tolerância.")
