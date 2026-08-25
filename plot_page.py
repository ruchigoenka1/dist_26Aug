import streamlit as st
import pandas as pd
import plotly.graph_objects as go

def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='black')
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgray')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgray')
    return fig

st.title("Historical Closing Balance Plotter")
st.write("Upload a CSV file containing your transaction dates and closing balances. Missing dates will be automatically filled with the previous day's balance.")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        
        # Ensure correct column names exist
        if 'Date' not in df.columns or 'Closing Balance' not in df.columns:
            st.error("The CSV must contain 'Date' and 'Closing Balance' columns.")
        else:
            # Convert Date to datetime and sort
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values(by='Date')
            
            # Set Date as index for resampling
            df.set_index('Date', inplace=True)
            
            # Create a complete date range from the min to max date in the dataset
            full_date_range = pd.date_range(start=df.index.min(), end=df.index.max())
            
            # Reindex to the full date range and forward fill missing values
            df_filled = df.reindex(full_date_range).ffill()
            df_filled.reset_index(inplace=True)
            df_filled.rename(columns={'index': 'Date'}, inplace=True)
            
            # Plotting the data
            st.subheader("Closing Balance Timeline")
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_filled["Date"], 
                y=df_filled["Closing Balance"], 
                mode="lines", 
                name="Closing Balance",
                line=dict(color="blue", width=2)
            ))
            
            fig = style_plotly_fig(fig)
            st.plotly_chart(fig, use_container_width=True)
            
            # Show the raw processed data
            with st.expander("View Processed Data"):
                st.dataframe(df_filled)
                
    except Exception as e:
        st.error(f"Error processing file: {e}")
