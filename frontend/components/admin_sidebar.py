import streamlit as st
from datetime import datetime

def render_admin_sidebar():
    """Render the admin sidebar with navigation and user profile."""
    
    with st.sidebar:
        # Logo / Store name
        st.markdown("### 🏪 Olá Market")
        st.markdown("---")
        
        # User Profile
        st.markdown("#### 👤 User")
        st.markdown("**Maria Silva**  \n_Owner_")
        
        st.markdown("---")
        
        # System Status
        st.markdown("#### System Status")
        col1, col2 = st.columns([0.2, 0.8])
        with col1:
            st.markdown("🟢")
        with col2:
            st.markdown("**All Systems Operational**")
        
        st.markdown("---")
        
        # Footer info
        st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
