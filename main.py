import time
import cv2
import mss
import numpy as np
import serial
import pyautogui
from google import genai
from google.genai import types

# --- CONFIGURAÇÕES DO SISTEMA ---
API_KEY = "SUA_API_KEY_AQUI"
PORTA_BLUETOOTH_VIRTUAL = ""  # Modifique para a sua porta COM gerada pelo Bluetooth
BAUD_RATE = 115200

# Configura o PyAutoGUI para segurança (mover o mouse para o canto superior esquerdo cancela o script se algo travar)
pyautogui.FAILSAFE = True

# Inicializa o cliente do Gemini
client = genai.Client(api_key=API_KEY)

# Inicializa a conexão com a Porta Bluetooth Virtual do sistema
try:
    bluetooth_virtual = serial.Serial(PORTA_BLUETOOTH_VIRTUAL, BAUD_RATE, timeout=1)
    print(f"Sucesso: Conectado ao canal Bluetooth Virtual na porta {PORTA_BLUETOOTH_VIRTUAL}!")
except Exception as e:
    print(f"Aviso: Não foi possível abrir a porta {PORTA_BLUETOOTH_VIRTUAL}. Executando em modo de simulação direta. Erro: {e}")
    bluetooth_virtual = None


def capturar_tela_tempo_real():
    """Captura a tela inteira instantaneamente e converte em bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Captura o monitor principal
        screenshot = sct.grab(monitor)
        
        # Converte a captura em formato de imagem processável
        img = np.array(screenshot)
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        
        # Reduz a resolução para acelerar o envio e processamento da IA
        img_otimizada = cv2.resize(img_bgr, (1024, 768))
        _, buffer = cv2.imencode('.jpg', img_otimizada)
        return buffer.tobytes()


def executar_acao_sistema(comando: str):
    """Lê o comando que passou pelo canal Bluetooth e executa no sistema operacional."""
    try:
        if "MOUSE:" in comando:
            # Extrai as coordenadas X e Y (Ex: MOUSE:500,400)
            dados = comando.replace("MOUSE:", "").strip()
            x, y = map(int, dados.split(","))
            
            print(f" Executando: Movendo mouse para X:{x}, Y:{y} e clicando.")
            pyautogui.moveTo(x, y, duration=0.4)
            pyautogui.click()
            
        elif "TECLADO:" in comando:
            # Extrai o texto a ser digitado
            texto = comando.replace("TECLADO:", "").strip()
            print(f" Executando: Digitando o texto '{texto}'.")
            pyautogui.write(texto, interval=0.05)
            
    except Exception as e:
        print(f"Erro ao simular entrada do usuário: {e}")


# --- LOOP PRINCIPAL DO AGENTE LUNA ---
print("\n Luna Agente Visual Iniciado. Pressione Ctrl+C no terminal para encerrar.")

while True:
    comando_usuario = input("\nO que você quer que a Luna faça no computador agora? ")
    if comando_usuario.lower() in ['sair', 'fechar', 'exit']:
        print("Encerrando o agente Luna.")
        break

    print(" Luna obtendo imagem da tela em tempo real...")
    frame_bytes = capturar_tela_tempo_real()

    # Instrução estrita para o modelo agir estritamente como um controlador de coordenadas
    instrucao_agente = (
        "Você é a Luna, um agente de automação visual para computadores. "
        "Analise a imagem da tela atual (resolução redimensionada para 1024x768). "
        "Baseado no pedido do usuário, determine o próximo passo técnico imediato.\n"
        "Regras de resposta (Responda APENAS com uma das opções abaixo, sem explicações):\n"
        "1. Se precisar clicar em algo: MOUSE:X,Y (onde X e Y são as coordenadas estimadas na tela 1024x768)\n"
        "2. Se precisar digitar algo: TECLADO:texto_aqui\n"
        "3. Se a ação solicitada já foi terminada com sucesso: FIM"
    )

    try:
        # Envia a tela e o pedido para a API do Gemini
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=f"Comando do usuário: {comando_usuario}")
            ],
            config=types.GenerateContentConfig(system_instruction=instrucao_agente)
        )

        decisao_ia = response.text.strip()
        print(f" Resposta da IA: {decisao_ia}")

        if decisao_ia == "FIM":
            print(" Luna concluiu a tarefa com sucesso!")
            continue

        # Simula o envio pelo canal Bluetooth Virtual escrevendo na porta serial interna
        if bluetooth_virtual and bluetooth_virtual.is_open:
            bluetooth_virtual.write((decisao_ia + "\n").encode('utf-8'))
            time.sleep(0.1)
            # O sistema lê o que foi enviado no canal Bluetooth para executar
            linha_recebida = bluetooth_virtual.readline().decode('utf-8').strip()
            executar_acao_sistema(linha_recebida)
        else:
            # Caso a porta COM virtual não esteja configurada, executa direto via software para não quebrar o código
            executar_acao_sistema(decisao_ia)

    except Exception as e:
        print(f"Erro durante o processamento do loop da IA: {e}")

    # Pausa de segurança entre ações consecutivas
    time.sleep(1)
    
