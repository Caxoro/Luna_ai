import asyncio
import os
import time
import re
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

@st.cache_resource
def obter_cliente_gemini():
    return genai.Client(api_key=MINHA_CHAVE_API)

client = obter_cliente_gemini()

# Inicializa o chat na sessão do navegador
if "chat_gemini" not in st.session_state:
    instrucao_sistema = (
        "Você é a Luna, uma inteligência artificial gentil, acolhedora, doce e humana. "
        "Não use emojis e nunca use o caractere asterisco (*) em suas respostas. "
        "DIRETRIZ DE ANÁLISE MUSICAL MULTIMODAL: "
        "Quando o usuário enviar um vídeo ou áudio de música e pedir para você cantar, "
        "analise o ritmo, a melodia, as pausas de respiração e a emoção contida na faixa. "
        "DIRETRIZ DE FORMATAÇÃO DE CANTO (SSML MANDATÓRIO): "
        "Para cantar de forma parecida com a música sem ler códigos ou picotar a voz, você DEVE estruturar "
        "a sua resposta estritamente usando marcações SSML válidas. Siga rigorosamente este padrão: "
        "1. Envolva toda a sua resposta estritamente dentro das tags <speak> e </speak>. "
        "2. Se for fazer um comentário inicial em tom de conversa, escreva-o normalmente logo após o <speak>. "
        "3. Ao iniciar a letra da música, envolva cada verso em uma tag <prosody> fechada corretamente. "
        "   - Se a melodia for lenta/suave use: <prosody rate='-20%' pitch='+1Hz'>letra do verso</prosody> "
        "   - Se a melodia for rápida/agitada use: <prosody rate='+15%' pitch='+3Hz'>letra do verso</prosody> "
        "4. Insira a tag de pausa obrigatoriamente neste formato exato e fechado entre os versos: <break time='400ms'/> "
        "5. Nunca deixe atributos de texto soltos como '+15%', 'pitch=' ou '+3Hz' fora dos sinais de maior e menor (< >). "
        "Exemplo de resposta perfeita esperada: "
        "<speak>Claro, vou cantar para você seguindo o ritmo original: "
        "<prosody rate='-15%' pitch='+1Hz'>Eu sei que vou te amar</prosody><break time='500ms'/>"
        "<prosody rate='-15%' pitch='+1Hz'>Por toda a minha vida</prosody></speak>"
    )

    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_PRINCIPAL,
        config=types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            temperature=0.4, # Temperatura mais baixa reduz as chances de alucinação de código
            tools=[{"google_search": {}}]
        )
    )

if "historico_mensagens" not in st.session_state:
    st.session_state.historico_mensagens = []

# --- ENGINE DE VOZ COM TRATAMENTO DE SSML SEGURO ---
async def gerar_audio_ssml_async(texto_ssml):
    """Sintetiza o áudio interpretando os comandos nativos de ritmo da Francisca de forma segura."""
    arquivo_audio = "luna_canto_ssml.mp3"
    VOZ = "pt-BR-FranciscaNeural" 

    # Sanitização por segurança: Remove eventuais tags mal formadas ou incompletas feitas pela IA
    texto_ssml = texto_ssml.replace("Hz]", "Hz'").replace("ms/", "ms'/")
    
    # Garante o envelopamento correto na tag raiz do SSML
    if not texto_ssml.strip().startswith("<speak>"):
        texto_ssml = f"<speak>{texto_ssml}</speak>"
    if not texto_ssml.strip().endswith("</speak>"):
        texto_ssml = f"{texto_ssml}</speak>"

    try:
        communicate = edge_tts.Communicate(texto_ssml, voice=VOZ)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        # Se falhar por erro de sintaxe complexo no SSML, faz o fallback para áudio de texto limpo automático
        try:
            texto_puro = re.sub(r'<[^>]*>', '', texto_ssml).strip()
            communicate = edge_tts.Communicate(texto_puro, voice=VOZ, rate="+10%")
            await communicate.save(arquivo_audio)
            return arquivo_audio
        except Exception:
            st.error(f"Erro ao sintetizar o áudio da Francisca: {e}")
            return None

# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Assistente Musical")
st.write("Anexe seu arquivo de vídeo ou áudio. A Luna usará a voz da Francisca de forma limpa para cantar!")

for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

with st.sidebar:
    st.header("Upload de Mídia")
    video_enviado = st.file_uploader("Anexe o vídeo/áudio da música aqui:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])

if user_input := st.chat_input("Peça para a Luna cantar..."):

    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    conteudo_envio = []
    caminho_local_midia = None

    if video_enviado:
        with st.spinner("Luna está escutando o arquivo para mapear o andamento e o tom..."):
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
            f"{user_input} (Analise cuidadosamente a melodia e o andamento do arquivo anexo. "
            f"Gere sua resposta estritamente estruturada dentro de marcações SSML válidas com <speak>, <prosody> e <break>. "
            f"Preste muita atenção para fechar todas as tags de forma perfeita e nunca deixar códigos vazados)."
        )
        conteudo_envio.append(types.Part.from_text(text=comando_contextualizado))
    else:
        conteudo_envio = user_input

    # Geração da Resposta da IA
    with st.chat_message("assistant"):
        placeholder_resposta = st.empty()

        try:
            response = st.session_state.chat_gemini.send_message(message=conteudo_envio)
            fala_bruta = response.text.strip() if response.text else "Não consegui extrair os dados da música."
            texto_luna = fala_bruta.replace("*", "")
            
            # Remove todas as marcações XML/SSML para que a exibição em tela fique perfeitamente limpa
            texto_limpo_tela = re.sub(r'<[^>]*>', '', texto_luna).strip()
            
            # Limpa qualquer resíduo textual de atributos que a IA possa ter deixado vazar
            texto_limpo_tela = (texto_limpo_tela
                                .replace("rate=", "")
                                .replace("pitch=", "")
                                .replace("time=", "")
                                .replace("+15%", "")
                                .replace("+3Hz", "")
                                .replace("+1Hz", "")
                                .replace("-20%", "")
                                .replace("300ms", "")
                                .replace("400ms", "")
                                .replace("500ms", "")
                                .replace("600ms", ""))
            
            # Remove múltiplos espaços extras deixados pelas limpezas
            texto_limpo_tela = re.sub(r'\s+', ' ', texto_limpo_tela).strip()
                
            placeholder_resposta.write(texto_limpo_tela)

            # Envia a estrutura completa com as tags de prosódia para o gerador de áudio
            caminho_som = asyncio.run(gerar_audio_ssml_async(texto_luna))

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, format="audio/mp3", autoplay=True)

            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)

            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_limpo_tela,
                "audio": caminho_som
            })

        except Exception as e:
            st.error(f"Erro na requisição: {e}")
            if caminho_local_midia and os.path.exists(caminho_local_midia):
                os.remove(caminho_local_midia)
                
