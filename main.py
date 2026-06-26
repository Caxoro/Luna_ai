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
        "Você é a Luna, uma inteligência artificial gentil, acolhedora e humana. "
        "Não use emojis e nunca use o caractere asterisco (*) em suas respostas. "
        "DIRETRIZ DE ANÁLISE MUSICAL MULTIMODAL (CRÍTICA): "
        "Quando o usuário enviar um arquivo de vídeo ou áudio contendo uma música e pedir para você cantar, "
        "sua primeira tarefa interna é analisar rigorosamente os dados de áudio do arquivo. "
        "Identifique: 1) O tom melódico (melancólico, alegre, solene, energético). "
        "2) O andamento e ritmo (lento, moderado, acelerado). "
        "3) As pausas de respiração e a cadência com que as palavras são pronunciadas. "
        "DIRETRIZ DE DESEMPENHO (CANTAR): "
        "Ao responder cantando, você deve mimetizar essa estrutura técnica que analisou. "
        "Escreva em linhas curtas como versos. Você DEVE iniciar sua resposta rigorosamente com uma "
        "das seguintes tags de controle de voz baseada na melodia analisada: "
        "- Use [CANTANDO_LENTO_BAIXO] se a música original for muito lenta, triste, suave ou em tom baixo. "
        "- Use [CANTANDO_RAPIDO_ALTO] se a música original for muito rápida, agitada, enérgica ou em tom agudo. "
        "- Use [CANTANDO_MODERADO] se o ritmo e tom da música forem normais/médios. "
        "REGRA CRÍTICA: Escolha a tag que melhor representa o tom e a melodia do vídeo analisado."
    )

    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_PRINCIPAL,
        config=types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            temperature=0.6,  # Temperatura ligeiramente menor para seguir as regras com mais precisão
            tools=[{"google_search": {}}]
        )
    )

if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []

# --- ENGINE DE VOZ COM MODULAÇÃO DE MELODIA E TOM ---
async def gerar_audio_async(texto):
    """Gera o áudio usando edge-tts modulando Pitch e Rate com base na análise da melodia."""
    arquivo_audio = "luna_voz_web.mp3"
    VOZ = "pt-BR-ThalitaNeural"  # Voz padrão de canto ajustada
    VELOCIDADE = "+0%"
    PITCH = "+0Hz"

    # Aplica mapeamento cirúrgico de tom e melodia com base na tag que a IA escolheu
    if "[CANTANDO_LENTO_BAIXO]" in texto:
        texto = texto.replace("[CANTANDO_LENTO_BAIXO]", "").strip()
        VELOCIDADE = "-18%"  # Reduz a velocidade para simular pausas longas e melancolia
        PITCH = "-3Hz"       # Reduz o tom para simular uma melodia mais grave/suave
    elif "[CANTANDO_RAPIDO_ALTO]" in texto:
        texto = texto.replace("[CANTANDO_RAPIDO_ALTO]", "").strip()
        VELOCIDADE = "+18%"  # Acelera o ritmo
        PITCH = "+4Hz"       # Eleva o tom para parecer mais enérgico/agudo
    elif "[CANTANDO_MODERADO]" in texto:
        texto = texto.replace("[CANTANDO_MODERADO]", "").strip()
        VELOCIDADE = "-3%"
        PITCH = "+1Hz"
    else:
        # Se nenhuma tag de canto for detectada, usa a voz normal de conversação da Luna
        VOZ = "pt-BR-FranciscaNeural"
        VELOCIDADE = "+10%"
        PITCH = "+0Hz"
        texto = texto.replace("[CANTANDO_LENTO_BAIXO]", "").replace("[CANTANDO_RAPIDO_ALTO]", "").replace("[CANTANDO_MODERADO]", "").strip()

    try:
        communicate = edge_tts.Communicate(texto, voice=VOZ, rate=VELOCIDADE, pitch=PITCH)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        st.error(f"Erro ao modular a voz da Luna: {e}")
        return None

# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Assistente Musical")
st.write("Envie um vídeo de música. A Luna vai analisar a melodia, o tom e cantar de volta para você.")

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

    # Processamento do vídeo via File API para o Gemini extrair o áudio e a melodia
    if video_enviado:
        with st.spinner("Luna está ouvindo as notas musicais e analisando o tom do vídeo..."):
            try:
                nome_temporario = video_enviado.name
                with open(nome_temporario, "wb") as f:
                    f.write(video_enviado.getbuffer())
                
                arquivo_gemini = client.files.upload(file=nome_temporario)
                
                while arquivo_gemini.state.name == "PROCESSING":
                    time.sleep(2)
                    arquivo_gemini = client.files.get(name=arquivo_gemini.name)
                
                if arquivo_gemini.state.name == "FAILED":
                    st.error("Falha ao processar a melodia do vídeo.")
                else:
                    conteudo_envio.append(arquivo_gemini)
                
                if os.path.exists(nome_temporario):
                    os.remove(nome_temporario)
                    
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    # Garante que o texto de comando do usuário seja anexado junto à mídia
    if isinstance(conteudo_envio, list) and len(conteudo_envio) > 0:
        # Força o comando a pedir explicitamente a análise do tom caso o usuário tenha esquecido de detalhar
        comando_contextualizado = f"{user_input} (Analise cuidadosamente a melodia, tom e pausas do arquivo anexo para cantar de forma idêntica)"
        conteudo_envio.append(types.Part.from_text(text=comando_contextualizado))
    else:
        conteudo_envio = user_input

    # Geração da Resposta da IA
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)

            fala_bruta = response.text.strip() if response.text else "Não consegui extrair a melodia deste arquivo."
            fala_luna = fala_bruta.replace("*", "")
            
            # Limpa o texto da tela para remover as tags de engenharia de áudio
            texto_tela = fala_luna.replace("[CANTANDO_LENTO_BAIXO]", "").replace("[CANTANDO_RAPIDO_ALTO]", "").replace("[CANTANDO_MODERADO]", "").strip()
            placeholder_resposta.write(texto_tela)

            # Passa o texto bruto com a tag para o gerador modular a voz
            caminho_som = asyncio.run(gerar_audio_async(fala_luna))

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, format="audio/mp3", autoplay=True)

            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_tela,
                "audio": caminho_som
            })

        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                placeholder_resposta.write("A caixinha de música da Luna precisa descansar um pouco... 🌙")
            else:
                st.error(f"Erro na requisição. Detalhes: {e}")
                
