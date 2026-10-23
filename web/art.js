// The panel's objects (lamp, air conditioner, turntable, bell, alarm clock), drawn in SVG and lit
// from the upper left. Colour and looping motion come from style.css; the shading overlays are the
// shared gradients in index.html (#art-defs), so every copy reuses one set of defs.

const NS = 'http://www.w3.org/2000/svg';

function art(name, viewBox, body) {
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', viewBox);
  s.setAttribute('class', `art ${name}`);
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = body;
  return s;
}

const SHADE = 'M26 12Q40 9.5 54 12L64 42Q40 47 16 42Z';
export const lamp = () => art('lamp-art', '0 0 80 100', `
  <g class="l-light">
    <circle class="l-halo" cx="40" cy="32" r="40" mask="url(#m-spot)"/>
    <path class="l-cone" d="M18 43H62L80 98H0Z" mask="url(#m-fade)"/>
    <ellipse class="l-pool" cx="40" cy="91" rx="36" ry="6" mask="url(#m-spot)"/>
  </g>
  <ellipse cx="40" cy="92" rx="17" ry="3.4" fill="#0a0907" opacity=".6"/>
  <path d="M26 87h28v3a14 3.4 0 0 1-28 0z" fill="url(#g-brass)"/>
  <ellipse cx="40" cy="87" rx="14" ry="3.4" fill="#d9bd85"/>
  <rect x="38.6" y="40" width="2.8" height="47" fill="url(#g-brass)"/>
  <g class="l-head">
    <path class="l-shade" d="${SHADE}"/>
    <path d="${SHADE}" fill="url(#g-cyl)"/>
    <ellipse cx="40" cy="11.6" rx="14" ry="1.6" fill="#14110d"/>
    <ellipse class="l-mouth" cx="40" cy="42.4" rx="24" ry="3.2"/>
    <g class="l-chain">
      <path d="M57 44V58" stroke="#c4a873" stroke-width="1" stroke-dasharray="1.3 1"/>
      <circle cx="57" cy="60" r="2.1" fill="url(#g-brass)"/>
    </g>
  </g>`);

export const aircon = () => art('ac-art', '0 0 160 96', `
  <g class="ac-air" mask="url(#m-fade)">
    <path d="M44 54q-7 10 0 20t0 20"/><path d="M80 54q-7 10 0 20t0 20"/><path d="M116 54q-7 10 0 20t0 20"/>
  </g>
  <g class="ac-dots"><circle cx="60" cy="54" r="1.6"/><circle cx="98" cy="56" r="1.3"/><circle cx="134" cy="54" r="1.5"/><circle cx="26" cy="56" r="1.2"/></g>
  <rect x="6" y="9" width="148" height="44" rx="12" fill="#0a0907" opacity=".45"/>
  <rect x="6" y="6" width="148" height="44" rx="12" fill="#e7e0d2"/>
  <rect x="6" y="6" width="148" height="44" rx="12" fill="url(#g-top)"/>
  <path d="M20 9.5H140" stroke="#fff" stroke-opacity=".75" stroke-linecap="round"/>
  <path d="M18 21H106M18 26H106" stroke="#000" stroke-opacity=".08" stroke-width="1.4" stroke-linecap="round"/>
  <rect x="114" y="14" width="32" height="17" rx="4" fill="#1b1915"/>
  <text class="ac-temp" x="130" y="26.4" text-anchor="middle"></text>
  <circle class="ac-led" cx="146" cy="40" r="1.7"/>
  <rect x="16" y="40" width="124" height="6" rx="3" fill="#2a251f"/>
  <rect class="ac-flap" x="16" y="40" width="124" height="6" rx="3"/>`);

export const turntable = () => art('tt-art', '0 0 120 100', `
  <rect x="4" y="8" width="112" height="88" rx="10" fill="#0a0907" opacity=".5"/>
  <rect x="4" y="4" width="112" height="88" rx="10" fill="#2b2620"/>
  <rect x="4" y="4" width="112" height="88" rx="10" fill="url(#g-top)"/>
  <circle cx="50" cy="48" r="40" fill="#0d0c0a"/>
  <g class="tt-disc">
    <circle cx="50" cy="48" r="38" fill="#161412"/>
    <g fill="none" stroke="#fff"><circle cx="50" cy="48" r="33" stroke-opacity=".06"/><circle cx="50" cy="48" r="29" stroke-opacity=".04"/><circle cx="50" cy="48" r="25" stroke-opacity=".06"/><circle cx="50" cy="48" r="20" stroke-opacity=".04"/></g>
    <circle class="tt-label" cx="50" cy="48" r="12"/>
    <path d="M44 42a8.5 8.5 0 0 1 12 0" fill="none" stroke="#1a140a" stroke-opacity=".55" stroke-width="1.6" stroke-linecap="round"/>
    <circle cx="50" cy="48" r="1.6" fill="#0d0c0a"/>
  </g>
  <path d="M50 10a38 38 0 0 1 33 19L50 48z" fill="#fff" opacity=".07"/>
  <path d="M50 86a38 38 0 0 1-33-19L50 48z" fill="#fff" opacity=".04"/>
  <g class="tt-arm">
    <circle cx="100" cy="18" r="7" fill="url(#g-brass)"/>
    <circle cx="100" cy="18" r="2.4" fill="#2b2620"/>
    <path d="M100 18L97 60L88 70" fill="none" stroke="#d6c8aa" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="82" y="67" width="10" height="6" rx="1.6" fill="#ebe5d9" transform="rotate(42 87 70)"/>
  </g>
  <circle class="tt-led" cx="106" cy="83" r="2.4"/>`);

const BELL = 'M16 6C10.4 6 8.6 10.4 8.6 15v5L6 24h20l-2.6-4v-5C23.4 10.4 21.6 6 16 6z';
export const bell = () => art('bell-art', '0 0 32 32', `
  <g class="b-swing">
    <circle cx="16" cy="4.6" r="2.2" fill="url(#g-brass)"/>
    <g class="b-clap"><circle cx="16" cy="26.4" r="2.6" fill="url(#g-brass)"/></g>
    <path class="b-body" d="${BELL}"/>
    <path d="${BELL}" fill="url(#g-cyl)"/>
    <ellipse cx="16" cy="24" rx="10" ry="1.8" fill="#8a6428"/>
    <path d="M12.2 9.4Q10.6 12 10.8 16" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.2" stroke-linecap="round"/>
  </g>`);

export const alarmClock = () => art('alarm-art', '0 0 32 32', `
  <g class="ak-shake">
    <path d="M8.5 26.5 6 30M23.5 26.5 26 30" stroke="#5a5145" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M2.8 10.2A5.6 5.6 0 0 1 11.6 3.6z" fill="url(#g-brass)"/>
    <path d="M29.2 10.2A5.6 5.6 0 0 0 20.4 3.6z" fill="url(#g-brass)"/>
    <circle class="ak-body" cx="16" cy="17.5" r="11"/>
    <circle cx="16" cy="17.5" r="11" fill="url(#g-ball)"/>
    <circle cx="16" cy="17.5" r="8.2" fill="#f2ebde"/>
    <path d="M16 17.5V12M16 17.5l3.6 2.2" stroke="#1b1915" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="16" cy="17.5" r="1" fill="#c9624a"/>
  </g>`);

export const reminderArt = (kind) => (kind === 'alarme' ? alarmClock() : bell());
