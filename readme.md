# Leitura de partituras e geracao de audio

O projeto tem dois motores:

- `simples`: OpenCV, uma pauta em clave de Sol (a imagem original do projeto).
- `audiveris`: paginas inteiras impressas em PNG/JPG, convertidas em MusicXML
  pelo Audiveris e interpretadas pelo music21. A reproducao seleciona uma parte
  monofonica. Acordes e vozes sobrepostas sao rejeitados.

`auto` e o padrao: uma imagem com uma pauta usa o leitor simples; paginas que nao
se enquadram nessa geometria ou varias imagens usam Audiveris. Para uma pauta
isolada com acidentes, ligaduras e pausas complexas, selecione `--motor audiveris`.

## Execucao neste computador, sem administrador

O ambiente Python esta em `../.venv` e a copia local do Audiveris em
`../.tools/Audiveris`. Nao sao necessarios drivers, servicos, instalacao de Java
ou instalacao de aplicativo em Program Files. O motor traz seu proprio runtime.
Os dados de OCR em ingles ficam em `../.tools/Audiveris/tessdata`.
O Audiveris pode gravar configuracoes/cache na pasta do usuario, sem administrador.
A execucao continua sujeita as politicas de aplicativos da faculdade.

A partir da pasta onde esta `main.py`:

```powershell
.\executar.ps1
.\executar.ps1 --imagem "C:\Users\2022012001\Downloads\hello-v-6.jpg" --bpm 158 --saida resultado/hello
.\executar.ps1 --imagem imagens/pagina1.png imagens/pagina2.png --bpm 120
.\executar.ps1 --musicxml "resultado/hello/omr_EXEMPLO/pagina.mxl" --bpm 158
```

Se a politica do PowerShell nao permitir executar o script, use diretamente o
Python do ambiente, sem mudar politicas do computador:

```powershell
..\.venv\Scripts\python.exe main.py --imagem "C:\caminho\pagina.png" --motor audiveris
```

Para usar em outro computador, dependencias Python estao em `requirements.txt`.
Uma copia do Audiveris ja disponibilizada/autorizada pode ser indicada por
`--audiveris "C:\caminho\Audiveris.exe"` ou `AUDIVERIS_PATH`.
Nao ha instalacao automatica durante a leitura.

## Ritmo e resultados

O BPM representa seminimas por minuto, com padrao 120. `--bpm 158` usa 158;
marcacoes e mudancas de andamento impressas nao substituem esse valor. Cada evento
imprime altura ou pausa, compasso, tempos e segundos (`tempos * 60 / BPM`).
Pausas geram amostras zero. Ligaduras de prolongacao unem a duracao das notas;
ligaduras de expressao preservam cada nota. Alturas alteradas usam os acidentes
interpretados do MusicXML. Repeticoes sao expandidas pelo music21.
Fermatas nao tem duracao numerica universal: o programa avisa e toca somente
a duracao escrita, sem inventar um prolongamento.

O motor de pagina guarda imagem preparada, log, `.omr` e `.mxl` numa subpasta
nova `resultado/omr_*`. `eventos.json` e `melodia.wav` so sao gerados depois da
validacao. A ausencia de formula de compasso, compassos com duracao inconsistente,
ligaduras incompletas, lacunas sem pausa explicita ou cobertura incompleta das
pautas interrompem a geracao. `erro_leitura.txt` identifica falhas de validacao.
Os arquivos de reconhecimento ficam disponiveis para revisao no Audiveris local;
um MusicXML corrigido pode ser lido com `--musicxml`, sem novo reconhecimento.
Um WAV de execucao anterior pode permanecer no disco quando uma nova leitura falha.

Uma imagem por argumento e considerada uma pagina na ordem fornecida. Cada pagina
precisa ser musicalmente independente: ligaduras de prolongacao entre arquivos e
heranca de armadura/compasso entre arquivos nao sao implementadas. Para essas
situacoes, use um unico MusicXML revisado contendo todas as paginas. Uma pagina
com varias pautas da mesma melodia e tratada dentro do mesmo arquivo. Nao ha
suporte a colunas, manuscritos nem garantia de reconhecimento de toda fonte.
`--parte 2` seleciona outra parte exportada; as demais nao sao misturadas ao audio.

## Validacao realizada

A imagem original `imagens/partitura.png` produz 15 notas, 24 tempos: 12 segundos
em 120 BPM. Sao cinco minimas, oito seminimas e duas minimas pontuadas. Nao ha
pausas, bandeirolas nem barras de ligacao visiveis nessa imagem.

O arquivo fornecido `hello-v-6.jpg` tem 565 x 800 pixels e oito pautas. O motor
local conseguiu executar e detectar as oito pautas, mas o reconhecimento nao
passou na validacao: no MusicXML exportado, o compasso 11 da parte 1 totaliza
3 tempos em vez de 4. O OCR tambem separou partes da mesma melodia de forma
inconsistente. Nao foi mantido um WAV como transcricao valida dessa pagina.
Esse resultado requer revisao do `.omr`/MusicXML ou uma imagem de melhor qualidade.
Ampliar uma imagem pequena nao recupera simbolos perdidos.

Testes:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
```

Os testes cobrem a imagem original, BPM, silencio, barras, bandeirolas, notas com
bemol, pausas de compasso, prolongacao, expressao, fermata e rejeicao de entradas
musicalmente inconsistentes. O leitor simples conserva seus limites: sem armadura,
acidentes, acordes, cabecas sem haste ou pausas de seminima/menores.


## PDF de Hello em alta qualidade: proxima etapa validada

Agora e possivel fornecer PDF diretamente. O arquivo original permanece intacto;
as paginas renderizadas e o registro das transformacoes ficam em `pdf_*`.

```powershell
..\.venv\Scripts\python.exe main.py --pdf "C:\Users\2022012001\Downloads\hello imagem nova.pdf" --paginas 1 --dpi 400 --ocultar-rotulos Violin Vl. --bpm 158 --saida resultado/hello_pdf
```

`--paginas` seleciona paginas a partir de 1. Sem essa opcao, renderiza todas.
`--dpi` aceita 150 a 600 (padrao 300). `--ocultar-rotulos` e opcional: mascara
apenas os textos indicados, na margem esquerda, na imagem de trabalho. Esta
opcao evitou que as variantes OCR de Violin/Vl. criassem instrumentos diferentes.
As caixas mascaradas ficam registradas em `renderizacao.json`.
As limitacoes de ligaduras/armadura entre paginas continuam valendo.

A primeira pagina foi testada em 300 e 400 DPI. As oito pautas foram detectadas,
mas a pagina ainda nao passou: no teste de 400 DPI, a pausa inicial de tres
compassos desapareceu e o compasso OMR 34 ficou com dois tempos em vez de quatro.
Contagens de pausas que o Audiveris substitui por um padrao agora tambem sao
rejeitadas. Duracoes consistentes, sozinhas, nao garantem transcricao correta.

Foi criada uma referencia separada dos oito primeiros compassos, conferida com
a primeira pauta. Os compassos iniciais de silencio foram restaurados por
conferencia humana do numero 3, e essa intervencao esta declarada no relatorio.
Nao e resultado automatico integral. Arquivos em `resultado/hello_pdf`:

- `diagnostico_validacao.json`: comparacao dos testes e problemas encontrados.
- `trecho_conferido/compassos_1_a_8.musicxml`: referencia revisada.
- `trecho_conferido/compassos_1_a_8.wav`: 32 tempos, cerca de 12,15 segundos em 158 BPM.
- `trecho_conferido/validacao.json`: eventos e registro da correcao humana.

O trecho comeca com tres compassos de silencio (cerca de 4,56 segundos), conforme
a partitura. As ligaduras de prolongacao conferidas somam as duracoes das notas.
As outras paginas ainda nao tiveram o reconhecimento musical validado.
