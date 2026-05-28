// Compute shader: integrate position from velocity.
export const positionShader = /* glsl */ `
  uniform float uDelta;
  void main() {
    vec2 uv = gl_FragCoord.xy / resolution.xy;
    vec4 pos = texture2D( texturePosition, uv );
    vec4 vel = texture2D( textureVelocity, uv );
    pos.xyz += vel.xyz * uDelta;
    gl_FragColor = pos;
  }
`

// Compute shader: forces -> velocity. uForceMode selects the active effect.
export const velocityShader = /* glsl */ `
  uniform float uDelta;
  uniform float uTime;
  uniform float uSpread;     // target sphere-shell radius
  uniform float uCore;       // inner radius
  uniform int   uForceMode;  // 0 none .. see effects.ts FORCE_MODE
  uniform vec3  uForceCenter;
  uniform vec3  uForceVector;
  uniform float uForceRadius;
  uniform float uForceStrength;

  vec3 targetFor(vec2 uv) {
    float n1 = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
    float n2 = fract(sin(dot(uv, vec2(39.3468, 11.135))) * 24634.6345);
    float n3 = fract(sin(dot(uv, vec2(73.156, 52.235))) * 91237.1234);
    float r = uCore + uSpread * pow(n3, 0.5);
    float theta = n1 * 6.28318530718;
    float phi = acos(n2 * 2.0 - 1.0);
    return vec3(
      cos(theta) * sin(phi),
      sin(theta) * sin(phi),
      cos(phi)
    ) * r;
  }

  vec3 tangent(vec3 v) { return normalize(vec3(-v.z, 0.0, v.x)); }

  void main() {
    vec2 uv = gl_FragCoord.xy / resolution.xy;
    vec4 pos = texture2D( texturePosition, uv );
    vec4 vel = texture2D( textureVelocity, uv );

    vec3 target = targetFor(uv);
    vec3 toTarget = target - pos.xyz;
    vel.xyz += toTarget * 0.6 * uDelta;

    if (uForceMode != 0) {
      vec3 toC = uForceCenter - pos.xyz;
      float d = length(toC);
      vec3 dir = d > 0.0001 ? toC / d : vec3(0.0);
      float falloff = max(0.0, 1.0 - d / max(uForceRadius, 0.0001));

      if (uForceMode == 1) {            // attract
        vel.xyz += dir * uForceStrength * falloff * uDelta * 60.0;
      } else if (uForceMode == 2) {     // repel
        vel.xyz -= dir * uForceStrength * falloff * uDelta * 60.0;
      } else if (uForceMode == 3) {     // freeze
        vel.xyz *= 0.5;
      } else if (uForceMode == 4) {     // shockwave (one-shot)
        vel.xyz -= dir * uForceStrength * falloff * uDelta * 60.0;
      } else if (uForceMode == 5) {     // vortex
        vel.xyz += dir * uForceStrength * falloff * uDelta * 30.0;
        vel.xyz += tangent(toC) * uForceStrength * falloff * uDelta * 30.0;
      } else if (uForceMode == 6) {     // orbit
        float ring = uForceRadius;
        vel.xyz += (d > ring ? dir : -dir) * uForceStrength * uDelta * 40.0;
        vel.xyz += tangent(toC) * uForceStrength * uDelta * 40.0;
      } else if (uForceMode == 7) {     // portal
        float ring = uForceRadius;
        if (abs(d - ring) < ring * 0.4) {
          vel.xyz += tangent(toC) * uForceStrength * uDelta * 40.0;
        } else {
          vel.xyz += (d > ring ? dir : -dir) * uForceStrength * uDelta * 30.0;
        }
      } else if (uForceMode == 8) {     // beam
        vel.xyz += normalize(uForceVector) * uForceStrength * uDelta * 40.0;
      } else if (uForceMode == 9) {     // wave (one-shot)
        vel.x += uForceVector.x * uForceStrength * uDelta * 40.0;
      } else if (uForceMode == 10) {    // breathe
        vel.xyz += -dir * sin(uTime * 2.5) * uForceStrength * falloff * uDelta * 30.0;
      }
    }

    vel.xyz *= 0.90;  // damping
    gl_FragColor = vel;
  }
`

export const renderVertexShader = /* glsl */ `
  uniform sampler2D texturePosition;
  uniform sampler2D textureVelocity;
  uniform float uHue;
  varying vec3 vColor;

  vec3 hsl2rgb(vec3 c) {
    vec3 rgb = clamp(abs(mod(c.x * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return c.z + c.y * (rgb - 0.5) * (1.0 - abs(2.0 * c.z - 1.0));
  }

  void main() {
    vec3 pos = texture2D( texturePosition, uv ).xyz;
    float speed = length( texture2D( textureVelocity, uv ).xyz );
    vColor = hsl2rgb(vec3(uHue + speed * 0.02, 0.85, 0.45 + min(speed * 0.1, 0.4)));
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    gl_PointSize = 2.0 + 60.0 / max(-mv.z, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`

export const renderFragmentShader = /* glsl */ `
  varying vec3 vColor;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float alpha = (1.0 - d * 2.0);
    gl_FragColor = vec4(vColor, alpha * 0.8);
  }
`
