/** Preserve a committed POST receipt even if subsequent GET refresh fails.
 * Mutation failures still reject and must not be misreported as a commit.
 * Never automatically re-issue an irreversible action.
 */
export async function actionWithRefresh(action, refresh, onRefreshFailure) {
  const receipt = await action();
  if (refresh) {
    try { await refresh(); }
    catch (error) { onRefreshFailure?.(error); }
  }
  return receipt;
}
