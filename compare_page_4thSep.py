import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# Updated styling function for a dark background
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117', 
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        title_font=dict(color='white'),
        legend=dict(
            font=dict(color='white'),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# ------------------------------------------------
# Sample Excel Generator
# ------------------------------------------------
def generate_sample_excel():
    df_sample = pd.DataFrame({
        "Date": ["2024-01-01", "2024-01-03", "2024-01-07", "2024-01-10", "2024-01-12"],
        "Closing Balance": [500, 439, 358, 600, 520]
    })
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_sample.to_excel(writer, index=False, sheet_name='Sample Data')
    return buffer.getvalue()

st.title("Historical vs Simulated Comparison")
st.write("Upload your historical inventory data. The system extracts exact daily demand, runs a simulation using your current policy parameters, and compares the outcomes.")

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
# File Upload & Demand Extraction
# ------------------------------------------------
uploaded_file = st.file_uploader("Upload Historical Data", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # Load Data
        if uploaded_file.name.endswith('.csv'):
            df_hist = pd.read_csv(uploaded_file)
        else:
            df_hist = pd.read_excel(uploaded_file)
            
        time_col = df_hist.columns[0]
        balance_col = df_hist.columns[1]
        
        # Handle gaps in dates/days
        is_numeric_index = pd.api.types.is_numeric_dtype(df_hist[time_col])
        if not is_numeric_index:
            df_hist[time_col] = pd.to_datetime(df_hist[time_col])
            
        df_hist = df_hist.sort_values(by=time_col)
        df_hist.set_index(time_col, inplace=True)
        
        if is_numeric_index:
            full_range = range(int(df_hist.index.min()), int(df_hist.index.max()) + 1)
        else:
            full_range = pd.date_range(start=df_hist.index.min(), end=df_hist.index.max())
        
        df_filled = df_hist.reindex(full_range).ffill()
        df_filled.reset_index(inplace=True)
        df_filled.rename(columns={'index': time_col}, inplace=True)
        
        # Extract daily demand by finding the day-over-day drop in closing balance
        df_filled['Previous Balance'] = df_filled[balance_col].shift(1)
        
        # If balance drops, the difference is demand. If it rises, it's a replenishment (demand = 0)
        df_filled['Derived Demand'] = np.where(
            df_filled['Previous Balance'] > df_filled[balance_col], 
            df_filled['Previous Balance'] - df_filled[balance_col], 
            0
        )
        df_filled['Derived Demand'] = df_filled['Derived Demand'].fillna(0)
        
        # ------------------------------------------------
        # Sidebar Inputs
        # ------------------------------------------------
        st.sidebar.header("Simulation Parameters")
        
        reorder_point = st.sidebar.number_input("Reorder Point", value=200)
        opening_balance = st.sidebar.number_input("Opening Balance", value=int(1.25 * reorder_point))
        lead_time = st.sidebar.number_input("Lead Time (Days)", value=3)
        order_qty = st.sidebar.number_input("Order Quantity", value=300)
        
        st.sidebar.subheader("Backorder Policy")
        max_wait_time = st.sidebar.number_input("Max Customer Wait Time (Days)", value=5, min_value=0, help="0 means no backorders allowed (instant lost sales).")
        
        st.sidebar.divider()
        include_pipeline = st.sidebar.checkbox("Include Pipeline Inventory in Chart", value=False)
        
        # ------------------------------------------------
        # Simulation Logic (Using Exact Historical Demand)
        # ------------------------------------------------
        num_days = len(df_filled)
        sim_demand = df_filled['Derived Demand'].values
        
        inventory = opening_balance
        pipeline_orders = []
        backorder_queue = [] 
        
        sim_phys_balances = []
        sim_net_balances = []
        sim_active_backorders = []
        sim_daily_lost_sales = []
        sim_closing_net_pipeline = []
        sim_new_orders = []
        
        total_demand_overall = 0
        total_lost_sales = 0
        
        for day in range(num_days):
            demand_today = sim_demand[day]
            total_demand_overall += demand_today
            daily_lost_sales = 0
            
            # 1. Expire unfulfilled backorders
            active_backorders = []
            for bo in backorder_queue:
                if (day - bo['day_created']) > max_wait_time:
                    daily_lost_sales += bo['qty']
                    total_lost_sales += bo['qty']
                else:
                    active_backorders.append(bo)
            backorder_queue = active_backorders

            # 2. Receive shipments
            shipment_received = 0
            for order in pipeline_orders.copy():
                if order[0] == day:
                    shipment_received += order[1]
                    pipeline_orders.remove(order)

            # 3. Fulfill existing backorders
            while shipment_received > 0 and backorder_queue:
                if shipment_received >= backorder_queue[0]['qty']:
                    shipment_received -= backorder_queue[0]['qty']
                    backorder_queue.pop(0)
                else:
                    backorder_queue[0]['qty'] -= shipment_received
                    shipment_received = 0

            inventory += shipment_received

            # 4. Process today's demand
            if inventory >= demand_today:
                inventory -= demand_today
            else:
                unmet = demand_today - inventory
                inventory = 0
                if max_wait_time > 0:
                    backorder_queue.append({'qty': unmet, 'day_created': day})
                else:
                    daily_lost_sales += unmet
                    total_lost_sales += unmet

            # Calculate Current Metrics
            current_backorders = sum(bo['qty'] for bo in backorder_queue)
            net_inventory = inventory - current_backorders
            pipeline_qty = sum(qty for arrival, qty in pipeline_orders)
            inventory_position = net_inventory + pipeline_qty

            # 5. Order Triggers
            new_order = 0
            if inventory_position < reorder_point:
                new_order = order_qty
                pipeline_orders.append((day + lead_time, order_qty))

            closing_net_with_pipeline = net_inventory + pipeline_qty

            sim_phys_balances.append(inventory)
            sim_net_balances.append(net_inventory)
            sim_active_backorders.append(current_backorders)
            sim_daily_lost_sales.append(daily_lost_sales)
            sim_closing_net_pipeline.append(closing_net_with_pipeline)
            sim_new_orders.append(new_order)
            
        df_filled['Physical Inventory'] = sim_phys_balances
        df_filled['Net Inventory'] = sim_net_balances
        df_filled['Active Backorders'] = sim_active_backorders
        df_filled['Daily Lost Sales'] = sim_daily_lost_sales
        df_filled['Closing Net Including Pipeline'] = sim_closing_net_pipeline
        df_filled['New Order'] = sim_new_orders
        
        # ------------------------------------------------
        # Output & Comparison KPIs
        # ------------------------------------------------
        st.subheader("Comparison & Performance KPIs")
        
        # --- Calculations ---
        avg_hist = df_filled[balance_col].mean()
        avg_sim_phys = df_filled['Physical Inventory'].mean()
        min_hist = df_filled[balance_col].min()
        max_hist = df_filled[balance_col].max()
        min_sim_net = df_filled['Net Inventory'].min()
        max_sim_net = df_filled['Net Inventory'].max()
        
        avg_demand = df_filled['Derived Demand'].mean()
        std_demand = df_filled['Derived Demand'].std()
        cov_demand = std_demand / avg_demand if avg_demand > 0 else 0
        min_demand = df_filled['Derived Demand'].min()
        max_demand = df_filled['Derived Demand'].max()
        
        stockout_days = (df_filled['Daily Lost Sales'] > 0).sum()
        avg_backorders = df_filled['Active Backorders'].mean()
        
        fill_rate = 100.0
        if total_demand_overall > 0:
            fill_rate = ((total_demand_overall - total_lost_sales) / total_demand_overall) * 100
        
        # --- Display Row 1: Averages & Performance ---
        st.markdown("**Averages & Performance**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Historical Avg Inventory", round(avg_hist, 0))
        
        diff = avg_sim_phys - avg_hist
        c2.metric("Simulated Avg Physical Inventory", round(avg_sim_phys, 0), delta=round(diff, 0), delta_color="inverse")
        
        c3.metric("Lost Sale Days (Stockouts)", stockout_days)
        c4.metric("Simulated Fill Rate", f"{round(fill_rate, 2)}%")
        
        # --- Display Row 2: Inventory Ranges ---
        st.markdown("**Inventory Ranges & Backorders**")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Historical Min Balance", round(min_hist, 0))
        r2.metric("Historical Max Balance", round(max_hist, 0))
        r3.metric("Simulated Min Net Inventory", round(min_sim_net, 0))
        r4.metric("Avg Active Backorders", round(avg_backorders, 1))

        # --- Display Row 3: Demand Statistics ---
        st.markdown("**Historical Demand Statistics**")
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Avg Daily Demand", round(avg_demand, 1))
        d2.metric("Demand Std Dev", round(std_demand, 1))
        d3.metric("CoV", round(cov_demand, 2))
        d4.metric("Min Daily Demand", round(min_demand, 0))
        d5.metric("Max Daily Demand", round(max_demand, 0))
        
        st.divider()

        # ------------------------------------------------
        # Data Visualizations
        # ------------------------------------------------
        st.subheader("Inventory & Demand Behaviour")

        st.markdown("### Physical Inventory vs Historical")
        # Graph 1: Physical Inventory
        fig1 = go.Figure()
        
        fig1.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled[balance_col], mode="lines", name="Historical Balance", line=dict(color="gray", width=2, dash="dash")))
        fig1.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled["Physical Inventory"], name="Simulated Physical Inventory", line=dict(color='skyblue', width=2)))

        reorders = df_filled[df_filled["New Order"] > 0]
        fig1.add_trace(go.Scatter(x=reorders[time_col], y=reorders["Physical Inventory"], mode="markers", name="Reorder Trigger", marker=dict(color="green", symbol="triangle-up", size=10)))

        actual_stockouts = df_filled[df_filled["Daily Lost Sales"] > 0]
        fig1.add_trace(go.Scatter(x=actual_stockouts[time_col], y=actual_stockouts["Physical Inventory"], mode="markers", name="Lost Sale (Stockout)", marker=dict(color="red", symbol="triangle-up", size=10)))

        fig1.add_hline(y=reorder_point, line_dash="dash", line_color="gray", annotation_text="Reorder Point", annotation_font_color="white")

        max_y = max(df_filled["Physical Inventory"].max(), df_filled[balance_col].max()) * 1.2
        fig1.add_hrect(y0=0, y1=reorder_point*0.5, fillcolor="red", opacity=0.1)
        fig1.add_hrect(y0=reorder_point*0.5, y1=reorder_point, fillcolor="yellow", opacity=0.1)
        fig1.add_hrect(y0=reorder_point, y1=max_y, fillcolor="green", opacity=0.05)

        fig1 = style_plotly_fig(fig1)
        st.plotly_chart(fig1, use_container_width=True)

        st.divider()

        st.markdown("### Net Inventory vs Historical")
        # Graph 2: Net Inventory 
        fig2 = go.Figure()
        
        fig2.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled[balance_col], mode="lines", name="Historical Balance", line=dict(color="gray", width=2, dash="dash")))
        fig2.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled["Net Inventory"], name="Net Inventory (Includes Backorders)", line=dict(color='orange', width=2)))

        if include_pipeline:
            fig2.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled["Closing Net Including Pipeline"], name="Inventory Position", line=dict(color='#1f77b4', width=2)))

        fig2.add_trace(go.Scatter(x=reorders[time_col], y=reorders["Net Inventory"], mode="markers", name="Reorder Trigger", marker=dict(color="green", symbol="triangle-up", size=10)))
        fig2.add_trace(go.Scatter(x=actual_stockouts[time_col], y=actual_stockouts["Net Inventory"], mode="markers", name="Lost Sale (Stockout)", marker=dict(color="red", symbol="triangle-up", size=10)))
            
        fig2.add_hline(y=reorder_point, line_dash="dash", line_color="gray", annotation_text="Reorder Point", annotation_font_color="white")
        fig2.add_hline(y=0, line_color="red", line_width=1) 

        fig2 = style_plotly_fig(fig2)
        fig2.update_yaxes(rangemode="normal") 
        st.plotly_chart(fig2, use_container_width=True)

        st.divider()

        st.markdown("### Lost Sales (Stockouts)")
        # Graph 3: Lost Sales
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled["Daily Lost Sales"], name="Lost Sales Qty", line=dict(color='red', width=2), fill='tozeroy', fillcolor='rgba(255,0,0,0.1)'))
        fig3 = style_plotly_fig(fig3)
        st.plotly_chart(fig3, use_container_width=True)

        st.divider()

        st.markdown("### Active Backorders")
        # Graph 4: Active Backorders
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=df_filled[time_col], y=df_filled["Active Backorders"], name="Active Backorders", line=dict(color='#ffaa00', width=2), fill='tozeroy', fillcolor='rgba(255,170,0,0.1)'))
        fig4 = style_plotly_fig(fig4)
        st.plotly_chart(fig4, use_container_width=True)

        # ------------------------------------------------
        # Data Tables
        # ------------------------------------------------
        st.divider()
        st.subheader("Historical Data")
        st.dataframe(df_filled[[time_col, balance_col, 'Derived Demand']], use_container_width=True)
        
        st.subheader("Simulated Data")
        st.dataframe(df_filled[[
            time_col, 'Derived Demand', 'Physical Inventory', 'Net Inventory', 
            'Active Backorders', 'Daily Lost Sales'
        ]], use_container_width=True)
        
    except Exception as e:
        st.error(f"Error processing file: {e}")
