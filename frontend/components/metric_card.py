import streamlit as st

def metric_card(label, value, change=None, icon="📊", color="accent", description=None):
    """
    Display a metric card with label, value, optional change indicator, and description.

    Args:
        label: The metric label
        value: The metric value
        change: Optional change indicator (e.g., "+12%" or "-5%")
        icon: Optional emoji icon
        color: Color context ("accent", "success", "warning", "danger")
        description: Optional short explanation shown below the value
    """

    change_color = ""
    if change:
        if change.startswith("+"):
            change_color = "color: #10B981"
        elif change.startswith("-"):
            change_color = "color: #EF4444"

    desc_html = (
        f'<p style="color:#9CA3AF;font-size:11px;margin:6px 0 0 0;line-height:1.4;">{description}</p>'
        if description else ""
    )

    card_html = f"""
    <div style="
        background-color: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 10px;
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="flex: 1;">
                <p style="color: #6B7280; font-size: 14px; margin: 0 0 8px 0; font-weight: 500;">
                    {label}
                </p>
                <p style="color: #111827; font-size: 32px; margin: 0; font-weight: 700;">
                    {value}
                </p>
                {f'<p style="{change_color}; font-size: 14px; margin: 8px 0 0 0; font-weight: 500;">{change}</p>' if change else ''}
                {desc_html}
            </div>
            <div style="font-size: 32px;">
                {icon}
            </div>
        </div>
    </div>
    """

    st.html(card_html)


def small_metric(label, value, suffix=""):
    """Display a smaller metric inline."""
    html = f"""
    <div style="
        background-color: #F7F8FA;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
    ">
        <p style="color: #6B7280; font-size: 12px; margin: 0; font-weight: 500;">
            {label}
        </p>
        <p style="color: #111827; font-size: 20px; margin: 4px 0 0 0; font-weight: 700;">
            {value}{suffix}
        </p>
    </div>
    """
    st.html(html)
