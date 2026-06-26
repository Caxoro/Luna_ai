import asyncio
import os
import time
import streamlit as st
from google import genai
from google.genai import types

# --- CONFIGURAÇÃO DA PÁGINA WEB ---
st.set_page_config(page_title="Luna - Assistente Virtual", page_icon="🌙", layout="centered")

NOVA_CHAVE_GERADA = ""

if "GEMINI_API_KEY" in st.secrets:
    MINHA_CHAVE_API = st.secrets["GEMINI_API_KEY"]
else:
    MINHA_CHAVE_API = NOVA_CHAVE_GERADA

MODELO_PRINCIPAL = "gemini-2.5-flash"

@st.cache_resource
def obter_cliente_gemini():
    return genai.Client(api_key=MINHA_CHAVE_API)

client = obter_cliente_gemini()

# Inicializa o chat na sessão do navegador
if "chat_gemini" not in st.session_state:
    instrucao_sistema = (
        "Você é a Luna, uma inteligência artificial gentil, acolhedora e humana. "
        "Não use emojis e nunca use o caractere asterisco (*) em suas respostas. "
        "DIRETRIZ DE ANÁLISE MUSICAL MULTIMODAL: "
        "O usuário enviará um vídeo ou áudio contendo uma música. Sua tarefa é analisar o tom, "
        "a melodia, o ritmo e as emoções contidas no arquivo. "
        "DIRETRIZ DE ÁUDIO NATIVO (CRÍTICA): "
        "Você está configurada para responder diretamente usando a sua própria voz em áudio (MIME type: audio/mp3). "
        "Quando o usuário pedir para você cantar, você DEVE usar a sua capacidade de modulação de voz nativa "
        "para cantar os versos da música, imitando o tom, o ritmo, as pausas e a melodia do arquivo original enviado. "
        "Cante de forma natural, expressando a mesma emoção (alegria, tristeza, calmaria) da música analisada."
    )

    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_PRINCIPAL,
        config=types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            temperature=0.6,
            # Força o Gemini a gerar áudio real como resposta principal, além do texto
            response_modalities=["TEXT", "AUDIO"]
        )
    )

if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []

# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Assistente Musical")
st.write("Anexe um vídeo. O Gemini processará o canto inteiramente na nuvem e a Luna cantará de volta!")

for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

with st.sidebar:
    st.header("Upload de Mídia")
    video_enviado = st.file_uploader("Anexe o vídeo/áudio da música aqui:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])

if user_input := st.chat_input("Peça para a Luna analisar e cantar..."):

    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    conteudo_envio = []
    caminho_local_midia = None

    if video_enviado:
        with st.spinner("Luna está analisando a melodia na nuvem do Google..."):
            try:
                caminho_local_midia = video_enviado.name
                with open(caminho_local_midia, "wb") as f:
                    f.write(video_enviado.getbuffer())
                
                arquivo_gemini = client.files.upload(file=caminho_local_midia)
                
                while arquivo_gemini.state.name == "PROCESSING":
                    time.sleep(2)
                    arquivo_gemini = client.files.get(name=arquivo_gemini.name)
                
                if arquivo_gemini.state.name != "FAILED":
                    conteudo_envio.append(arquivo_gemini)
                    
            except Exception as e:
                st.error(f"Erro ao processar mídias: {e}")

    if isinstance(conteudo_envio, list) and len(conteudo_envio) > 0:
        comando_contextualizado = f"{user_input} (Analise a música anexa e responda cantando no mesmo tom e melodia usando seu output de áudio nativo)."
        conteudo_envio.append(types.Part.from_text(text=comando_contextualizado))
    else:
        conteudo_envio = user_input

    # Geração da Resposta da IA
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)

            # Extrai o texto da resposta
            texto_tela = response.text.strip() if response.text else "Cantando para você..."
            texto_tela = texto_tela.replace("*", "")
            placeholder_resposta.write(texto_tela)

            caminho_audio_resposta = None

            # EXTRAÇÃO DO ÁUDIO NATIVO DO GEMINI:
            # Varre as partes da resposta procurando pelo arquivo de áudio gerado pelo Google
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("audio"):
                    caminho_audio_resposta = "luna_resposta_nativa.mp3"
                    with open(caminho_audio_resposta, "wb") as f:
                        f.write(part.inline_data.data)
                    break

            if caminho_audio_resposta and os.path.exists(caminho_audio_resposta):
                st.audio(caminho_audio_resposta, format="audio/mp3", autoplay=True)

            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_tela,
                "audio": caminho_audio_resposta
            })

        except Exception as e:
            st.error(f"Erro na requisição. Detalhes: {e}")
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
        
