import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Inventory Aging Analysis", layout="wide")

# Minimalist styling function for charts matching the dashboard theme
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117', 
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        title_font=dict(color='white'),
        legend=dict(font=dict(color='white'), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# =====================================================================
# PAGE HEADER
# =====================================================================
st.title("Inventory Aging & Capital Drilldown")
st.markdown("Analyze the average age of your active stock over time and drill down into specific days to identify obsolete inventory.")

# =====================================================================
# DATA UPLOAD & PROCESSING
# =====================================================================
uploaded_file = st.file_uploader("Upload Inventory Data", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # 1. Parse File
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        # Ensure column names map correctly to the expected format
        time_col = 'Date'
        demand_col = 'Demand/Sales' 
        receiving_col = 'Receiving'
        open_bal_col = 'Opening Balance'
        
        # Ensure continuous daily dates
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.set_index(time_col).asfreq('D').reset_index()
        df[receiving_col] = df[receiving_col].fillna(0)
        df[demand_col] = df[demand_col].fillna(0)
        
        # 2. FIFO Simulation Engine
        batches = []
        
        # Handle day 0 opening balance safely
        if not pd.isna(df.loc[0, open_bal_col]) and df.loc[0, open_bal_col] > 0:
            batches.append({'receive_date': df.loc[0, time_col], 'qty': df.loc[0, open_bal_col]})
            
        daily_avg_age = []
        daily_age_profile = {} 
        
        # Iterate day by day to track physical age of individual units
        for idx, row in df.iterrows():
            current_date = row[time_col]
            demand = row[demand_col]
            received = row[receiving_col]
            
            # Process Inbound Stock (Creates new batch)
            if received > 0:
                batches.append({'receive_date': current_date, 'qty': received})
                
            # Process Outbound Stock (Depletes oldest batches first via FIFO)
            while demand > 0 and len(batches) > 0:
                if batches[0]['qty'] <= demand:
                    demand -= batches[0]['qty']
                    batches.pop(0)
                else:
                    batches[0]['qty'] -= demand
                    demand = 0
                    
            # Capture End-of-Day Snapshots
            total_qty = 0
            total_age = 0
            current_profile = []
            
            for b in batches:
                age_days = (current_date - b['receive_date']).days
                total_qty += b['qty']
                total_age += b['qty'] * age_days
                current_profile.append({'age': age_days, 'qty': b['qty']})
                
            avg_age = total_age / total_qty if total_qty > 0 else 0
            daily_avg_age.append(avg_age)
            daily_age_profile[current_date] = current_profile
            
        df['Average Age'] = daily_avg_age
        
        st.divider()

        # =====================================================================
        # AGGREGATE CHART SECTION
        # =====================================================================
        st.subheader("Historical Average Age vs. Inventory Velocity")
        st.write("Understand what drives the average age of your stock up or down. Major receiving events pull the average age down sharply, while slow sales periods allow it to creep up.")
        
        # Create Combo Chart
        fig_agg = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Add Bars for In/Out to Secondary Y-Axis
        fig_agg.add_trace(
            go.Bar(x=df[time_col], y=df[receiving_col], name="Inventory In (Receiving)", marker_color="rgba(44, 160, 44, 0.6)"),
            secondary_y=True,
        )
        fig_agg.add_trace(
            go.Bar(x=df[time_col], y=-df[demand_col], name="Inventory Out (Demand)", marker_color="rgba(214, 39, 40, 0.6)"),
            secondary_y=True,
        )
        
        # Add Line for Avg Age to Primary Y-Axis
        fig_agg.add_trace(
            go.Scatter(x=df[time_col], y=df['Average Age'], name="Average Age (Days)", line=dict(color="skyblue", width=3)),
            secondary_y=False,
        )
        
        fig_agg.update_layout(barmode='relative', xaxis_title="Date", bargap=0.1)
        fig_agg.update_yaxes(title_text="Average Age (Days)", secondary_y=False, rangemode='tozero')
        fig_agg.update_yaxes(title_text="Units Processed (In/Out)", secondary_y=True)
        fig_agg = style_plotly_fig(fig_agg)
        
        st.plotly_chart(fig_agg, use_container_width=True)
        
        st.divider()
        
        # =====================================================================
        # POINT-IN-TIME DRILLDOWN
        # =====================================================================
        st.subheader("🔍 Point-in-Time Inventory Age Drilldown")
        
        ctrl1, ctrl2 = st.columns([1, 1])
        with ctrl1:
            bucket_input = st.text_input("Define Age Buckets (comma-separated days)", value="30, 60, 90")
            try:
                cutoffs = [int(x.strip()) for x in bucket_input.split(',')]
                cutoffs.sort()
            except ValueError:
                st.error("Please enter valid integers separated by commas (e.g., 30, 60, 90).")
                cutoffs = [30, 60, 90]
                
        with ctrl2:
            min_date = df[time_col].min().date()
            max_date = df[time_col].max().date()
            selected_date = st.date_input("Select specific date to inspect inventory age distribution", value=max_date, min_value=min_date, max_value=max_date)
            
        selected_date_ts = pd.Timestamp(selected_date)
        
        if selected_date_ts in daily_age_profile:
            profile = daily_age_profile[selected_date_ts]
            
            # Dynamically generate bucket labels and sort inventory
            buckets = {}
            labels = []
            prev = 0
            for cutoff in cutoffs:
                labels.append(f"{prev}-{cutoff} Days" if prev == 0 else f"{prev+1}-{cutoff} Days")
                prev = cutoff
            labels.append(f"{prev+1}+ Days")
            
            for l in labels: 
                buckets[l] = 0
            
            for b in profile:
                age = b['age']
                qty = b['qty']
                placed = False
                for i, cutoff in enumerate(cutoffs):
                    if age <= cutoff:
                        buckets[labels[i]] += qty
                        placed = True
                        break
                if not placed:
                    buckets[labels[-1]] += qty
                    
            # Draw Drilldown Matrix
            viz1, viz2 = st.columns([2, 1])
            
            with viz1:
                st.markdown(f"**Age Distribution on {selected_date}**")
                
                # Apply custom colors: fresh stock (first bucket) gets standard blue, aging stock gets a muted gray-blue
                colors = ['#1f77b4'] + ['#b0c4de'] * (len(labels) - 1)
                
                fig_bar = go.Figure(go.Bar(
                    x=list(buckets.keys()), 
                    y=list(buckets.values()), 
                    name="Actuals",
                    marker_color=colors
                ))
                fig_bar.update_layout(yaxis_title="Units", margin=dict(l=0, r=0, t=30, b=0), height=380)
                fig_bar = style_plotly_fig(fig_bar)
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with viz2:
                st.markdown("**Exact Stock Counts:**")
                tbl_df = pd.DataFrame({
                    "Age Bracket": list(buckets.keys()),
                    "Historical Actuals (Units)": [int(v) for v in buckets.values()]
                })
                st.dataframe(tbl_df, use_container_width=True, hide_index=True)
                
    except Exception as e:
        st.error(f"Error processing the file: {e}")
