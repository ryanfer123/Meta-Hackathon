import { json } from '../api';
export async function pollJob<T extends { status?: string; error?: string }>(
  path: string,
  onUpdate?: (result: T) => void,
): Promise<T> {
  const deadline = Date.now() + 60 * 60 * 1000;
  for (let n = 0; Date.now() < deadline; n++) {
    const result = await json<T>(path);
    onUpdate?.(result);
    if (result.status === 'error')
      throw new Error(result.error ?? 'The recording could not be checked.');
    if (result.status === 'ready') return result;
    await new Promise((resolve) => setTimeout(resolve, n < 30 ? 2000 : 5000));
  }
  throw new Error('Analysis is still running. Check My runs before trying again.');
}
