// Run with Node after installing @electric-sql/pglite in worker/output/external-sql-runtime.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '../output/external-sql-runtime/node_modules/@electric-sql/pglite/dist/index.js';

const db = new PGlite();
const owner = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
await db.exec(`
  create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth; create schema storage;
  create table auth.users(id uuid primary key);
  create function auth.uid() returns uuid language sql stable as
    'select nullif(current_setting(''test.user'',true),'''')::uuid';
  grant usage on schema auth to authenticated;
  grant execute on function auth.uid() to authenticated;
  insert into auth.users values ('${owner}'),('${other}');
  create table storage.objects(bucket_id text,name text,metadata jsonb);
`);
const initial = (await readFile(new URL('../../supabase/migrations/0001_init.sql', import.meta.url), 'utf8'))
  .replace('create extension if not exists pgcrypto;', '');
await db.exec(initial);
await db.exec(`
  alter type stage_status add value 'cancelled';
  create table public.image_replacement_requests(id uuid primary key default gen_random_uuid(),task_id uuid,invalidated_at timestamptz,status text,error text);
  grant usage on schema public to authenticated,service_role;
  grant select,insert,update on public.tasks,public.stages,public.artifacts to authenticated;
  alter table public.tasks enable row level security;
  create policy task_owner on public.tasks to authenticated using(owner=auth.uid()) with check(owner=auth.uid());
  alter table public.stages enable row level security;
  create policy stage_owner on public.stages to authenticated using(exists(select 1 from public.tasks where id=task_id and owner=auth.uid()));
  grant select,update on public.image_replacement_requests to authenticated;
`);
await db.exec(await readFile(new URL('../../supabase/migrations/0034_external_narration.sql', import.meta.url), 'utf8'));
await db.query('select set_config($1,$2,false)', ['test.user',owner]);
const task = (await db.query("insert into tasks(owner,tts_source) values($1,'external') returning id",[owner])).rows[0].id;
await db.query("update stages set seq=case kind when 'image' then 5 when 'book' then 6 when 'tts' then 7 else seq end where task_id=$1",[task]);
await db.query("update stages set status='done' where task_id=$1 and kind='book'",[task]);
await db.query("update stages set status='done',params=jsonb_build_object('final_text','今天读经典。') where task_id=$1 and kind='rewrite'",[task]);
await db.query("update stages set status='done' where task_id=$1 and kind in ('ingest','transcribe','clean')",[task]);
const stage = (await db.query("select * from stages where task_id=$1 and kind='tts'",[task])).rows[0];
assert.equal(stage.params.audio_source,'external');
const action = async (name,data={}) => (await db.query('select narration_action($1,$2,$3) as value',[stage.id,name,data])).rows[0].value;
const getStage = async () => (await db.query('select * from stages where id=$1',[stage.id])).rows[0];
const prepare = () => action('prepare',{name:'voice.wav',extension:'wav',size:100});

await db.exec('set role authenticated');
const n1 = await prepare();
await assert.rejects(action('submit',{id:n1.id}), /上传尚未完成/);
await db.exec('reset role');
await db.query("insert into storage.objects values('artifacts',$1,'{\"size\":100}')",[n1.original_path]);
await db.exec('set role authenticated');
await action('submit',{id:n1.id});
await action('submit',{id:n1.id}); // repeat confirmation is safe
assert.equal((await getStage()).params.external_id,n1.id);
await assert.rejects(db.query('select claim_media_stage($1)',[stage.id]),/permission denied/);
await db.exec('reset role');
const imageId=(await db.query("select id from stages where task_id=$1 and kind='image'",[task])).rows[0].id;
assert.equal((await db.query('select * from claim_media_stage($1)',[imageId])).rows.length,0);
const claim = (await db.query('select * from claim_media_stage($1)',[stage.id])).rows[0];
assert.equal(claim.status,'processing');
await assert.rejects(action('source',{source:'automatic'}),/正在处理/);
const finish = async (job,review={alignment_ready:true,duration:10}) =>
  (await db.query("select finish_external_narration($1,$2,'review',$3,$4,$5) as ok",[stage.id,job,review,n1.original_path.replace('original.wav','render.wav'),n1.original_path.replace('original.wav','subtitles.json')])).rows[0].ok;
assert.equal(await finish('obsolete-job'),false);
assert.equal(await finish(claim.params.external_job),true);
assert.equal((await getStage()).status,'needs_review');
await db.exec('set role authenticated');
const n1Row=(await db.query('select * from external_narrations where id=$1',[n1.id])).rows[0];
await assert.rejects(action('approve',{id:n1.id,subtitle_path:'stale.json'}),/字幕版本已变化/);
await action('approve',{id:n1.id,subtitle_path:n1Row.subtitle_path});
await action('approve',{id:n1.id,subtitle_path:n1Row.subtitle_path});
assert.equal((await getStage()).status,'done');
assert.equal((await db.query("select count(*)::int as n from artifacts where task_id=$1 and stage_kind='tts'",[task])).rows[0].n,2);
await db.exec('reset role');
assert.equal((await db.query('select * from claim_media_stage($1)',[imageId])).rows[0].status,'processing');
await db.exec('set role authenticated');
await assert.rejects(db.query('select * from regenerate_image_stage($1)',[imageId]),/正在处理/);
assert.equal((await getStage()).status,'done');
await db.exec('reset role');
await db.query("update stages set status='done' where id=$1",[imageId]);
const replacement=(await db.query("insert into image_replacement_requests(task_id,status) values($1,'pending') returning id",[task])).rows[0].id;
assert.equal((await db.query('select * from claim_image_replacement($1)',[replacement])).rows[0].status,'processing');
await db.exec('set role authenticated');
await assert.rejects(action('source',{source:'automatic'}),/图片正在替换/);
await assert.rejects(db.query('select * from regenerate_image_stage($1)',[imageId]),/图片正在替换/);
await assert.rejects(db.query('select * from rerun_stage($1)',[imageId]),/图片正在替换/);
await assert.rejects(db.query('select * from claim_image_replacement($1)',[replacement]),/permission denied/);
await db.exec('reset role');
await db.query("update image_replacement_requests set status='done' where id=$1",[replacement]);
await db.exec('set role authenticated');

// Image rerun preserves the reviewed recording.
const image=(await db.query("select id from stages where task_id=$1 and kind='image'",[task])).rows[0];
await db.query('select * from rerun_stage($1)',[image.id]);
assert.equal((await getStage()).status,'done');
await db.query('select * from regenerate_image_stage($1)',[image.id]);
assert.equal((await getStage()).status,'done');
const generation1=(await db.query('select params from stages where id=$1',[image.id])).rows[0].params.generation_id;
assert.ok(generation1);
await db.query('select * from regenerate_image_stage($1)',[image.id]);
assert.notEqual((await db.query('select params from stages where id=$1',[image.id])).rows[0].params.generation_id,generation1);
await db.exec('reset role');
await db.query("update image_replacement_requests set status='pending' where id=$1",[replacement]);
assert.equal((await db.query('select * from claim_image_replacement($1)',[replacement])).rows.length,0);
await db.exec('set role authenticated');

// A newer submitted version prevents a delayed older upload becoming active.
const n2=await prepare(), n3=await prepare();
await db.exec('reset role');
await db.query("insert into storage.objects values('artifacts',$1,'{\"size\":100}'),('artifacts',$2,'{\"size\":100}')",[n2.original_path,n3.original_path]);
await db.exec('set role authenticated');
await action('submit',{id:n3.id});
await assert.rejects(action('submit',{id:n2.id}),/较新的配音版本/);
await assert.rejects(action('approve',{id:n1.id,subtitle_path:n1Row.subtitle_path}),/配音版本已变化/);

// Owner isolation applies to both RPCs and the history table.
await db.query('select set_config($1,$2,false)', ['test.user',other]);
assert.equal((await db.query('select * from external_narrations')).rows.length,0);
await assert.rejects(action('source',{source:'automatic'}),/无权操作/);
await db.query('select set_config($1,$2,false)', ['test.user',owner]);
await db.query("update stages set status='pending' where task_id=$1 and kind='rewrite'",[task]);
assert.equal((await getStage()).params.external_id,undefined);
const automatic=(await db.query('insert into tasks(owner) values($1) returning id',[owner])).rows[0].id;
const automaticRewrite=(await db.query("select id from stages where task_id=$1 and kind='rewrite'",[automatic])).rows[0].id;
await db.query("update stages set status='done' where task_id=$1",[automatic]);
await db.query("update stages set params=jsonb_build_object('final_text','old','cover_title','old','cover_subtitle','old','cover_confirmed',true) where id=$1",[automaticRewrite]);
await db.query('select * from rerun_stage($1)',[automaticRewrite]);
const resetParams=(await db.query('select params from stages where id=$1',[automaticRewrite])).rows[0].params;
for(const key of ['final_text','cover_title','cover_subtitle','cover_confirmed']) assert.equal(resetParams[key],undefined);
await db.close();
console.log('External narration SQL: upload/version/permission/approval/rerun/invalidation checks passed');
