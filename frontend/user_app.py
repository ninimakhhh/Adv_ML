import sys
from pathlib import Path

# ── Path bootstrap ─────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_FRONTEND = Path(__file__).parent
for _p in (str(_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st

# ── Page config — must be FIRST Streamlit call ──────────────────────────────
st.set_page_config(
    layout="wide",
    page_title="Olá Market — Estilo Português",
    page_icon="🛒",
    initial_sidebar_state="collapsed",
)

# ── Lazy imports (after path bootstrap) ─────────────────────────────────────
from shared.data_loader import load_categories, get_sale_products, get_popular_products
from shared.navigation import navigate_to
from components.header import render_header
from components.product_card import render_product_card
from components.chatbot_widget import render_chatbot_widget

_CSS_FILE = _FRONTEND / "styles" / "user_styles.css"


def _load_css() -> None:
    with open(_CSS_FILE, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ── Reusable footer ──────────────────────────────────────────────────────────
def _render_footer() -> None:
    st.markdown(
        """
        <div class="store-footer">
          <div class="footer-grid">
            <div>
              <div class="footer-brand-name">🛒 Olá Market</div>
              <p class="footer-brand-desc">
                A sua loja de estilo de vida portuguesa. Produtos selecionados com
                cuidado de marcas artesanais e sustentáveis — do Minho ao Algarve.
              </p>
              <div style="display:flex;gap:10px;margin-top:16px">
                <a href="#" style="color:#888;font-size:18px;text-decoration:none">📘</a>
                <a href="#" style="color:#888;font-size:18px;text-decoration:none">📷</a>
                <a href="#" style="color:#888;font-size:18px;text-decoration:none">📌</a>
              </div>
            </div>
            <div class="footer-col">
              <h4>Sobre Nós</h4>
              <ul>
                <li><a href="#">A Nossa História</a></li>
                <li><a href="#">Sustentabilidade</a></li>
                <li><a href="#">Marcas Parceiras</a></li>
                <li><a href="#">Imprensa</a></li>
                <li><a href="#">Carreiras</a></li>
              </ul>
            </div>
            <div class="footer-col">
              <h4>Apoio ao Cliente</h4>
              <ul>
                <li><a href="#">FAQ</a></li>
                <li><a href="#">Devoluções &amp; Trocas</a></li>
                <li><a href="#">Envios &amp; Prazos</a></li>
                <li><a href="#">Acompanhar Encomenda</a></li>
                <li><a href="#">Contactar Suporte</a></li>
              </ul>
            </div>
            <div class="footer-col">
              <h4>Ligações</h4>
              <ul>
                <li><a href="#">Instagram</a></li>
                <li><a href="#">Facebook</a></li>
                <li><a href="#">Pinterest</a></li>
                <li><a href="#">Newsletter</a></li>
                <li><a href="#">Blog</a></li>
              </ul>
            </div>
          </div>
          <div class="footer-bottom">
            <span>© 2025 Olá Market · Lisboa, Portugal. Todos os direitos reservados.</span>
            <span style="color:#555">Desenvolvido para <strong style="color:#FF6B35">Nova SBE</strong> · Advanced Topics in Machine Learning 2026</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Home page ────────────────────────────────────────────────────────────────
def _render_home() -> None:
    render_header()

    # Hero banner
    st.markdown(
        """
        <div class="hero-banner">
          <div class="hero-inner">
            <div class="hero-badge">✦ Nova Coleção Verão 2025</div>
            <h1 class="hero-title">Essenciais de Estilo<br>com Alma Portuguesa</h1>
            <p class="hero-subtitle">
              Produtos selecionados de marcas artesanais e sustentáveis —<br>
              da cerâmica alentejana ao azeite do Ribatejo.
            </p>
            <a class="hero-cta" href="#">Descobrir Agora →</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Trust badges
    st.markdown(
        """
        <div style="background:#FAFAFA;border-bottom:1px solid #F0F0F0;">
          <div style="max-width:1400px;margin:0 auto;padding:16px 32px;display:flex;
                      justify-content:center;gap:48px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#555;font-weight:500">
              🚚 <span>Envio grátis acima de €50</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#555;font-weight:500">
              ↩️ <span>Devoluções em 30 dias</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#555;font-weight:500">
              🔒 <span>Pagamento seguro</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#555;font-weight:500">
              🇵🇹 <span>Produtos 100% portugueses</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Shop by Category ─────────────────────────────────────────────────────
    categories = load_categories()

    st.markdown(
        """
        <div style="max-width:1400px;margin:0 auto;padding:52px 32px 18px">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <h2 style="font-size:22px;font-weight:700;color:#111;margin:0;letter-spacing:-0.4px">
              Comprar por Categoria
            </h2>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cat_cols = st.columns(8)
    for i, cat in enumerate(categories):
        with cat_cols[i]:
            st.markdown(
                f"""
                <div class="cat-card">
                  <img src="{cat['image_url']}" alt="{cat['name']}" loading="lazy">
                  <div class="cat-overlay">
                    <div class="cat-emoji">{cat['icon_emoji']}</div>
                    <div class="cat-label">{cat['name']}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(cat["name"], key=f"home_cat_{cat['id']}", use_container_width=True):
                navigate_to("category", selected_category_id=cat["id"])

    # ── Current Deals ────────────────────────────────────────────────────────
    sale_products = get_sale_products()[:6]

    st.markdown(
        """
        <div style="max-width:1400px;margin:56px auto 0;padding:0 32px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
            <h2 style="font-size:22px;font-weight:700;color:#111;margin:0">🔥 Promoções de Hoje</h2>
            <a href="#" style="font-size:13px;font-weight:500;color:#FF6B35;text-decoration:none">
              Ver todas as promoções →
            </a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    deal_cols = st.columns(6)
    for i, product in enumerate(sale_products):
        with deal_cols[i]:
            render_product_card(product, f"home_deal_{product['id']}", navigate_to)

    # ── Popular Now ──────────────────────────────────────────────────────────
    popular_products = get_popular_products()[:6]

    st.markdown(
        """
        <div style="max-width:1400px;margin:56px auto 0;padding:0 32px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
            <h2 style="font-size:22px;font-weight:700;color:#111;margin:0">⭐ Popular Agora</h2>
            <a href="#" style="font-size:13px;font-weight:500;color:#FF6B35;text-decoration:none">
              Ver todos →
            </a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pop_cols = st.columns(6)
    for i, product in enumerate(popular_products):
        with pop_cols[i]:
            render_product_card(product, f"home_pop_{product['id']}", navigate_to)

    # ── Promo banner strip ───────────────────────────────────────────────────
    st.markdown(
        """
        <div style="max-width:1400px;margin:56px auto 0;padding:0 32px">
          <div style="background:linear-gradient(135deg,#1A1A2E,#0F3460);border-radius:16px;
                      padding:44px 48px;display:flex;align-items:center;justify-content:space-between;
                      flex-wrap:wrap;gap:24px">
            <div>
              <div style="color:#FF9A7A;font-size:12px;font-weight:700;text-transform:uppercase;
                          letter-spacing:1.2px;margin-bottom:10px">Newsletter exclusiva</div>
              <h3 style="color:#FFF;font-size:24px;font-weight:700;margin:0 0 8px;letter-spacing:-0.5px">
                10% de desconto na primeira encomenda
              </h3>
              <p style="color:rgba(255,255,255,0.6);font-size:14px;margin:0">
                Subscreva e receba ofertas exclusivas diretamente na sua caixa de entrada.
              </p>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap">
              <input type="email" placeholder="o-seu-email@exemplo.pt"
                     style="padding:12px 16px;border-radius:8px;border:none;font-size:14px;
                            width:260px;outline:none;font-family:inherit">
              <button style="background:#FF6B35;color:#FFF;border:none;padding:12px 24px;
                             border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;
                             font-family:inherit">
                Subscrever
              </button>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_footer()
    render_chatbot_widget()


# ── Routing ──────────────────────────────────────────────────────────────────
def _init_state() -> None:
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"
    if "cart_items" not in st.session_state:
        st.session_state.cart_items = []
    if "selected_category_id" not in st.session_state:
        st.session_state.selected_category_id = None
    if "selected_product_id" not in st.session_state:
        st.session_state.selected_product_id = None


def main() -> None:
    _load_css()
    _init_state()

    page = st.session_state.current_page

    if page == "home":
        _render_home()
    elif page == "category":
        from pages.category_view import render_category_view
        render_category_view()
    elif page == "product":
        from pages.product_detail import render_product_detail
        render_product_detail()
    else:
        st.session_state.current_page = "home"
        st.rerun()


main()
