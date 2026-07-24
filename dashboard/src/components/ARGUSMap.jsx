/**
 * ARGUSMap.jsx — Main ARGUS risk map
 * Migrated: MapBox + DeckGL → Leaflet + OpenStreetMap
 */
import { useEffect } from 'react'
import {
  MapContainer, TileLayer, CircleMarker,
  Popup, Tooltip, ZoomControl, useMap
} from 'react-leaflet'
import { TILE_LAYERS, ALERT_COLORS, DEFAULT_CENTER, DEFAULT_ZOOM } from './map/LeafletConfig'
import './map/LeafletConfig'  // Ensures icon fix runs
import VillagePopup from './VillagePopup'

// Risk radius helper (mirrors old riskRadius)
const riskRadius = (score) => {
  if (score >= 0.88) return 18
  if (score >= 0.72) return 14
  if (score >= 0.55) return 12
  return 10
}

// Alert level from risk score (mirrors old logic)
const alertLevelFromScore = (score) => {
  if (score >= 0.88) return 'EMERGENCY'
  if (score >= 0.72) return 'WARNING'
  if (score >= 0.55) return 'WATCH'
  if (score >= 0.35) return 'ADVISORY'
  return 'NORMAL'
}

// Auto-pans map when alert level changes to EMERGENCY
const EmergencyPanner = ({ predictions }) => {
  const map = useMap()
  useEffect(() => {
    const emergency = predictions.find(
      (p) => (p.alert_level || alertLevelFromScore(p.risk_score)) === 'EMERGENCY'
    )
    if (emergency) {
      map.flyTo([emergency.lat, emergency.lon], 12, { duration: 1.5 })
    }
  }, [predictions, map])
  return null
}

export default function ARGUSMap({ predictions }) {
  return (
    <div className="relative w-full h-full" style={{ borderRadius: '12px', overflow: 'hidden' }}>
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
      >
        {/* Dark CartoDB tiles — matches ARGUS dark theme */}
        <TileLayer
          url={TILE_LAYERS.dark.url}
          attribution={TILE_LAYERS.dark.attribution}
          maxZoom={TILE_LAYERS.dark.maxZoom}
        />

        <ZoomControl position="bottomright" />
        <EmergencyPanner predictions={predictions} />

        {predictions.map((village) => {
          const level = village.alert_level || alertLevelFromScore(village.risk_score)
          const colors = ALERT_COLORS[level] || ALERT_COLORS.NORMAL
          const radius = riskRadius(village.risk_score)

          return (
            <CircleMarker
              key={village.id || village.station_id}
              center={[village.lat, village.lon]}
              radius={radius}
              pathOptions={{
                fillColor:   colors.fill,
                fillOpacity: 0.9,
                color:       colors.border,
                weight:      1.5,
              }}
            >
              {/* Hover tooltip */}
              <Tooltip
                direction="top"
                offset={[0, -radius]}
                permanent={level === 'EMERGENCY'}
              >
                <div style={{ fontFamily: 'Exo 2, sans-serif', fontSize: '12px' }}>
                  <strong style={{ color: colors.fill }}>{level}</strong>
                  {' — '}{village.name}
                </div>
              </Tooltip>

              {/* Click popup — full details */}
              <Popup>
                <div style={{
                  fontFamily: 'Exo 2, sans-serif',
                  minWidth: '180px',
                  padding: '4px'
                }}>
                  <div style={{
                    background: colors.fill,
                    color: 'white',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontWeight: 'bold',
                    marginBottom: '8px'
                  }}>
                    {level} — {village.name}
                  </div>
                  <div style={{ fontSize: '13px', lineHeight: '1.6' }}>
                    <div>Risk Score: <strong>{Math.round(village.risk_score * 100)}%</strong></div>
                    <div>Population: <strong>{village.population?.toLocaleString()}</strong></div>
                    {village.explanation?.slice(0, 2).map((e, i) => (
                      <div key={i} style={{ color: '#666', fontSize: '11px', marginTop: '4px' }}>
                        ↑ {e.factor}
                      </div>
                    ))}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}
      </MapContainer>
    </div>
  )
}
