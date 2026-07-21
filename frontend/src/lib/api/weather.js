// ── Cafreso Weather ─────────────────────────────────────────────────────────
// Client for Open-Meteo (api.open-meteo.com) — the same provider serve.py's
// weather-archive cron uses, so what visitors see in the popup matches what
// the Search Network is archiving hourly. Free, no API key, CORS-enabled,
// worldwide lat/lon coverage.
//
// SAVED_LOCATIONS mirrors WEATHER_LOCATIONS in serve.py. If you add a location
// there, add it here too (keys must match — /weather/history is queried by key).

export const SAVED_LOCATIONS = [
  // -- US mid-Atlantic corridor --
  { key: 'DC',      label: 'Washington, DC',    region: 'Mid-Atlantic', lat: 38.9072, lon: -77.0369 },
  { key: 'BALT',    label: 'Baltimore, MD',     region: 'Mid-Atlantic', lat: 39.2904, lon: -76.6122 },
  { key: 'PHL',     label: 'Philadelphia, PA',  region: 'Mid-Atlantic', lat: 39.9526, lon: -75.1652 },
  { key: 'RIC',     label: 'Richmond, VA',      region: 'Mid-Atlantic', lat: 37.5407, lon: -77.4360 },
  { key: 'WILM',    label: 'Wilmington, DE',    region: 'Mid-Atlantic', lat: 39.7391, lon: -75.5398 },
  { key: 'AC',      label: 'Atlantic City, NJ', region: 'Mid-Atlantic', lat: 39.3643, lon: -74.4229 },
  // -- Northern Virginia --
  { key: 'ASHBURN', label: 'Ashburn, VA',       region: 'Northern Virginia', lat: 39.0437, lon: -77.4875 },
  { key: 'FAIRFAX', label: 'Fairfax, VA',       region: 'Northern Virginia', lat: 38.8462, lon: -77.3064 },
  // -- El Salvador: all 14 departments --
  { key: 'SV-AHUA', label: 'Ahuachapán',        region: 'El Salvador', lat: 13.9214, lon: -89.8450 },
  { key: 'SV-CAB',  label: 'Cabañas',           region: 'El Salvador', lat: 13.8722, lon: -88.6314 },
  { key: 'SV-CHAL', label: 'Chalatenango',      region: 'El Salvador', lat: 14.0333, lon: -88.9333 },
  { key: 'SV-CUSC', label: 'Cuscatlán',         region: 'El Salvador', lat: 13.7167, lon: -88.9333 },
  { key: 'SV-LLIB', label: 'La Libertad',       region: 'El Salvador', lat: 13.6769, lon: -89.2797 },
  { key: 'SV-LPAZ', label: 'La Paz',            region: 'El Salvador', lat: 13.5000, lon: -88.8667 },
  { key: 'SV-LUNI', label: 'La Unión',          region: 'El Salvador', lat: 13.3369, lon: -87.8433 },
  { key: 'SV-MORA', label: 'Morazán',           region: 'El Salvador', lat: 13.7000, lon: -88.1000 },
  { key: 'SV-SMIG', label: 'San Miguel',        region: 'El Salvador', lat: 13.4833, lon: -88.1833 },
  { key: 'SV-SSAL', label: 'San Salvador',      region: 'El Salvador', lat: 13.6929, lon: -89.2182 },
  { key: 'SV-SVIC', label: 'San Vicente',       region: 'El Salvador', lat: 13.6408, lon: -88.7844 },
  { key: 'SV-SANA', label: 'Santa Ana',         region: 'El Salvador', lat: 13.9942, lon: -89.5592 },
  { key: 'SV-SONS', label: 'Sonsonate',         region: 'El Salvador', lat: 13.7167, lon: -89.7239 },
  { key: 'SV-USUL', label: 'Usulután',          region: 'El Salvador', lat: 13.3500, lon: -88.4500 }
];

// WMO weather codes (Open-Meteo's `weather_code`) → text + Phosphor icon slug.
// Icon picks a day/night variant only where Phosphor has one.
const WMO = {
  0:  { text: 'Clear',                        day: 'sun',             night: 'moon-stars' },
  1:  { text: 'Mostly clear',                 day: 'sun',             night: 'moon-stars' },
  2:  { text: 'Partly cloudy',                day: 'cloud-sun',       night: 'cloud-moon' },
  3:  { text: 'Overcast',                     day: 'cloud',           night: 'cloud' },
  45: { text: 'Fog',                          day: 'cloud-fog',       night: 'cloud-fog' },
  48: { text: 'Freezing fog',                 day: 'cloud-fog',       night: 'cloud-fog' },
  51: { text: 'Light drizzle',                day: 'cloud-rain',      night: 'cloud-rain' },
  53: { text: 'Drizzle',                      day: 'cloud-rain',      night: 'cloud-rain' },
  55: { text: 'Dense drizzle',                day: 'cloud-rain',      night: 'cloud-rain' },
  56: { text: 'Light freezing drizzle',       day: 'cloud-rain',      night: 'cloud-rain' },
  57: { text: 'Freezing drizzle',             day: 'cloud-rain',      night: 'cloud-rain' },
  61: { text: 'Light rain',                   day: 'cloud-rain',      night: 'cloud-rain' },
  63: { text: 'Rain',                         day: 'cloud-rain',      night: 'cloud-rain' },
  65: { text: 'Heavy rain',                   day: 'cloud-rain',      night: 'cloud-rain' },
  66: { text: 'Light freezing rain',          day: 'cloud-rain',      night: 'cloud-rain' },
  67: { text: 'Freezing rain',                day: 'cloud-rain',      night: 'cloud-rain' },
  71: { text: 'Light snow',                   day: 'cloud-snow',      night: 'cloud-snow' },
  73: { text: 'Snow',                         day: 'cloud-snow',      night: 'cloud-snow' },
  75: { text: 'Heavy snow',                   day: 'cloud-snow',      night: 'cloud-snow' },
  77: { text: 'Snow grains',                  day: 'cloud-snow',      night: 'cloud-snow' },
  80: { text: 'Light rain showers',           day: 'cloud-rain',      night: 'cloud-rain' },
  81: { text: 'Rain showers',                 day: 'cloud-rain',      night: 'cloud-rain' },
  82: { text: 'Violent rain showers',         day: 'cloud-rain',      night: 'cloud-rain' },
  85: { text: 'Light snow showers',           day: 'cloud-snow',      night: 'cloud-snow' },
  86: { text: 'Snow showers',                 day: 'cloud-snow',      night: 'cloud-snow' },
  95: { text: 'Thunderstorm',                 day: 'cloud-lightning', night: 'cloud-lightning' },
  96: { text: 'Thunderstorm with hail',       day: 'cloud-lightning', night: 'cloud-lightning' },
  99: { text: 'Thunderstorm, heavy hail',     day: 'cloud-lightning', night: 'cloud-lightning' }
};

export function wmoText(code) {
  return WMO[code]?.text ?? (code == null ? '—' : `Code ${code}`);
}
export function wmoIcon(code, isDay = 1) {
  const e = WMO[code];
  if (!e) return 'cloud';
  return isDay ? e.day : e.night;
}

/** The animated hero scene for a weather code. */
export function wmoScene(code, isDay = 1) {
  if (code === 0 || code === 1) return isDay ? 'clear-day' : 'clear-night';
  if (code === 2) return isDay ? 'partly-day' : 'partly-night';
  if (code === 3) return 'cloudy';
  if (code === 45 || code === 48) return 'fog';
  if (code >= 95) return 'storm';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if (code >= 51) return 'rain';
  return isDay ? 'clear-day' : 'clear-night';
}

const CURRENT_FIELDS =
  'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,' +
  'weather_code,wind_speed_10m,surface_pressure,is_day';

async function _json(url, timeoutMs = 12000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Full forecast for one point: current conditions + next hours + 7 days.
 * Returns Open-Meteo's shape verbatim ({current, hourly, daily, timezone…});
 * temps are °F, wind mph — display-unit conversion is the UI's job.
 */
export async function fetchForecast(lat, lon) {
  const url =
    `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
    `&current=${CURRENT_FIELDS}` +
    `&hourly=temperature_2m,weather_code,precipitation_probability,is_day` +
    `&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max` +
    `&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto&forecast_days=7`;
  return _json(url);
}

/**
 * One batched call for current conditions at every SAVED_LOCATIONS point
 * (same batching trick serve.py uses). Returns { [key]: {tempF, code, isDay} }.
 */
export async function fetchSavedCurrent() {
  const lats = SAVED_LOCATIONS.map((l) => l.lat).join(',');
  const lons = SAVED_LOCATIONS.map((l) => l.lon).join(',');
  const url =
    `https://api.open-meteo.com/v1/forecast?latitude=${lats}&longitude=${lons}` +
    `&current=temperature_2m,weather_code,is_day&temperature_unit=fahrenheit`;
  const data = await _json(url);
  const rows = Array.isArray(data) ? data : [data];
  const out = {};
  rows.forEach((row, i) => {
    const loc = SAVED_LOCATIONS[i];
    const cur = row?.current;
    if (loc && cur) {
      out[loc.key] = {
        tempF: cur.temperature_2m,
        code: cur.weather_code,
        isDay: cur.is_day
      };
    }
  });
  return out;
}

/** Place search via Open-Meteo's free geocoder. Returns [{label, lat, lon}]. */
export async function geocode(query) {
  const q = (query || '').trim();
  if (q.length < 2) return [];
  const url =
    `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}` +
    `&count=6&language=en&format=json`;
  const data = await _json(url, 8000);
  return (data?.results || []).map((r) => ({
    label: [r.name, r.admin1, r.country_code].filter(Boolean).join(', '),
    lat: r.latitude,
    lon: r.longitude
  }));
}
