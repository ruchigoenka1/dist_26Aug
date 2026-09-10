import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm, gamma

st.set_page_config(page_title="Multi-SKU Joint Replenishment", layout="wide")

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
def generate_adaptive_demand(mu, sigma, days, seed):
    np.random.seed(seed)
    if sigma == 0:
        return np.full(days, mu)
    cov = sigma / mu if mu > 0 else 0
    if cov <= 0.5:
        return np.maximum(0, np.random.normal(mu, sigma, days)).round()
    else:
        shape = (mu / sigma) ** 2
        scale = (sigma ** 2) / mu
        return np.random.gamma(shape, scale, days).round()

# =====================================================================
# SIMULATION ENGINES
# =====================================================================
def simulate_independent_continuous(sku_data, sim_days, L, shared_order_cost, holding_rate, sl):
    total_holding_cost = 0.0
    total_transport_cost = 0.0
    total_orders_placed = 0
    
    sku_results = []
    
    for _, row in sku_data.iterrows():
        mu, sigma, unit_cost = row['Daily Mean'], row['Std Dev'], row['Unit Cost ($)']
        cov = sigma / mu if mu > 0 else 0
        
        if cov <= 0.5:
            s = int(mu * L + norm.ppf(sl) * sigma * np.sqrt(L))
        else:
            s = int(gamma.ppf(sl, a=((mu/sigma)**2)*L, scale=(sigma**2)/mu)) if sigma > 0 else int(mu * L)
            
        daily_hc = (unit_cost * holding_rate) / 365
        Q = max(1, int(np.sqrt((2 * mu * 365 * shared_order_cost) / max(0.01, daily_hc * 365))))
        
        demand = generate_adaptive_demand(mu, sigma, sim_days, 42)
        inv = s + Q
        pipeline = np.zeros(sim_days + L + 1)
        
        holding_units = 0
        orders = 0
        
        # Track physical inventory for min/max/avg
        inv_history = np.zeros(sim_days)
        
        for day in range(sim_days):
            inv += pipeline[day]
            inv = max(0, inv - demand[day])
            holding_units += inv
            inv_history[day] = inv
            
            inv_pos = inv + sum(pipeline[day+1 : day+L+1])
            if inv_pos < s:
                pipeline[day + L] += Q
                orders += 1
                total_orders_placed += 1
                total_transport_cost += shared_order_cost
                
        sku_holding_cost = holding_units * daily_hc
        total_holding_cost += sku_holding_cost
        
        sku_results.append({
            "SKU": row['SKU'],
            "Policy": f"Indep (s={s}, Q={Q})",
            "Avg Inv": int(inv_history.mean()),
            "Min Inv": int(inv_history.min()),
            "Max Inv": int(inv_history.max()),
            "Orders": orders,
            "Holding Cost": sku_holding_cost
        })
        
    return total_holding_cost, total_transport_cost, total_orders_placed, sku_results

def simulate_joint_periodic(sku_data, sim_days, L, R, shared_order_cost, holding_rate, sl):
    total_holding_cost = 0.0
    total_transport_cost = 0.0
    joint_orders_placed = 0
    
    num_skus = len(sku_data)
    demands = np.zeros((num_skus, sim_days))
    invs = np.zeros(num_skus)
    pipelines = np.zeros((num_skus, sim_days + L + 1))
    target_S = np.zeros(num_skus)
    daily_hcs = np.zeros(num_skus)
    
    for i, row in sku_data.iterrows():
        mu, sigma, unit_cost = row['Daily Mean'], row['Std Dev'], row['Unit Cost ($)']
        demands[i] = generate_adaptive_demand(mu, sigma, sim_days, 42)
        daily_hcs[i] = (unit_cost * holding_rate) / 365
        
        cov = sigma / mu if mu > 0 else 0
        if cov <= 0.5:
            target_S[i] = int(mu * (L + R) + norm.ppf(sl) * sigma * np.sqrt(L + R))
        else:
            target_S[i] = int(gamma.ppf(sl, a=((mu/sigma)**2)*(L+R), scale=(sigma**2)/mu)) if sigma > 0 else int(mu * (L+R))
            
        invs[i] = target_S[i]
        
    total_holding_units = np.zeros(num_skus)
    sku_order_counts = np.zeros(num_skus)
    
    # Track physical inventory for min/max/avg
    inv_history = np.zeros((num_skus, sim_days))
    
    for day in range(sim_days):
        invs += pipelines[:, day]
        invs = np.maximum(0, invs - demands[:, day])
        total_holding_units += invs
        inv_history[:, day] = invs
        
        if day % R == 0:
            inv_pos = invs + np.sum(pipelines[:, day+1 : day+L+1], axis=1)
            order_qtys = np.maximum(0, target_S - inv_pos)
            
            if np.any(order_qtys > 0):
                pipelines[:, day + L] += order_qtys
                joint_orders_placed += 1
                total_transport_cost += shared_order_cost 
                sku_order_counts += (order_qtys > 0).astype(int)
                
    sku_holding_costs = total_holding_units * daily_hcs
    total_holding_cost = np.sum(sku_holding_costs)
    
    sku_results = []
    for i, row in sku_data.iterrows():
        sku_results.append({
            "SKU": row['SKU'],
            "Policy": f"Joint (R={R}, S={int(target_S[i])})",
            "Avg Inv": int(inv_history[i].mean()),
            "Min Inv": int(inv_history[i].min()),
            "Max Inv": int(inv_history[i].max()),
            "Orders (Included in Joint)": int(sku_order_counts[i]),
            "Holding Cost": sku_holding_costs[i]
        })
        
    return total_holding_cost, total_transport_cost, joint_orders_placed, sku_results

# =====================================================================
# UI LAYOUT
# =====================================================================
st.title("📦 Multi-SKU Joint Replenishment Optimization")
st.markdown("Evaluate uncoordinated continuous reviews against synchronized periodic ordering when managing multiple SKUs from a single supplier.")

st.sidebar.header("Global Parameters")
shared_order_cost = st.sidebar.number_input("Fixed Transport/Order Cost ($)", value=500.0)
holding_rate = st.sidebar.number_input("Annual Holding Rate (%)", value=20.0) / 100.0
lead_time = st.sidebar.number_input("Shared Supplier Lead Time (Days)", value=14)
target_sl = st.sidebar.slider("Target Service Level (%)", 80.0, 99.9, 95.0) / 100.0
sim_days = st.sidebar.number_input("Simulation Horizon (Days)", value=365)

st.subheader("1. SKU Portfolio Configuration")
st.write("Define the demand profile and unit costs for the SKUs sharing this supplier. Edit the table directly to add or modify items.")

default_skus = pd.DataFrame({
    "SKU": ["SKU-A (Fast)", "SKU-B (Medium)", "SKU-C (Slow/Lumpy)"],
    "Daily Mean": [50, 15, 2],
    "Std Dev": [10, 8, 5],
    "Unit Cost ($)": [20, 85, 300]
})

edited_skus = st.data_editor(default_skus, num_rows="dynamic", use_container_width=True)

st.divider()

st.subheader("2. Define Joint Review Scenarios")
st.write("Compare the Independent policy against up to three different synchronized review cycles.")

col1, col2, col3 = st.columns(3)
with col1:
    r1 = st.number_input("Joint Scenario 1: Review Period (Days)", min_value=1, value=7)
with col2:
    r2 = st.number_input("Joint Scenario 2: Review Period (Days)", min_value=1, value=14)
with col3:
    r3 = st.number_input("Joint Scenario 3: Review Period (Days)", min_value=1, value=30)

if st.button("🚀 Run Synchronization Analysis", type="primary"):
    with st.spinner("Simulating multi-item trajectories..."):
        
        results_summary = []
        
        # 1. Run Independent Baseline
        h_cost_ind, t_cost_ind, ord_ind, detail_ind = simulate_independent_continuous(
            edited_skus, sim_days, lead_time, shared_order_cost, holding_rate, target_sl
        )
        results_summary.append({
            "Strategy": "Independent Continuous (s, Q)",
            "Total Holding Cost": h_cost_ind,
            "Total Transport Cost": t_cost_ind,
            "Total Cost": h_cost_ind + t_cost_ind,
            "Total Truck Deliveries": ord_ind
        })
        
        # 2. Run Joint Scenarios
        for r_val, name in zip([r1, r2, r3], [f"Joint Periodic (R={r1})", f"Joint Periodic (R={r2})", f"Joint Periodic (R={r3})"]):
            h_cost_j, t_cost_j, ord_j, detail_j = simulate_joint_periodic(
                edited_skus, sim_days, lead_time, r_val, shared_order_cost, holding_rate, target_sl
            )
            results_summary.append({
                "Strategy": name,
                "Total Holding Cost": h_cost_j,
                "Total Transport Cost": t_cost_j,
                "Total Cost": h_cost_j + t_cost_j,
                "Total Truck Deliveries": ord_j
            })
            
        df_summary = pd.DataFrame(results_summary)
        
        # --- Visualization ---
        st.markdown("### 📊 Cost Comparison Profile")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_summary["Strategy"], y=df_summary["Total Holding Cost"], 
            name="Holding Cost", marker_color="#1f77b4"
        ))
        fig.add_trace(go.Bar(
            x=df_summary["Strategy"], y=df_summary["Total Transport Cost"], 
            name="Transport Cost", marker_color="#ff7f0e"
        ))
        
        fig.update_layout(
            barmode='stack',
            yaxis_title="Total Annual Cost ($)",
            xaxis_title="Replenishment Strategy",
            hovermode="x unified"
        )
        st.plotly_chart(style_plotly_fig(fig), use_container_width=True)
        
        # --- Data Tables ---
        st.markdown("### 🏆 Executive Scorecard")
        st.dataframe(df_summary.style.format({
            "Total Holding Cost": "${:,.0f}",
            "Total Transport Cost": "${:,.0f}",
            "Total Cost": "${:,.0f}"
        }), use_container_width=True, hide_index=True)
        
        st.markdown("### 🔍 SKU-Level Breakdown")
        
        best_joint = min(results_summary[1:], key=lambda x: x["Total Cost"])
        best_r = int(best_joint["Strategy"].split("=")[1].replace(")", ""))
        
        _, _, _, best_detail = simulate_joint_periodic(edited_skus, sim_days, lead_time, best_r, shared_order_cost, holding_rate, target_sl)
        
        df_ind_detail = pd.DataFrame(detail_ind)
        df_best_detail = pd.DataFrame(best_detail)
        
        st.markdown("**Independent Continuous Detail**")
        st.dataframe(df_ind_detail.style.format({
            "Holding Cost": "${:,.0f}",
            "Avg Inv": "{:,}",
            "Min Inv": "{:,}",
            "Max Inv": "{:,}"
        }), use_container_width=True, hide_index=True)
        
        st.markdown(f"**Best Coordinated Detail ({best_joint['Strategy']})**")
        st.dataframe(df_best_detail.style.format({
            "Holding Cost": "${:,.0f}",
            "Avg Inv": "{:,}",
            "Min Inv": "{:,}",
            "Max Inv": "{:,}"
        }), use_container_width=True, hide_index=True)
