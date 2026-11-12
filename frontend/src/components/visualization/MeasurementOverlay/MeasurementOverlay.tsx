import React from 'react';
import { Html, Line } from '@react-three/drei';

interface MeasurementOverlayProps {
  plotW: number;
  plotD: number;
  bldgW: number;
  bldgD: number;
  bldgH: number;
  plotSqft: number;
  builtSqft: number;
  floors: number;
  selectedFloor: number | null;
  visible: boolean;
}

export function MeasurementOverlay({
  plotW,
  plotD,
  bldgW,
  bldgD,
  bldgH,
  plotSqft,
  builtSqft,
  floors,
  selectedFloor,
  visible,
}: MeasurementOverlayProps) {
  if (!visible) return null;

  const halfPW = plotW / 2;
  const halfPD = plotD / 2;
  const halfBW = bldgW / 2;
  const plotSideFt = Math.round(Math.sqrt(Math.max(plotSqft, 100)));

  return (
    <group>
      {/* Parcel Width Dimension Line */}
      <Line
        points={[
          [-halfPW, 0.08, halfPD + 1.1],
          [halfPW, 0.08, halfPD + 1.1],
        ]}
        color="#c86d3b"
        lineWidth={1.5}
      />
      <Html position={[0, 0.25, halfPD + 1.35]} center distanceFactor={28}>
        <div className="px-1.5 py-0.5 bg-[#0a0c0f]/90 border border-[#c86d3b]/60 text-[10px] font-mono text-[#eceee9] whitespace-nowrap pointer-events-none">
          PARCEL ~{plotSideFt} ft × {plotSideFt} ft ({plotSqft.toLocaleString()} sq ft)
        </div>
      </Html>

      {/* Building Height Elevation Line */}
      <Line
        points={[
          [halfBW + 0.9, 0, 0],
          [halfBW + 0.9, bldgH, 0],
        ]}
        color="#9ba3ae"
        lineWidth={1.2}
      />
      <Html position={[halfBW + 1.4, bldgH / 2, 0]} center distanceFactor={28}>
        <div className="px-1.5 py-0.5 bg-[#0a0c0f]/90 border border-white/20 text-[10px] font-mono text-[#eceee9] whitespace-nowrap pointer-events-none">
          H: {(floors * 3.1).toFixed(1)}m · {floors}F · {builtSqft.toLocaleString()} sqft
        </div>
      </Html>

      {selectedFloor !== null && (
        <Html position={[0, (selectedFloor - 0.5) * (bldgH / Math.max(floors, 1)), bldgD / 2 + 0.6]} center distanceFactor={24}>
          <div className="px-2 py-0.5 bg-[#c86d3b] text-[#0a0c0f] font-mono font-bold text-[10px] whitespace-nowrap pointer-events-none">
            LEVEL {String(selectedFloor).padStart(2, '0')} SELECTED
          </div>
        </Html>
      )}
    </group>
  );
}
