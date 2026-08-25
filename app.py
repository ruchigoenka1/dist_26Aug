import streamlit as st

st.set_page_config(layout="wide")

# Initialize login state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    st.title("Inventory Management System")
    st.subheader("Login")
    
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        # Replace with secure authentication logic as needed
        if username == "admin" and password == "admin": 
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid credentials. Please try again.")

if not st.session_state.logged_in:
    login_screen()
else:
    # Setup native Multi-Page navigation
    sim_page = st.Page("sim_page.py", title="Inventory Simulator", icon="⚙️")
    plot_page = st.Page("plot_page.py", title="Closing Balance Plotter", icon="📈")
    
    pg = st.navigation([sim_page, plot_page])
    pg.run()
