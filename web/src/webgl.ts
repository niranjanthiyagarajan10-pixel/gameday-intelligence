/** True when the browser can create a WebGL context. Kept out of the 3D chunk so the Live tab can ask cheaply. */
export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}
