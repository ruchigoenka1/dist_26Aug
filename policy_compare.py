import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm, gamma

st.set_page_config(page_title="Compare Inventory Policies", layout="wide")

# =====================================================================
# STYLING & HELPERS
# =====================================================================
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117',
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# Adaptive Demand Generation (Normal for low CoV, Gamma for high CoV)
@st.cache_data(show_spinner=False)
def generate_demand(mu, sigma, days, paths, seed):
    np.random.seed(seed)
    if sigma == 0:
        return np.full((paths, days), mu)
        
    cov = sigma / mu if mu > 0 else 0
    
    if cov <= 0.5:
        # Low CoV: Normal distribution with zero-truncation
        raw_demand = np.maximum(0, np.random.normal(mu, sigma, (paths, days)))
    else:
        # High CoV: Gamma distribution (strictly non-negative, naturally handles lumpy spikes)
        shape = (mu / sigma) ** 2
        scale = (sigma ** 2) / mu
        raw_demand = np.random.gamma(shape, scale, (paths, days))
        
    return np.round(raw_demand)

# Detailed single-path simulator for the raw data table
def simulate_single_path_detailed(demand_arr, policy_type, p1, p2, L, opening_inv, unit_cost):
    days = len(demand_arr)
    inventory = float(opening_inv)
    pipeline_orders = []
    
    data = []
    start_date = pd.Timestamp("2024-01-01")
    
    for day in range(days):
        demand_today = demand_arr[day]
        opening_phys = inventory
        
        # 1. Receive shipments
        shipment_received = sum([qty for arr_day, qty in pipeline_orders if arr_day == day])
        pipeline_orders = [(arr_day, qty) for arr_day, qty in pipeline_orders if arr_day != day]
        
        inventory += shipment_received
        
        # 2. Fulfill demand (Lost Sales Model)
        active_backorders = 0 
        if inventory >= demand_today:
            inventory -= demand_today
            daily_lost_sales = 0
        else:
            daily_lost_sales = demand_today - inventory
            inventory = 0
            
        net_inventory = inventory - active_backorders
        pipeline_qty = sum([qty for arr_day, qty in pipeline_orders])
        inventory_position = net_inventory + pipeline_qty
        
        # 3. Order Triggers
        new_order = 0
        if policy_type == "Continuous (s, Q)":
            if inventory_position < p1:
                new_order = p2
                pipeline_orders.append((day + L, new_order))
        elif policy_type == "Min-Max (s, S)":
            if inventory_position < p1:
                new_order = max(0, p2 - inventory_position)
                if new_order > 0:
                    pipeline_orders.append((day + L, new_order))
        elif policy_type == "Periodic (R, S)":
            if day % int(p1) == 0:
                if inventory_position < p2:
                    new_order = max(0, p2 - inventory_position)
                    if new_order > 0:
                        pipeline_orders.append((day + L, new_order))
                    
        closing_net_pipeline = net_inventory + pipeline_qty + new_order
        blocked_wc = inventory * unit_cost
        
        data.append([
            (start_date + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
            opening_phys, demand_today, shipment_received, active_backorders,
            net_inventory, inventory, pipeline_qty, inventory_position,
            new_order, closing_net_pipeline, daily_lost_sales, blocked_wc
        ])
        
    cols = [
        "Date", "Opening Physical", "Demand", "Shipment Received", 
        "Active Backorders", "Net Inventory", "Physical Inventory", 
        "Pipeline Order", "Inventory Position", "New Order", 
        "Closing Net Including Pipeline", "Daily Lost Sales", "Blocked Working Capital"
    ]
    return pd.DataFrame(data, columns=cols)

# Vectorized simulation engine for multi-path
def simulate_policy_multi_path(demand_matrix, policy_type, p1, p2, L, opening_inv):
    paths, days = demand_matrix.shape
    inv = np.full(paths, float(opening_inv))
    pipeline = np.zeros((paths, days + L + 1))
    
    hist_phys = np.zeros((paths, days))
    hist_pipe = np.zeros((paths, days))
    hist_tot = np.zeros((paths, days))
    hist_stockout = np.zeros((paths, days))
    unmet_tot = np.zeros(paths)
    order_count = np.zeros(paths)
    
    for day in range(days):
        inv += pipeline[:, day]
        
        demand_today = demand_matrix[:, day]
        unmet = np.maximum(0, demand_today - inv)
        inv = np.maximum(0, inv - demand_today)
        unmet_tot += unmet
        
        in_transit = np.sum(pipeline[:, day+1 : day+L+1], axis=1)
        inv_pos = inv + in_transit
        
        hist_phys[:, day] = inv
        hist_pipe[:, day] = in_transit
        hist_tot[:, day] = inv_pos
        hist_stockout[:, day] = (unmet > 0).astype(int)
        
        if policy_type == "Continuous (s, Q)":
            trigger = inv_pos < p1
            pipeline[trigger, day + L] += p2
            order_count += trigger.astype(int)
        elif policy_type == "Min-Max (s, S)":
            trigger = inv_pos < p1
            order_qty = np.maximum(0, p2 - inv_pos)
            pipeline[trigger, day + L] += order_qty[trigger]
            order_count += trigger.astype(int)
        elif policy_type == "Periodic (R, S)":
            if day % int(p1) == 0:
                trigger = inv_pos < p2
                order_qty = np.maximum(0, p2 - inv_pos)
                pipeline[trigger, day + L] += order_qty[trigger]
                order_count += trigger.astype(int)
                
    return hist_phys, hist_pipe, hist_tot, hist_stockout, unmet_tot, order_count

# =====================================================================
# STATE MANAGEMENT
# =====================================================================
if 'sim_seed' not in st.session_state:
    st.session_state.sim_seed = 42

# =====================================================================
# HEADER & GLOBAL INPUTS
# =====================================================================
st.title("🔀 Policy Comparison & Stress Testing")
st.markdown("Configure up to 4 distinct inventory policies and compare their performance against identical stochastic demand paths.")

st.sidebar.header("Global Parameters")
mu = st.sidebar.number_input("Daily Demand (Mean)", value=50.0)
sigma = st.sidebar.number_input("Daily Demand (Std Dev)", value=15.0)
L = st.sidebar.number_input("Lead Time (Days)", value=5)
unit_cost = st.sidebar.number_input("Unit Cost ($)", value=100.0)
order_cost = st.sidebar.number_input("Cost per Order ($)", value=250.0)
holding_rate = st.sidebar.number_input("Annual Holding Rate (%)", value=20.0) / 100.0
sim_days = st.sidebar.number_input("Simulation Days", value=365)

if st.sidebar.button("🔄 Reset Demand Pattern"):
    st.session_state.sim_seed = np.random.randint(1, 10000)
    st.sidebar.success("Demand pattern randomized!")

# Pre-calculate analytical baselines & check CoV
cov = sigma / mu if mu > 0 else 0
daily_holding = (unit_cost * holding_rate) / 365
annual_demand = mu * 365
analytical_eoq = int(np.sqrt((2 * annual_demand * order_cost) / (daily_holding * 365))) if daily_holding > 0 else 100

st.divider()

# =====================================================================
# POLICY CONFIGURATION
# =====================================================================
num_policies = st.slider("Number of Policies to Compare", min_value=1, max_value=4, value=2)

policies = []
cols = st.columns(num_policies)

for i in range(num_policies):
    with cols[i]:
        st.markdown(f"### Policy {i+1}")
        p_type = st.selectbox("Policy Type", ["Continuous (s, Q)", "Periodic (R, S)", "Min-Max (s, S)"], key=f"type_{i}")
        sl = st.slider("Target Service Level (%)", 50.0, 99.9, 95.0, 0.1, key=f"sl_{i}")
        
        # Adaptive Recommendation Engine (Normal vs Gamma)
        if cov <= 0.5:
            z = norm.ppf(sl / 100.0)
            rec_s = int(mu * L + z * sigma * np.sqrt(L))
            rec_S_periodic = int(mu * (L + 7) + z * sigma * np.sqrt(L + 7))
            rec_S_lt1 = int(mu * (L + 1) + z * sigma * np.sqrt(L + 1))
        else:
            shape = (mu / sigma) ** 2
            scale = (sigma ** 2) / mu
            rec_s = int(gamma.ppf(sl / 100.0, a=shape * L, scale=scale))
            rec_S_periodic = int(gamma.ppf(sl / 100.0, a=shape * (L + 7), scale=scale))
            rec_S_lt1 = int(gamma.ppf(sl / 100.0, a=shape * (L + 1), scale=scale))
        
        if p_type == "Continuous (s, Q)":
            st.caption(f"💡 **Recommended:** Reorder Point (s) = {rec_s}, Q = {analytical_eoq} (EOQ)")
            p1 = st.number_input("Reorder Point (s)", value=rec_s, key=f"p1_{i}")
            p2 = st.number_input("Order Quantity (Q)", value=analytical_eoq, key=f"p2_{i}")
            
        elif p_type == "Periodic (R, S)":
            p1 = st.number_input("Review Period (R in days)", min_value=1, value=7, key=f"p1_{i}")
            # Dynamically update recommendation based on chosen review period
            if cov <= 0.5:
                rec_S_dyn = int(mu * (L + p1) + norm.ppf(sl / 100.0) * sigma * np.sqrt(L + p1))
            else:
                rec_S_dyn = int(gamma.ppf(sl / 100.0, a=((mu/sigma)**2) * (L + p1), scale=(sigma**2)/mu))
            st.caption(f"💡 **Recommended:** Target Level (S) = {rec_S_dyn}")
            p2 = st.number_input("Target Level (S)", value=rec_S_dyn, key=f"p2_{i}")
            
        elif p_type == "Min-Max (s, S)":
            rec_S_eoq = rec_s + analytical_eoq
            
            st.caption(f"💡 **Recommended:** Min (s) = {rec_s}")
            st.caption(f"Option 1 (EOQ-based Max): {rec_S_eoq}")
            st.caption(f"Option 2 (LT+1 based Max): {rec_S_lt1}")
            
            p1 = st.number_input("Min Level (s)", value=rec_s, key=f"p1_{i}")
            p2 = st.number_input("Max Level (S)", value=rec_S_eoq, key=f"p2_{i}")
            
        opening_inv = st.number_input("Opening Inventory", value=int(p2 if p_type != "Continuous (s, Q)" else p1 + p2), key=f"ob_{i}")
        
        policies.append({
            "name": f"P{i+1}: {p_type.split(' ')[0]}",
            "type": p_type,
            "p1": p1,
            "p2": p2,
            "ob": opening_inv
        })

st.divider()

# =====================================================================
# SECTION 1: SINGLE PATH DETERMINISTIC COMPARISON
# =====================================================================
st.subheader("📊 Single Path Trajectory & KPI Comparison")
st.write("Visualizing how each policy reacts to the exact same demand pattern.")

# Run 1-path simulation
single_demand = generate_demand(mu, sigma, sim_days, 1, st.session_state.sim_seed)
total_dem = single_demand.sum()

results_ops = []
results_fin = []
traces = {"Physical": [], "Pipeline": [], "Total": []}
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
detailed_dfs = {}

for idx, pol in enumerate(policies):
    phys, pipe, tot, stockouts, unmet, orders = simulate_policy_multi_path(single_demand, pol["type"], pol["p1"], pol["p2"], L, pol["ob"])
    
    avg_phys = phys[0].mean()
    avg_pipe = pipe[0].mean()
    avg_tot = tot[0].mean()
    so_days = stockouts[0].sum()
    fill_rate = 100 * (1 - (unmet[0] / total_dem)) if total_dem > 0 else 100
    orders_placed = orders[0]
    
    # Financial Calculations
    hold_cost = avg_phys * unit_cost * holding_rate * (sim_days / 365.0)
    ord_cost = orders_placed * order_cost
    tot_inv_cost = hold_cost + ord_cost
    
    results_ops.append({
        "Policy": pol["name"],
        "Avg Physical Inv": avg_phys,
        "Avg Pipeline Inv": avg_pipe,
        "Avg Total Inv": avg_tot,
        "Min Physical Inv": phys[0].min(),
        "Max Physical Inv": phys[0].max(),
        "Stockout Days": so_days,
        "Fill Rate (%)": fill_rate
    })
    
    results_fin.append({
        "Policy": pol["name"],
        "Avg Working Capital ($)": avg_phys * unit_cost,
        "Holding Cost ($)": hold_cost,
        "Ordering Cost ($)": ord_cost,
        "Total Inventory Cost ($)": tot_inv_cost
    })
    
    # Store traces for plotting
    x_ax = np.arange(sim_days)
    traces["Physical"].append(go.Scatter(x=x_ax, y=phys[0], mode='lines', name=pol["name"], line=dict(color=colors[idx])))
    traces["Pipeline"].append(go.Scatter(x=x_ax, y=pipe[0], mode='lines', name=pol["name"], line=dict(color=colors[idx], dash='dot')))
    traces["Total"].append(go.Scatter(x=x_ax, y=tot[0], mode='lines', name=pol["name"], line=dict(color=colors[idx], dash='dash')))
    
    # Generate detailed dataframe for this policy
    detailed_dfs[pol["name"]] = simulate_single_path_detailed(single_demand[0], pol["type"], pol["p1"], pol["p2"], L, pol["ob"], unit_cost)

# --- GRAPH SECTION ---
st.markdown("### Inventory Trajectories")
tab1, tab2, tab3 = st.tabs(["Physical Inventory", "Pipeline Inventory", "Total Inventory Position"])

def render_comparison_fig(trace_list, title, y_title):
    fig = go.Figure()
    for t in trace_list:
        fig.add_trace(t)
    fig.update_layout(title=title, yaxis_title=y_title, hovermode='x unified')
    return style_plotly_fig(fig)

with tab1: st.plotly_chart(render_comparison_fig(traces["Physical"], "Physical Inventory Over Time", "Units"), use_container_width=True)
with tab2: st.plotly_chart(render_comparison_fig(traces["Pipeline"], "Pipeline (In-Transit) Inventory Over Time", "Units"), use_container_width=True)
with tab3: st.plotly_chart(render_comparison_fig(traces["Total"], "Total Inventory Position Over Time", "Units"), use_container_width=True)

# --- KPI TABLE SECTION ---
df_ops = pd.DataFrame(results_ops)
df_fin = pd.DataFrame(results_fin)

st.markdown("### Operational KPIs")
st.dataframe(df_ops.style.format({
    "Avg Physical Inv": "{:.0f}", "Avg Pipeline Inv": "{:.0f}", "Avg Total Inv": "{:.0f}", 
    "Min Physical Inv": "{:.0f}", "Max Physical Inv": "{:.0f}", 
    "Stockout Days": "{:.0f}", "Fill Rate (%)": "{:.2f}%"
}), use_container_width=True, hide_index=True)

st.markdown("### Financial KPIs")
st.dataframe(df_fin.style.format({
    "Avg Working Capital ($)": "${:,.2f}",
    "Holding Cost ($)": "${:,.2f}",
    "Ordering Cost ($)": "${:,.2f}",
    "Total Inventory Cost ($)": "${:,.2f}"
}), use_container_width=True, hide_index=True)

st.divider()

# --- DEMAND & RAW DATA SECTION ---
st.subheader("📈 Demand Distribution & Raw Data")

d_col1, d_col2 = st.columns(2)

with d_col1:
    st.markdown("#### Simulated Demand Profile (Daily)")
    fig_hist = go.Figure(data=[go.Histogram(
        x=single_demand[0], 
        marker_color='rgba(173, 216, 230, 0.8)', 
        marker_line=dict(color='#3399ff', width=1)
    )])
    fig_hist.update_layout(title="Frequency of Daily Demand", xaxis_title="Demand Quantity", yaxis_title="Days")
    st.plotly_chart(style_plotly_fig(fig_hist), use_container_width=True)
    
with d_col2:
    st.markdown("#### Rolling Window Demand Profile")
    roll_window = st.number_input("Rolling Window (Days)", min_value=1, max_value=365, value=7)
    rolling_demand = pd.Series(single_demand[0]).rolling(roll_window).sum().dropna()
    
    fig_roll = go.Figure(data=[go.Histogram(
        x=rolling_demand, 
        marker_color='rgba(255, 165, 0, 0.8)', 
        marker_line=dict(color='#ff8c00', width=1)
    )])
    fig_roll.update_layout(title=f"Frequency of {roll_window}-Day Rolling Demand", xaxis_title="Demand Quantity", yaxis_title="Periods")
    st.plotly_chart(style_plotly_fig(fig_roll), use_container_width=True)

st.markdown("#### Detailed Daily Raw Data")
selected_pol_data = st.selectbox("Select Policy to view raw data:", list(detailed_dfs.keys()))

with st.expander(f"🔍 View Simulation Data Table for {selected_pol_data}", expanded=False):
    st.dataframe(detailed_dfs[selected_pol_data].style.format({
        "Opening Physical": "{:.0f}",
        "Demand": "{:.0f}",
        "Shipment Received": "{:.0f}",
        "Active Backorders": "{:.0f}",
        "Net Inventory": "{:.0f}",
        "Physical Inventory": "{:.0f}",
        "Pipeline Order": "{:.0f}",
        "Inventory Position": "{:.0f}",
        "New Order": "{:.0f}",
        "Closing Net Including Pipeline": "{:.0f}",
        "Daily Lost Sales": "{:.0f}",
        "Blocked Working Capital": "${:,.2f}"
    }), use_container_width=True, hide_index=True)
    
    st.markdown(f"**{roll_window}-Day Rolling Demand Data**")
    df_roll = pd.DataFrame({
        "Period End Date": pd.date_range(start="2024-01-01", periods=sim_days)[roll_window-1:].strftime("%Y-%m-%d"),
        f"{roll_window}-Day Total Demand": rolling_demand.values
    })
    st.dataframe(df_roll, use_container_width=True, hide_index=True)

st.divider()

# =====================================================================
# SECTION 2: MONTE CARLO STRESS TESTING
# =====================================================================
st.subheader("🎲 Monte Carlo Stress Testing (Multiple Scenarios)")
st.write("Run the configured policies through hundreds of parallel demand universes to evaluate risk and worst-case performance.")

mc1, mc2, mc3 = st.columns(3)
with mc1:
    mc_paths = st.number_input("Number of Scenarios (Paths)", min_value=100, max_value=5000, value=500, step=100)
with mc2:
    mc_percentile = st.slider("Worst-Case Percentile Target (%)", 25, 99, 95)
with mc3:
    st.markdown("<br>", unsafe_allow_html=True)
    run_mc = st.button("🚀 Run Monte Carlo Simulation", type="primary")

if run_mc:
    with st.spinner(f"Simulating {mc_paths} parallel realities..."):
        mc_demand = generate_demand(mu, sigma, sim_days, mc_paths, st.session_state.sim_seed + 1)
        mc_total_dem_per_path = mc_demand.sum(axis=1)
        
        mc_results = []
        
        for pol in policies:
            phys, pipe, tot, stockouts, unmet, orders = simulate_policy_multi_path(mc_demand, pol["type"], pol["p1"], pol["p2"], L, pol["ob"])
            
            # Aggregate per path
            avg_phys_per_path = phys.mean(axis=1)
            so_days_per_path = stockouts.sum(axis=1)
            fill_rate_per_path = np.where(mc_total_dem_per_path > 0, 100 * (1 - (unmet / mc_total_dem_per_path)), 100)
            
            # Financials per path
            wc_per_path = avg_phys_per_path * unit_cost
            holding_cost_per_path = wc_per_path * holding_rate * (sim_days / 365.0)
            ordering_cost_per_path = orders * order_cost
            tot_cost_per_path = holding_cost_per_path + ordering_cost_per_path
            
            mc_results.append({
                "Policy": pol["name"],
                "Mean Fill Rate": f"{fill_rate_per_path.mean():.2f}%",
                f"Worst-Case Fill Rate (p{100-mc_percentile})": f"{np.percentile(fill_rate_per_path, 100-mc_percentile):.2f}%",
                "Mean Stockout Days": f"{so_days_per_path.mean():.1f}",
                f"Worst-Case Stockout Days (p{mc_percentile})": f"{np.percentile(so_days_per_path, mc_percentile):.1f}",
                "Mean Total Inv Cost": f"${tot_cost_per_path.mean():,.0f}",
                f"Worst-Case Inv Cost (p{mc_percentile})": f"${np.percentile(tot_cost_per_path, mc_percentile):,.0f}"
            })
            
        st.markdown(f"#### Monte Carlo Aggregates ({mc_paths} Paths)")
        st.dataframe(pd.DataFrame(mc_results), use_container_width=True, hide_index=True)
