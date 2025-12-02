import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, time, timedelta

# --- 1. CONFIGURAÇÃO E CARREGAMENTO DE DADOS (6H às 6H) ---

st.set_page_config(layout="wide", page_title="Nina Tracker: Ciclos e Projeção")

# **ATENÇÃO: SUBSTITUA ESTE LINK PELO SEU URL DE DOWNLOAD DIRETO DO GOOGLE DRIVE!**
GOOGLE_DRIVE_URL = "https://drive.google.com/uc?export=download&id=1ELIud71WxGMp9PskAib_fqVwLOcQNhMV"
N_DIAS_HISTORICO = 15
FUSO_HORARIO = 'America/Sao_Paulo' 

# Nomes de categorias principais para a entrada manual
MAIN_CATEGORIES = ['Acordada', 'Mamou', 'Dormiu']

@st.cache_data(ttl=3600)
def load_and_preprocess_data():
    """Carrega dados, limpa colunas e define o 'cycle_date' (6h às 6h)."""
    
    try:
        df = pd.read_csv(GOOGLE_DRIVE_URL)
    except Exception as e:
        st.error(f"Erro ao carregar os dados. Verifique a URL do Google Drive e as permissões. Erro: {e}")
        return pd.DataFrame()

    df.columns = df.columns.str.lower().str.replace(' ', '_')
    
    # Limpeza e Conversão de Tipos (usando o fuso horário para consistência)
    df['time_started'] = pd.to_datetime(df['time_started']).dt.tz_localize(FUSO_HORARIO, nonexistent='NaT', ambiguous='NaT')
    df['time_ended'] = pd.to_datetime(df['time_ended']).dt.tz_localize(FUSO_HORARIO, nonexistent='NaT', ambiguous='NaT')
    df['duration_minutes'] = pd.to_numeric(df['duration_minutes'], errors='coerce').fillna(0)
    
    # Filtra atividades onde 'categories' é NaN (se houver) e foca nas principais
    df = df.dropna(subset=['categories'])
    
    # Definição do Ciclo Diário (6h AM a 6h AM do dia seguinte)
    df['cycle_date'] = df['time_started'].dt.normalize().dt.tz_localize(None).dt.date
    
    # Se a hora de início (tz-naive) for menor que 6h, pertence ao ciclo do dia anterior.
    is_early_morning = df['time_started'].dt.tz_convert(None).dt.hour < 6
    
    # Para atividades da madrugada, subtrair um dia da data do ciclo.
    df.loc[is_early_morning, 'cycle_date'] = (pd.to_datetime(df.loc[is_early_morning, 'cycle_date']) - pd.Timedelta(days=1)).dt.date
    
    df['cycle_date'] = pd.to_datetime(df['cycle_date']).dt.date
    
    return df

# --- FUNÇÃO PARA PRÉ-PROCESSAMENTO (FIM) ---

df_raw = load_and_preprocess_data()

if df_raw.empty:
    st.stop()

# Define o ciclo mais recente do CSV (que é o ciclo que terminou hoje às 6h da manhã, ou seja, o ciclo de ontem).
all_cycle_dates = sorted(df_raw['cycle_date'].unique())
# O dia mais recente no CSV é o dia de "ontem" na perspectiva do ciclo.
historical_cycles = all_cycle_dates[-N_DIAS_HISTORICO:] 

# Dataframe apenas com o histórico relevante
df_history = df_raw[df_raw['cycle_date'].isin(historical_cycles)].copy()

# --- 2. DASHBOARD RESUMO (ÚLTIMOS 15 DIAS) ---

st.title("👶 Nina Tracker: Análise e Projeção de Ciclos")
st.subheader(f"Resumo Histórico ({N_DIAS_HISTORICO} Ciclos)")

daily_totals_history = df_history.groupby(['cycle_date', 'categories'])['duration_minutes'].sum().reset_index()

# 2.1 Média das Atividades
avg_totals = daily_totals_history.groupby('categories')['duration_minutes'].mean().reset_index()
avg_totals['duration_minutes_h'] = avg_totals['duration_minutes'] / 60
avg_totals.columns = ['Categoria', 'Média (min)', 'Média (h)']

st.markdown("##### Médias de Tempo por Categoria (por Ciclo)")
st.dataframe(
    avg_totals[avg_totals['Categoria'].isin(MAIN_CATEGORIES)].set_index('Categoria').sort_values('Média (h)', ascending=False),
    column_config={"Média (h)": st.column_config.NumberColumn(format="%.1f h")},
    use_container_width=True
)

# 2.2 Gráfico 1: Timeline dos Últimos 15 Dias (Stacked Bar)
st.markdown("##### 📈 Distribuição Diária das Atividades Principais")

fig_stack = px.bar(
    daily_totals_history[daily_totals_history['categories'].isin(MAIN_CATEGORIES)],
    x='cycle_date',
    y='duration_minutes',
    color='categories',
    title='Distribuição de Tempo por Categoria (6h às 6h)',
    labels={'cycle_date': 'Dia do Ciclo (Início às 6h)', 'duration_minutes': 'Duração (Minutos)', 'categories': 'Categoria'},
    height=450
)
fig_stack.update_layout(xaxis_tickangle=-45, legend_title="Atividade")
st.plotly_chart(fig_stack, use_container_width=True)

# 2.3 Gráfico 2: Minutos de Dormiu
df_sleep = daily_totals_history[daily_totals_history['categories'] == 'Dormiu']

fig_sleep = px.line(
    df_sleep,
    x='cycle_date',
    y='duration_minutes',
    title='Tempo Total Dormindo por Ciclo',
    labels={'cycle_date': 'Dia do Ciclo (Início às 6h)', 'duration_minutes': 'Minutos Dormidos'},
    markers=True
)
st.plotly_chart(fig_sleep, use_container_width=True)

st.markdown("---")

# --- 3. ENTRADA MANUAL DO DIA ATUAL PARA COMPARAÇÃO ---

st.header("🎯 Status do Ciclo de HOJE (Entrada Manual)")
current_datetime_tz = pd.Timestamp.now(tz=FUSO_HORARIO)

col_input_1, col_input_2 = st.columns([1, 2])

with col_input_1:
    st.markdown(f"**Hora da Consulta:** `{current_datetime_tz.strftime('%H:%M:%S %Z')}`")
    st.markdown("Preencha o tempo total acumulado em minutos **desde as 6h AM de hoje**.")
    
    # Inputs Manuais
    manual_totals = {}
    for cat in MAIN_CATEGORIES:
        manual_totals[cat] = st.number_input(
            f"Tempo total **{cat}** (minutos)", 
            min_value=0, 
            value=0, 
            key=f"input_{cat}"
        )

# 4. Cálculo de Corte e Estrutura de Dados do Dia Atual

# O ciclo de hoje começou às 6h da manhã.
today_start_of_cycle = current_datetime_tz.normalize().tz_localize(FUSO_HORARIO) + pd.Timedelta(hours=6)

# Se for antes das 6h, o ciclo começou ontem.
if current_datetime_tz.time() < time(6, 0):
    today_start_of_cycle -= pd.Timedelta(days=1)

# Tempo total que se passou no ciclo (em minutos)
time_passed_minutes = (current_datetime_tz - today_start_of_cycle) / np.timedelta64(1, 'm')

with col_input_2:
    st.metric(
        "Tempo Decorrido do Ciclo", 
        f"{time_passed_minutes:.0f} minutos", 
        help="Tempo decorrido desde o início do ciclo (6h AM) até a hora atual da consulta."
    )
    
# --- 5. ANÁLISE DE SIMILARIDADE E PROJEÇÃO ---

st.header("🔍 Projeção e Dias Semelhantes")

col_sim_1, col_sim_2 = st.columns(2)

with col_sim_1:
    similarity_category = st.selectbox(
        "Categoria Chave para Comparação",
        options=MAIN_CATEGORIES,
        index=2 # Padrão: Dormiu
    )
with col_sim_2:
    similarity_threshold = st.slider(
        f"Tolerância ($\pm$ min. de {similarity_category})",
        min_value=30,
        max_value=120,
        value=60, # 60 minutos = 1 hora
        step=10
    )

# Valor do dia atual (manual) para a categoria chave
today_key_value = manual_totals[similarity_category]

# 5.1 Encontrando Dias Similares
@st.cache_data
def calculate_historical_value(df_hist, key_category, time_passed_minutes_cutoff):
    """Calcula o total histórico da categoria chave até o ponto de corte do dia."""
    
    historical_data = []
    
    # Itera sobre cada dia histórico
    for cycle_date, group in df_hist.groupby('cycle_date'):
        cycle_start = pd.Timestamp(cycle_date).tz_localize(FUSO_HORARIO) + pd.Timedelta(hours=6)
        # O ponto de corte é o início do ciclo + o tempo passado no ciclo de hoje
        cutoff_time = cycle_start + pd.Timedelta(minutes=time_passed_minutes_cutoff)

        # Filtra atividades históricas que terminaram antes do ponto de corte
        df_filtered = group[group['time_ended'] < cutoff_time]
        
        # Soma a categoria chave para esse dia
        total_value = df_filtered[df_filtered['categories'] == key_category]['duration_minutes'].sum()
        
        historical_data.append({
            'cycle_date': cycle_date,
            'key_category_total': total_value
        })
        
    return pd.DataFrame(historical_data)

# Obtém os totais históricos até o tempo de corte atual
historical_key_totals_df = calculate_historical_value(df_history, similarity_category, time_passed_minutes)

# Encontrar dias similares (com base na entrada manual)
historical_key_totals_df['difference'] = abs(historical_key_totals_df['key_category_total'] - today_key_value)
similar_days_df = historical_key_totals_df[historical_key_totals_df['difference'] <= similarity_threshold]

similar_days = similar_days_df['cycle_date'].tolist()

st.info(
    f"O valor de **{similarity_category}** inserido é **{today_key_value:.0f} minutos** (até {current_datetime_tz.strftime('%H:%M')}). "
    f"Encontrados **{len(similar_days)}** dias históricos similares (tolerância de $\pm {similarity_threshold}$ minutos)."
)

if not similar_days:
    st.warning("Nenhum dia similar encontrado com os critérios atuais. Tente aumentar a tolerância.")
    st.stop()
    
# Resumo dos dias similares
st.dataframe(
    similar_days_df[['cycle_date', 'key_category_total', 'difference']].sort_values('difference'), 
    use_container_width=True
)


# 5.2 Projeção do Restante do Dia

st.subheader("Projeção Baseada em Dias Similares (Restante do Ciclo)")

# 1. Filtra os dados apenas dos dias similares
df_similar_days = df_history[df_history['cycle_date'].isin(similar_days)].copy()

# 2. Define o ponto de corte em cada dia similar
# O ponto de corte é o tempo decorrido no ciclo de hoje (time_passed_minutes)
df_projection_data = []

for cycle_date, group in df_similar_days.groupby('cycle_date'):
    cycle_start = pd.Timestamp(cycle_date).tz_localize(FUSO_HORARIO) + pd.Timedelta(hours=6)
    cutoff_time = cycle_start + pd.Timedelta(minutes=time_passed_minutes)
    
    # Atividades que aconteceram DEPOIS do ponto de corte nesse dia similar
    df_projection_data.append(group[group['time_started'] >= cutoff_time])

df_projection = pd.concat(df_projection_data)


# 3. Calcula o total MÍNIMO, MÉDIO e MÁXIMO restante
projection_summary = df_projection.groupby(['cycle_date', 'categories'])['duration_minutes'].sum().reset_index()

projection_final = projection_summary.groupby('categories')['duration_minutes'].agg(['min', 'mean', 'max']).reset_index()
projection_final.columns = ['Categoria', 'Min. Restante (min)', 'Média Restante (min)', 'Max. Restante (min)']

st.markdown("##### ⏳ Tempo Total de Atividade Projetado (Restante do Ciclo)")
st.dataframe(
    projection_final[projection_final['Categoria'].isin(MAIN_CATEGORIES)].set_index('Categoria').astype(int), 
    use_container_width=True
)

# 4. Gráfico de Timeline dos Dias Similares (Projeção)
st.markdown("##### 📈 Timeline de Atividades dos Dias Similares (A partir de agora)")

# Cria um tempo de início simulado para a linha de corte, para visualização
current_time_display = pd.Timestamp(current_datetime_tz.date()).tz_localize(FUSO_HORARIO) + pd.Timedelta(hours=current_datetime_tz.hour, minutes=current_datetime_tz.minute)

fig_timeline = px.timeline(
    df_projection,
    x_start="time_started", 
    x_end="time_ended", 
    y="cycle_date", 
    color="categories",
    title="Atividades Restantes nos Dias Similares",
    labels={"cycle_date": "Dia Similar"},
    hover_name="activity_name"
)

# Adiciona uma linha vertical para o tempo de corte (tempo atual)
fig_timeline.add_vline(x=current_time_display, line_dash="dash", line_color="Red", annotation_text="Tempo Atual")

fig_timeline.update_yaxes(autorange="reversed") 
st.plotly_chart(fig_timeline, use_container_width=True)
