import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io

def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117', 
        paper_bgcolor='#0E1117',
        font=dict(color='white')
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# ------------------------------------------------
# Sample Excel Generator
# ------------------------------------------------
def generate_sample_excel():
    df_sample = pd.DataFrame({
        "Date": ["2024-01-01", "2024-01-03", "2024-01-07"],
        "Closing Balance": [500, 439, 358]
    })
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_sample.to_excel(writer, index=False, sheet_name='Sample Data')
    return buffer.getvalue()

st.title("Historical Closing Balance Plotter")
st.write("Upload a CSV or Excel file containing your transaction dates/days and closing balances. Missing gaps will be automatically filled with the previous day's balance.")

# ------------------------------------------------
# Download Template Section
# ------------------------------------------------
st.download_button(
    label="📥 Download Sample Excel Template",
    data=generate_sample_excel(),
    file_name="inventory_sample_template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.divider()

# ------------------------------------------------
# File Upload & Processing
# ------------------------------------------------
uploaded_file = st.file_uploader("Upload File", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        
        time_col = df.columns[0]
        balance_col = df.columns[1]
        
        is_numeric_index = pd.api.types.is_numeric_dtype(df[time_col])
        
        if not is_numeric_index:
            df[time_col] = pd.to_datetime(df[time_col])
            
        df = df.sort_values(by=time_col)
        df.set_index(time_col, inplace=True)
        
        if is_numeric_index:
            full_range = range(int(df.index.min()), int(df.index.max()) + 1)
        else:
            full_range = pd.date_range(start=df.index.min(), end=df.index.max())
        
        df_filled = df.reindex(full_range).ffill()
        df_filled.reset_index(inplace=True)
        df_filled.rename(columns={'index': time_col}, inplace=True)
        
        # ------------------------------------------------
        # Historical KPIs (Metrics)
        # ------------------------------------------------
        st.subheader("Historical Inventory Metrics")
        kpi1, kpi2, kpi3 = st.columns(3)
        actual_min = df_filled[balance_col].min()
        
        kpi1.metric("Minimum Balance", round(actual_min, 1))
        kpi2.metric("Maximum Balance", round(df_filled[balance_col].max(), 1))
        kpi3.metric("Average Balance", round(df_filled[balance_col].mean(), 1))
        
        st.divider()
        
        # ------------------------------------------------
        # Chart Controls (Thresholds)
        # ------------------------------------------------
        st.subheader("Chart Analysis Tools")
        
        st.markdown("**Minimum Level Alert Box**")
        min_threshold = st.number_input("Set Alert Threshold", value=float(actual_min))
        show_min_box = st.checkbox("Show red box below this level", value=True)
        
        # ------------------------------------------------
        # Plotting the data
        # ------------------------------------------------
        st.subheader("Closing Balance Timeline")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_filled[time_col], 
            y=df_filled[balance_col], 
            mode="lines", 
            name="Closing Balance",
            line=dict(color="skyblue", width=2)
        ))
        
        # Add the horizontal box for the minimum level
        if show_min_box:
            fig.add_hrect(
                y0=0, y1=min_threshold, 
                fillcolor="red", opacity=0.15, 
                line_width=0, 
                annotation_text="Alert Zone", 
                annotation_font_color="white"
            )
            
        fig = style_plotly_fig(fig)
        st.plotly_chart(fig, use_container_width=True)
        
        # ------------------------------------------------
        # Data Table
        # ------------------------------------------------
        with st.expander("View Filled Data"):
            st.dataframe(df_filled, use_container_width=True)
            
    except Exception as e:
        st.error(f"Error processing file. Please ensure your file has two columns (Time/Date and Balance). Error details: {e}")
