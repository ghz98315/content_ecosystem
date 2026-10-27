export async function publicationResponse<T>(response: Response, fallback: string): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.toLowerCase().includes('application/json')) {
    if (response.status === 504) throw new Error('发布文案生成超时，请稍后重试；已完成的文案不会丢失');
    throw new Error(`${fallback}：服务返回了非 JSON 响应（HTTP ${response.status}），请稍后重试`);
  }
  let result: T & { error?: string };
  try { result = await response.json(); }
  catch { throw new Error(`${fallback}：服务响应格式异常（HTTP ${response.status}），请稍后重试`); }
  if (!response.ok) throw new Error(result?.error || `${fallback}（HTTP ${response.status}）`);
  return result;
}
