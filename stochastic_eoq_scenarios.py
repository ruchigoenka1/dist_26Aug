import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm

st.set_page_config(page_title="Stochastic EOQ & Transport Scenarios", layout="wide")

# =====================================================================
# STYLING
# =====================================================================
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
# VECTORIZED MONTE CARLO ENGINE
# =====================================================================
@st.cache_data(show_spinner=False)
def generate_demand_paths(mu, sigma, days, paths, seed=42):
    """Generates identical demand arrays to ensure fair comparison across scenarios."""
    np.random.seed(seed)
    return np.maximum(0, np.random.normal(mu, sigma, (paths, days)).round())

def simulate_policy_vectorized(demand_matrix, Q, R, L, opening_inv):
    """
    Simulates a (Q, R) continuous review policy over thousands of paths simultaneously.
    Returns array of total holding units, shortage units, and total order counts per path.
    Assumes a lost-sales environment for shortage tracking.
    """
    paths, days = demand_matrix.shape
    inv = np.full(paths, float(opening_inv))
    pipeline = np.zeros((paths, days + L + 1)) 
    
    total_holding = np.zeros(paths)
    total_shortage = np.zeros(paths)
    order_count = np.zeros(paths)
    
    for day in range(days):
        # 1. Receive pipeline orders
        inv += pipeline[:, day]
        
        # 2. Fulfill demand
        demand_today = demand_matrix[:, day]
        unmet = np.maximum(0, demand_today - inv)
        inv = np.maximum(0, inv - demand_today)
        
        total_shortage += unmet
        total_holding += inv
        
        # 3. Order trigger (Inventory Position = Physical + In-Transit)
        in_transit = np.sum(pipeline[:, day+1 : day+L+1], axis=1)
        inv_pos = inv + in_transit
        
        trigger = inv_pos < R
        order_count += trigger
        
        # Dispatch orders (they arrive exactly L days from now)
        pipeline[trigger, day + L] += Q
        
    return total_holding, total_shortage, order_count

# =====================================================================
# HEADER & INPUTS
# =====================================================================
st.title("⚖️ Stochastic EOQ & Lead Time Optimization")
st.markdown("Optimize inventory policies under volatile conditions. Evaluate whether the cost reduction in safety stock and stockouts justifies the premium paid for faster transportation.")

st.sidebar.header("Global Parameters")
daily_demand_mean = st.sidebar.number_input("Daily Demand (Mean)", value=50.0)
daily_demand_std = st.sidebar.number_input("Daily Demand (Std Dev)", value=20.0)
holding_cost = st.sidebar.number_input("Holding Cost (Per Unit/Day)", value=0.05)
shortage_cost = st.sidebar.number_input("Shortage Cost (Per Unit)", value=10.0)

st.sidebar.divider()
st.sidebar.subheader("Simulation Settings")
sim_days = st.sidebar.number_input("Timeframe (Days)", value=365, min_value=30)
sim_paths = st.sidebar.slider("Monte Carlo Paths", min_value=100, max_value=2000, value=500, step=100)

st.sidebar.divider()
st.sidebar.subheader("Optimization Target")
target_metric = st.sidebar.radio(
    "Minimize Cost Based On:",
    ["Average (Expected) Cost", "95% Worst-Case Cost", "98% Worst-Case Cost"],
    help="Targeting worst-case cost builds highly resilient inventory policies at the expense of baseline holding costs."
)

st.divider()

# =====================================================================
# SCENARIO CONFIGURATION
# =====================================================================
st.subheader("Transporter Scenarios Configuration")
st.write("Define your baseline and up to three premium shipping alternatives.")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("**Base Scenario**")
    base_L = st.number_input("Lead Time (Days)", value=10, key="base_L")
    base_O = st.number_input("Order/Transport Cost", value=500.0, key="base_O")
    
with col2:
    st.markdown("**Premium Route A**")
    a_active = st.checkbox("Enable Scenario A", value=True)
    a_L = st.number_input("Lead Time (Days)", value=7, key="a_L", disabled=not a_active)
    a_O = st.number_input("Order/Transport Cost", value=750.0, key="a_O", disabled=not a_active)

with col3:
    st.markdown("**Premium Route B**")
    b_active = st.checkbox("Enable Scenario B", value=True)
    b_L = st.number_input("Lead Time (Days)", value=5, key="b_L", disabled=not b_active)
    b_O = st.number_input("Order/Transport Cost", value=1100.0, key="b_O", disabled=not b_active)

with col4:
    st.markdown("**Express Air (C)**")
    c_active = st.checkbox("Enable Scenario C", value=False)
    c_L = st.number_input("Lead Time (Days)", value=2, key="c_L", disabled=not c_active)
    c_O = st.number_input("Order/Transport Cost", value=2500.0, key="c_O", disabled=not c_active)

# Build scenario dictionary dynamically
scenarios = {"Baseline": {"L": base_L, "O": base_O}}
if a_active: scenarios["Premium A"] = {"L": a_L, "O": a_O}
if b_active: scenarios["Premium B"] = {"L": b_L, "O": b_O}
if c_active: scenarios["Express Air C"] = {"L": c_L, "O": c_O}

st.divider()

# =====================================================================
# OPTIMIZATION EXECUTION
# =====================================================================
if st.button("Run Vectorized Optimization", type="primary"):
    with st.spinner("Generating stochastic demand matrices and searching policy state space..."):
        
        # 1. Generate identical demand paths for fair scenario evaluation
        demand_matrix = generate_demand_paths(daily_demand_mean, daily_demand_std, sim_days, sim_paths)
        
        results_data = []
        box_plot_data = {}
        
        for name, params in scenarios.items():
            L = params["L"]
            O = params["O"]
            
            # 2. Establish analytical baseline to build the search grid
            annual_demand = daily_demand_mean * sim_days
            analytical_eoq = np.sqrt((2 * annual_demand * O) / (holding_cost * sim_days)) if holding_cost > 0 else 100
            analytical_rop = (daily_demand_mean * L) + (norm.ppf(0.95) * daily_demand_std * np.sqrt(L))
            
            q_grid = np.linspace(max(10, analytical_eoq * 0.5), analytical_eoq * 1.5, 12).astype(int)
            r_grid = np.linspace(max(0, analytical_rop * 0.7), analytical_rop * 1.3, 12).astype(int)
            
            best_metric_val = float('inf')
            best_q = 0
            best_r = 0
            best_cost_array = None
            avg_holding_kpi = 0
            avg_shortage_kpi = 0
            
            # 3. Grid Search over Q and R (Vectorized over paths internally)
            for Q in q_grid:
                for R in r_grid:
                    opening_inv = R + (Q / 2) # Rough steady-state start
                    
                    tot_hold, tot_short, order_cnt = simulate_policy_vectorized(demand_matrix, Q, R, L, opening_inv)
                    
                    # Calculate total cost per path
                    cost_per_path = (tot_hold * holding_cost) + (tot_short * shortage_cost) + (order_cnt * O)
                    
                    # Evaluate based on user's selected risk metric
                    if target_metric == "Average (Expected) Cost":
                        eval_metric = np.mean(cost_per_path)
                    elif target_metric == "95% Worst-Case Cost":
                        eval_metric = np.percentile(cost_per_path, 95)
                    else:
                        eval_metric = np.percentile(cost_per_path, 98)
                        
                    if eval_metric < best_metric_val:
                        best_metric_val = eval_metric
                        best_q = Q
                        best_r = R
                        best_cost_array = cost_per_path
                        avg_holding_kpi = np.mean(tot_hold)
                        avg_shortage_kpi = np.mean(tot_short)
            
            # Store optimal results for this scenario
            box_plot_data[name] = best_cost_array
            
            results_data.append({
                "Scenario": name,
                "Lead Time (Days)": L,
                "Order/Transport Cost": f"${O:,.2f}",
                "Optimized EOQ (Q*)": best_q,
                "Optimized ROP (R*)": best_r,
                f"Min {target_metric}": f"${best_metric_val:,.2f}",
                "Avg Stockout Units": f"{avg_shortage_kpi:,.0f}",
                "Avg Holding Units": f"{avg_holding_kpi:,.0f}"
            })
            
        # =====================================================================
        # RESULTS RENDERING
        # =====================================================================
        st.subheader("Optimization Results & Scenario Comparison")
        
        df_results = pd.DataFrame(results_data)
        st.dataframe(df_results, use_container_width=True, hide_index=True)
        
        st.markdown("### Total Cost Distribution Profile")
        st.write("Box plots represent the spread of total costs across all Monte Carlo paths (Holding + Shortage + Ordering). Tighter boxes indicate lower risk and higher predictability.")
        
        fig_box = go.Figure()
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        
        for idx, (name, costs) in enumerate(box_plot_data.items()):
            fig_box.add_trace(go.Box(
                y=costs,
                name=name,
                marker_color=colors[idx % len(colors)],
                boxmean='sd'
            ))
            
        fig_box.update_layout(
            yaxis_title=f"Total Cost ({sim_days} Days)",
            xaxis_title="Transport Scenario",
            showlegend=False
        )
        
        st.plotly_chart(style_plotly_fig(fig_box), use_container_width=True)
