import { DeleteObjectsCommand, GetObjectCommand, HeadObjectCommand, ListObjectsV2Command, S3Client } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

let client: S3Client | undefined;
export const r2Enabled = () => Boolean(process.env.R2_BUCKET);
const bucket = () => process.env.R2_BUCKET!;

function r2() {
  if (client) return client;
  const { R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY } = process.env;
  if (!R2_ACCOUNT_ID || !/^[a-f0-9]{32}$/i.test(R2_ACCOUNT_ID) || !R2_ACCESS_KEY_ID || !R2_SECRET_ACCESS_KEY)
    throw new Error('R2 存储配置不完整');
  client = new S3Client({
    endpoint: `https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com`, region: 'auto', forcePathStyle: true,
    credentials: { accessKeyId: R2_ACCESS_KEY_ID, secretAccessKey: R2_SECRET_ACCESS_KEY },
    requestChecksumCalculation: 'WHEN_REQUIRED', responseChecksumValidation: 'WHEN_REQUIRED',
  });
  return client;
}

export function isR2MediaPath(path: string) {
  return /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\/.+\.(png|jpe?g|webp|mp4)$/i.test(path)
    && !path.includes('\\') && !path.split('/').some(part => !part || part === '.' || part === '..');
}

export async function r2MediaInfo(path: string) {
  if (!r2Enabled() || !isR2MediaPath(path)) return null;
  try {
    return await r2().send(new HeadObjectCommand({ Bucket: bucket(), Key: path }));
  } catch (error) {
    if ((error as { $metadata?: { httpStatusCode?: number } }).$metadata?.httpStatusCode === 404) return null;
    throw error;
  }
}

export async function signR2Media(path: string) {
  return getSignedUrl(r2(), new GetObjectCommand({ Bucket: bucket(), Key: path }), { expiresIn: 300 });
}

export async function removeR2Media(paths: string[]) {
  if (!r2Enabled() || !paths.length) return;
  const result = await r2().send(new DeleteObjectsCommand({
    Bucket: bucket(), Delete: { Objects: paths.map(Key => ({ Key })) },
  }));
  if (result.Errors?.length) throw new Error('R2 媒体清理失败');
}

export async function listR2TaskMedia(taskId: string) {
  if (!r2Enabled()) return [];
  const paths: string[] = [];
  let token: string | undefined;
  do {
    const page = await r2().send(new ListObjectsV2Command({ Bucket: bucket(), Prefix: `${taskId}/`, ContinuationToken: token }));
    for (const object of page.Contents || []) {
      if (object.Key?.startsWith(`${taskId}/`) && isR2MediaPath(object.Key)) paths.push(object.Key);
    }
    token = page.NextContinuationToken;
  } while (token);
  return paths;
}
