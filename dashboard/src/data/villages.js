/**
 * Static village list with coordinates for the ARGUS demo.
 * Covers key flood-prone areas in Himachal Pradesh and Assam.
 *
 * Each village has:
 *   - id: matches prediction API village_id
 *   - name: display name
 *   - lat, lon: WGS84 coordinates
 *   - state: Indian state
 *   - basin: river basin
 *   - acn_node: ACN node_id if deployed (null otherwise)
 */

const VILLAGES = [
  // ── Himachal Pradesh (Beas basin) ────────────────────
  {
    id: 'VIL-HP-MANDI',
    name: 'Mandi',
    lat: 31.7087,
    lon: 76.9318,
    state: 'Himachal Pradesh',
    basin: 'Beas',
    acn_node: 'himachal',
    danger_level_m: 4.5,
  },
  {
    id: 'VIL-HP-KULLU',
    name: 'Kullu',
    lat: 31.9579,
    lon: 77.1095,
    state: 'Himachal Pradesh',
    basin: 'Beas',
    acn_node: null,
    danger_level_m: 5.0,
  },
  {
    id: 'VIL-HP-MANALI',
    name: 'Manali',
    lat: 32.2396,
    lon: 77.1887,
    state: 'Himachal Pradesh',
    basin: 'Beas',
    acn_node: null,
    danger_level_m: 4.2,
  },
  {
    id: 'VIL-HP-BHUNTAR',
    name: 'Bhuntar',
    lat: 31.8775,
    lon: 77.1592,
    state: 'Himachal Pradesh',
    basin: 'Beas',
    acn_node: null,
    danger_level_m: 4.8,
  },
  {
    id: 'VIL-HP-PANDOH',
    name: 'Pandoh',
    lat: 31.6711,
    lon: 77.0569,
    state: 'Himachal Pradesh',
    basin: 'Beas',
    acn_node: null,
    danger_level_m: 5.2,
  },
  {
    id: 'VIL-HP-LARJI',
    name: 'Larji',
    lat: 31.7645,
    lon: 77.1233,
    state: 'Himachal Pradesh',
    basin: 'Beas',
    acn_node: null,
    danger_level_m: 4.0,
  },
  {
    id: 'VIL-HP-BANJAR',
    name: 'Banjar',
    lat: 31.6374,
    lon: 77.3395,
    state: 'Himachal Pradesh',
    basin: 'Tirthan',
    acn_node: null,
    danger_level_m: 3.8,
  },

  // ── Assam (Brahmaputra basin) ────────────────────────
  {
    id: 'VIL-AS-MAJULI',
    name: 'Majuli Island',
    lat: 26.9500,
    lon: 94.1672,
    state: 'Assam',
    basin: 'Brahmaputra',
    acn_node: 'majuli',
    danger_level_m: 6.5,
  },
  {
    id: 'VIL-AS-JORHAT',
    name: 'Jorhat',
    lat: 26.7509,
    lon: 94.2037,
    state: 'Assam',
    basin: 'Brahmaputra',
    acn_node: null,
    danger_level_m: 7.0,
  },
  {
    id: 'VIL-AS-DIBRUGARH',
    name: 'Dibrugarh',
    lat: 27.4728,
    lon: 94.9120,
    state: 'Assam',
    basin: 'Brahmaputra',
    acn_node: null,
    danger_level_m: 6.8,
  },
  {
    id: 'VIL-AS-TEZPUR',
    name: 'Tezpur',
    lat: 26.6338,
    lon: 92.7926,
    state: 'Assam',
    basin: 'Brahmaputra',
    acn_node: null,
    danger_level_m: 7.2,
  },
  {
    id: 'VIL-AS-GUWAHATI',
    name: 'Guwahati',
    lat: 26.1445,
    lon: 91.7362,
    state: 'Assam',
    basin: 'Brahmaputra',
    acn_node: null,
    danger_level_m: 7.5,
  },
]

export default VILLAGES
