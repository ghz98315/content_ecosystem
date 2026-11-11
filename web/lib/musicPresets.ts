export type MusicCategory = 'guoxue' | 'health';

export const DEFAULT_BGM_VOLUME = 0.10;

export type MusicPreset = {
  id: string;
  category: MusicCategory;
  label: string;
  mood: string;
  path: string;
  sourceUrl: string;
  credit: string;
  userProvided?: boolean;
};

const attribution = (title: string, sourceUrl: string) =>
  `音乐：${title} — Kevin MacLeod (incompetech.com)；来源：${sourceUrl}；CC BY 4.0：https://creativecommons.org/licenses/by/4.0/；用于本视频时已循环、调节音量并做淡入淡出。`;

const preset = (id: string, category: MusicCategory, label: string, mood: string, isrc: string): MusicPreset => {
  const sourceUrl = `https://incompetech.com/music/royalty-free/index.html?isrc=${isrc}`;
  return { id, category, label, mood, path: `music-presets/${id}.mp3`, sourceUrl, credit: attribution(label, sourceUrl) };
};

export const MUSIC_PRESETS: readonly MusicPreset[] = [
  { id:'guoxue-yougu', category:'guoxue', label:'国风幽谷静心曲', mood:'国风 · 静心', path:'music-presets/guoxue-yougu.mp3', sourceUrl:'', credit:'用户提供音频，请按实际授权范围使用。', userProvided:true },
  { id:'guoxue-1030', category:'guoxue', label:'国学类背景音乐1030', mood:'国学 · 舒缓', path:'music-presets/guoxue-1030.mp3', sourceUrl:'', credit:'用户提供音频，请按实际授权范围使用。', userProvided:true },
  { id:'health-yekong', category:'health', label:'夜空的寂静 — 赵海洋', mood:'钢琴 · 宁静', path:'music-presets/health-yekong.mp3', sourceUrl:'', credit:'《夜空的寂静》— 赵海洋。请按实际授权范围使用。', userProvided:true },
  { id:'health-qiudesi', category:'health', label:'秋的思念 — 赵海洋', mood:'钢琴 · 温柔', path:'music-presets/health-qiudesi.mp3', sourceUrl:'', credit:'《秋的思念》— 赵海洋。请按实际授权范围使用。', userProvided:true },
  preset('guoxue-ripples', 'guoxue', 'Ripples', '古筝独奏感 · 沉静', 'USUAN1100691'),
  preset('guoxue-ishikari-lore', 'guoxue', 'Ishikari Lore', '弹拨与笛声 · 叙事', 'USUAN1100192'),
  preset('guoxue-finding-movement', 'guoxue', 'Finding Movement', '弹拨与弦乐 · 温和', 'USUAN1100693'),
  preset('health-morning', 'health', 'Morning', '木吉他、竖琴与长笛 · 明朗', 'USUAN2300003'),
  preset('health-evening', 'health', 'Evening', '吉他、大提琴与双簧管 · 温暖', 'USUAN2300002'),
  preset('health-midsummer-sky', 'health', 'Midsummer Sky', '舒缓明亮 · 陪伴', 'USUAN1100158'),
];

export const MUSIC_PRESET_PATHS = new Set(MUSIC_PRESETS.map(item => item.path));
export const musicPresetByPath = (path: string) => MUSIC_PRESETS.find(item => item.path === path);
