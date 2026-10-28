import unittest
from pathlib import Path
import cv2
import numpy as np
from main import analisar, sintetizar


class RitmoTest(unittest.TestCase):
    def test_partitura_incluida(self):
        cinza = cv2.imread(str(Path(__file__).parent/'imagens/partitura.png'), 0)
        eventos, avisos, _ = analisar((cinza < 127).astype(np.uint8))
        self.assertEqual(avisos, [])
        self.assertEqual([e['nome'] for e in eventos],
                         ['Si4','Do5','Re5','Mi5','Fa5','Sol5','Fa5','Mi5',
                          'Fa5','Sol5','La5','Sol5','Fa5','Sol5','La5'])
        self.assertEqual([e['tempos'] for e in eventos],
                         [2,2,2,1,1,3,1,2,1,1,3,1,2,1,1])
        self.assertEqual(len(sintetizar(eventos,120)), 12*44100)
        self.assertEqual(len(sintetizar(eventos,60)), 24*44100)

    def test_silencio_e_arredondamento(self):
        eventos = [dict(tipo='pausa', tempos=t) for t in [1, .5, .25, 1.5]]
        audio = sintetizar(eventos,137)
        self.assertEqual(len(audio), round(3.25*60/137*44100))
        self.assertFalse(audio.any())
        self.assertEqual(len(sintetizar([],120)), 0)

    def pauta(self):
        b = np.zeros((95,220),np.uint8)
        for y in [30,40,50,60,70]:
            b[y,5:215] = 1
        return b

    def test_pausas_retangulares(self):
        b = self.pauta()
        b[46:50,80:94] = 1  # minima apoiada na terceira linha
        b[41:45,140:154] = 1  # semibreve sob a quarta linha
        eventos, avisos, _ = analisar(b)
        self.assertEqual(avisos, [])
        self.assertEqual([(e['tipo'],e['tempos']) for e in eventos],
                         [('pausa',2),('pausa',4)])

    def test_bandeirola_e_barra(self):
        b = self.pauta()
        for x in [85,145]:
            cv2.ellipse(b,(x-6,65),(7,4),-25,0,360,1,-1)
            b[20:66,x] = 1
        b[20:23,85:146] = 1
        eventos, avisos, _ = analisar(b)
        self.assertEqual([e['tempos'] for e in eventos], [.5,.5])
        self.assertEqual(avisos, [])

    def test_bandeirolas_sinteticas(self):
        for quantidade in [1,2,3]:
            with self.subTest(quantidade=quantidade):
                b = self.pauta()
                cv2.ellipse(b,(79,65),(7,4),-25,0,360,1,-1)
                b[15:66,85] = 1
                for i in range(quantidade):
                    b[15+7*i:18+7*i,85:98] = 1
                eventos, avisos, _ = analisar(b)
                self.assertEqual(avisos, [])
                self.assertEqual([e['tempos'] for e in eventos], [1/2**quantidade])

    def test_simbolo_desconhecido_avisa(self):
        b = self.pauta()
        cv2.circle(b,(110,55),7,1,-1)
        eventos, avisos, _ = analisar(b)
        self.assertEqual(eventos, [])
        self.assertTrue(avisos)


if __name__ == '__main__':
    unittest.main()
