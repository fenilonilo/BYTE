// Pure helpers for the weather section. Run: node --test tests/web/weather.test.mjs

export const CONDITION_WORD = {
  clear: 'céu limpo', partly_cloudy: 'parcialmente nublado', cloudy: 'nublado', fog: 'neblina',
  drizzle: 'garoa', rain: 'chuva', storm: 'tempestade',
};
const WEEKDAYS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
const round2 = (n) => Math.round(n * 100) / 100;
const round1 = (n) => Math.round(n * 10) / 10;

/** "23h" from an ISO time carrying the place's own offset: another city keeps its own clock. */
export const hourLabel = (iso) => `${iso.slice(11, 13)}h`;

const utcDay = (ymd) => new Date(`${ymd}T00:00:00Z`).getUTCDay();

/** "hoje" for the first forecast day, then "seg".."dom". */
export const dayLabel = (day, firstDay) => (day === firstDay ? 'hoje' : WEEKDAYS[utcDay(day)]);

/** Where a day's low..high sits across the week's span, as left/right insets in percent. */
export function rangeBar(day, days) {
  const lo = Math.min(...days.map((d) => d.low));
  const hi = Math.max(...days.map((d) => d.high));
  const span = hi - lo;
  if (span <= 0) return { left: 0, right: 0 };
  return { left: round2(((day.low - lo) / span) * 100), right: round2(((hi - day.high) / span) * 100) };
}

/** Geometry of the 24 h chart: rain-chance bars along the bottom, temperature line above. */
export function chart(hours, width, height) {
  const slot = width / hours.length;
  const top = 14; // room for the peak label
  const floor = height * 0.55;
  const temps = hours.map((h) => h.temperature);
  const lo = Math.min(...temps);
  const hi = Math.max(...temps);
  const ty = (t) => round1(hi === lo ? (top + floor) / 2 : top + (1 - (t - lo) / (hi - lo)) * (floor - top));
  const points = hours.map((h, i) => ({ x: round1(i * slot + slot / 2), y: ty(h.temperature) }));
  const bars = hours.map((h, i) => {
    const bh = round1((h.rain_chance / 100) * height * 0.4);
    return { x: round1(i * slot + slot * 0.15), y: round1(height - bh), w: round1(slot * 0.7), h: bh };
  });
  const peakAt = temps.indexOf(hi);
  return {
    line: points.map((p) => `${p.x},${p.y}`).join(' '),
    bars,
    peak: { ...points[peakAt], label: `${Math.round(hi)}°`, hour: hourLabel(hours[peakAt].time) },
  };
}
