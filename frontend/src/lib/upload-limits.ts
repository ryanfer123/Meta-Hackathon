import type { Health } from '../types';

const mib = (bytes: number) => `${Math.floor(bytes / (1024 * 1024))} MiB`;

export function uploadLimitReason(health: Health, files: (File | null | undefined)[]): string {
  const selected = files.filter((file): file is File => !!file);
  if (health.max_upload_bytes && selected.some((file) => file.size > health.max_upload_bytes!))
    return `Choose a recording of ${mib(health.max_upload_bytes)} or less.`;
  if (
    health.max_cloud_source_bytes &&
    selected.reduce((sum, file) => sum + file.size, 0) > health.max_cloud_source_bytes
  )
    return `These recordings exceed the ${mib(health.max_cloud_source_bytes)} combined cloud limit. Compress them or choose smaller files.`;
  return '';
}

export function cloudUploadHelp(health: Health): string {
  return health.max_cloud_source_bytes
    ? `Cloud saves allow ${mib(health.max_cloud_source_bytes)} total across the teaching and second videos. Duration and analysis limits also apply.`
    : '';
}
