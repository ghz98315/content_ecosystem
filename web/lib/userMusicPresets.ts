import { isMusicCategory } from './musicPresets';

const USER_PRESET = /^user-music\/([0-9a-f-]{36})\/([a-z_]+)\/[0-9a-f-]{36}--([A-Za-z0-9_-]+)\.(mp3|wav|m4a)$/;

export function userMusicPresetMatch(path: string) {
  const match = USER_PRESET.exec(path);
  return match && isMusicCategory(match[2]) ? match : null;
}
