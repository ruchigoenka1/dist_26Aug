import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm

st.set_page_config(page_title="Periodic Review Policy", layout="wide")

if "seed_counter" not in st.session_state:
    st.session_state.seed_counter = 42

st.header("Periodic Review")

st.markdown("""
In a periodic review system, inventory is checked at fixed intervals. The strategy must account for the mechanical reality of the **Protection Interval**—the time from when an order is placed until the *next* order can be placed and received.
""")

# --- Action: Regenerate Demand Button ---
btn_col1, btn_col2 = st.columns([1, 5])
with btn_col1:
    if st.button("🔄 Generate New Demand", key="regen_demand_pr"):
        st.session_state.seed_counter += 1

# --- 1. Baseline System Parameters Input ---
st.subheader("1. Supply Chain Parameters & Recommended Baseline")

p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
with p_col1:
    pr_avg_demand = st.number_input("Avg Daily Demand", value=100.0, step=10.0)
    pr_std_dev = st.number_input("Demand Std Dev", value=15.0, step=5.0)
with p_col2:
    review_period = st.number_input("Recommended Review (Days)", value=14, min_value=1, step=1)
    lead_time = st.number_input("Lead Time (Days)", value=7, min_value=1, step=1)
with p_col3:
    target_service_level = st.slider("Target Service Level (%)", min_value=50.0, max_value=99.9, value=95.0, step=0.1)
    z_score = norm.ppf(target_service_level / 100.0)
with p_col4:
    unit_cost = st.number_input("Unit Cost ($)", value=50.0, step=5.0)
    ordering_cost = st.number_input("Ordering Cost ($/order)", value=250.0, step=50.0, key="baseline_oc")
with p_col5:
    holding_cost_pct = st.number_input("Annual Holding Cost (%)", value=20.0, step=1.0)
    holding_cost_annual = unit_cost * (holding_cost_pct / 100.0)
    holding_cost_daily = holding_cost_annual / 365.0

# Calculate Recommended Baseline Target
protection_interval = review_period + lead_time
expected_demand_pi = pr_avg_demand * protection_interval
std_dev_pi = pr_std_dev * np.sqrt(protection_interval)
safety_stock = z_score * std_dev_pi
recommended_target = expected_demand_pi + safety_stock

st.info(f"**Calculated Baseline Target:** {int(recommended_target)} Units (Accommodating a {review_period}-day review cycle and {lead_time}-day lead time).")

# --- 2. Multi-Scenario Customization Setup ---
st.divider()

def sync_ordering_costs():
    for i in range(5):  # Max slider value is 5
        st.session_state[f"oc_key_{i}"] = st.session_state.baseline_oc

head_col1, head_col2 = st.columns([2, 1])
with head_col1:
    st.subheader("2. Multi-Scenario Strategy Comparison")
with head_col2:
    st.write("") # Spacing
    st.button("📋 Sync Baseline Cost to All Scenarios", on_click=sync_ordering_costs)
    
st.markdown("Test the recommended baseline against custom strategies. Modify the review period to see the mathematically optimum target update instantly.")

num_scenarios = st.slider("Select Number of Custom Scenarios to Compare:", min_value=1, max_value=5, value=2)

scenarios_data = []
s_cols = st.columns(num_scenarios)

for i, col in enumerate(s_cols):
    with col:
        st.markdown(f"##### Scenario {i+1}")
        
        default_t = int(review_period + ((i+1) * 7)) 
        t_val = st.number_input(f"Review Period (Days)", value=default_t, min_value=1, step=1, key=f"t_{i}")
        
        u_pi = t_val + lead_time
        opt_target = (pr_avg_demand * u_pi) + (z_score * (pr_std_dev * np.sqrt(u_pi)))
        st.caption(f"✨ **Optimum Target:** {int(opt_target)} Units")
        target_val = st.number_input(f"Target Level (Units)", value=int(opt_target), step=50, key=f"target_{i}")
        
        if f"oc_key_{i}" not in st.session_state:
            st.session_state[f"oc_key_{i}"] = ordering_cost
            
        oc_val = st.number_input(f"Ordering Cost ($)", step=10.0, key=f"oc_key_{i}")
        
        scenarios_data.append({
            'name': f"Scenario {i+1}", 
            'T': t_val, 
            'Target': target_val, 
            'OrderCost': oc_val
        })

# --- NumPy Optimized Simulation Engine ---
np.random.seed(st.session_state.seed_counter)
sim_days_pr = 365
daily_demand_pr = np.clip(np.random.normal(pr_avg_demand, pr_std_dev, sim_days_pr), 0, None).round(0)

def simulate_periodic_system_vectorized(demand_array, T, L, target, order_c, hold_c_daily):
    sim_days = len(demand_array)
    inventory_history = np.zeros(sim_days)
    receipts = np.zeros(sim_days + L + 1) 
    
    current_inv = target
    order_sizes = []
    units_fulfilled = 0
    
    for day in range(sim_days):
        current_inv += receipts[day]
        current_demand = demand_array[day]
        
        fulfilled = min(max(current_inv, 0), current_demand)
        current_inv -= fulfilled
        units_fulfilled += fulfilled
        
        inventory_history[day] = current_inv
        
        if day % T == 0:
            on_order = np.sum(receipts[day+1:day+L+1])
            inv_position = current_inv + on_order
            
            if inv_position < target:
                order_qty = target - inv_position
                receipts[day + L] += order_qty
                order_sizes.append(order_qty)
                
    holding_units_total = np.sum(np.maximum(inventory_history, 0))
    orders_placed = len(order_sizes)
    total_order_cost = orders_placed * order_c
    total_holding_cost = holding_units_total * hold_c_daily
    total_demand_sim = np.sum(demand_array)
    
    return {
        'history': inventory_history,
        'total_demand': total_demand_sim,
        'units_fulfilled': units_fulfilled,
        'lost_sales': total_demand_sim - units_fulfilled,
        'fill_rate': (units_fulfilled / total_demand_sim) * 100 if total_demand_sim > 0 else 0,
        'orders_placed': orders_placed,
        'min_order_size': np.min(order_sizes) if order_sizes else 0,
        'max_order_size': np.max(order_sizes) if order_sizes else 0,
        'avg_order_size': np.mean(order_sizes) if order_sizes else 0,
        'avg_inventory': holding_units_total / sim_days,
        'max_inventory': np.max(np.maximum(inventory_history, 0)),
        'min_inventory': np.min(inventory_history),
        'total_order_cost': total_order_cost,
        'total_holding_cost': total_holding_cost,
        'total_cost': total_order_cost + total_holding_cost
    }

# Execute simulations 
res_baseline = simulate_periodic_system_vectorized(daily_demand_pr, review_period, lead_time, recommended_target, ordering_cost, holding_cost_daily)

scenario_results = []
for s in scenarios_data:
    res = simulate_periodic_system_vectorized(daily_demand_pr, s['T'], lead_time, s['Target'], s['OrderCost'], holding_cost_daily)
    scenario_results.append(res)

# --- 3. Logically Bifurcated Summary Tables ---
st.divider()
st.markdown("### 📊 Policy Comparison & KPI Summary")

def fmt_usd(val): return f"${val:,.2f}"

# 3A. Operational Health Matrix
st.markdown("#### A. Operational & Capital Health Matrix")
ops_data = {
    "Metric": [
        "Review Interval", 
        "Target Inventory Level", 
        "Fill Rate (%)", 
        "Lost Sales (Units)", 
        "Min Inventory Level (Depth)",
        "Avg Working Capital", 
        "Max Working Capital"
    ]
}
ops_data["Recommended Baseline"] = [
    f"{review_period} Days", f"{int(recommended_target)}", f"{res_baseline['fill_rate']:.2f}%", 
    f"{int(res_baseline['lost_sales'])}", f"{int(res_baseline['min_inventory'])}",
    fmt_usd(res_baseline['avg_inventory'] * unit_cost), fmt_usd(res_baseline['max_inventory'] * unit_cost)
]
for idx, s in enumerate(scenarios_data):
    res = scenario_results[idx]
    ops_data[s['name']] = [
        f"{s['T']} Days", f"{int(s['Target'])}", f"{res['fill_rate']:.2f}%", 
        f"{int(res['lost_sales'])}", f"{int(res['min_inventory'])}",
        fmt_usd(res['avg_inventory'] * unit_cost), fmt_usd(res['max_inventory'] * unit_cost)
    ]
st.dataframe(pd.DataFrame(ops_data), use_container_width=True, hide_index=True)

# 3B. Order Dynamics Matrix
st.markdown("#### B. Order Dynamics Matrix")
order_data = {
    "Metric": ["Total No. of Orders", "Average Order Size", "Minimum Order Size", "Maximum Order Size"]
}
order_data["Recommended Baseline"] = [
    f"{res_baseline['orders_placed']}", f"{int(res_baseline['avg_order_size'])} Units", 
    f"{int(res_baseline['min_order_size'])} Units", f"{int(res_baseline['max_order_size'])} Units"
]
for idx, s in enumerate(scenarios_data):
    res = scenario_results[idx]
    order_data[s['name']] = [
        f"{res['orders_placed']}", f"{int(res['avg_order_size'])} Units", 
        f"{int(res['min_order_size'])} Units", f"{int(res['max_order_size'])} Units"
    ]
st.dataframe(pd.DataFrame(order_data), use_container_width=True, hide_index=True)

# 3C. Financial Matrix
st.markdown("#### C. Financial Projections Matrix")
fin_data = {
    "Metric": ["Applied Ordering Cost ($/order)", "Total Ordering Cost", "Total Holding Cost", "Total System Cost"]
}
fin_data["Recommended Baseline"] = [
    fmt_usd(ordering_cost), fmt_usd(res_baseline['total_order_cost']), 
    fmt_usd(res_baseline['total_holding_cost']), fmt_usd(res_baseline['total_cost'])
]
for idx, s in enumerate(scenarios_data):
    res = scenario_results[idx]
    fin_data[s['name']] = [
        fmt_usd(s['OrderCost']), fmt_usd(res['total_order_cost']), 
        fmt_usd(res['total_holding_cost']), fmt_usd(res['total_cost'])
    ]
st.dataframe(pd.DataFrame(fin_data), use_container_width=True, hide_index=True)

# --- 4. Visual Bifurcation & Trajectory ---
chart_col1, chart_col2 = st.columns([1, 1])
colors = ['#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

with chart_col1:
    st.markdown("#### Cost Bifurcation Analysis")
    names = ["Baseline"] + [s['name'] for s in scenarios_data]
    order_costs = [res_baseline['total_order_cost']] + [r['total_order_cost'] for r in scenario_results]
    hold_costs = [res_baseline['total_holding_cost']] + [r['total_holding_cost'] for r in scenario_results]
    
    fig_cost = go.Figure(data=[
        go.Bar(name='Ordering Cost', x=names, y=order_costs, marker_color='#2ca02c'),
        go.Bar(name='Holding Cost', x=names, y=hold_costs, marker_color='#1f77b4')
    ])
    fig_cost.update_layout(
        barmode='stack', template="plotly_white", yaxis_title="Total Cost ($)",
        height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_cost, use_container_width=True)

with chart_col2:
    st.markdown("#### Physical Inventory Trajectory")
    fig_comp = go.Figure()
    
    fig_comp.add_trace(go.Scatter(
        x=list(range(sim_days_pr)), y=res_baseline['history'], mode='lines', 
        name='Baseline', line=dict(color='#1f77b4', width=3)
    ))
    
    for idx, s in enumerate(scenarios_data):
        fig_comp.add_trace(go.Scatter(
            x=list(range(sim_days_pr)), y=scenario_results[idx]['history'], mode='lines', 
            name=s['name'], line=dict(color=colors[idx], width=1.5, dash='dot')
        ))
    
    fig_comp.add_hline(y=0, line_dash="solid", line_color="#333333", line_width=1)
    fig_comp.update_layout(
        template="plotly_white", xaxis_title="Simulation Day", yaxis_title="Units On Hand",
        height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_comp, use_container_width=True)

# --- 5. Blocked Working Capital Chart ---
st.write("<br>", unsafe_allow_html=True)
st.markdown("#### 💰 Blocked Working Capital Trajectory")
st.caption("Visualizes the daily capital tied up on the warehouse floor (ignores backorders).")

fig_wc = go.Figure()

# Baseline WC
baseline_wc = np.maximum(res_baseline['history'], 0) * unit_cost
fig_wc.add_trace(go.Scatter(
    x=list(range(sim_days_pr)), y=baseline_wc, mode='lines', 
    name='Baseline', line=dict(color='#1f77b4', width=3)
))

# Scenarios WC
for idx, s in enumerate(scenarios_data):
    scenario_wc = np.maximum(scenario_results[idx]['history'], 0) * unit_cost
    fig_wc.add_trace(go.Scatter(
        x=list(range(sim_days_pr)), y=scenario_wc, mode='lines', 
        name=s['name'], line=dict(color=colors[idx], width=1.5, dash='dot')
    ))
    
fig_wc.update_layout(
    template="plotly_white", xaxis_title="Simulation Day", yaxis_title="Capital Blocked ($)",
    height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig_wc, use_container_width=True)

# --- 6. Collapsible Raw Data Logs ---
with st.expander("📋 View Daily Simulation Log Tables"):
    st.markdown("Raw 365-day tracking for Physical Inventory levels side-by-side.")
    
    log_data = {
        "Day": range(1, sim_days_pr + 1),
        "Daily Demand": daily_demand_pr.astype(int),
        "Baseline Inv": res_baseline['history'].astype(int)
    }
    
    for idx, s in enumerate(scenarios_data):
        log_data[f"{s['name']} Inv"] = scenario_results[idx]['history'].astype(int)
        
    log_df = pd.DataFrame(log_data)
    
    def highlight_stockouts(val):
        color = '#ffcccc' if isinstance(val, (int, float)) and val < 0 else ''
        return f'background-color: {color}'
        
    st.dataframe(
        log_df.style.map(highlight_stockouts, subset=[c for c in log_df.columns if 'Inv' in c]), 
        use_container_width=True, hide_index=True
    )
