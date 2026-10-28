import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import numpy as np
from music21 import stream, note, chord, tie, meter, pitch, expressions
from leitura_pagina import (eventos_da_partitura, ler_musicxml, ErroPartitura,
                            preparar_imagem, localizar_audiveris)


class PaginaTest(unittest.TestCase):
    def partitura(self):
        score = stream.Score()
        parte = stream.Part()
        score.insert(0,parte)
        return score, parte

    def test_compassos_ligadura_pausa_e_bemol(self):
        score,parte = self.partitura()
        a = stream.Measure(number=1)
        a.timeSignature = meter.TimeSignature('4/4')
        n = note.Note('B-4',quarterLength=4)
        n.tie = tie.Tie('start')
        a.append(n)
        b = stream.Measure(number=2)
        n = note.Note('B-4',quarterLength=1)
        n.tie = tie.Tie('stop')
        b.append(n)
        b.append(note.Rest(quarterLength=1))
        b.append(note.Note('E-5',quarterLength=2))
        parte.append([a,b])
        eventos,avisos = eventos_da_partitura(score)
        self.assertEqual(avisos,[])
        self.assertEqual([e['nome'] for e in eventos],['Sib4','pausa','Mib5'])
        self.assertEqual([e['tempos'] for e in eventos],[5,1,2])
        self.assertAlmostEqual(eventos[0]['frequencia'],466.16376,places=3)
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = score.write('musicxml',fp=Path(pasta)/'exemplo.musicxml')
            atuais,_ = ler_musicxml(arquivo)
            self.assertEqual([e['tempos'] for e in atuais],[5,1,2])

    def test_nao_confunde_ligadura_de_expressao(self):
        from music21 import spanner
        score,parte = self.partitura()
        m = stream.Measure(number=1)
        a,b = note.Note('C5'),note.Note('D5')
        m.append([a,b])
        parte.append(m)
        parte.insert(0,spanner.Slur(a,b))
        eventos,_ = eventos_da_partitura(score)
        self.assertEqual(len(eventos),2)
        self.assertEqual([e['tempos'] for e in eventos],[1,1])

    def test_rejeita_acorde_lacuna_e_ligadura_incompleta(self):
        for elemento,inicio in [(chord.Chord(['C4','E4']),0),(note.Note('C4'),1)]:
            score,parte = self.partitura()
            m = stream.Measure(number=1)
            m.insert(inicio,elemento)
            parte.append(m)
            with self.assertRaises(ErroPartitura):
                eventos_da_partitura(score)
        score,parte = self.partitura()
        m = stream.Measure(number=1)
        n = note.Note('C5')
        n.tie = tie.Tie('start')
        m.append(n)
        parte.append(m)
        with self.assertRaisesRegex(ErroPartitura,'sem final'):
            eventos_da_partitura(score)

    def test_pausa_de_compasso(self):
        score,parte = self.partitura()
        m = stream.Measure(number=1)
        m.timeSignature = meter.TimeSignature('4/4')
        m.append(note.Rest(quarterLength=4))
        parte.append(m)
        eventos,_ = eventos_da_partitura(score)
        self.assertEqual(eventos[0]['tipo'],'pausa')
        self.assertEqual(eventos[0]['tempos'],4)

    def test_fermata_explicita_aviso(self):
        score,parte = self.partitura()
        m = stream.Measure(number=1)
        n = note.Note('C5',quarterLength=4)
        n.expressions.append(expressions.Fermata())
        m.append(n)
        parte.append(m)
        eventos,avisos = eventos_da_partitura(score)
        self.assertEqual(eventos[0]['tempos'],4)
        self.assertIn('fermata',avisos[0])

    def test_compasso_incompleto_nao_inventa_pausa(self):
        score,parte = self.partitura()
        m = stream.Measure(number=11)
        m.timeSignature = meter.TimeSignature('4/4')
        m.append(note.Note('C5',quarterLength=3))
        parte.append(m)
        with self.assertRaisesRegex(ErroPartitura,'Compasso 11'):
            eventos_da_partitura(score)

    def test_fim_a_fim_musicxml_para_wav(self):
        from argparse import Namespace
        from scipy.io import wavfile
        from leitura_pagina import processar_paginas
        score,parte = self.partitura()
        m = stream.Measure(number=1)
        m.timeSignature = meter.TimeSignature('4/4')
        m.append(note.Note('E-5',quarterLength=2))
        m.append(note.Rest(quarterLength=2))
        parte.append(m)
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            xml = score.write('musicxml',fp=raiz/'fonte.musicxml')
            args = Namespace(saida=raiz/'saida',musicxml=[xml],imagem=None,
                             bpm=120,parte=1,audiveris=None)
            with patch('builtins.print'):
                self.assertEqual(processar_paginas(args),0)
            taxa,audio = wavfile.read(raiz/'saida/melodia.wav')
            self.assertEqual(taxa,44100)
            self.assertEqual(len(audio),2*44100)
            self.assertTrue(audio[:44100].any())
            self.assertFalse(audio[44100:].any())
            self.assertTrue((raiz/'saida/eventos.json').is_file())

    def criar_pdf(self,caminho):
        conteudo = b'BT /F1 6 Tf 10 150 Td (Violin) Tj ET'
        objetos = [b'<< /Type /Catalog /Pages 2 0 R >>',
                   b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                   b'<< /Length '+str(len(conteudo)).encode()+b' >>\nstream\n'+conteudo+b'\nendstream']
        dados = b'%PDF-1.4\n'
        offsets = [0]
        for i,objeto in enumerate(objetos,1):
            offsets.append(len(dados))
            dados += str(i).encode()+b' 0 obj\n'+objeto+b'\nendobj\n'
        xref = len(dados)
        dados += b'xref\n0 6\n0000000000 65535 f \n'
        for offset in offsets[1:]:
            dados += f'{offset:010d} 00000 n \n'.encode()
        dados += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF'
        caminho.write_bytes(dados)

    def test_renderizar_pdf_preserva_original_e_registra_rotulo(self):
        import cv2,json
        from leitura_pagina import renderizar_pdf
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            pdf = raiz/'fonte.pdf'
            self.criar_pdf(pdf)
            original = pdf.read_bytes()
            a = renderizar_pdf(pdf,raiz/'normal',paginas=[1],dpi=150)
            b = renderizar_pdf(pdf,raiz/'sem_rotulo',paginas=[1],dpi=150,
                               ocultar_rotulos=['Violin'])
            sem_mascara,mascarada = cv2.imread(str(a[0]),0),cv2.imread(str(b[0]),0)
            self.assertEqual(sem_mascara.shape,(417,417))
            self.assertTrue(np.any(sem_mascara<mascarada))
            self.assertTrue(np.all(sem_mascara<=mascarada))
            self.assertEqual(pdf.read_bytes(),original)
            registro = json.loads((raiz/'sem_rotulo/renderizacao.json').read_text())
            self.assertEqual(registro['paginas'][0]['rotulos_ocultados'][0]['texto'],'Violin')
            with self.assertRaises(ErroPartitura):
                renderizar_pdf(pdf,raiz/'invalida',paginas=[2])

    def test_pausa_multicompasso_sem_contagem_e_rejeitada(self):
        import cv2
        from subprocess import CompletedProcess
        from leitura_pagina import transcrever
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            entrada = raiz/'fonte.png'
            cv2.imwrite(str(entrada),np.full((100,100),255,np.uint8))
            def executar(comando,**kwargs):
                destino = Path(comando[comando.index('-output')+1])
                (destino/'pagina.mxl').write_bytes(b'nao sera lido')
                kwargs['stdout'].write('WARN Multirest with no measure count, using default value 1\n')
                return CompletedProcess(comando,0)
            with patch('leitura_pagina.subprocess.run',side_effect=executar):
                with self.assertRaisesRegex(ErroPartitura,'Contagem de pausa'):
                    transcrever(entrada,raiz,'Audiveris.exe')

    def test_imagem_invalida_e_executavel_ausente(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ErroPartitura):
                preparar_imagem(Path(pasta)/'ausente.png',Path(pasta)/'destino.png')
        with self.assertRaises(ErroPartitura):
            localizar_audiveris('executavel_que_nao_existe_231.exe')


if __name__ == '__main__':
    unittest.main()
