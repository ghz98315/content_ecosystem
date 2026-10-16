// Start the production build locally, then run with its origin as argv[2].
import assert from 'node:assert/strict';
const base = process.argv[2] || 'http://127.0.0.1:3106';
const cases = [
  ['/', 'GET', 200],
  ['/video-collection', 'GET', 200],
  ['/api/narration?stageId=not-authenticated', 'GET', 400],
  ['/api/narration', 'POST', 400],
  ['/api/narration', 'PATCH', 409],
  ['/api/image-regeneration', 'POST', 400],
  ['/api/signed-url', 'GET', 400],
  ['/api/signed-url?path=test-task/external/test-version/narration.wav', 'GET', 401],
  ['/api/signed-url?path=test-task/background-music/music.mp3', 'GET', 401],
  ['/api/background-music', 'POST', 401],
  ['/api/voice-sample', 'POST', 401],
];
for (const [path, method, expected] of cases) {
  const response = await fetch(new URL(path, base), {
    method, headers: {'Content-Type':'application/json'},
    ...(method === 'GET' ? {} : {body:JSON.stringify({stageId:'not-authenticated'})}),
  });
  assert.equal(response.status, expected, `${method} ${path}`);
  if (path.startsWith('/api/')) {
    const data = await response.json();
    assert.equal(typeof data.error, 'string');
    assert.equal(data.signedUrl, undefined);
  }
  console.log(`PASS ${method} ${path} (${expected})`);
}
console.log(`${cases.length} HTTP checks passed; authenticated upload and ASR require their separate acceptance checks.`);
