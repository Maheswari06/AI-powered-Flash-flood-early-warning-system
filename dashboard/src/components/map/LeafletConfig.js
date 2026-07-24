/**
 * ARGUS Leaflet Configuration
 * Centralizes all map tile and icon config.
 * Import this in every component that uses Leaflet.
 */

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix Leaflet default marker icon broken by webpack/vite
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl:       'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl:     'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

// ARGUS tile configurations
export const TILE_LAYERS = {
  // Light — for government portals / print
  osm: {
    url:         'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom:     19
  },
  // Dark — matches ARGUS dark theme (#050d1a)
  dark: {
    url:         'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom:     20
  },
  // Satellite (from ESRI — free, no key)
  satellite: {
    url:         'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
    maxZoom:     18
  }
}

// ARGUS alert colors (consistent across all map components)
export const ALERT_COLORS = {
  EMERGENCY: { fill: '#dc2626', border: '#fca5a5', glow: 'rgba(220,38,38,0.4)' },
  WARNING:   { fill: '#ef4444', border: '#fca5a5', glow: 'rgba(239,68,68,0.3)'  },
  WATCH:     { fill: '#f97316', border: '#fdba74', glow: 'rgba(249,115,22,0.3)' },
  ADVISORY:  { fill: '#eab308', border: '#fde047', glow: 'rgba(234,179,8,0.3)'  },
  NORMAL:    { fill: '#22c55e', border: '#86efac', glow: 'rgba(34,197,94,0.2)'  },
}

// Default map center for Assam / Brahmaputra basin
export const DEFAULT_CENTER = [26.5, 93.5]
export const DEFAULT_ZOOM   = 8

// Majuli Island center (primary demo location)
export const MAJULI_CENTER  = [27.02, 94.55]
export const MAJULI_ZOOM    = 11
