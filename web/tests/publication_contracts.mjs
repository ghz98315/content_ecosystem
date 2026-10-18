import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const originalFetch = globalThis.fetch;
const moduleCache = new Map();
let allowOwner = true, stageStatus = 'done', script = '人到了一定年纪，要学会关心家人，也给彼此空间。今天读《道德经》。';
let saved = null, modelCalls = 0, writes = 0;
const taskId = '11111111-1111-4111-8111-111111111111';
const db = {
  auth: { getUser: async token => ({ data: { user: token === 'valid' ? { id: 'owner' } : null } }) },
  from(table) {
    let inserted;
    const query = new Proxy({}, { get(_, method) {
      if (method === 'then') return resolve => resolve({ data: table === 'artifacts' ? (saved ? [saved] : []) : null });
      if (method === 'insert') return payload => { inserted = payload; return query; };
      if (method === 'maybeSingle') return async () => ({ data: allowOwner ? { id: taskId, title: '原标题 #家庭', source_tags: ['家庭'], content_category: 'health' } : null });
      if (method === 'single') return async () => {
        if (table === 'stages') return { data: { status: stageStatus, params: { final_text: script } } };
        writes++; saved = { ...inserted, created_at: new Date().toISOString() }; return { data: saved };
      };
      return () => query;
    } }); return query;
  },
};
function load(file) {
  if (moduleCache.has(file)) return moduleCache.get(file);
  const module = { exports: {} };
  const resolve = name => name === '@supabase/supabase-js' ? { createClient: () => db } : name.startsWith('@/') ? load(`${name.slice(2)}.ts`) : require(name);
  new Function('module', 'exports', 'require', ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText)(module, module.exports, resolve);
  moduleCache.set(file, module.exports); return module.exports;
}
const { validatePublication, publicationText } = load('lib/publication.ts');
const copy = { cover_title: '关心也要留白', cover_subtitle: '把自己的日子过踏实', publish_title: '操心太多时读读道德经', description: '从家人的相处中，读懂关心与边界。', tags: ['#道德经', '家庭', '家庭'], interaction_comment: '关心家人也需要分寸。你有没有越操心越累的经历？', purchase_comment: '想继续读懂处世智慧，可以到主页橱窗看看相关书籍。', replies: ['谢谢分享，给彼此一点空间。'] };
copy.cover_options = [{ title: copy.cover_title, subtitle: copy.cover_subtitle }, { title: '操心也有边界', subtitle: '给家人一点空间' }, { title: '为什么越管越累', subtitle: '读懂关心的分寸' }];
copy.publish_titles = [copy.publish_title, '关心家人也要照顾自己', '你是否也有放不下的担心'];
assert.throws(() => validatePublication({ ...copy, cover_options: copy.cover_options.slice(0, 2) }));
assert.throws(() => validatePublication({ ...copy, publish_titles: Array(3).fill('相同标题') }));
assert.deepEqual(validatePublication(copy).tags, ['道德经', '家庭']);
assert.throws(() => validatePublication({ ...copy, interaction_comment: '字'.repeat(101) }));
assert.throws(() => validatePublication({ ...copy, purchase_comment: '字'.repeat(101) }));
assert.throws(() => validatePublication({ ...copy, replies: ['字'.repeat(51)] }));
assert.throws(() => validatePublication({ ...copy, replies: Array(6).fill('回复') }));
assert.throws(() => validatePublication({ ...copy, tags: ['不合法 话题'] }));
assert.match(publicationText(validatePublication(copy)), /回复建议1/);
process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.invalid';
process.env.SUPABASE_SERVICE_KEY = 'unit-service';
process.env.DEEPSEEK_API_KEY = 'unit-key';
const route = load('app/api/publication/route.ts');
const request = (body, token = 'valid') => new Request('https://example.invalid/api/publication', { method: 'POST', headers: token ? { authorization: `Bearer ${token}` } : {}, body: JSON.stringify({ taskId, ...body }) });
try {
  globalThis.fetch = async (url, options) => {
    modelCalls++;
    const body = JSON.parse(options.body);
    assert.equal(url, 'https://api.deepseek.com/chat/completions');
    assert.equal(JSON.parse(body.messages[1].content).confirmed_script, script);
    assert.match(body.messages[0].content, /100字以内/);
    return Response.json({ choices: [{ message: { content: JSON.stringify(copy) } }] });
  };
  assert.equal((await route.POST(request({ action: 'generate' }, ''))).status, 401);
  allowOwner = false; assert.equal((await route.POST(request({ action: 'generate' }))).status, 403); allowOwner = true;
  stageStatus = 'needs_review'; assert.equal((await route.POST(request({ action: 'generate' }))).status, 409); stageStatus = 'done';
  assert.equal(modelCalls, 0);
  const generated = await (await route.POST(request({ action: 'generate' }))).json();
  assert.equal(generated.copy.cover_title, copy.cover_title); assert.equal(writes, 0);
  assert.equal((await route.POST(request({ action: 'save', copy, sourceHash: 'old' }))).status, 409);
  const result = await route.POST(request({ action: 'save', copy, sourceHash: generated.sourceHash }));
  assert.equal(result.status, 201); assert.equal(writes, 1); assert.equal(saved.type, 'publication_copy');
  assert.equal((await route.POST(request({ action: 'save', copy, sourceHash: generated.sourceHash }))).status, 409);
  script += '新增正文';
  const get = new Request(`https://example.invalid/api/publication?taskId=${taskId}`, { headers: { authorization: 'Bearer valid' } });
  Object.defineProperty(get, 'nextUrl', { value: new URL(get.url) });
  const loaded = await (await route.GET(get)).json(); assert.equal(loaded.stale, true);
  assert.equal(writes, 1);
  const retention = fs.readFileSync('app/api/maintenance/media-retention/route.ts', 'utf8');
  assert.ok(!retention.match(/const MEDIA_TYPES = \[[^\]]*publication_copy/));
  console.log('PASS: publication lengths, owner authentication, confirmed script, draft-only generation, saved versions, stale detection and retention isolation');
} finally { globalThis.fetch = originalFetch; }
