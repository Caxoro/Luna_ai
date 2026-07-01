import asyncio
import os
import time
import edge_tts
import streamlit as st
import numpy as np
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


# --- DETECÇÃO ISOLADA E DINÂMICA DE BLUETOOTH ---
def verificar_ambiente_e_bluetooth() -> bool:
    """
    Verifica se o app está rodando localmente e possui uma porta Bluetooth ativa.
    Os imports são feitos internamente para que o Streamlit Cloud nunca quebre.
    """
    try:
        # Importa dinamicamente a ferramenta de escaneamento de portas
        import serial.tools.list_ports
        
        portas_disponiveis = serial.tools.list_ports.comports()
        for porta in portas_disponiveis:
            nome_porta = porta.description.lower()
            hwid_porta = porta.hwid.lower()
            
            # Detecta barramentos e identificadores padrão de Bluetooth (Windows/Linux/Mac)
            if "bluetooth" in nome_porta or "bthenum" in hwid_porta or "rfcomm" in nome_porta:
                # Se achou o Bluetooth, importa as bibliotecas de automação apenas neste momento
                global cv2, mss, pyautogui
                import cv2
                import mss
                import pyautogui
                pyautogui.FAILSAFE = True
                return True
        return False
    except Exception:
        # Qualquer falha de import ou ambiente (como na nuvem) desativa a automação com segurança
        return False


# --- FUNÇÕES DE SUPORTE DE TELA E MOUSE (SÓ AGEM SE O BT FOR DETECTADO) ---
def capturar_tela_local():
    """Captura a tela apenas se o ecossistema Bluetooth local estiver validado."""
    if not ST_BLUETOOTH_ATIVO:
        return None
    try:
        with mss.mss() as sct:
            monitor = sct.monitors
            screenshot = sct.grab(monitor)
            img = np.array(screenshot)
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            img_redimensionada = cv2.resize(img_bgr, (1024, 768))
            _, buffer = cv2.imencode('.jpg', img_redimensionada)
            return buffer.tobytes()
    except Exception:
        return None


def executar_comando_local(comando: str):
    """Executa a automação de hardware via Bluetooth de forma isolada."""
    if not ST_BLUETOOTH_ATIVO:
        return
    try:
        if "MOUSE:" in comando:
            dados = comando.replace("MOUSE:", "").strip()
            x, y = map(int, dados.split(","))
            pyautogui.moveTo(x, y, duration=0.4)
            pyautogui.click()
        elif "TECLADO:" in comando:
            texto = comando.replace("TECLADO:", "").strip()
            pyautogui.write(texto, interval=0.05)
    except Exception:
        pass


# --- ENGINE DE VOZ (FRANCISCA - EDGE-TTS) ---
async def gerar_audio_async(texto):
    """Gera o arquivo de áudio utilizando edge-tts com a voz da Francisca."""
    arquivo_audio = "luna_voz_web.mp3"
    VOZ = "pt-BR-FranciscaNeural"
    VELOCIDADE = "+10%"
    PITCH = "+0Hz"

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


# --- INTERFACE VISUAL DA WEB ---
st.title("🌙 Luna — Assistente Virtual")

# Executa a verificação dinâmica ao carregar a página
ST_BLUETOOTH_ATIVO = verificar_ambiente_e_bluetooth()

if ST_BLUETOOTH_ATIVO:
    st.success("Conexão Bluetooth Ativa! Controle do computador habilitado via hardware.")
else:
    st.info("Modo Nuvem Isolado: Sem conexões Bluetooth locais. Rodando em modo de conversa normal.")

st.write("Converse com a Luna, envie imagens ou anexe arquivos de vídeo e áudio!")

# Inicializa o histórico visual da tela se não existir
if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []

# Exibe o histórico de mensagens na tela
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

# Entrada de texto do Chat
if user_input := st.chat_input("Digite sua mensagem para a Luna..."):

    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    texto_envio = user_input
    conteudo_envio = []
    caminho_local_midia = None

    # Captura a tela em tempo real APENAS se o ecossistema Bluetooth local foi ativado e importado
    frame_tempo_real = capturar_tela_local()
    if frame_tempo_real:
        conteudo_envio.append(types.Part.from_bytes(data=frame_tempo_real, mime_type="image/jpeg"))
        texto_envio = (
            f"O usuário enviou este comando: '{user_input}'. "
            "Analise a imagem da sua tela em tempo real anexada e aja de acordo. "
            "Se precisar clicar, responda apenas 'MOUSE:X,Y'. Se precisar digitar, responda 'TECLADO:texto'. "
            "Se for apenas uma conversa comum ou a ação já terminou, responda normalmente por texto."
        )

    if video_enviado:
        with st.spinner("Luna está carregando o arquivo de mídia..."):
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

    if imagem_enviada:
        try:
            bytes_imagem = imagem_enviada.read()
            conteudo_envio.append(types.Part.from_bytes(data=bytes_imagem, mime_type="image/jpeg"))
        except Exception:
            st.error("Erro ao carregar o arquivo de imagem enviado.")

    if isinstance(conteudo_envio, list) and len(conteudo_envio) > 0:
        conteudo_envio.append(types.Part.from_text(text=texto_envio))
    else:
        conteudo_envio = texto_envio

    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)
            fala_bruta = response.text.strip() if response.text else "Desculpe, não consegui processar isso."
            
            if ST_BLUETOOTH_ATIVO and ("MOUSE:" in fala_bruta or "TECLADO:" in fala_bruta):
                executar_comando_local(fala_bruta)
                fala_luna = "Comando Bluetooth executado com sucesso na sua máquina local!"
            else:
                fala_luna = fala_bruta.replace("*", "")
                
            texto_tela = fala_luna.replace("[CANTANDO]", "").strip()
            placeholder_resposta.write(texto_tela)

            caminho_som = asyncio.run(gerar_audio_async(fala_luna))

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, format="audio/mp3", autoplay=True)

            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

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
                
