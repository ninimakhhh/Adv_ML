import sys
from pathlib import Path

_FRONTEND = Path(__file__).parent.parent
_ROOT = _FRONTEND.parent
for _p in (str(_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st
from components.header import render_header
from components.product_card import render_product_card
from components.chatbot_widget import render_chatbot_placeholder
from shared.data_loader import load_categories, get_category_by_id, get_products_by_category
from shared.navigation import navigate_to

_CSS = _FRONTEND / "styles" / "user_styles.css"


def _load_css():
    with open(_CSS, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def render_category_view() -> None:
    _load_css()
    render_header()

    category_id = st.session_state.get("selected_category_id")
    category = get_category_by_id(category_id) if category_id else None

    if not category:
        st.error("Categoria não encontrada.")
        if st.button("← Voltar ao Início"):
            navigate_to("home")
        return

    all_products = get_products_by_category(category_id)

    # ── Breadcrumb ───────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="page-wrap" style="padding-bottom:0">
          <div class="breadcrumb">
            <a href="#" onclick="return false;">Início</a>
            <span class="sep">›</span>
            Categorias
            <span class="sep">›</span>
            <span>{category['name']}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    back_col, _ = st.columns([1, 8])
    with back_col:
        if st.button("← Início", key="cat_back_home"):
            navigate_to("home")

    # ── Category banner ──────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="max-width:1400px;margin:0 auto;padding:0 32px 24px">
          <div class="cat-banner-overlay">
            <img src="{category['image_url'].replace('/400/300', '/1400/300')}" alt="{category['name']}">
            <div class="cat-banner-text">
              <div class="cat-banner-title">{category['icon_emoji']} {category['name']}</div>
              <div class="cat-banner-count">{len(all_products)} produtos disponíveis</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Filters + Products ───────────────────────────────────────────────────
    filter_col, products_col = st.columns([1, 3.5], gap="large")

    with filter_col:
        st.markdown("**Filtros**")
        st.markdown("---")

        price_range = st.slider(
            "Preço (€)",
            min_value=0,
            max_value=300,
            value=(0, 300),
            step=5,
            key="cat_price_range",
        )

        min_rating = st.select_slider(
            "Avaliação mínima",
            options=[1, 2, 3, 4, 5],
            value=1,
            format_func=lambda x: "★" * x,
            key="cat_min_rating",
        )

        in_stock_only = st.checkbox("Apenas em stock", value=False, key="cat_in_stock")

        sort_by = st.selectbox(
            "Ordenar por",
            options=["Popular", "Preço: baixo→alto", "Preço: alto→baixo", "Melhor avaliação"],
            key="cat_sort",
        )

        on_sale_only = st.checkbox("Apenas em promoção", value=False, key="cat_on_sale")

    with products_col:
        # Apply filters
        products = [
            p for p in all_products
            if price_range[0] <= p["price"] <= price_range[1]
            and p["rating"] >= min_rating
            and (not in_stock_only or p["in_stock"])
            and (not on_sale_only or p["is_on_sale"])
        ]

        # Sort
        if sort_by == "Preço: baixo→alto":
            products.sort(key=lambda p: p["price"])
        elif sort_by == "Preço: alto→baixo":
            products.sort(key=lambda p: p["price"], reverse=True)
        elif sort_by == "Melhor avaliação":
            products.sort(key=lambda p: p["rating"], reverse=True)
        elif sort_by == "Popular":
            products.sort(key=lambda p: (not p["is_popular"], -p["review_count"]))

        if not products:
            st.info("Nenhum produto encontrado com os filtros selecionados.")
        else:
            st.markdown(
                f"<p style='font-size:13px;color:#888;margin-bottom:16px'>"
                f"Mostrando {len(products)} produto{'s' if len(products) != 1 else ''}</p>",
                unsafe_allow_html=True,
            )
            rows = [products[i : i + 4] for i in range(0, len(products), 4)]
            for row in rows:
                row_cols = st.columns(4)
                for j, prod in enumerate(row):
                    with row_cols[j]:
                        render_product_card(
                            prod,
                            f"cat_prod_{prod['id']}",
                            navigate_to,
                        )
                st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)

    render_chatbot_placeholder()
