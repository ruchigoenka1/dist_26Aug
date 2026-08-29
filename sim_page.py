import streamlit as st
import pandas as pd
import numpy as np
from scipy.optimize import differential_evolution
import plotly.graph_objects as go
import io
import mealpy
from mealpy.swarm_based.PSO import OriginalPSO

# --- 1. PAGE SETUP & STYLING ---
st.set_page_config(page_title="AI Inventory Auditor Pro", layout="wide", initial_sidebar_state="expanded")

# Minimalist, professional UI with white backgrounds for clarity
st.markdown("""
    <style>
    .main {
        background-color: #FFFFFF;
        padding: 2rem 3rem;
    }
    div[data-testid="metric-container"] {
        border: 1px solid #1E90FF;
        border-radius: 6px;
        padding: 15px;
        background-color: #F8FBFF;
    }
    [data-testid="stDataFrame"] {
        border-radius: 6px;
        overflow: hidden;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. CORE HISTORICAL SIMULATION ENGINE ---
@st.cache_data
def extract_demand_data(file_bytes):
    df = pd.read_excel(file_bytes, sheet_name=0)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').reset_index(drop=True)
    
    if 'Demand/Sales' in df.columns:
        demands = df['Demand/Sales'].fillna(0).values
        dates_list = df['Date'].values
    elif 'Demand' in df.columns:
        demands = df['Demand'].fillna(0).values
        dates_list = df['Date'].values
    else:
        start_date = df['Date'].iloc[0]
        end_date = df['Date'].iloc[-1]
        date_range = pd.date_range(start=start_date, end=end_date)
        df_reindexed = df.set_index('Date').reindex(date_range)
        df_reindexed['Closing Balance'] = df_reindexed['Closing Balance'].ffill()
        daily_diff = df_reindexed['Closing Balance'].diff().fillna(0)
        demands = np.where(daily_diff < 0, -daily_diff, 0)
        dates_list = date_range.values

    return demands, dates_list, np.mean(demands), np.std(demands)

def run_historical_simulation(Q, rop, demands, lead_time, backorder_days, opening_balance):
    sim_days = len(demands)
    L = int(lead_time)
    
    opening_bal = np.zeros(sim_days)
    closing_bal = np.zeros(sim_days)
    shipments_rec = np.zeros(sim_days)
    pipeline_orders = np.zeros(sim_days)
    inv_position = np.zeros(sim_days)
    new_orders = np.zeros(sim_days)
    backorders_arr = np.zeros(sim_days)
    lost_sales_arr = np.zeros(sim_days)
    unmet_demand_arr = np.zeros(sim_days)
    
    current_physical = opening_balance
    current_backorders = 0
    pipeline_schedule = np.zeros(sim_days + L + 1)
    curr_pipe = 0
    
    for i in range(sim_days):
        opening_bal[i] = current_physical
        
        arrived = pipeline_schedule[i]
        shipments_rec[i] = arrived
        current_physical += arrived
        if arrived > 0:
            curr_pipe -= arrived
            
        d = demands[i]
        
        avail = max(0, current_physical - current_backorders)
        unmet_today = max(0, d - avail)
        unmet_demand_arr[i] = unmet_today
        
        req = d + current_backorders
        if current_physical >= req:
            current_physical -= req
            current_backorders = 0
            lost_sales_arr[i] = 0
        else:
            shortfall = req - current_physical
            current_physical = 0
            if backorder_days == 0:
                lost_sales_arr[i] = shortfall
                current_backorders = 0
            else:
                current_backorders = shortfall
                lost_sales_arr[i] = 0
                
        closing_bal[i] = current_physical
        backorders_arr[i] = current_backorders
        
        pipeline_orders[i] = curr_pipe
        inv_position[i] = current_physical + curr_pipe - current_backorders
        
        if inv_position[i] <= rop:
            new_orders[i] = Q
            pipeline_schedule[i + L] += Q
            curr_pipe += Q
            
    return (opening_bal, closing_bal, shipments_rec, pipeline_orders, 
            inv_position, new_orders, backorders_arr, lost_sales_arr, unmet_demand_arr)

def optimize_inventory_fixed(demands_array, lead_time, backorder_days, S, H_percent, unit_cost, target_fill_rate, method, target_goal, opening_balance):
    D_annual = np.mean(demands_array) * 365
    
    def evaluate_cost_and_fr(Q, rop):
        _, closing_bal, _, _, _, _, _, _, unmet_demand_arr = run_historical_simulation(
            Q, rop, demands_array, lead_time, backorder_days, opening_balance
        )
        avg_inv = np.mean(closing_bal)
        wc = avg_inv * unit_cost
        
        sim_days = len(demands_array)
        annual_scaling = 365.0 / sim_days if sim_days > 0 else 1
        
        _, _, _, _, _, new_orders, _, _, _ = run_historical_simulation(
            Q, rop, demands_array, lead_time, backorder_days, opening_balance
        )
        orders_placed = np.count_nonzero(new_orders) * annual_scaling
        ops_cost = (orders_placed * S) + (avg_inv * H_percent * unit_cost)
        
        tot_d = np.sum(demands_array)
        fill_rate = 1.0 - (np.sum(unmet_demand_arr) / tot_d) if tot_d > 0 else 1.0
        
        cost_val = wc if target_goal == "Strictly Minimize Working Capital" else ops_cost
        return cost_val, fill_rate, avg_inv, orders_placed

    def objective(x):
        Q, rop = x[0], x[1]
        cost, fr, _, _ = evaluate_cost_and_fr(Q, rop)
        if fr < target_fill_rate:
            cost += 1e9 * (target_fill_rate - fr + 0.01)
        return cost

    bounds = [(1, max(2000, D_annual)), (0, max(2000, D_annual))]
    
    if method == "Particle Swarm (Mealpy)":
        problem_dict = {
            "bounds": mealpy.FloatVar(lb=[1, 0], ub=[bounds[0][1], bounds[1][1]]),
            "obj_func": objective,
            "minmax": "min",
        }
        model = OriginalPSO(epoch=30, pop_size=30)
        g_best = model.solve(problem_dict)
        best_Q, best_rop = g_best.solution
    else:
        res = differential_evolution(objective, bounds, seed=42, maxiter=30, popsize=10)
        best_Q, best_rop = res.x
        
    _, final_fr, avg_inv, orders_per_year = evaluate_cost_and_fr(best_Q, best_rop)
    return best_Q, best_rop, avg_inv, final_fr, orders_per_year


# --- 3. UI DASHBOARD & DATA FLOW ---
st.title("AI Inventory Auditor Pro: Capital Optimization")

st.sidebar.header("1. Engine & Data")
opt_method = st.sidebar.selectbox("Optimization Engine", [
    "Particle Swarm (Mealpy)", 
    "Differential Evolution (Scipy)"
])
uploaded_file = st.sidebar.file_uploader("Upload Data", type=["xlsx"])

st.sidebar.header("2. Core Parameters")
lead_time = st.sidebar.number_input("Lead Time (Days)", value=7, min_value=1)
backorder_days = st.sidebar.number_input("Backorder Days Allowed", value=0, min_value=0)
unit_cost = st.sidebar.number_input("Unit Cost ($)", value=50.0, min_value=0.1)
ordering_cost = st.sidebar.number_input("Ordering Cost / Setup ($)", value=100.0, min_value=0.0)
holding_cost_pct = st.sidebar.number_input("Annual Holding Cost (%)", value=0.20, min_value=0.01)
target_fr = st.sidebar.slider("Target Fill Rate", min_value=0.80, max_value=1.00, value=0.994, step=0.001, format="%.3f")

st.sidebar.header("3. Optimization Objective")
target_goal = st.sidebar.radio(
    "Select Objective",
    ["Minimize Total Ops Cost (EOQ)", "Strictly Minimize Working Capital"]
)

if uploaded_file is not None:
    file_bytes = io.BytesIO(uploaded_file.getvalue())
    demands_array, dates_array, D_daily, std_daily = extract_demand_data(file_bytes)
else:
    demands_array, dates_array, D_daily, std_daily = np.full(60, 27.75), pd.date_range("2024-01-01", periods=60), 27.75, 8.21  

st.sidebar.header("4. Simulation Control")
default_opening = int(D_daily * lead_time)
opening_balance = st.sidebar.number_input("Opening Balance (Units)", value=default_opening, min_value=0)

if uploaded_file is not None or st.sidebar.button("Run with Dummy Data"):
    
    Q, rop, avg_inv, sim_fill_rate, orders_per_year = optimize_inventory_fixed(
        demands_array, lead_time, backorder_days, ordering_cost, holding_cost_pct, unit_cost, target_fr, opt_method, target_goal, opening_balance
    )
    
    opening_bal, closing_bal, shipments_rec, pipeline_orders, inv_position, new_orders, backorders_arr, lost_sales_arr, unmet_demand_arr = run_historical_simulation(
        Q, rop, demands_array, lead_time, backorder_days, opening_balance
    )
    
    closing_inc_pipeline = closing_bal + pipeline_orders
    net_inventory = closing_bal - backorders_arr
    blocked_wc = closing_inc_pipeline * unit_cost
    sim_avg_wc = np.mean(closing_bal) * unit_cost
    total_annual_ops_cost = (orders_per_year * ordering_cost) + (avg_inv * (holding_cost_pct * unit_cost))
    
    # Build Table
    sim_df = pd.DataFrame({
        "Date": dates_array,
        "Opening Balance": np.round(opening_bal).astype(int),
        "Demand": np.round(demands_array).astype(int),
        "Shipment Received": np.round(shipments_rec).astype(int),
        "Pipeline Order": np.round(pipeline_orders).astype(int),
        "Inventory Position": np.round(inv_position).astype(int),
        "New Order": np.round(new_orders).astype(int),
        "Closing Balance (Physical)": np.round(closing_bal).astype(int),
        "Net Inventory": np.round(net_inventory).astype(int)
    })
    
    sim_df["Lost Sales (Stockout)"] = np.round(lost_sales_arr).astype(int)
    sim_df["Backorders"] = np.round(backorders_arr).astype(int)
    sim_df["Closing Balance Including Pipeline"] = np.round(closing_inc_pipeline).astype(int)
    sim_df["Blocked Working Capital"] = np.round(blocked_wc).astype(int)
    
    st.markdown("### Optimization Results")
    include_pipeline = st.checkbox("Include Pipeline Inventory in KPIs", value=False)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Optimal Order Qty (Q)", f"{int(Q)} Units")
    with col2:
        st.metric("Reorder Point (ROP)", f"{int(rop)} Units")
    with col3:
        st.metric("Orders Per Year", f"{int(orders_per_year):.0f} Orders")
    with col4:
        st.metric("Total Annual Ops Cost", f"${total_annual_ops_cost:,.0f}")
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        display_units = avg_inv + (D_daily * lead_time) if include_pipeline else avg_inv
        display_wc = (display_units * unit_cost)
        st.metric("Theoretical Total Working Capital", f"${display_wc:,.0f} ({int(display_units)} Units)")
    with col6:
        safety_stock_calc = max(0, rop - (D_daily * max(0, lead_time - backorder_days)))
        st.metric("Safety Stock", f"{int(safety_stock_calc)} Units")
    with col7:
        st.metric("Simulated Fill Rate", f"{sim_fill_rate:.2%}")
    with col8:
        st.metric("Simulated Avg Working Capital", f"${sim_avg_wc:,.0f}")
        
    st.markdown("---")

    # --- 4. VISUALIZATION SUITE ---
    st.markdown("### Inventory Analytics")
    
    # Grid Layout for Charts
    chart_col1, chart_col2 = st.columns(2)
    
    # Graph 1: Physical Inventory
    with chart_col1:
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=dates_array, y=closing_bal, mode='lines', name='Physical Inventory', line=dict(color='#1E90FF', width=2)))
        fig1.add_trace(go.Scatter(x=[dates_array[0], dates_array[-1]], y=[rop, rop], mode='lines', name='ROP Trigger', line=dict(color='#A9A9A9', width=2, dash='dash')))
        
        # Mark Reorder Triggers (Green)
        trigger_dates = dates_array[new_orders > 0]
        trigger_vals = closing_bal[new_orders > 0]
        if len(trigger_dates) > 0:
            fig1.add_trace(go.Scatter(x=trigger_dates, y=trigger_vals, mode='markers', name='Order Placed', marker=dict(color='green', size=8, symbol='triangle-up')))
            
        # Mark True Stockouts/Lost Sales (Red)
        stockout_dates = dates_array[lost_sales_arr > 0]
        if len(stockout_dates) > 0:
            fig1.add_trace(go.Scatter(x=stockout_dates, y=np.zeros(len(stockout_dates)), mode='markers', name='Stockout (Lost Sale)', marker=dict(color='red', size=10, symbol='triangle-up')))
            
        fig1.update_layout(title="Physical Inventory Dynamics", plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=True, gridcolor='#E5E5E5'), yaxis=dict(showgrid=True, gridcolor='#E5E5E5'), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig1, use_container_width=True)

    # Graph 2: Net Inventory
    with chart_col2:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=dates_array, y=net_inventory, mode='lines', name='Net Inventory', line=dict(color='#FFA500', width=2)))
        fig2.add_hline(y=0, line_width=1, line_dash="dash", line_color="red")
        fig2.update_layout(title="Net Inventory (Accounting)", plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=True, gridcolor='#E5E5E5'), yaxis=dict(showgrid=True, gridcolor='#E5E5E5', title="Units"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig2, use_container_width=True)
        
    chart_col3, chart_col4 = st.columns(2)
    
    # Graph 3: Stockout Quantity (Lost Sales)
    with chart_col3:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=dates_array, y=lost_sales_arr, mode='lines', fill='tozeroy', name='Lost Sales', line=dict(color='#DC143C', width=2)))
        fig3.update_layout(title="Lost Sales Quantity Over Time", plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=True, gridcolor='#E5E5E5'), yaxis=dict(showgrid=True, gridcolor='#E5E5E5', title="Unfulfilled Units"), showlegend=False)
        st.plotly_chart(fig3, use_container_width=True)
        
    # Graph 4: Backorders Quantity
    with chart_col4:
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=dates_array, y=backorders_arr, mode='lines', fill='tozeroy', name='Backorders', line=dict(color='#8A2BE2', width=2)))
        fig4.update_layout(title="Backorders Over Time", plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=True, gridcolor='#E5E5E5'), yaxis=dict(showgrid=True, gridcolor='#E5E5E5', title="Backlogged Units"), showlegend=False)
        st.plotly_chart(fig4, use_container_width=True)

    st.markdown("### Simulation Data Table")
    st.dataframe(sim_df, use_container_width=True, hide_index=True)
    
else:
    st.info('Please upload your inventory template in the sidebar to run the auditor.')
