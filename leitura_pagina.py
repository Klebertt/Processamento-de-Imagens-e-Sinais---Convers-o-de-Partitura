"""Pagina impressa -> Audiveris -> MusicXML -> eventos para o sintetizador.

O OpenCV prepara a imagem; o reconhecimento musical fica a cargo do Audiveris.
O MusicXML e preservado para permitir revisar o resultado do OMR.
"""
from pathlib import Path
from contextlib import closing
import json
import os
import re
import shutil
import subprocess
import tempfile
import warnings

import cv2
import numpy as np


class ErroPartitura(ValueError):
    pass


def localizar_audiveris(caminho=None):
    if caminho:
        candidato = Path(caminho).expanduser()
        if candidato.is_file():
            return str(candidato.resolve())
        achado = shutil.which(str(caminho))
        if achado:
            return achado
        raise ErroPartitura(f'Audiveris nao encontrado: {caminho}')
    candidatos = [str(Path(__file__).resolve().parent.parent/'.tools/Audiveris/Audiveris.exe'),
                  os.environ.get('AUDIVERIS_PATH'), shutil.which('Audiveris'),
                  shutil.which('audiveris')]
    for raiz in [os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')]:
        if raiz:
            candidatos.extend([str(Path(raiz)/'Audiveris/Audiveris.exe'),
                               str(Path(raiz)/'Programs/Audiveris/Audiveris.exe')])
    for candidato in candidatos:
        if candidato and Path(candidato).is_file():
            return str(Path(candidato).resolve())
    raise ErroPartitura('Audiveris nao instalado/localizado. Instale com '
                        'winget install --id audiveris.org.Audiveris --exact '
                        'ou informe --audiveris CAMINHO_DO_EXECUTAVEL.')


def preparar_imagem(entrada, destino):
    imagem = cv2.imread(str(entrada), cv2.IMREAD_GRAYSCALE)
    if imagem is None:
        raise ErroPartitura(f'Nao foi possivel abrir: {entrada}')
    # Estima a distancia entre linhas longas para ampliar fontes pequenas.
    mascara = (imagem < 160).astype(np.uint8)
    horizontais = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,
                                 np.ones((1,max(25,imagem.shape[1]//5)),np.uint8))
    ys = np.flatnonzero(horizontais.sum(axis=1) > imagem.shape[1]*.25)
    grupos = np.split(ys, np.flatnonzero(np.diff(ys)>1)+1)
    centros = np.array([g.mean() for g in grupos if len(g)])
    distancias = np.diff(centros)
    distancias = distancias[(distancias >= 3) & (distancias <= 40)]
    espaco = float(np.median(distancias)) if len(distancias) else None
    escala = min(4., max(1., 12/espaco)) if espaco else 1.
    if escala > 1:
        imagem = cv2.resize(imagem,None,fx=escala,fy=escala,interpolation=cv2.INTER_CUBIC)
    if not cv2.imwrite(str(destino),imagem):
        raise ErroPartitura(f'Nao foi possivel gravar: {destino}')
    avisos = []
    if espaco is not None and espaco < 8:
        avisos.append(f'Baixa resolucao: espacamento original de {espaco:g} pixels; '
                      f'ampliacao {escala:g}x nao recupera detalhes perdidos.')
    return avisos


def transcrever(entrada, saida, executavel, timeout=600):
    # Pasta nova por execucao: nunca aceitar um MusicXML antigo como resultado.
    pasta = Path(tempfile.mkdtemp(prefix='omr_',dir=saida))
    preparada = pasta/'pagina.png'
    avisos = preparar_imagem(entrada, preparada)
    comando = [executavel,'-batch','-transcribe','-export','-save',
               '-constant','org.audiveris.omr.sheet.ProcessingSwitches.indentations=false',
               '-output',str(pasta.resolve()),'--',str(preparada.resolve())]
    log = pasta/'audiveris.log'
    print(f'Reconhecendo {entrada.name}; log: {log}',flush=True)
    ambiente = os.environ.copy()
    tessdata = Path(executavel).parent/'tessdata'
    if (tessdata/'eng.traineddata').is_file():
        ambiente['TESSDATA_PREFIX'] = str(tessdata.resolve())
    try:
        with log.open('w',encoding='utf-8') as arquivo:
            processo = subprocess.run(comando,stdout=arquivo,stderr=subprocess.STDOUT,
                                      timeout=timeout,check=False,env=ambiente)
    except subprocess.TimeoutExpired as erro:
        raise ErroPartitura(f'Audiveris excedeu {timeout}s. Consulte {log}') from erro
    except OSError as erro:
        raise ErroPartitura(f'Falha ao iniciar Audiveris: {erro}') from erro
    if processo.returncode:
        raise ErroPartitura(f'Audiveris terminou com codigo {processo.returncode}. Consulte {log}')
    arquivos = sorted(pasta.rglob('*.mxl'))
    if not arquivos:
        arquivos = sorted(pasta.rglob('*.musicxml'))
    if not arquivos:
        raise ErroPartitura(f'Audiveris nao exportou MusicXML. Consulte {log}')
    texto_log = log.read_text(encoding='utf-8',errors='replace')
    fonte = cv2.imread(str(entrada),cv2.IMREAD_GRAYSCALE)
    mascara = (fonte < 160).astype(np.uint8)
    linhas_longas = cv2.morphologyEx(mascara,cv2.MORPH_OPEN,
                                   np.ones((1,max(25,fonte.shape[1]//5)),np.uint8))
    ys = np.flatnonzero(linhas_longas.sum(1)>fonte.shape[1]*.25)
    faixas = np.split(ys,np.flatnonzero(np.diff(ys)>1)+1)
    centros = np.array([g.mean() for g in faixas if len(g)])
    distancias = np.diff(centros)
    proximas = distancias[(distancias>=3)&(distancias<=40)]
    passo = float(np.median(proximas)) if len(proximas) else 5.
    grupos = np.split(centros,np.flatnonzero(np.diff(centros)>3*passo)+1)
    esperadas = sum(len(g)>=3 for g in grupos)
    detectadas = sum(int(n) for n in re.findall(r'Retrieved raw line clusters: (\d+)',texto_log))
    if esperadas and detectadas < esperadas:
        raise ErroPartitura(f'Reconhecimento incompleto: {detectadas} pautas de aproximadamente '
                            f'{esperadas} visiveis. Consulte {log}')
    for linha in texto_log.splitlines():
        if any(p in linha.lower() for p in ['warn ', 'error ', 'abnormal', 'no system', 'no staff']):
            avisos.append(linha.strip())
    (pasta/'diagnostico.json').write_text(json.dumps(
        dict(entrada=str(entrada),pautas_estimadas=esperadas,pautas_omr=detectadas,
             musicxml=[str(a) for a in arquivos],avisos=avisos),
        ensure_ascii=False,indent=2),encoding='utf-8')
    for aviso in avisos:
        print('AVISO OMR:',aviso,flush=True)
    if 'Multirest with no measure count' in texto_log:
        raise ErroPartitura('Contagem de pausa de varios compassos nao reconhecida; '
                            'o valor padrao do OMR nao sera aceito. Consulte '+str(log))
    if len(arquivos) != 1:
        raise ErroPartitura('Foram encontrados varios movimentos MusicXML; '
                            'selecione o desejado usando --musicxml. Pasta: '+str(pasta))
    print(f'MusicXML exportado: {arquivos[0]}',flush=True)
    return arquivos[0], avisos


def eventos_da_partitura(partitura, parte=1):
    """Seleciona uma parte monofonica, junta ligaduras de prolongacao e ordena.

    Ligaduras de expressao nao somam duracoes; bemois/sustenidos vem do pitch
    interpretado do MusicXML. Lacunas e sobreposicoes sao erros, nao duracoes
    inventadas pelo sintetizador.
    """
    from music21 import chord, expressions, note, stream
    avisos = []
    partes = list(partitura.parts) if isinstance(partitura,stream.Score) else [partitura]
    if not 1 <= parte <= len(partes):
        raise ErroPartitura(f'Parte {parte} inexistente; encontradas {len(partes)} partes.')
    if len(partes) > 1:
        avisos.append(f'Encontradas {len(partes)} partes; lendo somente a parte {parte}.')
    selecionada = partes[parte-1]
    for medida in selecionada.getElementsByClass(stream.Measure):
        try:
            esperado = float(medida.barDuration.quarterLength)
        except Exception:
            continue
        real = float(medida.highestTime) + float(medida.paddingLeft)
        if abs(real-esperado) > 1e-6:
            raise ErroPartitura(f'Compasso {medida.number}: duracao {real:g}, '
                                f'esperados {esperado:g} tempos. Revise o MusicXML.')
    # Antes de stripTies, detecta pontas soltas: elas indicam reconhecimento
    # incompleto ou uma pagina isolada no meio de uma ligadura.
    pendentes = set()
    for el in selecionada.recurse().notes:
        if isinstance(el,chord.Chord):
            raise ErroPartitura(f'Acorde no compasso {el.measureNumber}: '
                                'este modo requer uma melodia monofonica.')
        if not isinstance(el,note.Note):
            raise ErroPartitura(f'Nota sem altura suportada no compasso {el.measureNumber}.')
        if el.tie:
            chave = el.pitch.nameWithOctave
            if el.tie.type in ('stop','continue') and chave not in pendentes:
                raise ErroPartitura(f'Ligadura sem inicio no compasso {el.measureNumber} ({chave}).')
            if el.tie.type in ('start','continue'):
                pendentes.add(chave)
            else:
                pendentes.discard(chave)
    if pendentes:
        raise ErroPartitura('Ligadura sem final: '+', '.join(sorted(pendentes)))
    try:
        selecionada = selecionada.expandRepeats()
    except Exception as erro:
        raise ErroPartitura(f'Nao foi possivel interpretar repeticoes: {erro}') from erro
    selecionada = selecionada.stripTies()
    itens = sorted(selecionada.recurse().notesAndRests,
                   key=lambda el: el.getOffsetInHierarchy(selecionada))
    eventos, fim = [], 0.
    nomes = {'C':'Do','D':'Re','E':'Mi','F':'Fa','G':'Sol','A':'La','B':'Si'}
    for el in itens:
        inicio = float(el.getOffsetInHierarchy(selecionada))
        duracao = float(el.duration.quarterLength)
        compasso = el.measureNumber
        if el.duration.isGrace or duracao <= 0:
            raise ErroPartitura(f'Ornamento/nota sem duracao no compasso {compasso}.')
        if abs(inicio-fim) > 1e-6:
            problema = 'sobreposicao de vozes' if inicio < fim else 'lacuna sem pausa explicita'
            raise ErroPartitura(f'Compasso {compasso}: {problema} em {inicio:g} tempos '
                                f'(fim anterior: {fim:g}). Revise o MusicXML.')
        if any(isinstance(exp,expressions.Fermata) for exp in el.expressions):
            avisos.append(f'Compasso {compasso}: fermata sem duracao numerica; '
                          'audio usa a duracao escrita, sem prolongamento adicional.')
        evento = dict(tipo='pausa' if el.isRest else 'nota',tempos=duracao,
                      inicio=inicio,compasso=compasso,figura=el.duration.type,
                      pontos=el.duration.dots,nome='pausa')
        if not el.isRest:
            alteracao = el.pitch.accidental.alter if el.pitch.accidental else 0
            if alteracao not in (-2,-1,0,1,2):
                raise ErroPartitura(f'Alteracao microtonal nao suportada no compasso {compasso}.')
            acidente = {-2:'bb',-1:'b',0:'',1:'#',2:'##'}[alteracao]
            evento['nome'] = nomes[el.pitch.step]+acidente+str(el.pitch.octave)
            evento['frequencia'] = float(el.pitch.frequency)
        eventos.append(evento)
        fim = inicio+duracao
    if not eventos:
        raise ErroPartitura('MusicXML nao contem notas ou pausas na parte selecionada.')
    return eventos, avisos


def ler_musicxml(caminho, parte=1):
    try:
        from music21 import converter
    except ImportError as erro:
        raise ErroPartitura('Dependencia ausente: instale com python -m pip install -r requirements.txt') from erro
    with warnings.catch_warnings(record=True) as capturados:
        warnings.simplefilter('always')
        try:
            partitura = converter.parse(str(Path(caminho).resolve()),forceSource=True)
            from music21 import meter
            if not list(partitura.recurse().getElementsByClass(meter.TimeSignature)):
                raise ErroPartitura('Formula de compasso nao reconhecida; revise o MusicXML: '+str(caminho))
            eventos, avisos = eventos_da_partitura(partitura,parte)
        except ErroPartitura:
            raise
        except Exception as erro:
            raise ErroPartitura(f'Erro ao ler MusicXML {caminho}: {erro}') from erro
    avisos.extend(str(aviso.message) for aviso in capturados)
    return eventos, avisos


def renderizar_pdf(caminho, destino, paginas=None, dpi=300, ocultar_rotulos=()):
    """Renderiza a fonte vetorial; nunca altera o PDF original.

    Rotulos explicitamente indicados so podem ser ocultados na margem esquerda.
    As caixas removidas ficam registradas para revisao.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as erro:
        raise ErroPartitura('pypdfium2 ausente; instale requirements.txt no ambiente local.') from erro
    if not 150 <= dpi <= 600:
        raise ErroPartitura('DPI deve estar entre 150 e 600.')
    destino = Path(destino)
    destino.mkdir(parents=True,exist_ok=True)
    imagens, registro = [], []
    try:
        documento_pdf = pdfium.PdfDocument(str(caminho))
    except Exception as erro:
        raise ErroPartitura(f'Nao foi possivel abrir o PDF {caminho}: {erro}') from erro
    with documento_pdf as documento:
        indices = paginas if paginas is not None else list(range(1,len(documento)+1))
        if not indices or len(indices)!=len(set(indices)) or any(i<1 or i>len(documento) for i in indices):
            raise ErroPartitura(f'Paginas invalidas; PDF tem {len(documento)} paginas.')
        for numero in indices:
            with closing(documento[numero-1]) as pagina:
                escala = dpi/72
                largura,altura = pagina.get_size()
                bitmap = pagina.render(scale=escala)
                try:
                    imagem = bitmap.to_numpy().copy()
                finally:
                    bitmap.close()
                removidos = []
                with closing(pagina.get_textpage()) as texto:
                    for rotulo in ocultar_rotulos:
                        if not rotulo.strip():
                            raise ErroPartitura('Rotulo vazio nao e permitido.')
                        busca = texto.search(rotulo,match_case=True,match_whole_word=True)
                        try:
                            while True:
                                encontrado = busca.get_next()
                                if encontrado is None:
                                    break
                                inicio,tamanho = encontrado
                                caixas = [texto.get_charbox(i) for i in range(inicio,inicio+tamanho)]
                                x1 = min(b[0] for b in caixas)
                                y1 = min(b[1] for b in caixas)
                                x2 = max(b[2] for b in caixas)
                                y2 = max(b[3] for b in caixas)
                                if x2 > largura*.15:
                                    raise ErroPartitura(f'Rotulo {rotulo!r} fora da margem esquerda; nao sera ocultado.')
                                xa,xb = max(0,int(np.floor(x1*escala))-1),int(np.ceil(x2*escala))+1
                                ya,yb = max(0,int(np.floor((altura-y2)*escala))-1),int(np.ceil((altura-y1)*escala))+1
                                imagem[ya:yb,xa:xb] = 255
                                removidos.append(dict(texto=rotulo,caixa_pdf=[x1,y1,x2,y2]))
                        finally:
                            busca.close()
                arquivo = destino/f'pagina_{numero:03}.png'
                if not cv2.imwrite(str(arquivo),imagem):
                    raise ErroPartitura(f'Nao foi possivel gravar {arquivo}')
                imagens.append(arquivo)
                registro.append(dict(pagina=numero,imagem=str(arquivo),dpi=dpi,
                                     largura=imagem.shape[1],altura=imagem.shape[0],rotulos_ocultados=removidos))
    (destino/'renderizacao.json').write_text(json.dumps(
        dict(pdf=str(Path(caminho).resolve()),paginas=registro),ensure_ascii=False,indent=2),encoding='utf-8')
    return imagens


def processar_paginas(args):
    from main import sintetizar
    try:
        import music21
    except ImportError as erro:
        raise ErroPartitura('music21 ausente neste Python. Use executar.ps1 ou instale requirements.txt.') from erro
    from scipy.io import wavfile
    saida = args.saida.resolve()
    saida.mkdir(parents=True,exist_ok=True)
    eventos, avisos, fontes = [], [], []
    arquivos = args.musicxml if args.musicxml else args.imagem
    if getattr(args,'pdf',None):
        pasta_pdf = Path(tempfile.mkdtemp(prefix='pdf_',dir=saida))
        arquivos = renderizar_pdf(args.pdf,pasta_pdf,args.paginas,args.dpi,args.ocultar_rotulos)
    executavel = None if args.musicxml else localizar_audiveris(args.audiveris)
    for pagina, arquivo in enumerate(arquivos,1):
        entrada = Path(arquivo).resolve()
        if not entrada.is_file():
            raise ErroPartitura(f'Arquivo nao encontrado: {entrada}')
        if args.musicxml:
            xml = entrada
        else:
            xml, alertas = transcrever(entrada,saida,executavel)
            avisos.extend(f'Pagina {pagina}: {a}' for a in alertas)
        try:
            atuais, alertas = ler_musicxml(xml,args.parte)
        except ErroPartitura as erro:
            (saida/'erro_leitura.txt').write_text(
                f'Entrada: {entrada}\nMusicXML: {xml}\nErro: {erro}\n',encoding='utf-8')
            raise
        avisos.extend(f'Pagina {pagina}: {a}' for a in alertas)
        for evento in atuais:
            evento['pagina'] = pagina
        eventos.extend(atuais)
        fontes.append(str(xml))
    print(f'BPM: {args.bpm:g} (seminimas/minuto, configurado pelo usuario ou padrao 120)')
    for e in eventos:
        print(f"Pagina {e['pagina']} | compasso {e['compasso']} | {e['nome']:6} | "
              f"{e['tempos']:g} tempos | {e['tempos']*60/args.bpm:g} s")
    for aviso in avisos:
        print('AVISO:',aviso)
    if not args.musicxml:
        print('AVISO: transcricao optica automatica; revise o MusicXML e o log do Audiveris.')
    relatorio = dict(bpm=args.bpm,fontes=fontes,avisos=avisos,eventos=eventos,
                     origem='musicxml' if args.musicxml else 'omr_nao_revisado')
    (saida/'eventos.json').write_text(json.dumps(relatorio,ensure_ascii=False,indent=2),encoding='utf-8')
    audio = sintetizar(eventos,args.bpm)
    wavfile.write(str(saida/'melodia.wav'),44100,audio)
    print(f"Audio: {saida/'melodia.wav'} | {len(audio)/44100:g} s")
    return 0
