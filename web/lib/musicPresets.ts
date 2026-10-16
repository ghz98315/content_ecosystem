export type MusicCategory = 'guoxue' | 'health';

export type MusicPreset = {
  id: string;
  category: MusicCategory;
  label: string;
  mood: string;
  path: string;
  defaultVolume: number;
  sourceUrl: string;
  credit: string;
};

const attribution = (title: string, sourceUrl: string) =>
  `音乐：${title} — Kevin MacLeod (incompetech.com)；来源：${sourceUrl}；CC BY 4.0：https://creativecommons.org/licenses/by/4.0/；用于本视频时已循环、调节音量并做淡入淡出。`;

const preset = (id: string, category: MusicCategory, label: string, mood: string, isrc: string, defaultVolume: number): MusicPreset => {
  const sourceUrl = `https://incompetech.com/music/royalty-free/index.html?isrc=${isrc}`;
  return { id, category, label, mood, path: `music-presets/${id}.mp3`, defaultVolume, sourceUrl, credit: attribution(label, sourceUrl) };
};

export const MUSIC_PRESETS: readonly MusicPreset[] = [
  preset('guoxue-ripples', 'guoxue', 'Ripples', '古筝独奏感 · 沉静', 'USUAN1100691', 0.08),
  preset('guoxue-ishikari-lore', 'guoxue', 'Ishikari Lore', '弹拨与笛声 · 叙事', 'USUAN1100192', 0.07),
  preset('guoxue-finding-movement', 'guoxue', 'Finding Movement', '弹拨与弦乐 · 温和', 'USUAN1100693', 0.07),
  preset('health-morning', 'health', 'Morning', '木吉他、竖琴与长笛 · 明朗', 'USUAN2300003', 0.08),
  preset('health-evening', 'health', 'Evening', '吉他、大提琴与双簧管 · 温暖', 'USUAN2300002', 0.08),
  preset('health-midsummer-sky', 'health', 'Midsummer Sky', '舒缓明亮 · 陪伴', 'USUAN1100158', 0.07),
];

export const MUSIC_PRESET_PATHS = new Set(MUSIC_PRESETS.map(item => item.path));
export const musicPresetByPath = (path: string) => MUSIC_PRESETS.find(item => item.path === path);
