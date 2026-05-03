import streamlit as st


def navigate_to(page: str, **kwargs) -> None:
    st.session_state.current_page = page
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.rerun()
