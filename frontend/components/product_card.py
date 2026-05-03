import sys
from pathlib import Path

_FRONTEND = Path(__file__).parent.parent
_ROOT = _FRONTEND.parent
for _p in (str(_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st


def _stars(rating: float) -> str:
    filled = round(rating)
    return "★" * filled + "☆" * (5 - filled)


def render_product_card(product: dict, card_key: str, navigate_func) -> None:
    discount_badge = (
        f'<div class="disc-badge">-{product["discount_percent"]}%</div>'
        if product.get("is_on_sale")
        else ""
    )
    popular_badge = (
        '<div class="pop-badge">Popular</div>' if product.get("is_popular") else ""
    )

    price_class = " sale" if product.get("is_on_sale") else ""
    price_html = f'<span class="pc-price-now{price_class}">€{product["price"]:.2f}</span>'
    if product.get("is_on_sale"):
        price_html += f' <span class="pc-price-was">€{product["original_price"]:.2f}</span>'

    stars = _stars(product["rating"])

    st.markdown(
        f"""
        <div class="pc-wrap">
          <div class="pc-img-wrap">
            <img src="{product['image_url']}" alt="{product['name']}" loading="lazy">
            {discount_badge}
            {popular_badge}
          </div>
          <div class="pc-body">
            <div class="pc-name">{product['name']}</div>
            <div class="pc-rating-row">
              <span class="pc-stars">{stars}</span>
              <span>{product['rating']} &nbsp;({product['review_count']} avaliações)</span>
            </div>
            <div class="pc-price">{price_html}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="pc-btn-wrap">', unsafe_allow_html=True)
    if st.button("Ver Produto →", key=card_key, use_container_width=True):
        navigate_func("product", selected_product_id=product["id"])
    st.markdown("</div>", unsafe_allow_html=True)
