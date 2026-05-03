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
from shared.data_loader import (
    get_product_by_id,
    get_category_by_id,
    get_reviews_by_product,
    get_products_by_category,
)
from shared.navigation import navigate_to

_CSS = _FRONTEND / "styles" / "user_styles.css"

_FAKE_SPECS: dict[str, list[tuple[str, str]]] = {
    "cat_1": [("Material", "Madeira/Metal/Cerâmica"), ("Dimensões", "Variável"), ("Origem", "Portugal"), ("Garantia", "1 ano"), ("Cor", "Conforme imagem")],
    "cat_2": [("Composição", "Ver etiqueta"), ("Lavagem", "30°C máx."), ("Tamanhos", "XS–XXL"), ("Origem", "Portugal"), ("Certificação", "GOTS / Oeko-Tex")],
    "cat_3": [("Volume", "30–85 ml"), ("Origem", "Portugal / Marrocos"), ("Cruelty-free", "Sim"), ("Vegan", "Sim"), ("Prazo validade", "24 meses")],
    "cat_4": [("Conectividade", "Bluetooth 5.0 / USB-C"), ("Bateria", "Ver descrição"), ("Resistência", "IPX6 / 5ATM"), ("Garantia", "2 anos"), ("Certificação", "CE / FCC")],
    "cat_5": [("Peso", "Ver embalagem"), ("Origem", "Portugal"), ("Conservação", "Lugar fresco e seco"), ("Validade", "12–24 meses"), ("Certificação", "Biológico / Artesanal")],
    "cat_6": [("Material", "TPE / Borracha / Aço inox"), ("Dimensões", "Ver descrição"), ("Peso", "Ver descrição"), ("Garantia", "2 anos"), ("Norma", "CE EN71")],
    "cat_7": [("Páginas", "Ver descrição"), ("Encadernação", "Capa dura / Brochura"), ("Idioma", "Português PT"), ("Editora", "Edições Olá"), ("Ano", "2024–2025")],
    "cat_8": [("Idade recomendada", "Ver descrição"), ("Material", "Madeira FSC / Algodão orgânico"), ("Certificação", "EN71 / Oeko-Tex"), ("Lavagem", "30°C máx."), ("Norma", "CE")],
}


def _load_css() -> None:
    with open(_CSS, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def _stars(rating: float) -> str:
    filled = round(rating)
    return "★" * filled + "☆" * (5 - filled)


def _rating_breakdown(reviews: list[dict]) -> dict[int, float]:
    counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for r in reviews:
        counts[r["rating"]] = counts.get(r["rating"], 0) + 1
    total = len(reviews) or 1
    return {k: round(v / total * 100) for k, v in counts.items()}


def render_product_detail() -> None:
    _load_css()
    render_header()

    product_id = st.session_state.get("selected_product_id")
    product = get_product_by_id(product_id) if product_id else None

    if not product:
        st.error("Produto não encontrado.")
        if st.button("← Voltar ao Início"):
            navigate_to("home")
        return

    category = get_category_by_id(product["category_id"])
    reviews = get_reviews_by_product(product_id)
    category_name = category["name"] if category else "Categoria"

    # ── Breadcrumb ───────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="page-wrap" style="padding-bottom:8px">
          <div class="breadcrumb">
            <a href="#" onclick="return false;">Início</a>
            <span class="sep">›</span>
            <a href="#" onclick="return false;">{category_name}</a>
            <span class="sep">›</span>
            <span>{product['name']}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    bcol1, bcol2, _ = st.columns([1, 1, 7])
    with bcol1:
        if st.button("← Início", key="pd_back_home"):
            navigate_to("home")
    with bcol2:
        if category and st.button(f"← {category_name}", key="pd_back_cat"):
            navigate_to("category", selected_category_id=product["category_id"])

    # ── Product hero ─────────────────────────────────────────────────────────
    st.markdown('<div class="page-wrap" style="padding-top:8px">', unsafe_allow_html=True)
    img_col, detail_col = st.columns([1, 1], gap="large")

    with img_col:
        st.markdown(
            f"""
            <div style="border-radius:12px;overflow:hidden;background:#F6F6F6;">
              <img src="{product['image_url']}" style="width:100%;display:block;aspect-ratio:1;object-fit:cover;">
            </div>
            """,
            unsafe_allow_html=True,
        )
        if product.get("is_on_sale"):
            st.markdown(
                f"""
                <div style="margin-top:12px;background:#FFF5F2;border:1px solid #FFD5C5;
                     border-radius:8px;padding:10px 14px;font-size:13px;color:#C23B00;font-weight:600;text-align:center;">
                  🔥 Poupa €{product['original_price'] - product['price']:.2f} — Promoção por tempo limitado
                </div>
                """,
                unsafe_allow_html=True,
            )

    with detail_col:
        stars_html = _stars(product["rating"])
        price_class = "pd-price sale" if product["is_on_sale"] else "pd-price"

        st.markdown(
            f"""
            <h1 class="pd-name">{product['name']}</h1>
            <div class="pd-rating-row">
              <span class="pd-stars">{stars_html}</span>
              <span>{product['rating']} &nbsp;·&nbsp; {product['review_count']} avaliações</span>
            </div>
            <div style="margin-bottom:16px">
              <span class="{price_class}">€{product['price']:.2f}</span>
              {"<span class='pd-price-orig'>€" + f"{product['original_price']:.2f}" + "</span>" if product.get('is_on_sale') else ""}
              {"<span style='margin-left:10px;background:#FF3B30;color:#FFF;font-size:12px;font-weight:700;padding:3px 8px;border-radius:5px'>-" + str(product['discount_percent']) + "%</span>" if product.get('is_on_sale') else ""}
            </div>
            <p class="pd-desc">{product['description']}</p>
            """,
            unsafe_allow_html=True,
        )

        if product["in_stock"]:
            if product["stock_count"] <= 5:
                st.markdown(
                    f'<div class="pd-stock-low">⚠️ Apenas {product["stock_count"]} em stock!</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="pd-stock-ok">✓ Em stock</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="pd-stock-no">✗ Esgotado</div>', unsafe_allow_html=True)

        qty = st.number_input("Quantidade", min_value=1, max_value=max(1, product["stock_count"]), value=1, key="pd_qty")

        add_col, wish_col = st.columns([2, 1])
        with add_col:
            if st.button(
                "🛒  Adicionar ao Cesto",
                key="pd_add_cart",
                use_container_width=True,
                disabled=not product["in_stock"],
            ):
                if "cart_items" not in st.session_state:
                    st.session_state.cart_items = []
                st.session_state.cart_items.append({"product": product, "qty": qty})
                st.success(f"✓ {product['name']} adicionado ao cesto!")

        with wish_col:
            st.button("♡  Favorito", key="pd_wishlist", use_container_width=True)

        st.markdown(
            """
            <div class="pd-info-box">🚚 Entrega grátis em encomendas acima de €50</div>
            <div class="pd-return-box">↩️ Devoluções gratuitas em 30 dias</div>
            """,
            unsafe_allow_html=True,
        )

        tags_html = " ".join(
            f'<span style="background:#F5F5F5;border:1px solid #EEE;border-radius:20px;padding:3px 10px;font-size:11.5px;color:#666;margin-right:5px">{t}</span>'
            for t in product.get("tags", [])
        )
        if tags_html:
            st.markdown(
                f'<div style="margin-top:14px">{tags_html}</div>', unsafe_allow_html=True
            )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="page-wrap" style="padding-top:12px">', unsafe_allow_html=True)
    tab_desc, tab_specs, tab_reviews = st.tabs(
        ["📋 Descrição", "⚙️ Especificações", f"💬 Avaliações ({len(reviews)})"]
    )

    with tab_desc:
        st.markdown(
            f'<p style="font-size:15px;color:#444;line-height:1.75;max-width:720px">{product["full_description"]}</p>',
            unsafe_allow_html=True,
        )

    with tab_specs:
        specs = _FAKE_SPECS.get(product["category_id"], _FAKE_SPECS["cat_1"])
        spec_rows = "".join(
            f"""<tr>
              <td style="padding:10px 16px;font-weight:600;color:#333;font-size:13.5px;background:#FAFAFA;
                         border-bottom:1px solid #F0F0F0;width:35%">{label}</td>
              <td style="padding:10px 16px;color:#555;font-size:13.5px;border-bottom:1px solid #F0F0F0">{value}</td>
            </tr>"""
            for label, value in specs
        )
        st.markdown(
            f"""<table style="width:100%;border-collapse:collapse;border:1px solid #F0F0F0;border-radius:8px;overflow:hidden">
                {spec_rows}
               </table>""",
            unsafe_allow_html=True,
        )

    with tab_reviews:
        if not reviews:
            st.info("Este produto ainda não tem avaliações.")
        else:
            breakdown = _rating_breakdown(reviews)
            avg = sum(r["rating"] for r in reviews) / len(reviews)

            # Rating summary
            st.markdown(
                f"""
                <div class="rating-summary">
                  <div class="big-rating">
                    <div class="big-rating-num">{avg:.1f}</div>
                    <div class="big-rating-stars">{"★" * round(avg)}{"☆" * (5 - round(avg))}</div>
                    <div class="big-rating-count">{len(reviews)} avaliações</div>
                  </div>
                  <div class="rating-bars">
                    {"".join(
                        f'''<div class="rbar-row">
                          <span style="width:18px">{star}★</span>
                          <div class="rbar-track"><div class="rbar-fill" style="width:{breakdown.get(star,0)}%"></div></div>
                          <span class="rbar-count">{breakdown.get(star,0)}%</span>
                        </div>'''
                        for star in [5, 4, 3, 2, 1]
                    )}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Sort
            sort_reviews = st.selectbox(
                "Ordenar avaliações",
                ["Mais úteis", "Mais recentes", "Melhor avaliação", "Pior avaliação"],
                key="pd_review_sort",
                label_visibility="collapsed",
            )

            sorted_reviews = list(reviews)
            if sort_reviews == "Mais úteis":
                sorted_reviews.sort(key=lambda r: r["helpful_count"], reverse=True)
            elif sort_reviews == "Mais recentes":
                sorted_reviews.sort(key=lambda r: r["date"], reverse=True)
            elif sort_reviews == "Melhor avaliação":
                sorted_reviews.sort(key=lambda r: r["rating"], reverse=True)
            elif sort_reviews == "Pior avaliação":
                sorted_reviews.sort(key=lambda r: r["rating"])

            for rev in sorted_reviews:
                stars_r = "★" * rev["rating"] + "☆" * (5 - rev["rating"])
                verified_badge = (
                    '<span class="verified">✓ Compra verificada</span>'
                    if rev.get("verified_purchase")
                    else ""
                )
                st.markdown(
                    f"""
                    <div class="review-item">
                      <div class="review-hd">
                        <div>
                          <span class="review-author">{rev['author_name']}</span>
                          {verified_badge}
                        </div>
                        <span class="review-date">{rev['date']}</span>
                      </div>
                      <div class="review-stars">{stars_r}</div>
                      <div class="review-title">{rev['title']}</div>
                      <div class="review-body">{rev['body']}</div>
                      <div class="helpful-count">👍 {rev['helpful_count']} pessoas acharam útil</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Related products ─────────────────────────────────────────────────────
    related = [
        p
        for p in get_products_by_category(product["category_id"])
        if p["id"] != product_id
    ][:4]

    if related:
        st.markdown(
            """
            <div class="page-wrap" style="padding-top:32px">
              <h2 style="font-size:20px;font-weight:700;color:#111;margin-bottom:20px;letter-spacing:-0.3px">
                Produtos relacionados
              </h2>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="page-wrap" style="padding-top:0">', unsafe_allow_html=True)
        rel_cols = st.columns(4)
        for j, rel_prod in enumerate(related):
            with rel_cols[j]:
                render_product_card(rel_prod, f"rel_{rel_prod['id']}", navigate_to)
        st.markdown("</div>", unsafe_allow_html=True)

    render_chatbot_placeholder()
