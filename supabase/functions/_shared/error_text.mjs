export function errorText(error, limit = 1200) {
  if (error instanceof Error) return String(error.message || error.name || 'unknown error').slice(0, limit);
  if (typeof error === 'string') return error.slice(0, limit);
  if (error == null) return String(error);
  try {
    const fields = ['message', 'code', 'details', 'hint', 'status', 'statusCode'];
    const picked = Object.fromEntries(fields.filter(key => error[key] != null).map(key => [key, error[key]]));
    const value = Object.keys(picked).length ? picked : error;
    const text = JSON.stringify(value);
    return (text && text !== '{}') ? text.slice(0, limit) : 'unknown structured error';
  } catch {
    return 'unserializable structured error';
  }
}
