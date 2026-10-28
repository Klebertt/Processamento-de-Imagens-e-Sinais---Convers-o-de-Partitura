from pathlib import Path
import argparse
import cv2
import numpy as np
from scipy.io import wavfile


# Tempos medidos em seminimas, independentemente da formula de compasso.
FIGURAS = {4: 'semibreve', 2: 'minima', 1: 'seminima',
           .5: 'colcheia', .25: 'semicolcheia', .125: 'fusa'}


def componentes(mascara):
    n, _, stats, _ = cv2.connectedComponentsWithStats(mascara.astype(np.uint8))
    return [tuple(map(int, r)) for r in stats[1:]]


def detectar_pauta(original):
    projecao = original.sum(axis=1)
    ys = np.flatnonzero(projecao > projecao.max() * .6)
    grupos = np.split(ys, np.flatnonzero(np.diff(ys) > 1) + 1)
    linhas = np.array([int(round(g.mean())) for g in grupos if len(g)])
    if len(linhas) != 5:
        raise ValueError('Suportada apenas uma pauta com cinco linhas bem definidas.')
    espaco = float(np.mean(np.diff(linhas)))
    if espaco < 4 or np.max(abs(np.diff(linhas) - espaco)) > 1:
        raise ValueError('Espacamento da pauta insuficiente ou irregular.')
    return linhas, espaco, ys


def identificar_nota(y, inferior, espaco):
    # Mesmo mapeamento diatonico da versao anterior: clave de Sol, Mi4 na base.
    indice = round((inferior - y) / (espaco / 2)) + 2
    nomes = ['Do', 'Re', 'Mi', 'Fa', 'Sol', 'La', 'Si']
    oitava, grau = divmod(indice, 7)
    nome = nomes[grau] + str(4 + oitava)
    midi = 12 * (5 + oitava) + [0, 2, 4, 5, 7, 9, 11][grau]
    return nome, 440 * 2 ** ((midi - 69) / 12)


def analisar(original):
    linhas, s, ys = detectar_pauta(original)
    avisos, eventos = [], []
    # A matriz original permanece intacta. Hastes, cabecas, ligacoes e pontos
    # sao medidos ANTES de qualquer limpeza para visualizacao.
    hastes = cv2.morphologyEx(original, cv2.MORPH_OPEN,
                            np.ones((round(3.5 * s), 1), np.uint8))
    sem_pauta = original.copy()
    sem_pauta[ys] = 0  # mascara auxiliar; nunca usada como fonte unica do ritmo
    usados = np.zeros_like(original)
    inicio = int(5.5 * s)  # regiao reservada a clave de Sol
    usados[:, :inicio] = 1
    barras = []
    for x, y, w, h, area in componentes(hastes):
        if x < inicio:
            continue
        if y <= linhas[0] + s / 2 and y + h >= linhas[-1] + 2 * s:
            barras.append(x)
            usados[:, max(0, x-1):x+w+1] = 1
            continue
        candidatos = []
        for direcao, ponta in [(1, y), (-1, y+h-1)]:
            xa = x + w if direcao == 1 else max(0, x-round(1.6*s))
            xb = min(original.shape[1], x+w+round(1.6*s)) if direcao == 1 else x
            ya, yb = max(0, ponta-round(.9*s)), min(len(original), ponta+round(.9*s)+1)
            rec = sem_pauta[ya:yb, xa:xb]
            pesos = rec.sum(axis=1).astype(float)
            if pesos.sum() < 1.5*s:
                continue
            cy = float(np.average(np.arange(ya, yb), weights=pesos))
            candidatos.append((pesos.sum(), direcao, xa, xb, cy))
        if not candidatos:
            avisos.append(f'Haste em x={x} sem cabeca reconhecivel.')
            continue
        _, direcao, xa, xb, cy = max(candidatos)
        cx = x + direcao * .65*s
        # Interior da elipse: linhas da pauta nao contam como preenchimento.
        yy, xx = np.indices(original.shape)
        interior = ((xx-cx)/(.42*s))**2 + ((yy-cy)/(.30*s))**2 <= 1
        interior[ys] = False
        # Linhas suplementares tambem atravessam cabecas vazadas.
        for ly in range(round(linhas[0]-s), -1, -round(s)):
            if original[ly, max(0,x-2):min(original.shape[1],x+round(2*s))].sum() >= 2*s:
                interior[ly] = False
        ocupacao = original[interior].mean() if interior.any() else .5
        if .35 < ocupacao < .65:
            avisos.append(f'Cabeca ambigua em x={x}: preenchimento={ocupacao:.2f}.')
            continue
        vazada = ocupacao <= .35
        # Conte bandas de tinta fora da cabeca junto a haste. Uma bandeirola
        # ou uma barra corresponde a uma divisao por dois da seminima.
        ya, yb = (round(cy+1.7*s), y+h) if direcao == 1 else (y, round(cy-1.7*s))
        bandas = []
        regiao_ligacoes = np.zeros_like(original)
        for xa_flag, xb_flag in [(x+w+1, min(original.shape[1], x+w+round(1.3*s))),
                                 (max(0,x-round(1.3*s)), max(0,x-1))]:
            rec = sem_pauta[max(0, ya):max(0, yb), xa_flag:xb_flag]
            if rec.size:
                ocupadas = rec.sum(axis=1) >= max(2, .55*s)
                for ly in ys:
                    k = int(ly-max(0,ya))
                    if 0 < k < len(ocupadas)-1 and ocupadas[k-1] and ocupadas[k+1]:
                        ocupadas[k] = True
                rr = np.flatnonzero(ocupadas)
                grupos = [g for g in np.split(rr, np.flatnonzero(np.diff(rr)>1)+1) if len(g)]
                if len(grupos) > len(bandas):
                    bandas = grupos
                if grupos:
                    regiao_ligacoes[max(0,ya):max(0,yb),xa_flag:xb_flag] = 1
        # Uma barra pode chegar pela esquerda na ultima nota do grupo.
        horizontais = cv2.morphologyEx(sem_pauta, cv2.MORPH_OPEN,
                                      np.ones((1,round(2*s)),np.uint8))
        for bx,by,bw,bh,_ in componentes(horizontais):
            if bx <= x+w+1 and bx+bw >= x-1 and ya <= by < yb:
                regiao_ligacoes[by:by+bh,bx:bx+bw] = 1
        numero = len(bandas)
        if numero > 3 or (vazada and numero):
            avisos.append(f'Ligacao/bandeirola nao suportada em x={x}.')
            continue
        tempos = 2. if vazada else 1. / 2**numero
        nota, freq = identificar_nota(cy, linhas[-1], s)
        eventos.append(dict(x=int(round(cx)), y=int(round(cy)), tipo='nota',
                            nome=nota, frequencia=freq, tempos=tempos, pontos=0,
                            figura=FIGURAS[tempos]))
        usados[max(0, round(cy-s)):min(len(original), round(cy+s)+1),
               max(0, x-round(1.9*s)):min(original.shape[1], x+round(2*s))] = 1
        usados[y:y+h, max(0,x-1):x+w+1] = 1
        if numero:
            usados |= regiao_ligacoes

    # Pontos isolados e pausas retangulares sao buscados na imagem com apenas
    # as linhas da pauta mascaradas; nao se deduzem pausas por espaco vazio.
    restantes = sem_pauta * (1-usados)
    pequenos = componentes(restantes)

    restantes = sem_pauta * (1-usados)
    for x,y,w,h,a in componentes(restantes):
        if a < max(3, .25*s*s):
            continue
        # Pausa de minima: retangulo apoiado na terceira linha.
        # Pausa de semibreve: retangulo pendurado na quarta linha.
        if .8*s <= w <= 2*s and .3*s <= h <= .8*s and a >= .8*w*h:
            if abs(y+h-linhas[2]) <= 1:
                tempos = 2.
            elif abs(y-(linhas[1]+1)) <= 1:
                tempos = 4.
            else:
                tempos = None
            if tempos:
                usados[y:y+h,x:x+w] = 1
                eventos.append(dict(x=x+w//2, y=y+h//2, tipo='pausa', nome='pausa',
                                    tempos=tempos, pontos=0, figura=FIGURAS[tempos]))
                continue
        avisos.append(f'Simbolo nao suportado/ambiguo em ({x},{y}), {w}x{h}; '
                      'possivel pausa, acidente, cabeca sem haste ou outro sinal.')
    for e in eventos:
        pontos = []
        for x,y,w,h,a in pequenos:
            if (1 <= w <= .65*s and 1 <= h <= .65*s and a >= 2
                    and .8*s < x-e['x'] < 3*s and abs(y+h/2-e['y']) < .8*s):
                pontos.append((x,y,w,h))
        pontos.sort()
        for x,y,w,h in pontos[:2]:
            usados[y:y+h,x:x+w] = 1
        e['pontos'] = min(len(pontos), 2)
        e['tempos'] *= sum(.5**i for i in range(e['pontos']+1))

    eventos.sort(key=lambda e:e['x'])
    return eventos, avisos, linhas


def sintetizar(eventos, bpm, taxa=44100):
    partes = []
    fim = 0
    for e in eventos:
        novo_fim = fim + e['tempos'] * 60 / bpm * taxa
        n = round(novo_fim) - round(fim)
        fim = novo_fim
        if e['tipo'] == 'pausa':
            sinal = np.zeros(n)
        else:
            sinal = np.sin(2*np.pi*e['frequencia']*np.arange(n)/taxa)
            rampa = min(round(.005*taxa), n//2)
            if rampa:
                sinal[:rampa] *= np.linspace(0,1,rampa)
                sinal[-rampa:] *= np.linspace(1,0,rampa)
        partes.append(sinal)
    return (np.concatenate(partes)*32767).astype(np.int16) if partes else np.zeros(0,np.int16)


def main():
    pasta = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description='Leitura de pauta monofonica em clave de Sol.')
    parser.add_argument('--bpm', type=float, default=120, help='Seminimas por minuto (padrao: 120).')
    entradas = parser.add_mutually_exclusive_group()
    entradas.add_argument('--imagem', type=Path, nargs='+', help='Uma ou mais imagens, em ordem de leitura.')
    entradas.add_argument('--musicxml', type=Path, nargs='+', help='MusicXML/MXL revisado; dispensa o Audiveris.')
    entradas.add_argument('--pdf', type=Path, help='PDF vetorial ou digitalizado.')
    parser.add_argument('--paginas', type=int, nargs='+', help='Paginas do PDF, numeradas a partir de 1.')
    parser.add_argument('--dpi', type=int, default=300, help='Resolucao do PDF (150 a 600; padrao 300).')
    parser.add_argument('--ocultar-rotulos', nargs='+', default=[], help='Rotulos de instrumento a ocultar somente na margem esquerda do PDF.')
    parser.add_argument('--motor', choices=['auto','simples','audiveris'], default='auto')
    parser.add_argument('--audiveris', help='Caminho do executavel do Audiveris.')
    parser.add_argument('--parte', type=int, default=1, help='Parte instrumental a tocar (padrao: 1).')
    parser.add_argument('--saida', type=Path, default=pasta/'resultado')
    parser.add_argument('--mostrar', action='store_true', help='Abre a janela de visualizacao.')
    args = parser.parse_args()
    if args.parte < 1:
        parser.error('--parte deve ser maior que zero.')
    if args.motor == 'simples' and args.imagem and len(args.imagem) > 1:
        parser.error('O motor simples aceita somente uma pauta em uma imagem.')
    if not np.isfinite(args.bpm) or args.bpm <= 0:
        parser.error('BPM deve ser um numero finito maior que zero.')
    if (args.paginas or args.ocultar_rotulos) and not args.pdf:
        parser.error('--paginas e --ocultar-rotulos exigem --pdf.')
    if args.pdf and args.motor == 'simples':
        parser.error('PDF exige o motor audiveris ou auto.')
    if not 150 <= args.dpi <= 600:
        parser.error('--dpi deve estar entre 150 e 600.')
    if not args.imagem and not args.musicxml and not args.pdf:
        args.imagem = [pasta/'imagens/partitura.png']
    if args.pdf or args.musicxml or args.motor == 'audiveris' or len(args.imagem) > 1:
        from leitura_pagina import processar_paginas, ErroPartitura
        try:
            return processar_paginas(args)
        except ErroPartitura as erro:
            print('ERRO:', erro)
            print('Audio novo nao gerado; um WAV anterior pode permanecer no disco.')
            return 1
    imagem = cv2.imread(str(args.imagem[0]))
    if imagem is None:
        parser.error(f'Imagem nao encontrada: {args.imagem}')
    original = (cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) < 127).astype(np.uint8)
    if args.motor == 'auto':
        try:
            detectar_pauta(original)
        except ValueError:
            from leitura_pagina import processar_paginas, ErroPartitura
            try:
                return processar_paginas(args)
            except ErroPartitura as erro:
                print('ERRO:', erro)
                print('Audio novo nao gerado; um WAV anterior pode permanecer no disco.')
                return 1
    try:
        eventos, avisos, linhas = analisar(original)
    except ValueError as erro:
        parser.error(str(erro))
    print(f'Linhas da pauta: {linhas.tolist()} | BPM: {args.bpm:g}')
    for e in eventos:
        segundos = e['tempos'] * 60 / args.bpm
        print(f"X={e['x']:3} | {e['nome']:5} | {e['figura']} | pontos={e['pontos']} | "
              f"{e['tempos']:g} tempos | {segundos:g} s")
        cv2.putText(imagem, f"{e['nome']}:{e['tempos']:g}",
                    (max(0,e['x']-4), max(8,e['y']-7)),
                    cv2.FONT_HERSHEY_SIMPLEX, .23, (0,0,255), 1)
    args.saida.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.saida/'notas_identificadas.png'), imagem)
    for aviso in avisos:
        print('AVISO:', aviso)
    if avisos or not eventos:
        print('Audio nao gerado: ha simbolos nao resolvidos ou nenhum evento reconhecido.')
        return 1
    audio = sintetizar(eventos, args.bpm)
    wavfile.write(str(args.saida/'melodia.wav'), 44100, audio)
    print(f"Audio: {args.saida/'melodia.wav'} | {len(audio)/44100:g} s")
    if args.mostrar:
        cv2.imshow('Notas identificadas', imagem)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
