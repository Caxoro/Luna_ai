import asyncio
import os
import time
import edge_tts
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


# Inicializa o cliente do Gemini
@st.cache_resource
def obter_cliente_gemini():
    return genai.Client(api_key=MINHA_CHAVE_API)


client = obter_cliente_gemini()

# Inicializa o chat na sessão do navegador para manter o histórico
if "chat_gemini" not in st.session_state:
    instrucao_sistema = (
        "Você é a Luna. Uma inteligência artificial gentil, acolhedora, doce e humana. "
        "Sempre responda com carinho, empatia e muita educação. "
        "Você pode falar usando gírias e linguagem informal, mas não use emojis. "
        "Se o usuário enviar uma imagem ou um arquivo de vídeo/áudio, analise-o com atenção e descreva o que vê/ouve de forma natural. "
        "ANÁLISE DE MÚSICA: Caso o usuário envie um arquivo de vídeo ou áudio contendo uma música e peça para você cantar, "
        "analise atentamente as entonações, pausas, formas de falar e a emoção da música para tentar replicar esse sentimento na escrita. "
        "HABILIDADE DE CANTAR: Se o usuário pedir para você cantar, mude seu estilo de escrita para linhas curtas, "
        "como versos de uma música. Comece a resposta da música estritamente com a palavra [CANTANDO] para que o sistema saiba "
        "mudar o tom da sua voz. "
        "REGRA CRÍTICA DE FORMATAÇÃO: Nunca use o caractere asterisco (*) em suas respostas. Escreva texto limpo."
    )

    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_PRINCIPAL,
        config=types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            temperature=0.85,
            tools=[{"google_search": {}}]
        )
    )

# Inicializa o histórico visual da tela
if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []


# --- ENGINE DE VOZ (FRANCISCA) ---
async def gerar_audio_async(texto):
    """Gera o arquivo de áudio utilizando edge-tts com a voz da Francisca."""
    arquivo_audio = "luna_voz_web.mp3"
    VOZ = "pt-BR-FranciscaNeural"
    VELOCIDADE = "+10%"
    PITCH = "+0Hz"

    # Se a Luna incluiu o marcador de canto, altera a velocidade e a afinação da Francisca
    if "[CANTANDO]" in texto:
        texto = texto.replace("[CANTANDO]", "").strip()
        VELOCIDADE = "-5%"
        PITCH = "+2Hz"
    else:
        texto = texto.replace("[CANTANDO]", "").strip()

    try:
        communicate = edge_tts.Communicate(texto, voice=VOZ, rate=VELOCIDADE, pitch=PITCH)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        st.error(f"Erro ao gerar a voz da Luna: {e}")
        return None


# --- INTERFACE VISUAL DA WEB (ESTILO WHATSAPP/CHAT) ---
st.title("🌙 Luna — Assistente Virtual")
st.write("Converse com a Luna, envie imagens ou anexe arquivos de vídeo e áudio!")

# Exibe o histórico de mensagens na tela com estilo nativo de chat
for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

# Componentes de entrada lateral (Upload de Mídia)
with st.sidebar:
    st.header("Configurações e Anexos")
    imagem_enviada = st.file_uploader("Anexe uma imagem para a Luna ver:", type=["jpg", "jpeg", "png", "webp"])
    video_enviado = st.file_uploader("Anexe um arquivo de vídeo ou áudio musical:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])
    
    if st.button("🔄 Reiniciar Contexto", use_container_width=True):
        st.session_state.chat_gemini = client.chats.create(
            model=MODELO_PRINCIPAL,
            config=types.GenerateContentConfig(
                system_instruction=instrucao_sistema,
                temperature=0.85,
                tools=[{"google_search": {}}]
            )
        )
        st.session_state.historico_mensagens = []
        st.success("Histórico limpo com sucesso!")
        st.rerun()

# Entrada de texto do Chat estilo mobile
if user_input := st.chat_input("Digite sua mensagem para a Luna..."):

    # 1. Exibe a mensagem do usuário imediatamente na tela
    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    texto_envio = user_input
    conteudo_envio = []
    caminho_local_midia = None

    # Processa arquivo de vídeo/áudio se houver usando a File API do Gemini
    if video_enviado:
        with st.spinner("Luna está carregando o arquivo de mídia..."):
            try:
                caminho_local_midia = video_enviado.name
                with open(caminho_local_midia, "wb") as f:
                    f.write(video_enviado.getbuffer())
                
                # Envia o vídeo/áudio para os servidores do Gemini
                arquivo_gemini = client.files.upload(file=caminho_local_midia)
                
                while arquivo_gemini.state.name == "PROCESSING":
                    time.sleep(2)
                    arquivo_gemini = client.files.get(name=arquivo_gemini.name)
                
                if arquivo_gemini.state.name != "FAILED":
                    conteudo_envio.append(arquivo_gemini)
            except Exception as e:
                st.error(f"Erro ao processar mídias: {e}")

    # Processa imagem se houver
    if imagem_enviada:
        try:
            bytes_imagem = imagem_enviada.read()
            conteudo_envio.append(types.Part.from_bytes(data=bytes_imagem, mime_type="image/jpeg"))
        except Exception:
            st.error("Erro ao carregar o arquivo de imagem enviado.")

    # Combina o texto com os arquivos anexados
    if isinstance(conteudo_envio, list) and len(conteudo_envio) > 0:
        conteudo_envio.append(types.Part.from_text(text=texto_envio))
    else:
        conteudo_envio = texto_envio

    # 2. Resposta da IA
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            # Envia para a API do Gemini
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)

            fala_bruta = response.text.strip() if response.text else "Desculpe, não consegui processar isso."
            fala_luna = fala_bruta.replace("*", "")
            texto_tela = fala_luna.replace("[CANTANDO]", "").strip()

            # Mostra o texto gerado de forma limpa na tela
            placeholder_resposta.write(texto_tela)

            # Gera o áudio correspondente usando a voz modificada da Francisca
            caminho_som = asyncio.run(gerar_audio_async(fala_luna))

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, format="audio/mp3", autoplay=True)

            # Limpa o arquivo temporário salvo localmente
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

            # Salva no histórico da sessão
            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_tela,
                "audio": caminho_som
            })

        except Exception as e:
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
                
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                aviso = "Poxa... Minha caixinha de pensamentos gastou toda a energia diária por hoje... 🌙"
                placeholder_resposta.write(aviso)
            else:
                st.error(f"Erro na requisição. Detalhes: {e}")
                
