import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import norm

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
                
                # New calculation: age of the remaining inventory from the first time it was sold
                age_from_first_sale = (batch_inspect_ts - b['first_sale_date']).days if not pd.isna(b['first_sale_date']) else None
                
                active_records.append({
                    "Receipt Date": b['receive_date'].strftime('%Y-%m-%d'),
                    "Original Qty": int(b['original_qty']),
                    "Remaining Qty": int(b['remaining_qty']),
                    "Current Age (Days)": curr_age,
                    "First Sale Date": first_sale_str,
                    "Pre-Sale Age (Days)": pre_sale_age,
                    "Age from First Sale (Days)": age_from_first_sale
                })
            else:
                # Calculate metrics for Depleted Inventory
                first_sale_str = b['first_sale_date'].strftime('%Y-%m-%d') if not pd.isna(b['first_sale_date']) else "N/A"
                last_sale_str = b['last_sale_date'].strftime('%Y-%m-%d') if not pd.isna(b['last_sale_date']) else "N/A"
                pre_sale_age = (b['first_sale_date'] - b['receive_date']).days if not pd.isna(b['first_sale_date']) else None
                age_at_depletion = (b['last_sale_date'] - b['receive_date']).days if not pd.isna(b['last_sale_date']) else None
                
                # Calculate days from first sale to last sale
                time_to_sell = (b['last_sale_date'] - b['first_sale_date']).days if not pd.isna(b['first_sale_date']) and not pd.isna(b['last_sale_date']) else None
                
                depleted_records.append({
                    "Receipt Date": b['receive_date'].strftime('%Y-%m-%d'),
                    "Original Qty": int(b['original_qty']),
                    "First Sale Date": first_sale_str,
                    "Depletion Date": last_sale_str,
                    "Pre-Sale Age (Days)": pre_sale_age,
                    "Age at Depletion (Days)": age_at_depletion,
                    "Time to Sell (Days)": time_to_sell
                })
                
        # Render the Tables
        st.markdown("#### 🟢 Active Batches (Current Stock)")
        if active_records:
            df_active = pd.DataFrame(active_records)
            st.dataframe(
                df_active.style.format({
                    "Pre-Sale Age (Days)": "{:.0f}",
                    "Age from First Sale (Days)": "{:.0f}"
                }), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info(f"No active inventory batches remaining on {batch_inspect_date}.")
        st.markdown("#### ⚪ Depleted Batches (Historical Performance)")
        if depleted_records:
            df_depleted = pd.DataFrame(depleted_records)
            st.dataframe(
                df_depleted.style.format({
                    "Pre-Sale Age (Days)": "{:.0f}", 
                    "Age at Depletion (Days)": "{:.0f}",
                    "Time to Sell (Days)": "{:.0f}"
                }), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info(f"No fully depleted batches as of {batch_inspect_date}.")

        # =====================================================================
        # PROBABILISTIC VELOCITY ANALYSIS (ACTUAL VS MINIMUM EXPECTED)
        # =====================================================================
        st.divider()
        st.subheader("⚡ Probabilistic Velocity Risk")
        st.write("Compare actual batch depletion against a probabilistic minimum sales threshold to immediately flag stock moving slower than the worst-case statistical expectation.")
        
        # Derive historical demand metrics
        vel_avg_demand = df[demand_col].mean()
        vel_std_demand = df[demand_col].std()
        if pd.isna(vel_std_demand):
            vel_std_demand = 0.0
            
        vel_cov = vel_std_demand / vel_avg_demand if vel_avg_demand > 0 else 0

        st.markdown("##### Configuration & Confidence Levels")
        vc1, vc2, vc3, vc4, vc5 = st.columns(5)
        with vc1:
            st.metric("Historical Avg Demand", f"{vel_avg_demand:.2f}")
        with vc2:
            st.metric("Historical Std Dev", f"{vel_std_demand:.2f}")
        with vc3:
            st.metric("CoV", f"{vel_cov:.2f}")
        with vc4:
            vel_conf_min = st.number_input("Min SL (Worst Case %)", min_value=50.0, max_value=99.9, value=95.0, step=0.1, key="vel_min")
        with vc5:
            vel_conf_max = st.number_input("Max SL (Best Case %)", min_value=50.0, max_value=99.9, value=75.0, step=0.1, key="vel_max")
            
        z_min = norm.ppf(vel_conf_min / 100.0)
        z_max = norm.ppf(vel_conf_max / 100.0)
        z_mid = 0.0 # 50% Confidence
        
        # --- Pre-compute Minimum Expected Sales Lookup Tables ---
        max_possible_age = len(df) + 10 # Buffer for age lookups
        hist_exp_min, hist_exp_mid, hist_exp_max = {0: 0}, {0: 0}, {0: 0}
        historical_demand_array = df[demand_col].values
        
        if vel_cov > 0.5 and vel_avg_demand > 0:
            st.caption("🤖 **Auto-Selected Model:** Empirical Bootstrapping (Historical CoV > 0.5 indicates volatile/lumpy demand)")
            np.random.seed(42)
            for t in range(1, max_possible_age + 1):
                samples = np.random.choice(historical_demand_array, size=(1000, t), replace=True)
                sums = samples.sum(axis=1)
                hist_exp_min[t] = max(0, np.percentile(sums, 100 - vel_conf_min))
                hist_exp_mid[t] = max(0, np.percentile(sums, 50))
                hist_exp_max[t] = max(0, np.percentile(sums, 100 - vel_conf_max))
        else:
            st.caption("🤖 **Auto-Selected Model:** Normal Distribution (Historical CoV <= 0.5 indicates stable demand)")
            for t in range(1, max_possible_age + 1):
                hist_exp_min[t] = max(0, (vel_avg_demand * t) - (z_min * vel_std_demand * np.sqrt(t)))
                hist_exp_mid[t] = max(0, (vel_avg_demand * t) - (z_mid * vel_std_demand * np.sqrt(t)))
                hist_exp_max[t] = max(0, (vel_avg_demand * t) - (z_max * vel_std_demand * np.sqrt(t)))
                
        # Bind the minimum threshold to the variable used in Part A's snapshot table
        hist_min_expected = hist_exp_min
        
        # ---------------------------------------------------------
        # PART A: POINT-IN-TIME VELOCITY SNAPSHOT
        # ---------------------------------------------------------
        st.markdown("#### Point-in-Time Velocity Snapshot")
        vel_snapshot_date = st.date_input(
            "Select Date for Velocity Snapshot", 
            value=max_date, 
            min_value=min_date, 
            max_value=max_date, 
            key="vel_snap_date"
        )
        vel_snapshot_ts = pd.Timestamp(vel_snapshot_date)

        # Run lightweight FIFO up to the selected snapshot date
        df_vel_sim = df[df[time_col] <= vel_snapshot_ts].copy()
        
        vel_batches = []
        if not pd.isna(df_vel_sim.loc[0, open_bal_col]) and df_vel_sim.loc[0, open_bal_col] > 0:
            vel_batches.append({
                'receive_date': df_vel_sim.loc[0, time_col], 
                'original_qty': df_vel_sim.loc[0, open_bal_col], 
                'remaining_qty': df_vel_sim.loc[0, open_bal_col],
                'first_sale_date': pd.NaT
            })
            
        active_vel_idx = 0 
        for idx, row in df_vel_sim.iterrows():
            current_date = row[time_col]
            demand = row[demand_col]
            received = row[receiving_col]
            
            if received > 0:
                vel_batches.append({
                    'receive_date': current_date,
                    'original_qty': received,
                    'remaining_qty': received,
                    'first_sale_date': pd.NaT
                })
                
            while demand > 0 and active_vel_idx < len(vel_batches):
                b = vel_batches[active_vel_idx]
                if b['remaining_qty'] > 0:
                    if pd.isna(b['first_sale_date']):
                        b['first_sale_date'] = current_date
                        
                    if b['remaining_qty'] <= demand:
                        demand -= b['remaining_qty']
                        b['remaining_qty'] = 0
                        active_vel_idx += 1 
                    else:
                        b['remaining_qty'] -= demand
                        demand = 0
                else:
                    active_vel_idx += 1

        active_vel_records = []
        for b in vel_batches:
            if b['remaining_qty'] > 0:
                age_receipt = (vel_snapshot_ts - b['receive_date']).days
                age_sale = (vel_snapshot_ts - b['first_sale_date']).days if not pd.isna(b['first_sale_date']) else None
                actual_sales = b["original_qty"] - b["remaining_qty"]
                
                # Velocity from Receipt Date
                if age_receipt > 0:
                    min_sales_receipt = hist_min_expected.get(age_receipt, 0)
                    ratio_receipt = actual_sales / min_sales_receipt if min_sales_receipt > 0 else (float('inf') if actual_sales > 0 else 0)
                else:
                    min_sales_receipt = 0
                    ratio_receipt = 0
                    
                # Velocity from First Sale Date
                if age_sale is not None and age_sale > 0:
                    min_sales_first = hist_min_expected.get(age_sale, 0)
                    ratio_first = actual_sales / min_sales_first if min_sales_first > 0 else (float('inf') if actual_sales > 0 else 0)
                else:
                    min_sales_first = 0
                    ratio_first = None

                active_vel_records.append({
                    "Receipt Date": b['receive_date'].strftime('%Y-%m-%d'),
                    "Days Since Receipt": age_receipt,
                    "Days Since 1st Sale": age_sale,
                    "Remaining Qty": int(b['remaining_qty']),
                    "Actual Sales": int(actual_sales),
                    "Min Expected (Since Receipt)": min_sales_receipt,
                    "Velocity Ratio (Receipt)": ratio_receipt,
                    "Min Expected (Since 1st Sale)": min_sales_first,
                    "Velocity Ratio (1st Sale)": ratio_first
                })

        if active_vel_records:
            df_vel = pd.DataFrame(active_vel_records)
            
            def highlight_risk(val):
                if pd.isna(val) or val == float('inf'):
                    return ''
                if isinstance(val, (int, float)):
                    if val < 1.0:
                        return 'background-color: rgba(255, 75, 75, 0.2)' 
                    else:
                        return 'background-color: rgba(44, 160, 44, 0.2)'
                return ''

            styled_df = df_vel.style.map(highlight_risk, subset=["Velocity Ratio (Receipt)"]).format({
                "Days Since Receipt": "{:.0f}",
                "Days Since 1st Sale": lambda x: f"{x:.0f}" if pd.notnull(x) else "N/A",
                "Min Expected (Since Receipt)": "{:.0f}",
                "Velocity Ratio (Receipt)": "{:.2f}x",
                "Min Expected (Since 1st Sale)": "{:.0f}",
                "Velocity Ratio (1st Sale)": lambda x: f"{x:.2f}x" if pd.notnull(x) else "N/A"
            })
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No active batches available on {vel_snapshot_date} to calculate velocity.")

        
        # ---------------------------------------------------------
        # PART B: INDIVIDUAL BATCH VELOCITY TRAJECTORY
        # ---------------------------------------------------------
        st.divider()
        st.markdown("#### 📈 Batch Velocity Trajectory")
        st.write("Track the cumulative sales trajectory of a specific batch compared to its minimum expected risk threshold.")
        
        # Run a full simulation to track the daily history of EVERY batch for the graph
        all_sim_batches = []
        batch_counter = 1
        batch_trajectories = {}
        
        sim_active_idx = 0
        
        if not pd.isna(df.loc[0, open_bal_col]) and df.loc[0, open_bal_col] > 0:
            b_id = f"Batch {batch_counter} - {df.loc[0, time_col].strftime('%Y-%m-%d')} (Opening Qty: {df.loc[0, open_bal_col]:.0f})"
            b_dict = {'id': b_id, 'receive_date': df.loc[0, time_col], 'original_qty': df.loc[0, open_bal_col], 'remaining_qty': df.loc[0, open_bal_col], 'first_sale_date': pd.NaT}
            all_sim_batches.append(b_dict)
            batch_trajectories[b_id] = {"receipt_date": df.loc[0, time_col], "original_qty": df.loc[0, open_bal_col], "history": []}
            batch_counter += 1
            
        for idx, row in df.iterrows():
            current_date = row[time_col]
            demand = row[demand_col]
            received = row[receiving_col]
            
            if received > 0:
                b_id = f"Batch {batch_counter} - {current_date.strftime('%Y-%m-%d')} (Receipt Qty: {received:.0f})"
                b_dict = {'id': b_id, 'receive_date': current_date, 'original_qty': received, 'remaining_qty': received, 'first_sale_date': pd.NaT}
                all_sim_batches.append(b_dict)
                batch_trajectories[b_id] = {"receipt_date": current_date, "original_qty": received, "history": []}
                batch_counter += 1
                
            while demand > 0 and sim_active_idx < len(all_sim_batches):
                b = all_sim_batches[sim_active_idx]
                if b['remaining_qty'] > 0:
                    if pd.isna(b['first_sale_date']):
                        b['first_sale_date'] = current_date
                        
                    if b['remaining_qty'] <= demand:
                        demand -= b['remaining_qty']
                        b['remaining_qty'] = 0
                        sim_active_idx += 1
                    else:
                        b['remaining_qty'] -= demand
                        demand = 0
                else:
                    sim_active_idx += 1
                    
            for b in all_sim_batches:
                if len(batch_trajectories[b['id']]['history']) > 0 and batch_trajectories[b['id']]['history'][-1]['remaining_qty'] == 0:
                    continue 
                batch_trajectories[b['id']]['history'].append({
                    'date': current_date,
                    'remaining_qty': b['remaining_qty'],
                    'first_sale_date': b['first_sale_date']
                })
                
        if batch_trajectories:
            selected_batch_id = st.selectbox("Select a Batch to Inspect", list(batch_trajectories.keys()))
            
            traj = batch_trajectories[selected_batch_id]
            dates, actuals = [], []
            
            # Data containers for both timelines
            exp_rec_min, exp_rec_mid, exp_rec_max = [], [], []
            exp_fs_min, exp_fs_mid, exp_fs_max = [], [], []
            
            for h in traj['history']:
                d = h['date']
                rem = h['remaining_qty']
                fs_date = h['first_sale_date']
                
                age_receipt = (d - traj['receipt_date']).days
                age_sale = (d - fs_date).days if not pd.isna(fs_date) else 0
                act_sale = traj['original_qty'] - rem
                
                dates.append(d)
                actuals.append(act_sale)
                
                # Append Receipt Timeline Lookups
                exp_rec_min.append(hist_exp_min.get(age_receipt, 0) if age_receipt > 0 else 0)
                exp_rec_mid.append(hist_exp_mid.get(age_receipt, 0) if age_receipt > 0 else 0)
                exp_rec_max.append(hist_exp_max.get(age_receipt, 0) if age_receipt > 0 else 0)
                
                # Append First Sale Timeline Lookups
                exp_fs_min.append(hist_exp_min.get(age_sale, 0) if not pd.isna(fs_date) and age_sale > 0 else 0)
                exp_fs_mid.append(hist_exp_mid.get(age_sale, 0) if not pd.isna(fs_date) and age_sale > 0 else 0)
                exp_fs_max.append(hist_exp_max.get(age_sale, 0) if not pd.isna(fs_date) and age_sale > 0 else 0)
                
            # Helper function to standardize the zoned plotting logic
            def create_zoned_fig(title, dates_list, actuals_list, e_min, e_mid, e_max):
                fig = go.Figure()
                
                # 1. Min Threshold Line (Start of Red Zone)
                fig.add_trace(go.Scatter(x=dates_list, y=e_min, mode='lines', name=f'Min SL ({vel_conf_min}%)', line=dict(color='rgba(255, 75, 75, 0.8)', width=1)))
                
                # 2. Mid Threshold Line (Fills down to Min in Red)
                fig.add_trace(go.Scatter(x=dates_list, y=e_mid, mode='lines', name='Avg SL (50%)', fill='tonexty', fillcolor='rgba(255, 75, 75, 0.2)', line=dict(color='rgba(255, 200, 0, 0.8)', width=2, dash='dot')))
                
                # 3. Max Threshold Line (Fills down to Mid in Green)
                fig.add_trace(go.Scatter(x=dates_list, y=e_max, mode='lines', name=f'Max SL ({vel_conf_max}%)', fill='tonexty', fillcolor='rgba(44, 160, 44, 0.2)', line=dict(color='rgba(44, 160, 44, 0.8)', width=1)))
                
                # 4. Actual Sales Line
                fig.add_trace(go.Scatter(x=dates_list, y=actuals_list, mode='lines', name='Actual Cumulative Sales', line=dict(color='#ffffff', width=3)))
                
                fig.update_layout(
                    title=title,
                    xaxis_title="Date",
                    yaxis_title="Cumulative Units Sold",
                    hovermode='x unified',
                    # Push legend to the absolute bottom and drastically increase top margin
                    margin=dict(l=20, r=20, t=80, b=80), 
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5) 
                )
                return style_plotly_fig(fig)

            # --- Render Bifurcated Tabs ---
            tab_rec, tab_fs = st.tabs(["Trajectory (Since Receipt)", "Trajectory (Since 1st Sale)"])
            
            with tab_rec:
                fig_rec = create_zoned_fig(f"Since Receipt: {selected_batch_id}", dates, actuals, exp_rec_min, exp_rec_mid, exp_rec_max)
                st.plotly_chart(fig_rec, use_container_width=True)
                
            with tab_fs:
                fig_fs = create_zoned_fig(f"Since 1st Sale: {selected_batch_id}", dates, actuals, exp_fs_min, exp_fs_mid, exp_fs_max)
                st.plotly_chart(fig_fs, use_container_width=True)
            
            st.markdown("##### Trajectory Data Table")
            df_traj = pd.DataFrame({
                "Date": [d.strftime('%Y-%m-%d') for d in dates],
                "Actual Cumulative Sales": [int(x) for x in actuals],
                "Min Expected (Receipt)": [int(x) for x in exp_rec_min],
                "Avg Expected (Receipt)": [int(x) for x in exp_rec_mid],
                "Min Expected (1st Sale)": [int(x) for x in exp_fs_min],
                "Avg Expected (1st Sale)": [int(x) for x in exp_fs_mid]
            })
            st.dataframe(df_traj, use_container_width=True, hide_index=True)

        
        # ---------------------------------------------------------
        # PART C: BATCH VELOCITY TRAJECTORY (FORECASTED DEMAND)
        # ---------------------------------------------------------
        st.divider()
        st.markdown("#### 🔮 Batch Velocity Trajectory (Forecasted Demand)")
        st.write("Evaluate batch performance against a custom forecasted demand distribution, dynamically scaled against historical volatility.")
        
        fc1, fc2 = st.columns(2)
        with fc1:
            forecast_avg_input = st.number_input("Forecasted Expected Demand", min_value=1.0, value=100.0, key="fc_avg")
        with fc2:
            forecast_duration = st.number_input("Duration for Forecast (Days)", min_value=1, value=30, key="fc_dur")
            
        fc_daily_avg = forecast_avg_input / forecast_duration
        fc_daily_std = fc_daily_avg * vel_cov # Scale std dev based on historical variation to maintain CoV
        
        st.info(f"Scaled Daily Forecast Avg: **{fc_daily_avg:.2f} Units** | Scaled Daily Std Dev: **{fc_daily_std:.2f} Units**")
        
        # --- Pre-compute Forecasted Minimum Expected Sales Lookup ---
        fc_min_expected = {0: 0}
        
        if vel_cov > 0.5 and vel_avg_demand > 0:
            np.random.seed(42)
            scaling_factor = fc_daily_avg / vel_avg_demand
            for t in range(1, max_possible_age + 1):
                samples = np.random.choice(historical_demand_array, size=(1000, t), replace=True)
                sums = samples.sum(axis=1) * scaling_factor
                fc_min_expected[t] = max(0, np.percentile(sums, 100 - vel_conf_level))
        else:
            for t in range(1, max_possible_age + 1):
                fc_min_expected[t] = max(0, (fc_daily_avg * t) - (z_score_vel * fc_daily_std * np.sqrt(t)))
                
        if batch_trajectories:
            selected_fc_batch_id = st.selectbox("Select a Batch to Inspect (Forecasted)", list(batch_trajectories.keys()), key="fc_batch_sel")
            
            traj_fc = batch_trajectories[selected_fc_batch_id]
            dates_fc = []
            actuals_fc = []
            exp_rec_fc = []
            exp_first_fc = []
            
            for h in traj_fc['history']:
                d = h['date']
                rem = h['remaining_qty']
                fs_date = h['first_sale_date']
                
                age_receipt = (d - traj_fc['receipt_date']).days
                age_sale = (d - fs_date).days if not pd.isna(fs_date) else 0
                
                act_sale = traj_fc['original_qty'] - rem
                
                e_rec = fc_min_expected.get(age_receipt, 0) if age_receipt > 0 else 0
                e_first = fc_min_expected.get(age_sale, 0) if not pd.isna(fs_date) and age_sale > 0 else 0
                    
                dates_fc.append(d)
                actuals_fc.append(act_sale)
                exp_rec_fc.append(e_rec)
                exp_first_fc.append(e_first)
                
            fig_fc = go.Figure()
            
            fig_fc.add_trace(go.Scatter(
                x=dates_fc, y=exp_rec_fc, 
                mode='lines', 
                name='Forecast Min Expected (Since Receipt)', 
                line=dict(color='#ff9999', width=2, dash='dot')
            ))
            
            fig_fc.add_trace(go.Scatter(
                x=dates_fc, y=exp_first_fc, 
                mode='lines', 
                name='Forecast Min Expected (Since 1st Sale)', 
                line=dict(color='#ff4b4b', width=2, dash='dash')
            ))
            
            fig_fc.add_trace(go.Scatter(
                x=dates_fc, y=actuals_fc, 
                mode='lines', 
                name='Actual Cumulative Sales', 
                line=dict(color='#2ca02c', width=4)
            ))
            
            fig_fc.update_layout(
                title=f"Forecasted Sales Trajectory: {selected_fc_batch_id}",
                xaxis_title="Date",
                yaxis_title="Cumulative Units Sold",
                hovermode='x unified',
                margin=dict(l=20, r=20, t=50, b=20)
            )
            
            st.plotly_chart(style_plotly_fig(fig_fc), use_container_width=True)
            
            st.markdown("##### Forecasted Trajectory Data Table")
            df_traj_fc = pd.DataFrame({
                "Date": [d.strftime('%Y-%m-%d') for d in dates_fc],
                "Actual Cumulative Sales": [int(x) for x in actuals_fc],
                "Forecast Min Expected (Since Receipt)": [int(x) for x in exp_rec_fc],
                "Forecast Min Expected (Since 1st Sale)": [int(x) for x in exp_first_fc]
            })
            st.dataframe(df_traj_fc, use_container_width=True, hide_index=True)
                
    except Exception as e:
        st.error(f"Error processing the file: {e}")
