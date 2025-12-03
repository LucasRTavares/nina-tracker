import streamlit as st
import pandas as pd
import plotly.express as px
import datetime as dt

# --- 1. CONFIGURAÇÕES GERAIS ---
st.set_page_config(layout="wide", page_title="Nina Tracker: Hourly Precision")

# CONFIGURAÇÕES
ID_ARQUIVO = "1ELIud71WxGMp9PskAib_fqVwLOcQNhMV" 
GOOGLE_DRIVE_URL = f"https://drive.google.com/uc?export=download&id={ID_ARQUIVO}"
FUSO_HORARIO = 'America/Sao_Paulo'
CATEGORIAS_PRINCIPAIS = ['Acordada', 'Mamou', 'Dormiu']
DIAS_PADRAO_INICIAL = 15

# --- 2. CAMADA DE DADOS (ETL) ---

@st.cache_data(ttl=3600)
def get_raw_data():
    try:
        df = pd.read_csv(GOOGLE_DRIVE_URL)
        return df
    except Exception as e:
        st.error(f"Erro no download: {e}")
        return pd.DataFrame()

def process_daily_data(df_raw):
    """Limpeza básica e tipagem."""
    if df_raw.empty: return pd.DataFrame()
    df = df_raw.copy()
    df.columns = df.columns.str.lower().str.replace(' ', '_')
    
    for col in ['time_started', 'time_ended']:
        df[col] = pd.to_datetime(df[col])
        df[col] = df[col].apply(lambda x: x.tz_localize(FUSO_HORARIO) if x.tzinfo is None else x.tz_convert(FUSO_HORARIO))

    df['duration_minutes'] = pd.to_numeric(df['duration_minutes'], errors='coerce').fillna(0)
    df = df.dropna(subset=['categories'])
    
    # Enriquecimento Básico
    df['date'] = df['time_started'].dt.date
    df['hour'] = df['time_started'].dt.hour
    
    def definir_periodo(hora):
        return "Matutino (06h-18h)" if 6 <= hora < 18 else "Noturno (18h-06h)"
    df['periodo_dia'] = df['hour'].apply(definir_periodo)
    
    return df

@st.cache_data
def expand_events_by_hour(df):
    """
    TRANSFORMAÇÃO CRÍTICA:
    Quebra eventos que cruzam a hora em múltiplas linhas.
    Ex: 17:50 até 18:10 vira:
        - 17:50 até 18:00 (10 min) na hora 17
        - 18:00 até 18:10 (10 min) na hora 18
    """
    new_rows = []
    
    for _, row in df.iterrows():
        start = row['time_started']
        end = row['time_ended']
        cat = row['categories']
        
        # Arredonda o start para o início da próxima hora
        # Ex: 17:50 -> proxima hora cheia é 18:00
        next_hour = start.ceil('h')
        
        current_start = start
        
        # Enquanto o tempo de início atual for menor que o tempo final real
        while current_start < end:
            # O fim deste segmento é o menor valor entre: 
            # (próxima hora cheia) OU (fim real do evento)
            # Se next_hour for 18:00 e end for 18:10, segment_end será 18:00 (primeiro loop)
            current_end_of_hour = pd.Timestamp(current_start).ceil('h')
            # Correção para quando current_start já é hora cheia
            if current_end_of_hour == current_start:
                current_end_of_hour += pd.Timedelta(hours=1)
                
            segment_end = min(current_end_of_hour, end)
            
            # Calcula duração deste pedaço
            duration = (segment_end - current_start).total_seconds() / 60
            
            if duration > 0:
                new_rows.append({
                    'date': current_start.date(),
                    'hour': current_start.hour,
                    'categories': cat,
                    'duration_minutes': duration
                })
            
            # Prepara para o próximo loop
            current_start = segment_end
            
    return pd.DataFrame(new_rows)

# --- 3. EXECUÇÃO ---

df_raw = get_raw_data()
if df_raw.empty: st.stop()

# DataFrame 1: Eventos Originais (Para Timeline e Boxplot)
df_events = process_daily_data(df_raw)

# Filtro de Data
st.sidebar.header("📅 Filtros")
min_date = df_events['date'].min()
max_date = df_events['date'].max()
default_start = max(min_date, max_date - dt.timedelta(days=DIAS_PADRAO_INICIAL))

date_range = st.sidebar.date_input("Período", value=(default_start, max_date), min_value=min_date, max_value=max_date)

if isinstance(date_range, tuple) and len(date_range) == 2:
    # Filtra Eventos Originais
    mask_events = (df_events['date'] >= date_range[0]) & (df_events['date'] <= date_range[1])
    df_filtered_events = df_events.loc[mask_events]
    
    # GERA DATAFRAME 2: Expandido (Para Heatmap)
    # Processamos apenas o período filtrado para ganhar performance
    df_hourly_split = expand_events_by_hour(df_filtered_events)
else:
    st.stop()

# --- 4. VISUALIZAÇÃO ---

st.title("📊 Análise Diária de Precisão")

# 4.1 MÉDIAS (Usando dados originais ou split dá na mesma para soma diária)
st.subheader("1. Médias Diárias")
daily_totals = df_filtered_events.groupby(['date', 'categories'])['duration_minutes'].sum().reset_index()
avg_metrics = daily_totals.groupby('categories')['duration_minutes'].mean().reset_index()

cols = st.columns(len(CATEGORIAS_PRINCIPAIS))
for i, cat in enumerate(CATEGORIAS_PRINCIPAIS):
    if i < len(cols):
        row = avg_metrics[avg_metrics['categories'] == cat]
        val = row['duration_minutes'].values[0] if not row.empty else 0
        cols[i].metric(f"Média {cat}", f"{val/60:.1f}h", f"{val:.0f} min")

st.divider()

# 4.2 TIMELINE (Original Events - Visualmente melhor ver o bloco inteiro)
st.subheader("2. Timeline de Eventos")
fig_timeline = px.bar(
    df_filtered_events,
    x='date', y='duration_minutes', color='categories',
    title="Volume Total por Dia", barmode='stack'
)
st.plotly_chart(fig_timeline, use_container_width=True)

st.divider()

# 4.3 HEATMAP DE PRECISÃO (Usando Tabela Paralela 'df_hourly_split')
st.subheader("3. Padrão Horário Real (Minutos/Hora)")
st.markdown("Soma exata de minutos gastos em cada hora do dia.")

if not df_hourly_split.empty:
    # Agrupa por Hora e Categoria somando MINUTOS (não contagem)
    heatmap_data = df_hourly_split.groupby(['hour', 'categories'])['duration_minutes'].sum().reset_index()
    
    # Normaliza pelo número de dias selecionados para mostrar "Média de Minutos por Hora"
    # Se preferir ver o total absoluto acumulado no período, remova a divisão abaixo.
    n_days = (date_range[1] - date_range[0]).days + 1
    heatmap_data['minutes_per_hour_avg'] = heatmap_data['duration_minutes'] / n_days
    
    # Preenche horas vazias
    all_hours = pd.DataFrame({'hour': range(24)})
    heatmap_data = heatmap_data.merge(all_hours, on='hour', how='outer').fillna(0)
    
    escala_matrix = ["#050505", "#003300", "#006400", "#00cc00", "#99ff99"]

    fig_heatmap = px.density_heatmap(
        heatmap_data,
        x='hour',
        y='categories',
        z='minutes_per_hour_avg', # Eixo Z agora é a média de minutos
        title=f"Intensidade Média (Minutos dentro da hora) - Base: {n_days} dias",
        nbinsx=24,
        color_continuous_scale=escala_matrix,
        histfunc='sum' # Garante que o Plotly some os valores de Z
    )
    
    fig_heatmap.update_layout(
        xaxis=dict(tickmode='linear', dtick=1, title="Hora do Dia"),
        yaxis=dict(title="Categoria"),
        coloraxis_colorbar=dict(title="Média Min/Hora"),
        plot_bgcolor='#0e1117'
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)
else:
    st.info("Sem dados suficientes para o Heatmap neste período.")

st.divider()

# 4.4 BOXPLOT (Usa Eventos Originais - Queremos consistência da 'tirada' de sono)
st.subheader("4. Consistência: Matutino vs Noturno")
st.markdown("Analisa a duração de **cada evento individualmente**. (Dados não fragmentados)")

color_map = {"Matutino (06h-18h)": "#FFA500", "Noturno (18h-06h)": "#191970"}

fig_box = px.box(
    df_filtered_events,
    x='categories', y='duration_minutes', color='periodo_dia',
    color_discrete_map=color_map, points="all",
    title="Duração dos Eventos (Consistência)"
)
fig_box.update_layout(boxmode='group')
st.plotly_chart(fig_box, use_container_width=True)
