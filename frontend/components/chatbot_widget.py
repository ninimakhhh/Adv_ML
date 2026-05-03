import streamlit as st


def render_chatbot_placeholder():
    # TODO: Wire to RAG pipeline in chatbot/rag_pipeline.py —
    # replace placeholder popup with actual chat interface using st.dialog or custom panel.
    st.markdown("""
    <button class="chat-fab" onclick="toggleChat()" id="chatFab" title="Assistente IA">
      💬
    </button>

    <div class="chat-popup" id="chatPopup">
      <button class="chat-close" onclick="toggleChat()">✕</button>
      <div class="chat-popup-hd">
        <div class="chat-popup-avatar">🤖</div>
        <div>
          <div class="chat-popup-name">Assistente Olá Market</div>
          <div class="chat-popup-status">● Online agora</div>
        </div>
      </div>
      <div class="chat-popup-msg">
        Olá! Posso ajudá-lo a encontrar produtos, responder a perguntas sobre encomendas
        e muito mais. Como posso ajudar?
      </div>
      <div class="chat-coming-badge">✨ IA com RAG — Brevemente</div>
    </div>

    <script>
    function toggleChat() {
      const popup = document.getElementById('chatPopup');
      popup.classList.toggle('open');
    }
    </script>
    """, unsafe_allow_html=True)
