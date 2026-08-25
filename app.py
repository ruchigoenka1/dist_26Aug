import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(layout="wide")

# =========================================================================
# SECURE AUTHENTICATION MODULE (v0.3.0+)
# =========================================================================
config = {
    'credentials': {
        'usernames': {
            'admin': {
                'email': 'ashutosh.goenka123@gmail.com',
                'name': 'System Admin',
                'password': '$2b$12$93MC4ONIi0.6QXjnL9uGveabXcSb1jCkauE4UiR68KeA5/0HRTyCK'
            }
        }
    },
    'cookie': {
        'expiry_days': 1, # Set to 1 day so the user only logs in once a day
        'key': 'random_secret_signature_key_here', 
        'name': 'inventory_app_cookie'
    }
}

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

try:
    authenticator.login()
except Exception as e:
    st.error(e)

# Stop execution if not properly authenticated
if st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password to access the app")
    st.stop()

# =========================================================================
# APP NAVIGATION (Runs only if authentication_status is True)
# =========================================================================

# Display a welcome message and a logout button in the sidebar
with st.sidebar:
    st.write(f"Welcome, **{st.session_state.get('name')}**")
    authenticator.logout("Logout", "sidebar")
    st.divider()

# Setup native Multi-Page navigation
sim_page = st.Page("sim_page.py", title="Inventory Simulator", icon="⚙️")
plot_page = st.Page("plot_page.py", title="Closing Balance Plotter", icon="📈")

pg = st.navigation([sim_page, plot_page])
pg.run()
