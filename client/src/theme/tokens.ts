/**
 * Tasarım belirteçleri.
 *
 * Meydan: kırık beyaz kâğıt, mürekkep, tek vurgu mühür bordosu.
 * Mahzen: tam siyah, fosfor amberi. Kontrast oranları DESIGN.md §13'te.
 */

export const paper = {
  bg: '#F4EFE4',
  bgDeep: '#ECE5D6',
  sheet: '#F8F4EB',
  ink: '#1B1A17',
  inkSoft: '#4A463E', // kâğıt üstünde 8,2:1
  muted: '#6B6558', // kâğıt üstünde 5,0:1
  rule: '#1B1A17',
  hairline: '#CFC6B3',
  seal: '#7A1E2B', // kâğıt üstünde 9,0:1
  sealWash: 'rgba(122, 30, 43, 0.07)',
  insertWash: 'rgba(122, 30, 43, 0.16)', // diff'te eklenen metnin zemini; mürekkep üstünde 13:1
  strip: '#0E0D0B',
  stripText: '#D4576B', // siyah şerit üstünde 5,4:1 (bordonun açık tonu)
  ok: '#2F4A2A',
  disabled: '#A39C8E', // devre dışı düğme çerçevesi; yazısı muted
};

export const cellar = {
  bg: '#000000',
  amber: '#FFB000', // siyah üstünde 11,5:1
  // Tarama çizgisi satırı %14 karartır; oranlar o satırda da AA kalacak şekilde seçildi (DESIGN.md §13).
  amberDecayed: '#B88000', // çürümüş metnin alt sınırı: 6,1:1, tarama satırında 4,7:1
  amberDim: '#8F6400', // yalnızca çerçeve, çubuk, büyük yazı: 4,0:1, tarama satırında 3,2:1
  amberGlow: 'rgba(255, 176, 0, 0.12)',
  line: '#3A2900',
};

export const fonts = {
  serif: 'Newsreader_400Regular',
  serifItalic: 'Newsreader_400Regular_Italic',
  serifMedium: 'Newsreader_500Medium',
  serifBold: 'Newsreader_700Bold',
  serifDisplay: 'Newsreader_800ExtraBold',
  mono: 'IBMPlexMono_400Regular',
  monoMedium: 'IBMPlexMono_500Medium',
  monoBold: 'IBMPlexMono_700Bold',
  terminal: 'VT323_400Regular',
};

export const layout = {
  maxWidth: 780,
  gutter: 16,
};
