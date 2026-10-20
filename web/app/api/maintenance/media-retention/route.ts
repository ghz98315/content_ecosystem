import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { cleanupCancelledTask } from '@/lib/cancelledTaskCleanup';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const GRID_TYPES = ['image_grid'];
const IMAGE_TYPES = ['image', 'image_replacement', 'cover_image'];
const VIDEO_TYPES = ['final'];
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const GRID_AGE_MS = 24 * 60 * 60 * 1000;
const IMAGE_AGE_MS = 48 * 60 * 60 * 1000;
const VIDEO_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const INFO_CONCURRENCY = 25;

export async function GET(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get('authorization') !== `Bearer ${secret}`)
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) return NextResponse.json({ error: 'server misconfigured' }, { status: 500 });

  const dryRun = request.nextUrl.searchParams.get('dryRun') === '1';
  const gridCutoff = new Date(Date.now() - GRID_AGE_MS).toISOString();
  const imageCutoff = new Date(Date.now() - IMAGE_AGE_MS).toISOString();
  const videoCutoff = new Date(Date.now() - VIDEO_AGE_MS).toISOString();
  const supabase = createClient(url, key);
  // Run a bounded cancellation sweep first, so media retention cannot starve it.
  const cancelledResults: Array<{ id: string; result: string }> = [];
  const cancelledFailures: string[] = [];
  if (!dryRun) {
    const { data: cancelled, error: cancelledError } = await supabase.from('tasks')
      .select('id').eq('status', 'cancelled').order('updated_at', { ascending: true }).limit(20);
    if (cancelledError) cancelledFailures.push(`cancelled tasks: ${cancelledError.message}`);
    for (const task of cancelled || []) {
      if (cancelledResults.filter(item => item.result === 'deleted').length >= 3) break;
      try {
        const result = await cleanupCancelledTask(supabase, task.id, undefined, true);
        cancelledResults.push({ id: task.id, result: result.result });
      } catch (error) {
        cancelledFailures.push(`cancelled task ${task.id}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }
  const [gridsResult, imagesResult, videosResult] = await Promise.all([
    supabase.from('artifacts').select('id,task_id,type,storage_path,created_at')
      .in('type', GRID_TYPES).lt('created_at', gridCutoff)
      .order('created_at', { ascending: true }).limit(100),
    supabase.from('artifacts').select('id,task_id,type,storage_path,created_at')
      .in('type', IMAGE_TYPES).lt('created_at', imageCutoff)
      .order('created_at', { ascending: true }).limit(250),
    supabase.from('artifacts').select('id,task_id,type,storage_path,created_at')
      .in('type', VIDEO_TYPES).lt('created_at', videoCutoff)
      .order('created_at', { ascending: true }).limit(50),
  ]);
  if (gridsResult.error || imagesResult.error || videosResult.error)
    return NextResponse.json({ error: gridsResult.error?.message || imagesResult.error?.message || videosResult.error?.message }, { status: 500 });
  const rows = [...(gridsResult.data || []), ...(imagesResult.data || []), ...(videosResult.data || [])];

  const taskIds = [...new Set((rows || []).map(row => row.task_id))];
  const { data: tasks, error: taskError } = taskIds.length
    ? await supabase.from('tasks').select('id,status').in('id', taskIds)
    : { data: [], error: null };
  if (taskError) return NextResponse.json({ error: taskError.message }, { status: 500 });
  const terminal = new Set((tasks || []).filter(task => ['done', 'failed', 'cancelled'].includes(task.status)).map(task => task.id));
  const { data: imageStages, error: imageStageError } = taskIds.length
    ? await supabase.from('stages').select('task_id').in('task_id', taskIds).eq('kind', 'image').eq('status', 'done')
    : { data: [], error: null };
  if (imageStageError) return NextResponse.json({ error: imageStageError.message }, { status: 500 });
  const imageDone = new Set((imageStages || []).map(stage => stage.task_id));
  const seen = new Set<string>();
  const candidates = rows
    .filter(row => (terminal.has(row.task_id) || (row.type === 'image_grid' && imageDone.has(row.task_id))) && UUID.test(row.task_id)
      && row.storage_path.startsWith(`${row.task_id}/`)
      && !row.storage_path.includes('\\') && !row.storage_path.split('/').some((part: string) => !part || part === '.' || part === '..'))
    .filter(row => { if (seen.has(row.storage_path)) return false; seen.add(row.storage_path); return true; });

  let removed = 0;
  let missingObjects = 0;
  let skippedNewer = 0;
  const failures: string[] = cancelledFailures;
  // A task can have hundreds of stills. Bound concurrency to fit one cron
  // invocation without sending an unbounded burst to Supabase.
  for (let start = 0; start < candidates.length; start += INFO_CONCURRENCY) {
    await Promise.all(candidates.slice(start, start + INFO_CONCURRENCY).map(async candidate => {
      const { storage_path: path, type } = candidate;
      const cutoff = type === 'image_grid' ? gridCutoff : IMAGE_TYPES.includes(type) ? imageCutoff : videoCutoff;
      try {
        // A rerender can reuse a storage path. Never delete its new object
        // because an older artifact row crossed the retention boundary.
        const { data: latest, error: latestError } = await supabase.from('artifacts')
          .select('id,created_at').eq('storage_path', path)
          .order('created_at', { ascending: false }).limit(1);
        if (latestError) throw latestError;
        if (!latest?.length || latest[0].created_at >= cutoff) { skippedNewer++; return; }
        // Older releases did not refresh artifact.created_at on overwrite.
        const { data: objectInfo, error: infoError } = await supabase.storage.from('artifacts').info(path);
        if (infoError && /object not found/i.test(infoError.message)) {
          // Older manual cleanups removed the object but left its DB row.
          // Clear only the stale media record; no Storage deletion is needed.
          missingObjects++;
          if (!dryRun) {
            const { error: deleteError } = await supabase.from('artifacts').delete()
              .eq('storage_path', path).eq('type', type).lt('created_at', cutoff);
            if (deleteError) throw deleteError;
          }
          return;
        }
        if (infoError || !objectInfo?.lastModified) throw infoError || new Error('Object timestamp unavailable');
        if (new Date(objectInfo.lastModified).getTime() >= new Date(cutoff).getTime()) {
          skippedNewer++;
          if (!dryRun) {
            const { error: refreshError } = await supabase.from('artifacts')
              .update({ created_at: objectInfo.lastModified }).eq('storage_path', path)
              .eq('type', type).lt('created_at', cutoff);
            if (refreshError) throw refreshError;
          }
          return;
        }
        if (dryRun) { removed++; return; }
        const { error: removeError } = await supabase.storage.from('artifacts').remove([path]);
        if (removeError) throw removeError;
        const { error: deleteError } = await supabase.from('artifacts').delete()
          .eq('storage_path', path).eq('type', type).lt('created_at', cutoff);
        if (deleteError) throw deleteError;
        removed++;
      } catch {
        failures.push(path);
      }
    }));
  }
  // External uploads are stored outside artifacts. Expire their physical audio
  // after 48h, while keeping transcript, subtitle text and review history.
  const { data: externalRows, error: externalError } = await supabase.from('external_narrations')
    .select('id,task_id,original_path,audio_path,review,created_at')
    .lt('created_at', imageCutoff).order('created_at', { ascending: true }).limit(100);
  if (externalError) failures.push(`external narrations: ${externalError.message}`);
  const externalPending = (externalRows || []).filter(row => !row.review?.audio_expired_at).slice(0, 10);
  const externalTaskIds = [...new Set(externalPending.map(row => row.task_id))];
  const { data: externalTasks, error: externalTaskError } = externalTaskIds.length
    ? await supabase.from('tasks').select('id,status').in('id', externalTaskIds)
    : { data: [], error: null };
  if (externalTaskError) failures.push(`external tasks: ${externalTaskError.message}`);
  const externalTerminal = new Set((externalTasks || []).filter(task => ['done', 'failed', 'cancelled'].includes(task.status)).map(task => task.id));
  let expiredExternalVersions = 0;
  let removedExternalAudio = 0;
  for (const row of externalPending) {
    if (!externalTerminal.has(row.task_id) || !UUID.test(row.task_id)) continue;
    const paths = [...new Set([row.original_path, row.audio_path].filter((path): path is string => !!path))];
    if (paths.some(path => !path.startsWith(`${row.task_id}/external/`) || path.includes('\\')
      || path.split('/').some(part => !part || part === '.' || part === '..'))) continue;
    try {
      const existing: string[] = [];
      let recentlyModified = false;
      for (const path of paths) {
        const { data: info, error: infoError } = await supabase.storage.from('artifacts').info(path);
        if (infoError && /object not found/i.test(infoError.message)) continue;
        if (infoError || !info?.lastModified) throw infoError || new Error('Audio timestamp unavailable');
        if (new Date(info.lastModified).getTime() >= new Date(imageCutoff).getTime()) { recentlyModified = true; break; }
        existing.push(path);
      }
      if (recentlyModified) continue;
      if (!dryRun) {
        if (existing.length) {
          const { error: removeError } = await supabase.storage.from('artifacts').remove(existing);
          if (removeError) throw removeError;
          for (const path of existing) {
            const { error: artifactError } = await supabase.from('artifacts').delete()
              .eq('task_id', row.task_id).eq('type', 'audio').eq('storage_path', path);
            if (artifactError) throw artifactError;
          }
        }
        const { error: updateError } = await supabase.from('external_narrations').update({
          audio_path: null,
          review: { ...(row.review || {}), audio_expired_at: new Date().toISOString() },
        }).eq('id', row.id);
        if (updateError) throw updateError;
      }
      expiredExternalVersions++;
      removedExternalAudio += existing.length;
    } catch {
      failures.push(`external narration ${row.id}`);
    }
  }
  return NextResponse.json({ dryRun, scanned: rows.length, eligible: candidates.length,
    removed, missingObjects, skippedNewer, expiredExternalVersions, removedExternalAudio, failures: failures.length,
    moreCandidates: (gridsResult.data?.length || 0) === 100 || (imagesResult.data?.length || 0) === 250 || (videosResult.data?.length || 0) === 50,
    retentionHours: { sourceGrids: 24, images: 48, finalVideo: 168 }, cancelledResults });
}
