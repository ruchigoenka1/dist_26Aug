import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm

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

@st.cache_data(show_spinner=False)
def generate_demand(mu, sigma, days, paths, seed):
    np.random.seed(seed)
    return np.maximum(0, np.random.normal(mu, sigma, (paths, days)).round())

# Vectorized simulation engine for all policy types
def simulate_policy_multi_path(demand_matrix, policy_type, p1, p2, L, opening_inv):
    paths, days = demand_matrix.shape
    inv = np.full(paths, float(opening_inv))
    pipeline = np.zeros((paths, days + L + 1))
    
    hist_phys = np.zeros((paths, days))
    hist_pipe = np.zeros((paths, days))
    hist_tot = np.zeros((paths, days))
    hist_stockout = np.zeros((paths, days))
    unmet_tot = np.zeros(paths)
    
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
        elif policy_type == "Min-Max (s, S)":
            trigger = inv_pos < p1
            pipeline[trigger, day + L] += (p2 - inv_pos[trigger])
        elif policy_type == "Periodic (R, S)":
            if day % int(p1) == 0:
                trigger = inv_pos < p2
                pipeline[trigger, day + L] += (p2 - inv_pos[trigger])
                
    return hist_phys, hist_pipe, hist_tot, hist_stockout, unmet_tot

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

# Pre-calculate analytical baselines
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
        z = norm.ppf(sl / 100.0)
        
        if p_type == "Continuous (s, Q)":
            rec_s = int(mu * L + z * sigma * np.sqrt(L))
            st.caption(f"💡 **Recommended:** Reorder Point (s) = {rec_s}, Q = {analytical_eoq} (EOQ)")
            p1 = st.number_input("Reorder Point (s)", value=rec_s, key=f"p1_{i}")
            p2 = st.number_input("Order Quantity (Q)", value=analytical_eoq, key=f"p2_{i}")
            
        elif p_type == "Periodic (R, S)":
            p1 = st.number_input("Review Period (R in days)", min_value=1, value=7, key=f"p1_{i}")
            rec_S = int(mu * (L + p1) + z * sigma * np.sqrt(L + p1))
            st.caption(f"💡 **Recommended:** Target Level (S) = {rec_S}")
            p2 = st.number_input("Target Level (S)", value=rec_S, key=f"p2_{i}")
            
        elif p_type == "Min-Max (s, S)":
            rec_s = int(mu * L + z * sigma * np.sqrt(L))
            rec_S_eoq = rec_s + analytical_eoq
            rec_S_lt1 = int(mu * (L + 1) + z * sigma * np.sqrt(L + 1))
            
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
st.write("Visualizing how each policy reacts to the exact same 1-year demand pattern.")

# Run 1-path simulation
single_demand = generate_demand(mu, sigma, sim_days, 1, st.session_state.sim_seed)
total_dem = single_demand.sum()

results_single = []
traces = {"Physical": [], "Pipeline": [], "Total": []}
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

for idx, pol in enumerate(policies):
    phys, pipe, tot, stockouts, unmet = simulate_policy_multi_path(single_demand, pol["type"], pol["p1"], pol["p2"], L, pol["ob"])
    
    avg_phys = phys[0].mean()
    avg_pipe = pipe[0].mean()
    avg_tot = tot[0].mean()
    so_days = stockouts[0].sum()
    fill_rate = 100 * (1 - (unmet[0] / total_dem)) if total_dem > 0 else 100
    
    results_single.append({
        "Policy": pol["name"],
        "Avg Physical Inv": avg_phys,
        "Avg Pipeline Inv": avg_pipe,
        "Avg Total Inv": avg_tot,
        "Min Physical Inv": phys[0].min(),
        "Max Physical Inv": phys[0].max(),
        "Stockout Days": so_days,
        "Fill Rate (%)": fill_rate,
        "Avg Working Capital ($)": avg_phys * unit_cost
    })
    
    # Store traces for plotting
    x_ax = np.arange(sim_days)
    traces["Physical"].append(go.Scatter(x=x_ax, y=phys[0], mode='lines', name=pol["name"], line=dict(color=colors[idx])))
    traces["Pipeline"].append(go.Scatter(x=x_ax, y=pipe[0], mode='lines', name=pol["name"], line=dict(color=colors[idx], dash='dot')))
    traces["Total"].append(go.Scatter(x=x_ax, y=tot[0], mode='lines', name=pol["name"], line=dict(color=colors[idx], dash='dash')))

# 1. Trajectory Graphs (Tabs to prevent 12-line clutter)
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

# 2. Tables
df_kpi = pd.DataFrame(results_single)

col_t1, col_t2 = st.columns([6, 4])
with col_t1:
    st.markdown("**Operational KPIs**")
    st.dataframe(df_kpi.drop(columns=["Avg Working Capital ($)"]).style.format({
        "Avg Physical Inv": "{:.0f}", "Avg Pipeline Inv": "{:.0f}", "Avg Total Inv": "{:.0f}", 
        "Min Physical Inv": "{:.0f}", "Max Physical Inv": "{:.0f}", 
        "Stockout Days": "{:.0f}", "Fill Rate (%)": "{:.2f}%"
    }), use_container_width=True, hide_index=True)

with col_t2:
    st.markdown("**Financial KPIs**")
    st.dataframe(df_kpi[["Policy", "Avg Working Capital ($)"]].style.format({
        "Avg Working Capital ($)": "${:,.2f}"
    }), use_container_width=True, hide_index=True)


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
            phys, pipe, tot, stockouts, unmet = simulate_policy_multi_path(mc_demand, pol["type"], pol["p1"], pol["p2"], L, pol["ob"])
            
            # Arrays of shape (paths,) representing the average/sum per path
            avg_phys_per_path = phys.mean(axis=1)
            wc_per_path = avg_phys_per_path * unit_cost
            so_days_per_path = stockouts.sum(axis=1)
            fill_rate_per_path = np.where(mc_total_dem_per_path > 0, 100 * (1 - (unmet / mc_total_dem_per_path)), 100)
            
            mc_results.append({
                "Policy": pol["name"],
                "Mean Fill Rate": f"{fill_rate_per_path.mean():.2f}%",
                f"Worst-Case Fill Rate (p{100-mc_percentile})": f"{np.percentile(fill_rate_per_path, 100-mc_percentile):.2f}%",
                "Mean Stockout Days": f"{so_days_per_path.mean():.1f}",
                f"Worst-Case Stockout Days (p{mc_percentile})": f"{np.percentile(so_days_per_path, mc_percentile):.1f}",
                "Mean Working Capital": f"${wc_per_path.mean():,.0f}",
                f"Worst-Case Working Cap (p{mc_percentile})": f"${np.percentile(wc_per_path, mc_percentile):,.0f}"
            })
            
        st.markdown(f"#### Monte Carlo Aggregates ({mc_paths} Paths)")
        st.dataframe(pd.DataFrame(mc_results), use_container_width=True, hide_index=True)
