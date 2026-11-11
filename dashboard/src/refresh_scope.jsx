import {createContext, useCallback, useContext, useEffect, useRef} from 'react';

const RefreshContext = createContext(null);

export function RefreshScope({children}) {
  const callbacks = useRef(new Set());
  const pending = useRef(null);
  const register = useCallback(callback => {
    callbacks.current.add(callback);
    return () => callbacks.current.delete(callback);
  }, []);
  const refresh = useCallback(() => {
    if (!pending.current) {
      pending.current = Promise.allSettled([...callbacks.current].map(fn => fn()))
        .then(results => {
          const failed = results.find(r => r.status === 'rejected');
          if (failed) throw failed.reason;
        }).finally(() => {pending.current = null;});
    }
    return pending.current;
  }, []);
  return <RefreshContext.Provider value={{register, refresh}}>{children}</RefreshContext.Provider>;
}

// Only mounted screens register GET loaders. Updating a callback never remounts forms.
export function useScreenRefresh(callback) {
  const scope = useContext(RefreshContext);
  const latest = useRef(callback);
  latest.current = callback;
  useEffect(() => scope?.register(() => latest.current()), [scope?.register]);
}

export function useRefreshScreen() {
  return useContext(RefreshContext)?.refresh;
}
