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
        "DIRETRIZ DE MARCAÇÃO DE RITMO (SISTEMA DE ETIQUETAS): "
        "Para cantar no ritmo certo, você deve usar etiquetas simples no início de cada linha ou verso. "
        "Nunca escreva códigos XML ou termos como 'prosody', 'rate' ou 'pitch' no texto. "
        "Use estritamente estas três etiquetas antes dos versos para indicar o ritmo que você analisou: "
        "- Use [LENTO] no início do verso se aquela parte for calma, lenta ou melancólica. "
        "- Use [RAPIDO] no início do verso se aquela parte for acelerada, enérgica ou falada rápida. "
        "- Use [PAUSA] em uma linha sozinha entre os versos onde houver uma pausa de respiração ou silêncio na música. "
        "Exemplo de resposta esperada: "
        "Claro, vou cantar para você seguindo o ritmo original:\n"
        "[LENTO] Eu sei que vou te amar\n"
        "[PAUSA]\n"
        "[LENTO] Por toda a minha vida"
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


# --- PARSER PYTHON PARA CONSTRUÇÃO DE SSML PERFEITO ---
def converter_etiquetas_para_ssml(texto_luna):
    """Transforma as etiquetas simples em código SSML válido antes de enviar ao Edge-TTS."""
    linhas = texto_luna.split("\n")
    linhas_ssml = []
    
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
            
        if linha.startswith("[LENTO]"):
            conteudo = linha.replace("[LENTO]", "").strip()
            linhas_ssml.append(f"<prosody rate='-20%' pitch='+1Hz'>{conteudo}</prosody>")
        elif linha.startswith("[RAPIDO]"):
            conteudo = linha.replace("[RAPIDO]", "").strip()
            linhas_ssml.append(f"<prosody rate='+15%' pitch='+3Hz'>{conteudo}</prosody>")
        elif linha.startswith("[PAUSA]"):
            linhas_ssml.append("<break time='600ms'/>")
        else:
            # Texto comum (comentários da Luna fora do canto)
            linhas_ssml.append(f"<prosody rate='+10%' pitch='+0Hz'>{linha}</prosody>")
            
    ssml_final = f"<speak>{''.join(linhas_ssml)}</speak>"
    return ssml_final


# --- ENGINE DE VOZ SEGURO ---
async def gerar_audio_seguro_async(texto_luna):
    """Gera o áudio convertendo as etiquetas de forma controlada pelo backend Python."""
    arquivo_audio = "luna_canto_ssml.mp3"
    VOZ = "pt-BR-FranciscaNeural" 

    # Constrói o SSML perfeitamente formatado via código, sem chance de erros de digitação da IA
    texto_ssml = converter_etiquetas_para_ssml(texto_luna)

    try:
        communicate = edge_tts.Communicate(texto_ssml, voice=VOZ)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        # Fallback de segurança absoluto caso o SSML falhe
        try:
            texto_puro = texto_luna.replace("[LENTO]", "").replace("[RAPIDO]", "").replace("[PAUSA]", "")
            communicate = edge_tts.Communicate(texto_puro, voice=VOZ, rate="+10%")
            await communicate.save(arquivo_audio)
            return arquivo_audio
        except Exception:
            st.error(f"Erro ao gerar a voz da Francisca: {e}")
            return None


# --- INTERFACE VISUAL ---
st.title("🌙 Luna — Assistente Musical")
st.write("Anexe seu arquivo de vídeo ou áudio. A Luna analisará o ritmo e cantará de forma fluida sem vazar códigos!")

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
            f"Adicione as etiquetas [LENTO], [RAPIDO] ou [PAUSA] no início de cada linha para indicar o ritmo correto. "
            f"Nunca tente escrever códigos XML ou comandos técnicos)."
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
            
            # Limpa as etiquetas apenas para a exibição visual na tela do Streamlit
            texto_limpo_tela = (texto_luna
                                .replace("[LENTO]", "")
                                .replace("[RAPIDO]", "")
                                .replace("[PAUSA]", "\n"))
            
            # Remove linhas em branco extras criadas pela remoção das pausas
            texto_limpo_tela = re.sub(r'\n\s*\n', '\n', texto_limpo_tela).strip()
                
            placeholder_resposta.write(texto_limpo_tela)

            # Passa o texto estruturado com etiquetas simples para o construtor SSML interno gerar o áudio
            caminho_som = asyncio.run(gerar_audio_seguro_async(texto_luna))

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
                
