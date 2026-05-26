// MediaPipe Hands gesture tracker
// window.THREE must be set before calling init()

const GESTURE = {
  pinchDist:   0.06,
  explosiveMs: 150,
};

let camera3D    = null;
let lastGesture = 'none';
let lastFistTime = null;
let prevPalmPos  = { x: 0, y: 0, z: 0 };
let prevTime     = performance.now();

/**
 * @param {HTMLVideoElement} videoEl
 * @param {THREE.PerspectiveCamera} camera — Three.js camera for world-space unproject
 * @param {Function} onGesture — ({gesture, worldPos, velocity}) each frame
 */
export async function init(videoEl, camera, onGesture) {
  camera3D = camera;

  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js');
  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js');

  const hands = new window.Hands({
    locateFile: (f) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  });

  hands.setOptions({
    maxNumHands: 1,
    modelComplexity: 1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.5,
  });

  hands.onResults((results) => {
    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      if (lastGesture !== 'none') {
        onGesture({ gesture: 'none', worldPos: null, velocity: null });
        lastGesture = 'none';
      }
      return;
    }

    const lm      = results.multiHandLandmarks[0];
    const gesture = _classify(lm);
    const worldPos = _landmarkToWorld(lm[9]);

    const now = performance.now();
    const dt  = Math.max((now - prevTime) / 1000, 0.001);
    prevTime  = now;

    const velocity = {
      x: (worldPos.x - prevPalmPos.x) / dt,
      y: (worldPos.y - prevPalmPos.y) / dt,
      z: (worldPos.z - prevPalmPos.z) / dt,
    };
    prevPalmPos = { ...worldPos };
    lastGesture = gesture;

    onGesture({ gesture, worldPos, velocity });
  });

  const mpCamera = new window.Camera(videoEl, {
    onFrame: async () => { await hands.send({ image: videoEl }); },
    width: 320,
    height: 240,
  });
  mpCamera.start();
}

function _loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const s = document.createElement('script');
    s.src = src;
    s.onload  = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

function _dist(a, b) {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
}

function _classify(lm) {
  const thumbTip  = lm[4];
  const indexTip  = lm[8];
  const middleTip = lm[12];
  const ringTip   = lm[16];
  const pinkyTip  = lm[20];

  // Pinch: thumb-index close
  if (_dist(thumbTip, indexTip) < GESTURE.pinchDist) return 'pinch';

  // Curl: tip y > pip y in image coords (y increases downward)
  const indexCurled  = indexTip.y  > lm[6].y;
  const middleCurled = middleTip.y > lm[10].y;
  const ringCurled   = ringTip.y   > lm[14].y;
  const pinkyCurled  = pinkyTip.y  > lm[18].y;

  const allCurled = indexCurled && middleCurled && ringCurled && pinkyCurled;
  if (allCurled) {
    if (lastGesture !== 'attract') lastFistTime = performance.now();
    return 'attract';
  }

  // Explosive open: fist → open within threshold
  if (lastGesture === 'attract' && lastFistTime !== null) {
    const elapsed = performance.now() - lastFistTime;
    if (elapsed < GESTURE.explosiveMs) {
      lastFistTime = null;
      return 'explode';
    }
  }

  // Point: only index extended
  if (!indexCurled && middleCurled && ringCurled && pinkyCurled) return 'repel';

  const allOpen = !indexCurled && !middleCurled && !ringCurled && !pinkyCurled;
  if (allOpen) {
    // Wrist tilt: angle of wrist→middle_mcp determines rotate vs flow
    const dx    = lm[9].x - lm[0].x;
    const dy    = lm[9].y - lm[0].y;
    const angle = Math.abs(Math.atan2(dy, dx));
    return (angle < 0.5 || angle > 2.6) ? 'rotate' : 'flow';
  }

  return 'none';
}

function _landmarkToWorld(lm) {
  const THREE = window.THREE;
  const ndcX  = (lm.x * 2) - 1;
  const ndcY  = -(lm.y * 2) + 1;

  const v   = new THREE.Vector3(ndcX, ndcY, 0.5);
  v.unproject(camera3D);
  const dir = v.sub(camera3D.position).normalize();
  const t   = -camera3D.position.z / dir.z;
  const wp  = camera3D.position.clone().add(dir.multiplyScalar(t));

  return { x: wp.x, y: wp.y, z: wp.z };
}
