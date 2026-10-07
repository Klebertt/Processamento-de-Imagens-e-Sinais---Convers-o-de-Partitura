import cv2
import numpy as np
from scipy.io import wavfile
import os

# =========================================================
# 1. CARREGA A IMAGEM
# =========================================================

imagem = cv2.imread("imagens/partitura.png")

if imagem is None:
    print("Erro ao carregar a imagem.")
    exit()

cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

_, binaria = cv2.threshold(
    cinza,
    127,
    255,
    cv2.THRESH_BINARY_INV
)

# =========================================================
# 2. DETECTA AS 5 LINHAS DA PAUTA
# =========================================================

projecao = np.sum(binaria, axis=1)

limiar = np.max(projecao) * 0.6

linhas = np.where(projecao > limiar)[0]

print("Linhas da pauta:")
print(linhas)

linha_inferior = linhas[-1]

espacamento = np.mean(np.diff(linhas))

# Uma nota pode ficar em linha ou espaço
passo = espacamento / 2

# =========================================================
# 3. REMOVE AS LINHAS HORIZONTAIS
# =========================================================

kernel_horizontal = cv2.getStructuringElement(
    cv2.MORPH_RECT,
    (25, 1)
)

linhas_horizontais = cv2.morphologyEx(
    binaria,
    cv2.MORPH_OPEN,
    kernel_horizontal
)

sem_linhas = cv2.subtract(
    binaria,
    linhas_horizontais
)

# =========================================================
# 4. REMOVE HASTES E BARRAS VERTICAIS
# =========================================================

kernel_vertical = cv2.getStructuringElement(
    cv2.MORPH_RECT,
    (1, 12)
)

linhas_verticais = cv2.morphologyEx(
    sem_linhas,
    cv2.MORPH_OPEN,
    kernel_vertical
)

sem_hastes = cv2.subtract(
    sem_linhas,
    linhas_verticais
)

# =========================================================
# 5. ENCONTRA PEDAÇOS DE POSSÍVEIS CABEÇAS
# =========================================================

contornos, _ = cv2.findContours(
    sem_hastes,
    cv2.RETR_EXTERNAL,
    cv2.CHAIN_APPROX_SIMPLE
)

candidatos = []

for contorno in contornos:

    x, y, w, h = cv2.boundingRect(contorno)

    area = cv2.contourArea(contorno)

    # Ignora clave de Sol
    if x < 25:
        continue

    # Tamanho compatível com pedaços de cabeças
    if 2 <= w <= 12 and 2 <= h <= 10 and area >= 1:

        candidatos.append({
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "area": area
        })

# Ordena horizontalmente
candidatos.sort(
    key=lambda c: c["x"]
)

# =========================================================
# 6. AGRUPA PEDAÇOS QUE PERTENCEM À MESMA NOTA
# =========================================================

grupos = []

for candidato in candidatos:

    centro_x = candidato["x"] + candidato["w"] / 2

    encontrado = False

    for grupo in grupos:

        # Centro X médio do grupo
        xs = [
            c["x"] + c["w"] / 2
            for c in grupo
        ]

        centro_grupo = np.mean(xs)

        # Se estão muito próximos horizontalmente,
        # provavelmente são partes da mesma nota
        if abs(centro_x - centro_grupo) <= 5:

            grupo.append(candidato)

            encontrado = True
            break

    if not encontrado:
        grupos.append([candidato])

# =========================================================
# 7. TRANSFORMA CADA GRUPO EM UMA ÚNICA NOTA
# =========================================================

notas_detectadas = []

for grupo in grupos:

    area_total = sum(
        c["area"]
        for c in grupo
    )

    # Elimina pequenos resíduos
    if area_total < 2.5:
        continue

    x_min = min(
        c["x"]
        for c in grupo
    )

    y_min = min(
        c["y"]
        for c in grupo
    )

    x_max = max(
        c["x"] + c["w"]
        for c in grupo
    )

    y_max = max(
        c["y"] + c["h"]
        for c in grupo
    )

    centro_x = int(
        (x_min + x_max) / 2
    )

    centro_y = int(
        (y_min + y_max) / 2
    )

    notas_detectadas.append(
        (centro_x, centro_y)
    )

# Ordem temporal
notas_detectadas.sort(
    key=lambda nota: nota[0]
)

# =========================================================
# 8. MAPA DE NOTAS DA CLAVE DE SOL
# =========================================================

notas_musicais = [
    "Mi4",
    "Fa4",
    "Sol4",
    "La4",
    "Si4",
    "Do5",
    "Re5",
    "Mi5",
    "Fa5",
    "Sol5",
    "La5",
    "Si5",
    "Do6"
]


notas_abaixo = [
    "Mi4",
    "Re4",
    "Do4",
    "Si3",
    "La3"
]


def identificar_nota(y):

    diferenca = linha_inferior - y

    indice = round(
        diferenca / passo
    )

    if indice >= 0:

        if indice < len(notas_musicais):
            return notas_musicais[indice]

    else:

        indice_abaixo = abs(indice)

        if indice_abaixo < len(notas_abaixo):
            return notas_abaixo[indice_abaixo]

    return "?"

# =========================================================
# 9. IDENTIFICA A MELODIA
# =========================================================

resultado = imagem.copy()

melodia = []

print("\nNotas encontradas:")

for x, y in notas_detectadas:

    nota = identificar_nota(y)

    melodia.append(nota)

    print(
        f"X={x:3} | Y={y:2} | {nota}"
    )

    cv2.circle(
        resultado,
        (x, y),
        3,
        (0, 0, 255),
        1
    )

    cv2.putText(
        resultado,
        nota,
        (x - 8, max(y - 6, 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.25,
        (255, 0, 0),
        1
    )

# =========================================================
# 10. RESULTADO
# =========================================================

print("\nQuantidade de notas:", len(melodia))

print("\nMelodia detectada:")

print(
    " -> ".join(melodia)
)

# =========================================================
# 11. FREQUÊNCIAS DAS NOTAS
# =========================================================

frequencias = {
    "Si3": 246.94,

    "Do4": 261.63,
    "Re4": 293.66,
    "Mi4": 329.63,
    "Fa4": 349.23,
    "Sol4": 392.00,
    "La4": 440.00,
    "Si4": 493.88,

    "Do5": 523.25,
    "Re5": 587.33,
    "Mi5": 659.25,
    "Fa5": 698.46,
    "Sol5": 783.99,
    "La5": 880.00,
    "Si5": 987.77,

    "Do6": 1046.50
}

# =========================================================
# 12. CONFIGURAÇÕES DO ÁUDIO
# =========================================================

taxa_amostragem = 44100

duracao_nota = 0.5

audio_completo = []

# =========================================================
# 13. GERA UMA SENOIDE PARA CADA NOTA
# =========================================================

for nota in melodia:

    if nota not in frequencias:
        continue

    frequencia = frequencias[nota]

    t = np.linspace(
        0,
        duracao_nota,
        int(taxa_amostragem * duracao_nota),
        endpoint=False
    )

    sinal = np.sin(
        2 * np.pi * frequencia * t
    )

    audio_completo.append(sinal)

# =========================================================
# 14. CONCATENA TODAS AS NOTAS
# =========================================================

audio_completo = np.concatenate(
    audio_completo
)

# =========================================================
# 15. NORMALIZA PARA WAV
# =========================================================

audio_completo = (
    audio_completo * 32767
).astype(np.int16)

# =========================================================
# 16. SALVA O ARQUIVO
# =========================================================

caminho_audio = "resultado/melodia.wav"

wavfile.write(
    caminho_audio,
    taxa_amostragem,
    audio_completo
)

print("\nÁudio gerado com sucesso!")
print("Arquivo:", caminho_audio)

cv2.imshow(
    "Notas identificadas",
    resultado
)

cv2.imwrite(
    "resultado/notas_identificadas.png",
    resultado
)

cv2.waitKey(0)
cv2.destroyAllWindows()