import { SupabaseClient } from '@supabase/supabase-js';

const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const BUCKET = 'artifacts';

/** A cancelled task is disposable only after active processing has stopped. */
export async function cleanupCancelledTask(db: SupabaseClient, taskId: string, owner?: string, allowStaleProcessing = false) {
  if (!UUID.test(taskId)) throw new Error('无效任务编号');
  let query = db.from('tasks').select('id,owner,status,updated_at').eq('id', taskId).eq('status', 'cancelled');
  if (owner) query = query.eq('owner', owner);
  const { data: task, error: taskError } = await query.maybeSingle();
  if (taskError) throw taskError;
  if (!task) return { result: 'not_found' as const, removedFiles: 0 };

  const [{ data: running, error: stageError }, { data: posts, error: postError }] = await Promise.all([
    db.from('stages').select('id').eq('task_id', taskId).eq('status', 'processing').limit(1),
    db.from('published_posts').select('id').eq('task_id', taskId).limit(1),
  ]);
  if (stageError || postError) throw stageError || postError;
  if (posts?.length) return { result: 'published' as const, removedFiles: 0 };
  if (running?.length && (!allowStaleProcessing || Date.now() - Date.parse(task.updated_at) < 2 * 60 * 60 * 1000))
    return { result: 'busy' as const, removedFiles: 0 };

  const files: string[] = [];
  const folders = [taskId];
  while (folders.length) {
    const folder = folders.pop()!;
    for (let offset = 0; ; offset += 100) {
      const { data: entries, error } = await db.storage.from(BUCKET).list(folder, { limit: 100, offset });
      if (error) throw error;
      for (const entry of entries || []) {
        if (!entry.name || entry.name === '.' || entry.name === '..' || entry.name.includes('/') || entry.name.includes('\\'))
          throw new Error('存储路径异常，已停止清理');
        const path = `${folder}/${entry.name}`;
        if (entry.id) files.push(path);
        else folders.push(path);
      }
      if ((entries || []).length < 100) break;
    }
  }
  for (let index = 0; index < files.length; index += 100) {
    const { error } = await db.storage.from(BUCKET).remove(files.slice(index, index + 100));
    if (error) throw error;
  }
  const { data: deleted, error: deleteError } = await db.from('tasks').delete()
    .eq('id', taskId).eq('owner', task.owner).eq('status', 'cancelled').select('id');
  if (deleteError) throw deleteError;
  return { result: deleted?.length ? 'deleted' as const : 'not_found' as const, removedFiles: files.length };
}
