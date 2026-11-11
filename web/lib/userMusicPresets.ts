const USER_PRESET = /^user-music\/([0-9a-f-]{36})\/(guoxue|health)\/[0-9a-f-]{36}--([A-Za-z0-9_-]+)\.(mp3|wav|m4a)$/;

export function userMusicPresetMatch(path: string) {
  return USER_PRESET.exec(path);
}
