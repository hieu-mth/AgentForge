// Serialize only fields declared by the selected backend adapter.
export function profilePayload(values,adapter) {
  const profile={id:values.id?.trim(),provider:adapter.id,
    model:values.model?.trim(),enabled:values.enabled===true};
  for(const key of Object.keys(adapter.defaults))profile[key]=values[key]?.trim();
  return profile;
}
