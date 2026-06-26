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

MODELO_CEREBRO = "gemini-2.5-flash"
# Modelo especialista do Google para sintetizar voz nativa avançada
MODELO_VOZ_NATIVA = "gemini-2.5-flash" 

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
        "Quando o usuário enviar um vídeo ou áudio contendo uma música e pedir para você cantar, "
        "sua tarefa é analisar os dados do arquivo: a melodia, o ritmo, as pausas e as emoções contidas. "
        "DIRETRIZ DE ESCRITA DE CANTO: "
        "Ao responder cantando, escreva a letra de forma limpa, natural e corrida. "
        "Ajuste o vocabulário para expressar exatamente o mesmo sentimento da música analisada (tristeza, alegria, calmaria). "
        "Sua resposta textual será convertida em ondas de áudio nativas reais, então crie versos fluidos."
    )

    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_CEREBRO,
        config=types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            temperature=0.7,
            tools=[{"google_search": {}}]
        )
    )

if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []

# --- SÍNTESE DE ÁUDIO NATIVA DO GOOGLE ---
def gerar_audio_nativo_gemini(texto_para_cantar, instrucao_musical):
    """Utiliza o motor generativo de áudio do Google para vocalizar as estrofes."""
    arquivo_audio = "luna_canto_nativo.wav"
    try:
        # Prompt de engenharia acústica focado em fazer o sintetizador cantar
        prompt_voz = (
            f"Vocalize o seguinte texto cantando de forma expressiva: '{texto_para_cantar}'. "
            f"Contexto rítmico obrigatório: {instrucao_musical}. "
            f"Imite o andamento, as pausas de respiração e a melodia descrita."
        )
        
        # Executa a geração usando a inteligência de áudio da nuvem do Google
        response = client.models.generate_content(
            model=MODELO_VOZ_NATIVA,
            contents=prompt_voz,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"], # Solicita estritamente o retorno em áudio
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Aoede" # Voz expressiva do catálogo do Gemini
                        )
                    )
                )
            )
        )
        
        # Varre o payload de resposta para extrair o binário do áudio gerado
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("audio"):
                    with open(arquivo_audio, "wb") as f:
                        f.write(part.inline_data.data)
                    return arquivo_audio
                    
        return None
    except Exception as e:
        st.error(f"Erro na síntese de áudio do Google: {e}")
        return None

# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Voz Nativa Gemini")
st.write("Anexe uma música. O Gemini analisará a estrutura rítmica e cantará de volta usando o motor de áudio nativo do Google!")

for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"])

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
        with st.spinner("Luna está enviando o arquivo para a nuvem do Google mapear a melodia..."):
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
            f"{user_input} (Analise cirurgicamente o andamento, tom e pausas do arquivo anexo. "
            f"Gere a letra adaptada para que eu possa enviar ao seu sintetizador de voz)."
        )
        conteudo_envio.append(types.Part.from_text(text=comando_contextualizado))
    else:
        conteudo_envio = user_input

    # Geração da Resposta da IA
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            # 1. O cérebro do Gemini analisa o vídeo e gera o texto/letra
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)
            texto_tela = response.text.strip() if response.text else "Cantando para você..."
            texto_tela = texto_tela.replace("*", "")
            placeholder_resposta.write(texto_tela)

            caminho_som = None

            # Contexto padrão de canto caso não tenha enviado arquivo de referência
            instrucao_musical = "Cante com ritmo melódico e entonação suave de música."
            
            # Se o usuário enviou um vídeo, pedimos para a IA formular um metadado rítmico descritivo
            if caminho_local_midia:
                instrucao_musical = (
                    f"Cante reproduzindo fielmente o andamento, o tom emocional e as pausas "
                    f"técnicas identificadas no arquivo de vídeo anexado anteriormente."
                )

            # 2. O motor especialista em áudio do Google gera a voz cantada nativa com base no texto e nas diretrizes rítmicas
            with St.spinner("Luna está utilizando o motor generativo de áudio do Google para cantar..."):
                caminho_som = gerar_audio_nativo_gemini(texto_tela, instrucao_musical)

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, autoplay=True)

            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_tela,
                "audio": caminho_som
            })

        except Exception as e:
            st.error(f"Erro na requisição geral: {e}")
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
                
