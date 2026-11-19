// Serialize only fields declared by the selected backend adapter.
export function profilePayload(values,adapter) {
  const profile={id:values.id?.trim(),provider:adapter.id,
    model:values.model?.trim(),enabled:values.enabled===true};
  for(const key of Object.keys(adapter.defaults))profile[key]=values[key]?.trim();
  if(adapter.id==='comfyui'&&adapter.flux_workflow_max_bytes&&values.flux_enabled) {
    const {workflow,max_resolution,max_steps,timeout_seconds,output_dir}=values.flux_settings;
    profile.flux={workflow:JSON.parse(workflow),max_resolution,max_steps,timeout_seconds,output_dir};
  }
  return profile;
}
