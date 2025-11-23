import streamlit as st
import plotly.express as px

def render_time_series(df, has_multiple_loops, loop_ids):
    """時系列分析タブをレンダリング"""
    st.header("Full Time Series Data")
    
    # ループフィルター
    if has_multiple_loops:
        loop_filter = st.selectbox("Filter by Loop", ['All'] + list(loop_ids), key='ts_loop')
        df_display = df if loop_filter == 'All' else df[df['LoopID'] == loop_filter]
    else:
        df_display = df
    
    # カラム選択
    default_cols = ['Pressure', 'Flow'] if 'Pressure' in df_display.columns and 'Flow' in df_display.columns else []
    cols = st.multiselect("Select Columns to Plot", df_display.columns, default=default_cols)
    
    # プロット
    if cols:
        fig_ts = px.line(df_display, x='Time', y=cols,
                        color='LoopID' if has_multiple_loops and 'LoopID' in df_display.columns else None,
                        title="Custom Time Series Plot")
        st.plotly_chart(fig_ts, use_container_width=True)
    
    # 生データ表示
    st.subheader("Raw Data")
    st.dataframe(df_display)