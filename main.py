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

# Definição do prompt limpo e fixo do sistema
INSTRUCAO_SISTEMA = (
    "Você é a Luna, uma inteligência artificial gentil, acolhedora, doce e humana. "
    "Não use emojis e nunca use o caractere asterisco (*) em suas respostas. "
    "DIRETRIZ DE ANÁLISE MUSICAL: "
    "Quando o usuário enviar um vídeo ou áudio de música e pedir para você cantar, "
    "analise o ritmo, a melodia, as pausas de respiração e a emoção contida na faixa. "
    "DIRETRIZ OBRIGATÓRIA DE MARCAÇÃO DE RITMO (SISTEMA DE ETIQUETAS): "
    "Para cantar no ritmo certo, você deve usar etiquetas simples no início de cada linha ou verso. "
    "NUNCA escreva códigos XML ou termos técnicos como 'prosody', 'rate', 'pitch', 'break', 'time', 'ms' ou símbolos de porcentagem/sinais como '+15%', '+3Hz'. "
    "Você deve usar APENAS estas três etiquetas literais antes dos versos para guiar o ritmo musical: "
    "- [LENTO] no início do verso se aquela parte for calma, lenta ou melancólica. "
    "- [RAPIDO] no início do verso se aquela parte for acelerada, enérgica ou falada rápida. "
    "- [PAUSA] em uma linha sozinha entre os versos onde houver uma pausa de respiração na música. "
    "Exemplo de resposta esperada: "
    "Claro, vou cantar para você seguindo o ritmo original:\n"
    "[LENTO] Eu sei que vou te amar\n"
    "[PAUSA]\n"
    "[LENTO] Por toda a minha vida"
)

# Inicializa ou reinicia o chat na sessão do navegador
def inicializar_chat():
    st.session_state.chat_gemini = client.chats.create(
        model=MODELO_PRINCIPAL,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCAO_SISTEMA,
            temperature=0.3, # Temperatura reduzida drasticamente para evitar qualquer invenção de código
            tools=[{"google_search": {}}]
        )
    )
    st.session_state.historico_mensagens = []

if "chat_gemini" not in st.session_state:
    inicializar_chat()

# --- PARSER PYTHON PARA CONSTRUÇÃO DE SSML PERFEITO ---
def converter_etiquetas_para_ssml(texto_luna):
    """Transforma as etiquetas simples em código SSML válido antes de enviar ao Edge-TTS."""
    linhas = texto_luna.split("\n")
    linhas_ssml = []
    
    for linha in lines:
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
            # Texto comum (comentários normais da Luna)
            linhas_ssml.append(f"<prosody rate='+10%' pitch='+0Hz'>{linha}</prosody>")
            
    ssml_final = f"<speak>{''.join(linhas_ssml)}</speak>"
    return ssml_final


# --- ENGINE DE VOZ SEGURO E FILTRADO CONTRA CÓDIGOS VAZADOS ---
async def gerar_audio_seguro_async(texto_luna):
    """Gera o áudio convertendo as etiquetas e limpando qualquer palavra técnica por teimosia da IA."""
    arquivo_audio = "luna_canto_ssml.mp3"
    VOZ = "pt-BR-FranciscaNeural" 

    # Filtro de Segurança Absoluto contra Alucinações:
    # Se a IA vazou termos técnicos fora de tags, essa Regex apaga essas palavras específicas antes de ir para a voz da Francisca
    texto_luna = re.sub(r'(rate|pitch|time|break|prosody|speak|ms|Hz|[\+\-]\d+[\%|Hz]?)', '', texto_luna, flags=re.IGNORECASE)

    # Constrói o SSML controlado no backend
    texto_ssml = converter_etiquetas_para_ssml(texto_luna)

    try:
        communicate = edge_tts.Communicate(texto_ssml, voice=VOZ)
        await communicate.save(arquivo_audio)
        return arquivo_audio
    except Exception as e:
        try:
            # Fallback secundário: remove tudo e lê apenas letras
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

with st.sidebar:
    st.header("Configurações e Anexos")
    video_enviado = st.file_uploader("Anexe o vídeo/áudio da música aqui:", type=["mp4", "avi", "mov", "mp3", "wav", "m4a"])
    
    # Botão crítico para limpar o histórico corrompido do Gemini
    if st.button("🔄 Recomeçar Chat Musical (Limpar Códigos)", use_container_width=True):
        inicializar_chat()
        st.success("O histórico foi limpo! A Luna esqueceu os códigos antigos.")
        st.rerun()

# Exibe o histórico de mensagens
for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

if user_input := st.chat_input("Peça para a Luna cantar..."):

    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    conteudo_envio = []
    caminho_local_midia = None

    if video_enviado:
        with st.spinner("Luna está escutando o arquivo para mapear o andamento..."):
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
            f"{user_input} (Analise a melodia do arquivo anexo. Adicione as etiquetas [LENTO], [RAPIDO] ou [PAUSA] "
            f"no início de cada linha para indicar o ritmo. Não escreva nenhum código XML ou termo como 'rate', 'pitch' ou 'ms')."
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
            
            # Limpa as etiquetas e resíduos para exibição visual limpa na tela
            texto_limpo_tela = (texto_luna
                                .replace("[LENTO]", "")
                                .replace("[RAPIDO]", "")
                                .replace("[PAUSA]", "\n"))
            
            # Aplica o filtro de regex também no texto da tela por garantia estética
            texto_limpo_tela = re.sub(r'(rate|pitch|time|break|prosody|speak|ms|Hz|[\+\-]\d+[\%|Hz]?)', '', texto_limpo_tela, flags=re.IGNORECASE)
            texto_limpo_tela = re.sub(r'\n\s*\n', '\n', texto_limpo_tela).strip()
                
            placeholder_resposta.write(texto_limpo_tela)

            # Passa o texto estruturado com etiquetas simples para o gerador de áudio
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
                
