import { friendlyError } from '../api';

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const { message, details } = friendlyError(error);
  return (
    <div className="error-message" role="alert">
      <p>{message}</p>
      {details !== message && (
        <details>
          <summary>Show details</summary>
          <p className="mono">{details}</p>
        </details>
      )}
    </div>
  );
}
