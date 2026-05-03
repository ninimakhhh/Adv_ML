import streamlit as st
from components.admin_sidebar import render_admin_sidebar
from components.chatbot_widget import render_admin_chatbot_widget

st.set_page_config(layout="wide", page_title="Settings - Olá Market Admin")

# Render sidebar
render_admin_sidebar()

# Main content
st.title("⚙️ Settings")
st.markdown("---")

# Settings sections
st.markdown("### Account Settings")
col1, col2 = st.columns(2)

with col1:
    st.text_input("Store Name", value="Olá Market")
    st.text_input("Owner Email", value="maria@olamarket.com")

with col2:
    st.text_input("Phone", value="+351 912 345 678")
    st.text_input("Location", value="Lisbon, Portugal")

st.markdown("### Notification Preferences")
col1, col2 = st.columns(2)

with col1:
    st.checkbox("Email alerts for high priority tickets", value=True)
    st.checkbox("Daily performance report", value=True)

with col2:
    st.checkbox("AI accuracy warnings", value=True)
    st.checkbox("Revenue alerts", value=True)

st.markdown("### System Settings")
st.slider("Auto-resolution confidence threshold (%)", min_value=50, max_value=100, value=80)
st.selectbox("Support queue assignment", ["AI Only", "AI + Manual Review", "Manual Only"])

st.markdown("---")
if st.button("💾 Save Settings", width="stretch"):
    st.success("Settings saved successfully!")

# Chatbot widget
render_admin_chatbot_widget()
