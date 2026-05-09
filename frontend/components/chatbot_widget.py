import streamlit as st


def render_chatbot_placeholder():
    # TODO: Wire to RAG pipeline in chatbot/rag_pipeline.py —
    # replace placeholder popup with actual chat interface using st.dialog or custom panel.
    st.markdown("""
    <button class="chat-fab" onclick="toggleChat()" id="chatFab" title="AI Assistant">
      💬
    </button>

    <div class="chat-popup" id="chatPopup">
      <button class="chat-close" onclick="toggleChat()">✕</button>
      <div class="chat-popup-hd">
        <div class="chat-popup-avatar">🤖</div>
        <div>
          <div class="chat-popup-name">Olá Market Assistant</div>
          <div class="chat-popup-status">● Online now</div>
        </div>
      </div>
      <div class="chat-popup-msg">
        Hi! I can help you find products, answer questions about orders,
        and much more. How can I help you?
      </div>
      <div class="chat-coming-badge">✨ RAG-powered AI — Coming Soon</div>
    </div>

    <script>
    function toggleChat() {
      const popup = document.getElementById('chatPopup');
      popup.classList.toggle('open');
    }
    </script>
    """, unsafe_allow_html=True)


def render_admin_chatbot_widget():
    """Render floating chatbot widget for admin dashboard."""
    
    widget_html = """
    <style>
        .admin-chatbot-widget {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999;
        }
        
        .admin-chatbot-button {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background-color: #4F46E5;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
            transition: all 0.3s ease;
        }
        
        .admin-chatbot-button:hover {
            background-color: #4338CA;
            box-shadow: 0 6px 16px rgba(79, 70, 229, 0.5);
            transform: scale(1.1);
        }
    </style>
    
    <div class="admin-chatbot-widget">
        <button class="admin-chatbot-button" onclick="alert('Test Mode - Coming Soon\\n\\nIn production, this will open a sandbox chatbot.');" title="Chat with AI">
            💬
        </button>
    </div>
    """
    
    st.markdown(widget_html, unsafe_allow_html=True)
