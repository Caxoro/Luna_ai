import asyncio
import os
import time
import edge_tts
import streamlit as st
from google import genai
from google.genai import types
# Importa o ElevenLabs para o canto idêntico baseado em IA
from elevenlabs.client import ElevenLabs

# --- CONFIGURAÇÃO DA PÁGINA WEB ---
st.set_page_config(page_title="Luna - Assistente Virtual", page_icon="🌙", layout="centered")

# Suas chaves de API
NOVA_CHAVE_GERADA = ""
ELEVENLABS_API_KEY = st.secrets.get("ELEVENLABS_API_KEY", "") # Adicione sua chave nos Secrets do Streamlit
ID_VOZ_LUNA = st.secrets.get("ELEVENLABS_VOICE_ID", "")       # O ID da voz que você clonou ou escolheu para a Luna

if "GEMINI_API_KEY" in st.secrets:
    MINHA_CHAVE_API = st.secrets["GEMINI_API_KEY"]
else:
    MINHA_CHAVE_API = NOVA_CHAVE_GERADA

MODELO_PRINCIPAL = "gemini-2.5-flash"

@st.cache_resource
def obter_cliente_gemini():
    return genai.Client(api_key=MINHA_CHAVE_API)

@st.cache_resource
def obter_cliente_elevenlabs():
    if ELEVENLABS_API_KEY:
        return ElevenLabs(api_key=ELEVENLABS_API_KEY)
    return None

client = obter_cliente_gemini()
client_eleven = obter_cliente_elevenlabs()

# Inicializa o chat na sessão do navegador
if "chat_gemini" not in st.session_state:
    instrucao_sistema = (
        "Você é a Luna, uma inteligência artificial gentil, acolhedora e humana. "
        "Não use emojis e nunca use o caractere asterisco (*) em suas respostas. "
        "DIRETRIZ DE ANÁLISE MUSICAL MULTIMODAL: "
        "Quando o usuário enviar um arquivo de vídeo ou áudio contendo uma música e pedir para você cantar, "
        "analise rigorosamente os dados de áudio do arquivo. Identifique o tom melódico, o ritmo e as pausas de respiração. "
        "DIRETRIZ DE DESEMPENHO (CANTAR): "
        "Escreva sua resposta em formato de versos curtos de música. "
        "Se um arquivo de áudio/vídeo foi fornecido, comece sua resposta rigorosamente com a tag [CANTO_REPLICADO]. "
        "Caso você esteja cantando uma música apenas por texto (sem arquivo de referência), use a tag [CANTANDO_PADRAO]. "
        "Isso avisará o sistema se deve usar o motor de clonagem melódica ou o motor padrão de fala."
    )

    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_PRINCIPAL,
        config=types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            temperature=0.6,
            tools=[{"google_search": {}}]
        )
    )

if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []


# --- ENGINE DE VOZ E CANTO MISTO ---
def gerar_canto_identico_elevenlabs(caminho_audio_original):
    """Utiliza a tecnologia Speech-to-Speech para manter a melodia exata substituindo a voz."""
    if not client_eleven or not ID_VOZ_LUNA:
        return None
    
    arquivo_saida = "luna_canto_identico.mp3"
    try:
        with open(caminho_audio_original, "rb") as audio_file:
            # A API ElevenLabs recebe o áudio original do usuário cantarolando ou da música
            # e re-sintetiza com as mesmas notas, tons e pausas exatas usando a voz da Luna
            audio_gerado = client_eleven.speech_to_speech.convert(
                voice_id=ID_VOZ_LUNA,
                audio=audio_file,
                model_id="eleven_multilingual_sts_v2" # Modelo específico para manter entonação e canto
            )
            
            # Salva o arquivo de áudio cantado
            with open(arquivo_saida, "wb") as f:
                for chunk in audio_gerado:
                    f.write(chunk)
            return arquivo_saida
    except Exception as e:
        st.error(f"Erro na conversão melódica do ElevenLabs: {e}")
        return None


async def gerar_audio_padrao_async(texto):
    """Gera o áudio usando edge-tts gratuito quando for apenas texto falado."""
    arquivo_audio = "luna_voz_web.mp3"
    VOZ = "pt-BR-FranciscaNeural"
    VELOCIDADE = "+10%"
    PITCH = "+0Hz"

    if "[CANTANDO_PADRAO]" in texto:
        texto = texto.replace("[CANTANDO_PADRAO]", "").strip()
        VOZ = "pt-BR-ThalitaNeural"
        VELOCIDADE = "-5%"
        PITCH = "+2Hz"
    else:
        texto = texto.replace("[CANTANDO_PADRAO]", "").strip()

    try:
        communicate = edge_tts.Communicate(texto, voice=VOZ, rate=VELOCIDADE, pitch=PITCH)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        st.error(f"Erro ao gerar a voz padrão da Luna: {e}")
        return None


# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Assistente Musical Avançada")
st.write("Envie um vídeo ou áudio cantado. A Luna cantará de volta usando a melodia e tom exatos da música!")

for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

with st.sidebar:
    st.header("Upload de Mídia")
    video_enviado = st.file_uploader("Anexe o vídeo/áudio da música aqui:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])
    
    if not ELEVENLABS_API_KEY:
        st.warning("⚠️ Chave da ElevenLabs não configurada. A Luna usará a aproximação padrão do Edge-TTS (sem melodia perfeita).")

if user_input := st.chat_input("Peça para a Luna analisar e cantar de forma idêntica..."):

    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    conteudo_envio = []
    caminho_local_midia = None

    # Processamento e salvamento do arquivo local para uso dos dois motores de IA
    if video_enviado:
        with st.spinner("Luna está carregando os dados melódicos do arquivo..."):
            try:
                caminho_local_midia = video_enviado.name
                with open(caminho_local_midia, "wb") as f:
                    f.write(video_enviado.getbuffer())
                
                # Envia para a API do Gemini analisar semanticamente e contextualmente
                arquivo_gemini = client.files.upload(file=caminho_local_midia)
                
                while arquivo_gemini.state.name == "PROCESSING":
                    time.sleep(2)
                    arquivo_gemini = client.files.get(name=arquivo_gemini.name)
                
                if arquivo_gemini.state.name != "FAILED":
                    conteudo_envio.append(arquivo_gemini)
                    
            except Exception as e:
                st.error(f"Erro ao processar mídias: {e}")

    if isinstance(conteudo_envio, list) and len(conteudo_envio) > 0:
        comando_contextualizado = f"{user_input} (A música de referência está anexada. Crie sua resposta adaptada e use a tag adequada para replicação)."
        conteudo_envio.append(types.Part.from_text(text=comando_contextualizado))
    else:
        conteudo_envio = user_input

    # Resposta do Assistente
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)

            fala_bruta = response.text.strip() if response.text else "Não consegui analisar o som."
            fala_luna = fala_bruta.replace("*", "")
            
            texto_tela = fala_luna.replace("[CANTO_REPLICADO]", "").replace("[CANTANDO_PADRAO]", "").strip()
            placeholder_resposta.write(texto_tela)

            caminho_som = None

            # DECISÃO DO MOTOR DE CANTO:
            # Se a IA usou [CANTO_REPLICADO] e temos o arquivo original e a chave configurada
            if "[CANTO_REPLICADO]" in fala_luna and caminho_local_midia and client_eleven:
                with st.spinner("Luna está aquecendo as cordas vocais para clonar a melodia exata da música..."):
                    caminho_som = gerar_canto_identico_elevenlabs(caminho_local_midia)
            
            # Fallback caso não tenha a API Key ou seja uma música sem arquivo de referência
            if not camino_som:
                caminho_som = asyncio.run(gerar_audio_padrao_async(fala_luna))

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, format="audio/mp3", autoplay=True)

            # Limpeza do arquivo temporário local de mídia do usuário
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_tela,
                "audio": caminho_som
            })

        except Exception as e:
            st.error(f"Erro na requisição. Detalhes: {e}")
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
    
