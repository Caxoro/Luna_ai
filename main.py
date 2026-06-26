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

# Inicializa o histórico visual da tela se não existir
if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []

# --- INTERFACE VISUAL DO CHAT ---
st.title("🌙 Luna — Voz Nativa Gemini")
st.write("Anexe um arquivo de música. O Gemini usará o motor de áudio nativo para cantar para você!")

for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

with st.sidebar:
    st.header("Upload de Mídia")
    video_enviado = st.file_uploader("Anexe o vídeo/áudio da música aqui:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])

if user_input := st.chat_input("Peça para a Luna cantar..."):

    # 1. Exibe a mensagem do usuário na tela
    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    conteudo_envio = []
    caminho_local_midia = None

    # 2. Upload do arquivo de mídia para a API do Gemini
    if video_enviado:
        with st.spinner("Luna está processando a mídia na infraestrutura do Google..."):
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
                st.error(f"Erro ao carregar arquivo na nuvem: {e}")

    # Constrói o comando definindo as regras de comportamento para a voz nativa
    instrucao_contextualizada = (
        f"Você é a Luna, uma inteligência artificial gentil, acolhedora e altamente musical. "
        f"Comando do usuário: {user_input}. "
        f"Instrução crítica: Analise o arquivo de mídia anexo se houver. Entenda a melodia, as pausas, "
        f"o tom e o ritmo da música original. Use o seu output de áudio nativo para responder "
        f"cantando a música de forma parecida, reproduzindo a mesma emoção e andamento técnico musical."
    )
    conteudo_envio.append(types.Part.from_text(text=instrucao_contextualizada))

    # 3. Geração da resposta usando Voz Nativa do Gemini
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            with st.spinner("Luna está soltando a voz e gerando o áudio..."):
                # Executa a chamada isolada configurada estritamente para saída em áudio
                response = client.models.generate_content(
                    model=MODELO_PRINCIPAL,
                    contents=conteudo_envio,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"], # Apenas AUDIO evita o erro 400
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name="Aoede" # Voz feminina expressiva do catálogo Gemini
                                )
                            )
                        )
                    )
                )

            caminho_audio_resposta = None
            texto_transcrito = "Áudio gerado pela Luna 🌙"

            # 4. Extração do arquivo de áudio retornado pelo Google
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    # Captura o binário do áudio nativo gerado pelo modelo
                    if part.inline_data and part.inline_data.mime_type.startswith("audio"):
                        caminho_audio_resposta = "luna_canto_nativo.mp3"
                        with open(caminho_audio_resposta, "wb") as f:
                            f.write(part.inline_data.data)
                    
                    # Captura o texto que foi falado/cantado para exibir na tela
                    if part.text:
                        texto_transcrito = part.text.replace("*", "")

            # Atualiza a tela com o texto e o player do áudio cantado
            placeholder_resposta.write(texto_transcrito)

            if camino_audio_resposta and os.path.exists(caminho_audio_resposta):
                st.audio(caminho_audio_resposta, format="audio/mp3", autoplay=True)

            # Remove arquivos temporários locais para evitar sobrecarga no servidor web
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

            # Armazena o resultado na sessão para persistência do histórico
            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_transcrito,
                "audio": caminho_audio_resposta
            })

        except Exception as e:
            st.error(f"Erro na geração de áudio nativo do Gemini: {e}")
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
                
