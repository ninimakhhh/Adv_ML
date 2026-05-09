import streamlit as st


def render_header(navigate_to_home=None):
    st.markdown("""
    <div class="store-header">
      <div class="header-inner">
        <div class="header-logo">🛒 Olá Market</div>
        <div class="header-search">
          <span class="search-icon">🔍</span>
          <input type="text" placeholder="Search products, brands and categories...">
        </div>
        <div class="header-actions">
          <div class="header-action-btn">
            <span class="act-icon">👤</span>
            <span>Account</span>
          </div>
          <div class="header-action-btn">
            <span class="act-icon">♡</span>
            <span>Favorites</span>
          </div>
          <div class="header-action-btn">
            <span class="act-icon">🛒</span>
            <span>Cart</span>
          </div>
        </div>
      </div>
      <nav class="header-nav">
        <div class="header-nav-inner">
          <a class="nav-link active" href="#">Home</a>
          <a class="nav-link" href="#">Categories</a>
          <a class="nav-link sale" href="#">🔥 Deals</a>
          <a class="nav-link" href="#">New Arrivals</a>
          <a class="nav-link" href="#">Brands</a>
          <a class="nav-link" href="#">Contact</a>
        </div>
      </nav>
    </div>
    <div class="header-spacer"></div>
    """, unsafe_allow_html=True)
