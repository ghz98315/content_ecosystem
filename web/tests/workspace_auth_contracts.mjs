import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
const effects = [], states = [], listeners = [];
let signIns = 0;
const module = { exports: {} };
const supabase = { auth: {
  getSession: async () => ({ data: { session: null } }),
  signInAnonymously: async () => { signIns++; return { data: { user: { id: 'same-workspace' } } }; },
  onAuthStateChange: fn => { listeners.push(fn); return { data: { subscription: { unsubscribe() {} } } }; },
} };
new Function('module', 'exports', 'require', ts.transpileModule(fs.readFileSync('lib/useAnonAuth.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText)(module, module.exports, name => name === 'react' ? { useEffect: fn => effects.push(fn), useState: () => [null, value => states.push(value)] } : { supabase });
module.exports.useAnonAuth(); module.exports.useAnonAuth();
const cleanups = effects.map(effect => effect());
for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve));
assert.equal(signIns, 1, 'Concurrent page mounts must share anonymous sign-in');
assert.equal(states.filter(value => value === 'same-workspace').length, 2);
listeners.forEach(fn => fn('TOKEN_REFRESHED', { user: { id: 'same-workspace' } }));
assert.equal(signIns, 1, 'Token refresh must not create a new identity');
cleanups.forEach(cleanup => cleanup());
console.log('PASS: concurrent workspace initialization shares one identity and follows session refresh');
