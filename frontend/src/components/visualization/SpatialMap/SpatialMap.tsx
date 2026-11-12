import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { ZoneAnalysis, ZoneMarkerItem } from '@/types/api';

interface SpatialMapProps {
  latitude: number;
  longitude: number;
  zoneAnalysis?: ZoneAnalysis | null;
  onSelectCoord?: (lat: number, lon: number) => void;
  show3DBuildings?: boolean;
  heightClass?: string;
  highlightedCoord?: { latitude: number; longitude: number } | null;
  extraMarkers?: Array<{ latitude: number; longitude: number; label: string; color: string }>;
}

function createCirclePolygon(lat: number, lon: number, radiusMeters: number, points = 32): [number, number][] {
  const coords: [number, number][] = [];
  const km = radiusMeters / 1000.0;
  const distLat = km / 111.32;
  const distLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= points; i++) {
    const theta = (i / points) * Math.PI * 2;
    coords.push([lon + distLon * Math.cos(theta), lat + distLat * Math.sin(theta)]);
  }
  return coords;
}

export function SpatialMap({
  latitude,
  longitude,
  zoneAnalysis,
  onSelectCoord,
  show3DBuildings = true,
  heightClass = 'h-[400px]',
  highlightedCoord = null,
  extraMarkers = [],
}: SpatialMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const subjectMarkerRef = useRef<maplibregl.Marker | null>(null);
  const hubMarkersRef = useRef<maplibregl.Marker[]>([]);
  const [webglFailed, setWebglFailed] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    try {
      const style: maplibregl.StyleSpecification = {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors',
          },
        },
        layers: [
          {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm',
            paint: {
              'raster-saturation': -0.45,
              'raster-contrast': 0.12,
              'raster-brightness-max': 0.85,
            },
          },
        ],
      };

      const map = new maplibregl.Map({
        container: containerRef.current,
        style,
        center: [longitude, latitude],
        zoom: show3DBuildings ? 14.2 : 12.6,
        pitch: show3DBuildings ? 42 : 0,
        bearing: show3DBuildings ? -14 : 0,
      });

      map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');

      map.on('load', () => {
        map.addSource('zone-circles', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        });
        map.addLayer({
          id: 'zone-circles-fill',
          type: 'fill',
          source: 'zone-circles',
          paint: {
            'fill-color': ['get', 'color'],
            'fill-opacity': ['case', ['get', 'inside'], 0.16, 0.04],
          },
        });
        map.addLayer({
          id: 'zone-circles-line',
          type: 'line',
          source: 'zone-circles',
          paint: {
            'line-color': ['get', 'color'],
            'line-width': ['case', ['get', 'inside'], 2, 1],
            'line-opacity': 0.8,
          },
        });

        // 3D Parcel & Conceptual Massing Footprint centered at subject
        map.addSource('subject-extrusion', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        });
        if (show3DBuildings) {
          map.addLayer({
            id: 'subject-massing-3d',
            type: 'fill-extrusion',
            source: 'subject-extrusion',
            paint: {
              'fill-extrusion-color': '#c86d3b',
              'fill-extrusion-height': ['get', 'height'],
              'fill-extrusion-opacity': 0.68,
            },
          });
        }
      });

      map.on('click', (e) => {
        if (onSelectCoord) {
          onSelectCoord(e.lngLat.lat, e.lngLat.lng);
        }
      });

      const markerEl = document.createElement('div');
      markerEl.className = 'w-4 h-4 border-2 border-white bg-[#c86d3b] shadow-lg';
      const marker = new maplibregl.Marker({ element: markerEl, draggable: !!onSelectCoord })
        .setLngLat([longitude, latitude])
        .addTo(map);

      marker.on('dragend', () => {
        const ll = marker.getLngLat();
        if (onSelectCoord) onSelectCoord(ll.lat, ll.lng);
      });

      mapRef.current = map;
      subjectMarkerRef.current = marker;

      return () => {
        map.remove();
        mapRef.current = null;
      };
    } catch {
      setWebglFailed(true);
    }
  }, []);

  // Update center, zone circles, 3D parcel massing & markers dynamically
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    subjectMarkerRef.current?.setLngLat([longitude, latitude]);
    map.easeTo({ center: [longitude, latitude], duration: 500 });

    const features: any[] = [];
    const addZoneList = (items: ZoneMarkerItem[]) => {
      items.forEach((item) => {
        features.push({
          type: 'Feature',
          properties: { color: item.hex_color, inside: item.inside_zone, name: item.name },
          geometry: {
            type: 'Polygon',
            coordinates: [createCirclePolygon(item.latitude, item.longitude, item.zone_radius_m || 5000)],
          },
        });
      });
    };
    if (zoneAnalysis) {
      addZoneList(zoneAnalysis.green_zones || []);
    }

    const src = map.getSource('zone-circles') as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData({ type: 'FeatureCollection', features });

    const extSrc = map.getSource('subject-extrusion') as maplibregl.GeoJSONSource | undefined;
    if (extSrc) {
      const dx = 0.00025;
      const dy = 0.00022;
      extSrc.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: { height: 22 },
            geometry: {
              type: 'Polygon',
              coordinates: [
                [
                  [longitude - dx, latitude - dy],
                  [longitude + dx, latitude - dy],
                  [longitude + dx, latitude + dy],
                  [longitude - dx, latitude + dy],
                  [longitude - dx, latitude - dy],
                ],
              ],
            },
          },
        ],
      });
    }

    hubMarkersRef.current.forEach((m) => m.remove());
    hubMarkersRef.current = [];
    const allZones = [...(zoneAnalysis?.green_zones || [])];
    allZones.forEach((z) => {
      const el = document.createElement('div');
      el.style.width = z.inside_zone ? '11px' : '8px';
      el.style.height = z.inside_zone ? '11px' : '8px';
      el.style.borderRadius = '9999px';
      el.style.backgroundColor = z.hex_color;
      el.style.border = '1.5px solid #0a0c0f';
      const hm = new maplibregl.Marker({ element: el })
        .setLngLat([z.longitude, z.latitude])
        .setPopup(new maplibregl.Popup({ offset: 12 }).setHTML(`<strong>${z.name}</strong><br/>${z.category} · ${z.distance_km} km`))
        .addTo(map);
      hubMarkersRef.current.push(hm);
    });

    extraMarkers.forEach((m) => {
      const el = document.createElement('div');
      el.style.width = '10px';
      el.style.height = '10px';
      el.style.backgroundColor = m.color;
      el.style.border = '1.5px solid #ffffff';
      const mk = new maplibregl.Marker({ element: el })
        .setLngLat([m.longitude, m.latitude])
        .setPopup(new maplibregl.Popup({ offset: 10 }).setText(m.label))
        .addTo(map);
      hubMarkersRef.current.push(mk);
    });
  }, [latitude, longitude, zoneAnalysis, extraMarkers]);

  useEffect(() => {
    if (highlightedCoord && mapRef.current) {
      mapRef.current.easeTo({ center: [highlightedCoord.longitude, highlightedCoord.latitude], duration: 450 });
    }
  }, [highlightedCoord]);

  if (webglFailed) {
    return (
      <div className={`w-full ${heightClass} border border-[var(--border-hairline)] bg-[var(--bg-input)] p-4 flex flex-col justify-between`}>
        <div className="flex justify-between items-center font-mono text-[11px] text-[var(--text-secondary)]">
          <span>COORDINATE CANVAS FALLBACK (NON-WEBGL)</span>
          <span>
            {latitude.toFixed(4)}° N, {longitude.toFixed(4)}° E
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 my-3 overflow-y-auto">
          {(zoneAnalysis?.green_zones || []).slice(0, 6).map((z) => (
            <div key={z.name} className="panel-elevated p-2 text-[11px] flex items-center justify-between gap-2">
              <span className="truncate flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: z.hex_color }} />
                {z.name}
              </span>
              <span className="font-mono text-[10px] text-[var(--text-muted)]">{z.distance_km}km</span>
            </div>
          ))}
        </div>
        <div className="text-[10px] font-mono text-[var(--text-muted)]">
          Green Medical Zones Active: {zoneAnalysis?.active_green_facilities_count ?? 0}
        </div>
      </div>
    );
  }

  return (
    <div className={`relative w-full ${heightClass} border border-[var(--border-hairline)] overflow-hidden`}>
      <div ref={containerRef} className="w-full h-full" />
      <div className="absolute bottom-2.5 left-2.5 z-10 pointer-events-none flex flex-wrap gap-2 px-2.5 py-1 bg-[#0a0c0f]/90 border border-white/15 text-[10px] font-mono text-[#eceee9]">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-500" /> Green: Medical ({zoneAnalysis?.active_green_facilities_count ?? 0})
        </span>
      </div>
    </div>
  );
}
