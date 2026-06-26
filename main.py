import asyncio
import os
from PIL import Image
import edge_tts
import streamlit as st
from google import genai
from google.genai import types

# --- CONFIGURAÇÃO DA PÁGINA WEB ---
st.set_page_config(page_title="Luna - Assistente Virtual", page_icon="🌙", layout="centered")

# Cole a sua NOVA chave gerada no AI Studio entre as aspas:
NOVA_CHAVE_GERADA = "AQ.Ab8RN6JqXhgj_3hVBwJbJPlirNFnP0K3LxbtZ2GB9JsWK6zSJA"

# Se estiver rodando no Streamlit Cloud, ele tenta pegar dos 'Secrets' seguros, 
# se não encontrar, usa a chave que você colou acima.
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
        "Se o usuário enviar uma imagem, analise-a com atenção e descreva o que vê de forma natural. "
        "HABILIDADE DE PESQUISA DE MÚSICA: Você TEM ACESSO à ferramenta de busca do Google e DEVE usá-la "
        "sempre que o usuário pedir a letra de uma música. Para garantir a letra correta, você deve priorizar "
        "e buscar os resultados vindos de fontes oficiais como: YouTube, Spotify, YouTube Music, ou grandes portais "
        "especializados em letras (como Letras.mus.br, Vagalume ou Genius). Nunca invente ou tente adivinhar uma "
        "letra de cabeça se não tiver certeza absoluta; use a busca para confirmar versos, compositores e variações. "
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


# --- ENGINE DE VOZ ---
async def gerar_audio_async(texto):
    """Gera o arquivo de áudio utilizando edge-tts com base nas emoções detectadas."""
    arquivo_audio = "luna_voz_web.mp3"
    VOZ = "pt-BR-FranciscaNeural"
    VELOCIDADE = "+10%"
    PITCH = "+0Hz"

    if "[CANTANDO]" in texto:
        texto = texto.replace("[CANTANDO]", "").strip()
        VOZ = "pt-BR-ThalitaNeural"
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
st.write("Converse com a Luna, peça letras de música ou envie imagens direto pelo celular!")

# Exibe o histórico de mensagens na tela com estilo nativo de chat
for msg in st.session_state.historico_mensagens:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "audio" in msg and msg["audio"]:
            st.audio(msg["audio"], format="audio/mp3")

# Componentes de entrada lateral ou inferior (Upload de Imagem)
with st.sidebar:
    st.header("Configurações e Anexos")
    imagem_enviada = st.file_uploader("Anexe uma imagem para a Luna ver:", type=["jpg", "jpeg", "png", "webp"])

# Entrada de texto do Chat estilo mobile
if user_input := st.chat_input("Digite sua mensagem para a Luna..."):

    # 1. Exibe a mensagem do usuário imediatamente na tela
    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.historico_mensagens.append({"role": "user", "content": user_input})

    # Otimizador de busca para letras de música
    texto_envio = user_input
    palavras_chave = ["letra da musica", "letra de", "cante a musica", "pesquise a letra", "letras de"]
    if any(chave in user_input.lower() for chave in palavras_chave):
        texto_envio += " (Busque a letra oficial resumida no Letras.mus.br)"

    conteudo_envio = []

    # Processa imagem se houver
    if imagem_enviada:
        try:
            bytes_imagem = imagem_enviada.read()
            conteudo_envio.append(types.Part.from_bytes(data=bytes_imagem, mime_type="image/jpeg"))
            conteudo_envio.append(types.Part.from_text(text=texto_envio))
        except Exception:
            st.error("Erro ao carregar o arquivo de imagem enviado.")
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

            # Mostra o texto gerado
            placeholder_resposta.write(texto_tela)

            # Gera o áudio correspondente para o navegador tocar
            caminho_som = asyncio.run(gerar_audio_async(fala_luna))

            if caminho_som and os.path.exists(caminho_som):
                st.audio(caminho_som, format="audio/mp3", autoplay=True)

            # Salva no histórico da sessão
            st.session_state.historico_mensagens.append({
                "role": "assistant",
                "content": texto_tela,
                "audio": caminho_som
            })

        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                aviso = "Poxa... Minha caixinha de pensamentos gastou toda a energia diária por hoje... 🌙"
                placeholder_resposta.write(aviso)
            else:
                st.error(f"Erro na requisição. Detalhes: {e}")
