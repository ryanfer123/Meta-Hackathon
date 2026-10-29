import { json } from '../api';
export async function pollJob<T extends { status?: string; error?: string }>(
  path: string,
): Promise<T> {
  for (let n = 0; n < 300; n++) {
    const result = await json<T>(path);
    if (result.status === 'error')
      throw new Error(result.error ?? 'The recording could not be checked.');
    if (result.status === 'ready') return result;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error('Analysis is still running. Check My runs before trying again.');
}
