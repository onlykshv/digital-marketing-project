"""Entry point for the KKBox Retention Intelligence dashboard.

Run from the dashboard/ folder with:  streamlit run app.py
See README.md for setup details.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(page_title="KKBox Retention Intelligence", layout="wide", initial_sidebar_state="expanded")

# Navigation lives in a fixed left sidebar (the product's app shell), in the order a manager works:
# see the picture -> find who to save -> check their value -> pick the play -> open a customer ->
# ask why.
#
# NOTE: style injection intentionally does NOT happen here. Content emitted by app.py *before*
# nav.run() is not reliably delivered to the browser on every rerun (confirmed via isolated
# repro -- the CSS itself is fine; the bug is specifically about pre-nav.run() markdown calls).
# Each page calls theme.apply_page_style() itself instead, as part of the same script execution
# nav.run() dispatches to.

PAGES_DIR = Path(__file__).resolve().parent / "pages"

overview = st.Page(str(PAGES_DIR / "overview.py"), title="Overview", icon=":material/space_dashboard:", default=True)
priority_customers = st.Page(str(PAGES_DIR / "priority_customers.py"), title="Priority Customers", icon=":material/group:")
customer_value = st.Page(str(PAGES_DIR / "customer_value.py"), title="Customer Value", icon=":material/payments:")
action_center = st.Page(str(PAGES_DIR / "action_center.py"), title="Action Center", icon=":material/campaign:")
customer_360 = st.Page(str(PAGES_DIR / "customer_360.py"), title="Customer 360", icon=":material/account_circle:")
retention_copilot = st.Page(str(PAGES_DIR / "retention_copilot.py"), title="Retention Intelligence", icon=":material/forum:")

nav = st.navigation(
    [overview, priority_customers, customer_value, action_center, customer_360, retention_copilot],
    position="sidebar",
)
nav.run()
