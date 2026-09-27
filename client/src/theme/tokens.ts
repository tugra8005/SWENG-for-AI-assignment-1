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
  strip: '#0E0D0B',
  stripText: '#D4576B', // siyah şerit üstünde 5,4:1 (bordonun açık tonu)
  ok: '#2F4A2A',
};

export const cellar = {
  bg: '#000000',
  amber: '#FFB000', // siyah üstünde 11,5:1
  amberDecayed: '#A87300', // çürümüş metnin alt sınırı, 5,1:1
  amberDim: '#7A5500', // yalnızca çerçeve, çubuk, büyük yazı (3,1:1)
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
