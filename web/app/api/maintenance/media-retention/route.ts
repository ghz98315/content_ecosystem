import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const MEDIA_TYPES = ['image', 'image_grid', 'image_replacement', 'cover_image', 'final'];
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
// Hobby cron can run once daily and up to 59 minutes into its hour. Start on
// day 13 so a normally running scheduler removes media before day 15.
const AGE_MS = 13 * 24 * 60 * 60 * 1000;
const INFO_CONCURRENCY = 25;

export async function GET(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get('authorization') !== `Bearer ${secret}`)
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) return NextResponse.json({ error: 'server misconfigured' }, { status: 500 });

  const dryRun = request.nextUrl.searchParams.get('dryRun') === '1';
  const cutoff = new Date(Date.now() - AGE_MS).toISOString();
  const supabase = createClient(url, key);
  const { data: rows, error } = await supabase.from('artifacts')
    .select('id,task_id,type,storage_path,created_at')
    .in('type', MEDIA_TYPES).lt('created_at', cutoff)
    .order('created_at', { ascending: true }).limit(500);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const taskIds = [...new Set((rows || []).map(row => row.task_id))];
  const { data: tasks, error: taskError } = taskIds.length
    ? await supabase.from('tasks').select('id,status').in('id', taskIds)
    : { data: [], error: null };
  if (taskError) return NextResponse.json({ error: taskError.message }, { status: 500 });
  const terminal = new Set((tasks || []).filter(task => ['done', 'failed', 'cancelled'].includes(task.status)).map(task => task.id));
  const paths = [...new Set((rows || [])
    .filter(row => terminal.has(row.task_id) && UUID.test(row.task_id)
      && row.storage_path.startsWith(`${row.task_id}/`)
      && !row.storage_path.includes('\\') && !row.storage_path.split('/').some((part: string) => !part || part === '.' || part === '..'))
    .map(row => row.storage_path))];

  let removed = 0;
  let missingObjects = 0;
  let skippedNewer = 0;
  const failures: string[] = [];
  // A task can have hundreds of stills. Bound concurrency to fit one cron
  // invocation without sending an unbounded burst to Supabase.
  for (let start = 0; start < paths.length; start += INFO_CONCURRENCY) {
    await Promise.all(paths.slice(start, start + INFO_CONCURRENCY).map(async path => {
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
              .eq('storage_path', path).in('type', MEDIA_TYPES).lt('created_at', cutoff);
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
              .in('type', MEDIA_TYPES).lt('created_at', cutoff);
            if (refreshError) throw refreshError;
          }
          return;
        }
        if (dryRun) { removed++; return; }
        const { error: removeError } = await supabase.storage.from('artifacts').remove([path]);
        if (removeError) throw removeError;
        const { error: deleteError } = await supabase.from('artifacts').delete()
          .eq('storage_path', path).in('type', MEDIA_TYPES).lt('created_at', cutoff);
        if (deleteError) throw deleteError;
        removed++;
      } catch {
        failures.push(path);
      }
    }));
  }
  return NextResponse.json({ dryRun, scanned: rows?.length || 0, eligible: paths.length,
    removed, missingObjects, skippedNewer, failures: failures.length,
    moreCandidates: (rows?.length || 0) === 500 });
}
