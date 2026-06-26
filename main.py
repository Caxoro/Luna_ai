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
    MINHA_CHAVE_API = NOVA_CHAVE_GENERADA

MODELO_PRINCIPAL = "gemini-2.5-flash"

@st.cache_resource
def obter_cliente_gemini():
    return genai.Client(api_key=MINHA_CHAVE_API)

client = obter_cliente_gemini()

# Inicializa o chat na sessão do navegador
if "chat_gemini" not in st.session_state:
    instrucao_sistema = (
        "Você é a Luna, uma inteligência artificial gentil, acolhedora e altamente musical. "
        "Não use emojis e nunca use o caractere asterisco (*) em suas respostas. "
        "DIRETRIZ DE ANÁLISE MULTIMODAL E RITMO: "
        "Quando o usuário enviar um vídeo/áudio de música, analise profundamente o andamento, o tom e o ritmo. "
        "Como seu sistema de voz é baseado em texto, você DEVE fazer uma engenharia reversa na letra para que a engine de voz simule o canto real. "
        "REGRAS DE FORMATAÇÃO DE CANTO (CRÍTICAS): "
        "1. Escreva em versos muito curtos (linhas pequenas). "
        "2. Use reticências (...) entre as palavras onde o cantor original estica a nota ou faz uma pausa dramática. "
        "3. Use hífen (-) para separar sílabas de palavras que são cantadas de forma prolongada (Ex: A-mo-oo-oor). "
        "4. Use pontos finais (.) ou exclamações (!) apenas no fim de frases rítmicas para forçar a parada da voz. "
        "5. Você DEVE começar sua resposta estritamente com uma destas três tags para controlar a velocidade do canto: "
        "   - [CANTANDO_LENTO] se a música for calma, melancólica ou balada acústica. "
        "   - [CANTANDO_RAPIDO] se a música for pop, rock, rap ou muito agitada. "
        "   - [CANTANDO_MODERADO] para ritmos médios e convencionais."
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

# --- ENGINE DE VOZ GRATUITA OTIMIZADA PARA RITMO ---
async def gerar_audio_async(texto_bruto):
    """Gera o áudio usando edge-tts com modulação agressiva de tempo e pitch para simular canto."""
    arquivo_audio = "luna_voz_web.mp3"
    VOZ = "pt-BR-ThalitaNeural"  # Voz mais expressiva e jovem para cantar
    VELOCIDADE = "+0%"
    PITCH = "+0Hz"

    # Define os parâmetros base de velocidade e tom com base no ritmo determinado pelo Gemini
    if "[CANTANDO_LENTO]" in texto_bruto:
        texto = texto_bruto.replace("[CANTANDO_LENTO]", "").strip()
        VELOCIDADE = "-20%"  # Reduz bem a velocidade para as pausas (...) surtirem efeito de canto lento
        PITCH = "+1Hz"
    elif "[CANTANDO_RAPIDO]" in texto_bruto:
        texto = texto_bruto.replace("[CANTANDO_RAPIDO]", "").strip()
        VELOCIDADE = "+20%"  # Acelera o fluxo rítmico
        PITCH = "+4Hz"       # Sobe o tom para dar mais energia
    elif "[CANTANDO_MODERADO]" in texto_bruto:
        texto = texto_bruto.replace("[CANTANDO_MODERADO]", "").strip()
        VELOCIDADE = "-5%"
        PITCH = "+2Hz"
    else:
        # Voz de fala normal da Luna
        VOZ = "pt-BR-FranciscaNeural"
        VELOCIDADE = "+10%"
        PITCH = "+0Hz"
        texto = texto_bruto.replace("[CANTANDO_LENTO]", "").replace("[CANTANDO_RAPIDO]", "").replace("[CANTANDO_MODERADO]", "").strip()

    try:
        # O Edge-TTS respeitará as quebras de linha, hífens e reticências gerados estrategicamente pela IA
        communicate = edge_tts.Communicate(texto, voice=VOZ, rate=VELOCIDADE, pitch=PITCH)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        st.error(f"Erro ao gerar a voz da Luna: {e}")
        return None

# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Assistente Musical")
st.write("Anexe uma música e a Luna adaptará o ritmo e as pausas com precisão para cantar de volta!")

for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

with st.sidebar:
    st.header("Upload de Mídia")
    video_enviado = st.file_uploader("Anexe o vídeo/áudio da música aqui:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])

if user_input := st.chat_input("Peça para a Luna analisar o ritmo e cantar..."):

    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    conteudo_envio = []
    caminho_local_midia = None

    if video_enviado:
        with st.spinner("Luna está escutando atentamente o ritmo e as pausas da música..."):
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
        comando_contextualizado = (
            f"{user_input} (Analise cirurgicamente o tempo, melodia e pausas do arquivo anexo. "
            f"Escreva o texto final usando a formatação de pontuação rítmica com hífens e reticências para mimetizar o canto original)."
        )
        conteudo_envio.append(types.Part.from_text(text=comando_contextualizado))
    else:
        conteudo_envio = user_input

    # Geração da Resposta da IA
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)

            fala_bruta = response.text.strip() if response.text else "Não consegui extrair o ritmo deste arquivo."
            fala_luna = fala_bruta.replace("*", "")
            
            # Limpa apenas as tags de velocidade na tela, deixando as pontuações rítmicas visíveis para o usuário notar a métrica da música
            texto_tela = fala_luna.replace("[CANTANDO_LENTO]", "").replace("[CANTANDO_RAPIDO]", "").replace("[CANTANDO_MODERADO]", "").strip()
            placeholder_resposta.write(texto_tela)

            # Passa o texto bruto com as reticências e hífens para a síntese de voz
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
            st.error(f"Erro na requisição. Detalhes: {e}")
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
                
