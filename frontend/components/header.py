import streamlit as st


def render_header(navigate_to_home=None):
    st.markdown("""
    <div class="store-header">
      <div class="header-inner">
        <div class="header-logo">🛒 Olá Market</div>
        <div class="header-search">
          <span class="search-icon">🔍</span>
          <input type="text" placeholder="Pesquisar produtos, marcas e categorias...">
        </div>
        <div class="header-actions">
          <div class="header-action-btn">
            <span class="act-icon">👤</span>
            <span>Conta</span>
          </div>
          <div class="header-action-btn">
            <span class="act-icon">♡</span>
            <span>Favoritos</span>
          </div>
          <div class="header-action-btn">
            <span class="act-icon">🛒</span>
            <span>Cesto</span>
          </div>
        </div>
      </div>
      <nav class="header-nav">
        <div class="header-nav-inner">
          <a class="nav-link active" href="#">Início</a>
          <a class="nav-link" href="#">Categorias</a>
          <a class="nav-link sale" href="#">🔥 Promoções</a>
          <a class="nav-link" href="#">Novidades</a>
          <a class="nav-link" href="#">Marcas</a>
          <a class="nav-link" href="#">Contacto</a>
        </div>
      </nav>
    </div>
    <div class="header-spacer"></div>
    """, unsafe_allow_html=True)
