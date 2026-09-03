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
        
        if not pd.isna(df.loc[0, open_bal_col]) and df.loc[0, open_bal_col] > 0:
            batches.append({'receive_date': df.loc[0, time_col], 'qty': df.loc[0, open_bal_col]})
            
        daily_avg_age = []
        daily_age_profile = {} 
        
        for idx, row in df.iterrows():
            current_date = row[time_col]
            demand = row[demand_col]
            received = row[receiving_col]
            
            if received > 0:
                batches.append({'receive_date': current_date, 'qty': received})
                
            while demand > 0 and len(batches) > 0:
                if batches[0]['qty'] <= demand:
                    demand -= batches[0]['qty']
                    batches.pop(0)
                else:
                    batches[0]['qty'] -= demand
                    demand = 0
                    
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
        
        fig_agg = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig_agg.add_trace(go.Bar(x=df[time_col], y=df[receiving_col], name="Inventory In (Receiving)", marker_color="rgba(44, 160, 44, 0.6)"), secondary_y=True)
        fig_agg.add_trace(go.Bar(x=df[time_col], y=-df[demand_col], name="Inventory Out (Demand)", marker_color="rgba(214, 39, 40, 0.6)"), secondary_y=True)
        fig_agg.add_trace(go.Scatter(x=df[time_col], y=df['Average Age'], name="Average Age (Days)", line=dict(color="skyblue", width=3)), secondary_y=False)
        
        fig_agg.update_layout(barmode='relative', xaxis_title="Date", bargap=0.1)
        fig_agg.update_yaxes(title_text="Average Age (Days)", secondary_y=False, rangemode='tozero')
        fig_agg.update_yaxes(title_text="Units Processed (In/Out)", secondary_y=True)
        st.plotly_chart(style_plotly_fig(fig_agg), use_container_width=True)
        
        st.divider()
        
        # =====================================================================
        # INVENTORY AGE PROFILE (FIFO STACKED)
        # =====================================================================
        st.subheader("🕒 Inventory Age Profile (FIFO Stacked)")
        st.write("Visualize what fraction of your total inventory sitting in the warehouse belongs to distinct aging brackets over time.")
        
        # Move the Bucket Input here so it drives both the Stacked Area and the Drilldown
        bucket_input = st.text_input("Define custom inventory age thresholds in days (comma-separated, e.g., '30, 60, 90')", value="30, 60, 90")
        try:
            cutoffs = [int(x.strip()) for x in bucket_input.split(',')]
            cutoffs.sort()
        except ValueError:
            st.error("Please enter valid integers separated by commas (e.g., 30, 60, 90).")
            cutoffs = [30, 60, 90]
            
        # Generate Labels based on cutoffs
        labels = []
        prev = 0
        for cutoff in cutoffs:
            labels.append(f"{prev}-{cutoff} Days" if prev == 0 else f"{prev+1}-{cutoff} Days")
            prev = cutoff
        labels.append(f"{prev+1}+ Days")
        
        # 3. Calculate time-series buckets for the stacked chart
        ts_data = {l: [] for l in labels}
        dates_list = []
        
        for current_date in df[time_col]:
            profile = daily_age_profile.get(pd.Timestamp(current_date), [])
            daily_buckets = {l: 0 for l in labels}
            
            for b in profile:
                age = b['age']
                qty = b['qty']
                placed = False
                for i, cutoff in enumerate(cutoffs):
                    if age <= cutoff:
                        daily_buckets[labels[i]] += qty
                        placed = True
                        break
                if not placed:
                    daily_buckets[labels[-1]] += qty
                    
            for l in labels:
                ts_data[l].append(daily_buckets[l])
            dates_list.append(current_date)
            
        # Plot the Stacked Area Chart
        fig_stacked = go.Figure()
        
        # Warm to hot colors (Blue for fresh, Brown/Red for aged)
        color_palette = ['#4A789C', '#285375', '#8C6C38', '#8B2E2E', '#5E1E1E', '#3E1010'] 
        
        for i, label in enumerate(labels):
            fig_stacked.add_trace(go.Scatter(
                x=dates_list,
                y=ts_data[label],
                mode='lines',
                line=dict(width=0, color=color_palette[i % len(color_palette)]),
                fillcolor=color_palette[i % len(color_palette)], # Force exact hex color
                opacity=1.0, # Remove default Plotly transparency
                stackgroup='one',
                name=label
            ))
            
        fig_stacked.update_layout(yaxis_title="Units In Stock", hovermode='x unified')
        st.plotly_chart(style_plotly_fig(fig_stacked), use_container_width=True)
        
        st.divider()

        # =====================================================================
        # POINT-IN-TIME DRILLDOWN
        # =====================================================================
        st.subheader("🔍 Point-in-Time Inventory Age Drilldown")
        st.write("Select specific date to inspect inventory age distribution")
        
        min_date = df[time_col].min().date()
        max_date = df[time_col].max().date()
        selected_date = st.date_input("Date Inspector", value=max_date, min_value=min_date, max_value=max_date)
            
        selected_date_ts = pd.Timestamp(selected_date)
        
        if selected_date_ts in daily_age_profile:
            profile = daily_age_profile[selected_date_ts]
            
            # Reuse the dynamic labels and buckets from above
            drilldown_buckets = {l: 0 for l in labels}
            
            for b in profile:
                age = b['age']
                qty = b['qty']
                placed = False
                for i, cutoff in enumerate(cutoffs):
                    if age <= cutoff:
                        drilldown_buckets[labels[i]] += qty
                        placed = True
                        break
                if not placed:
                    drilldown_buckets[labels[-1]] += qty
                    
            # Draw Drilldown Matrix
            viz1, viz2 = st.columns([2, 1])
            
            with viz1:
                st.markdown(f"**Age Distribution on {selected_date}**")
                
                # Colors: first bucket gets standard blue, aging stock gets a muted gray-blue
                bar_colors = ['#1f77b4'] + ['#b0c4de'] * (len(labels) - 1)
                
                fig_bar = go.Figure(go.Bar(
                    x=list(drilldown_buckets.keys()), 
                    y=list(drilldown_buckets.values()), 
                    name="Actuals",
                    marker_color=bar_colors
                ))
                fig_bar.update_layout(yaxis_title="Units", margin=dict(l=0, r=0, t=30, b=0), height=380)
                st.plotly_chart(style_plotly_fig(fig_bar), use_container_width=True)
                
            with viz2:
                st.markdown("**Exact Stock Counts:**")
                tbl_df = pd.DataFrame({
                    "Age Bracket": list(drilldown_buckets.keys()),
                    "Historical Actuals (Units)": [int(v) for v in drilldown_buckets.values()]
                })
                st.dataframe(tbl_df, use_container_width=True, hide_index=True)

        # =====================================================================
        # BATCH-LEVEL AGING & PRE-SALE ANALYSIS
        # =====================================================================
        st.divider()
        st.subheader("📦 Batch-Level Aging & Lifecycle Analysis")
        st.write("Inspect individual inventory batches to track exactly how long they sit before the first sale, and how long they take to fully deplete.")
        
        batch_inspect_date = st.date_input(
            "Select Date for Batch Analysis", 
            value=max_date, 
            min_value=min_date, 
            max_value=max_date, 
            key="batch_inspector_date"
        )
        
        batch_inspect_ts = pd.Timestamp(batch_inspect_date)
        df_batch_sim = df[df[time_col] <= batch_inspect_ts].copy()
        
        all_batches = []
        
        # Safely handle opening balance
        if not pd.isna(df_batch_sim.loc[0, open_bal_col]) and df_batch_sim.loc[0, open_bal_col] > 0:
            all_batches.append({
                'receive_date': df_batch_sim.loc[0, time_col], 
                'original_qty': df_batch_sim.loc[0, open_bal_col], 
                'remaining_qty': df_batch_sim.loc[0, open_bal_col],
                'first_sale_date': pd.NaT,
                'last_sale_date': pd.NaT
            })
            
        active_batch_idx = 0 
        
        # Run isolated FIFO up to the selected date
        for idx, row in df_batch_sim.iterrows():
            current_date = row[time_col]
            demand = row[demand_col]
            received = row[receiving_col]
            
            if received > 0:
                all_batches.append({
                    'receive_date': current_date,
                    'original_qty': received,
                    'remaining_qty': received,
                    'first_sale_date': pd.NaT,
                    'last_sale_date': pd.NaT
                })
                
            # Deduct demand (FIFO)
            while demand > 0 and active_batch_idx < len(all_batches):
                b = all_batches[active_batch_idx]
                
                if b['remaining_qty'] > 0:
                    if pd.isna(b['first_sale_date']):
                        b['first_sale_date'] = current_date
                        
                    if b['remaining_qty'] <= demand:
                        demand -= b['remaining_qty']
                        b['remaining_qty'] = 0
                        b['last_sale_date'] = current_date  # Mark depletion date
                        active_batch_idx += 1 
                    else:
                        b['remaining_qty'] -= demand
                        demand = 0
                else:
                    active_batch_idx += 1
                    
        # Split results into Active vs Depleted tables
        active_records = []
        depleted_records = []
        
        for b in all_batches:
            if b['remaining_qty'] > 0:
                # Calculate metrics for Active Inventory
                curr_age = (batch_inspect_ts - b['receive_date']).days
                first_sale_str = b['first_sale_date'].strftime('%Y-%m-%d') if not pd.isna(b['first_sale_date']) else "Not Yet Sold"
                pre_sale_age = (b['first_sale_date'] - b['receive_date']).days if not pd.isna(b['first_sale_date']) else None
                
                active_records.append({
                    "Receipt Date": b['receive_date'].strftime('%Y-%m-%d'),
                    "Original Qty": int(b['original_qty']),
                    "Remaining Qty": int(b['remaining_qty']),
                    "Current Age (Days)": curr_age,
                    "First Sale Date": first_sale_str,
                    "Pre-Sale Age (Days)": pre_sale_age
                })
            else:
                # Calculate metrics for Depleted Inventory
                first_sale_str = b['first_sale_date'].strftime('%Y-%m-%d') if not pd.isna(b['first_sale_date']) else "N/A"
                last_sale_str = b['last_sale_date'].strftime('%Y-%m-%d') if not pd.isna(b['last_sale_date']) else "N/A"
                pre_sale_age = (b['first_sale_date'] - b['receive_date']).days if not pd.isna(b['first_sale_date']) else None
                age_at_depletion = (b['last_sale_date'] - b['receive_date']).days if not pd.isna(b['last_sale_date']) else None
                
                depleted_records.append({
                    "Receipt Date": b['receive_date'].strftime('%Y-%m-%d'),
                    "Original Qty": int(b['original_qty']),
                    "First Sale Date": first_sale_str,
                    "Depletion Date": last_sale_str,
                    "Pre-Sale Age (Days)": pre_sale_age,
                    "Age at Depletion (Days)": age_at_depletion
                })
                
        # Render the Tables
        st.markdown("#### 🟢 Active Batches (Current Stock)")
        if active_records:
            df_active = pd.DataFrame(active_records)
            st.dataframe(df_active.style.format({"Pre-Sale Age (Days)": "{:.0f}"}), use_container_width=True, hide_index=True)
        else:
            st.info(f"No active inventory batches remaining on {batch_inspect_date}.")
            
        st.markdown("#### ⚪ Depleted Batches (Historical Performance)")
        if depleted_records:
            df_depleted = pd.DataFrame(depleted_records)
            st.dataframe(df_depleted.style.format({"Pre-Sale Age (Days)": "{:.0f}", "Age at Depletion (Days)": "{:.0f}"}), use_container_width=True, hide_index=True)
        else:
            st.info(f"No fully depleted batches as of {batch_inspect_date}.")
                
    except Exception as e:
        st.error(f"Error processing the file: {e}")
