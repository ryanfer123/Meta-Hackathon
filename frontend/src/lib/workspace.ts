import type { Run } from '../types';
import { supabase } from './supabase';

export interface SavedRun {
  id: string;
  name: string;
  provenance: 'synthetic' | 'live-recording';
  source_run_id: string;
  created_at: string;
  chain_root: string | null;
}
export interface Recording {
  id: string;
  name: string;
  object_path: string;
  kind: 'expert' | 'held_out' | 'novice';
  size_bytes: number;
  status: string;
  created_at: string;
}

function client() {
  if (!supabase) throw new Error('Cloud storage is not configured for this installation.');
  return supabase;
}

export async function saveRun(run: Run) {
  const { data, error } = await client().rpc('save_run_snapshot', { snapshot: run });
  if (error) throw error;
  return data as string;
}

export async function listRuns(): Promise<SavedRun[]> {
  const { data, error } = await client()
    .from('run_records')
    .select('id,name,provenance,source_run_id,created_at,chain_root')
    .order('created_at', { ascending: false })
    .limit(100);
  if (error) throw error;
  return data;
}

export async function openSavedRun(id: string): Promise<Run> {
  const { data, error } = await client()
    .from('run_records')
    .select('payload')
    .eq('id', id)
    .single();
  if (error) throw error;
  return data.payload as Run;
}

export async function deleteSavedRun(id: string) {
  const { error } = await client().rpc('delete_run_snapshot', { run_uuid: id });
  if (error) throw error;
}

export async function listRecordings(): Promise<Recording[]> {
  const { data, error } = await client()
    .from('recordings')
    .select('id,name,object_path,kind,size_bytes,status,created_at')
    .order('created_at', { ascending: false })
    .limit(100);
  if (error) throw error;
  return data;
}

export async function uploadRecording(file: File, kind: Recording['kind'], userId: string) {
  if (file.size === 0 || file.size > 50 * 1024 * 1024)
    throw new Error('Choose a non-empty recording under 50 MB.');
  const mime =
    file.type || (file.name.toLowerCase().endsWith('.mov') ? 'video/quicktime' : 'video/mp4');
  if (!['video/mp4', 'video/quicktime'].includes(mime))
    throw new Error('Choose an MP4 or MOV recording.');
  const db = client();
  const path = `${userId}/${crypto.randomUUID()}.${mime === 'video/quicktime' ? 'mov' : 'mp4'}`;
  const { error: uploadError } = await db.storage
    .from('recordings')
    .upload(path, file, { contentType: mime, upsert: false });
  if (uploadError) throw uploadError;
  const { error } = await db
    .from('recordings')
    .insert({
      owner_id: userId,
      name: file.name.slice(0, 240),
      object_path: path,
      kind,
      size_bytes: file.size,
      mime_type: mime,
    });
  if (error) {
    await db.storage.from('recordings').remove([path]);
    throw error;
  }
}

export async function recordingUrl(path: string) {
  const { data, error } = await client().storage.from('recordings').createSignedUrl(path, 60);
  if (error) throw error;
  return data.signedUrl;
}

export async function deleteRecording(recording: Recording) {
  const db = client();
  const { error: fileError } = await db.storage.from('recordings').remove([recording.object_path]);
  if (fileError) throw fileError;
  const { error } = await db.from('recordings').delete().eq('id', recording.id);
  if (error) throw error;
}
