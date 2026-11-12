import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Line } from '@react-three/drei';
import * as THREE from 'three';
import type { SceneLayersState } from '@/components/visualization/FloorSelector/FloorSelector';
import { MeasurementOverlay } from '@/components/visualization/MeasurementOverlay/MeasurementOverlay';
import type { ZoneAnalysis } from '@/types/api';

interface BuildingModelProps {
  plotAreaSqft: number;
  builtupAreaSqft: number;
  floors: number;
  assetType: 'residential' | 'commercial' | 'land';
  roadWidthFt: string;
  selectedFloor: number | null;
  onSelectFloor: (floor: number | null) => void;
  layers: SceneLayersState;
  zoneAnalysis?: ZoneAnalysis | null;
  autoRotate?: boolean;
}

export function BuildingModel({
  plotAreaSqft,
  builtupAreaSqft,
  floors,
  assetType,
  roadWidthFt,
  selectedFloor,
  onSelectFloor,
  layers,
  zoneAnalysis,
  autoRotate = false,
}: BuildingModelProps) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    if (autoRotate && groupRef.current) {
      groupRef.current.rotation.y += delta * 0.08;
    }
  });

  // Normalized architectural meters scale (1 scene unit ~= 2.5m)
  const effectiveFloors = assetType === 'land' ? 0 : Math.min(Math.max(floors, 1), 16);
  const plotDim = Math.max(4.5, Math.min(12.0, Math.sqrt(Math.max(plotAreaSqft, 400)) * 0.14));
  const footprintRatio = assetType === 'commercial' ? 0.72 : 0.62;
  const bldgW = plotDim * footprintRatio;
  const bldgD = plotDim * (footprintRatio * 0.88);
  const floorHeight = 0.82;
  const totalHeight = effectiveFloors * floorHeight;

  const roadScale = roadWidthFt.includes('40') ? 3.2 : roadWidthFt.includes('30') ? 2.4 : 1.7;

  // Nearby illustrative context buildings (pure spatial context massing)
  const contextMasses: Array<{ pos: [number, number, number]; size: [number, number, number] }> = [
    { pos: [-plotDim * 1.15, 1.4, -2.0], size: [2.8, 2.8, 3.2] },
    { pos: [plotDim * 1.15, 2.0, -1.2], size: [3.1, 4.0, 2.6] },
    { pos: [-plotDim * 0.9, 1.0, -plotDim * 1.05], size: [3.4, 2.0, 2.5] },
    { pos: [plotDim * 0.85, 1.7, -plotDim * 1.1], size: [2.5, 3.4, 2.8] },
  ];

  // Directional Green medical infra pylons positioned by backend distance vectors
  const infraBeacons: Array<{ pos: [number, number, number]; color: string; height: number }> = [];
  if (layers.infrastructure && zoneAnalysis) {
    (zoneAnalysis.green_zones || []).slice(0, 4).forEach((g, idx) => {
      const ang = (idx * 1.65) + 0.5;
      const dist = Math.min(plotDim * 0.85 + g.distance_km * 0.6, 13);
      infraBeacons.push({ pos: [Math.cos(ang) * dist, 1.2, Math.sin(ang) * dist], color: '#22c55e', height: 2.4 });
    });
  }

  return (
    <group ref={groupRef}>
      {/* Architectural Ground Plane & Technical Grid */}
      <gridHelper args={[36, 36, '#3a414c', '#1e242d']} position={[0, 0, 0]} />

      {/* Land Parcel Boundary */}
      {layers.parcel && (
        <group>
          <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={[plotDim, plotDim]} />
            <meshStandardMaterial color="#1f252e" roughness={0.9} metalness={0.1} />
          </mesh>
          <Line
            points={[
              [-plotDim / 2, 0.06, -plotDim / 2],
              [plotDim / 2, 0.06, -plotDim / 2],
              [plotDim / 2, 0.06, plotDim / 2],
              [-plotDim / 2, 0.06, plotDim / 2],
              [-plotDim / 2, 0.06, -plotDim / 2],
            ]}
            color="#c86d3b"
            lineWidth={2}
          />
        </group>
      )}

      {/* Access Road */}
      {layers.roads && (
        <group position={[0, 0.02, plotDim / 2 + roadScale / 2 + 0.4]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[28, roadScale]} />
            <meshStandardMaterial color="#14181f" roughness={0.95} />
          </mesh>
          <Line
            points={[
              [-14, 0.03, 0],
              [14, 0.03, 0],
            ]}
            color="#6b7280"
            dashed
            dashSize={0.6}
            gapSize={0.5}
          />
        </group>
      )}

      {/* Building Massing & Floor-by-Floor Interactive Plates */}
      {layers.building && effectiveFloors > 0 && (
        <group>
          {Array.from({ length: effectiveFloors }, (_, i) => {
            const floorNum = i + 1;
            const yCenter = i * floorHeight + floorHeight / 2 + 0.06;
            const isSelected = selectedFloor === floorNum;
            const isDimmed = selectedFloor !== null && !isSelected;
            const slabColor = isSelected ? '#c86d3b' : assetType === 'commercial' ? '#4f5c6e' : '#3d4552';

            return (
              <group key={floorNum} position={[0, yCenter, 0]}>
                <mesh
                  castShadow
                  receiveShadow
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectFloor(selectedFloor === floorNum ? null : floorNum);
                  }}
                >
                  <boxGeometry args={[bldgW, floorHeight * 0.84, bldgD]} />
                  <meshStandardMaterial
                    color={slabColor}
                    roughness={0.42}
                    metalness={0.28}
                    transparent={isDimmed}
                    opacity={isDimmed ? 0.35 : 0.94}
                  />
                </mesh>

                {/* Floor Slab Trim Lines */}
                {layers.floors && (
                  <mesh position={[0, -floorHeight * 0.44, 0]}>
                    <boxGeometry args={[bldgW + 0.08, 0.07, bldgD + 0.08]} />
                    <meshStandardMaterial color={isSelected ? '#e89b6e' : '#8b939f'} roughness={0.3} metalness={0.5} />
                  </mesh>
                )}
              </group>
            );
          })}

          {/* Roof Parapet & Core Lift Shaft */}
          <mesh position={[0, totalHeight + 0.14, 0]}>
            <boxGeometry args={[bldgW * 0.36, 0.28, bldgD * 0.36]} />
            <meshStandardMaterial color="#2c333d" roughness={0.5} metalness={0.4} />
          </mesh>
        </group>
      )}

      {/* Surrounding Context Buildings */}
      {layers.nearby &&
        contextMasses.map((b, i) => (
          <mesh key={i} position={b.pos}>
            <boxGeometry args={b.size} />
            <meshStandardMaterial color="#181c23" roughness={0.8} transparent opacity={0.65} />
          </mesh>
        ))}

      {/* Infrastructure & Priority Zone Pylons */}
      {infraBeacons.map((b, i) => (
        <group key={i} position={[b.pos[0], 0, b.pos[2]]}>
          <mesh position={[0, b.height / 2, 0]}>
            <cylinderGeometry args={[0.09, 0.14, b.height, 8]} />
            <meshStandardMaterial color={b.color} emissive={b.color} emissiveIntensity={0.35} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.04, 0]}>
            <ringGeometry args={[0.35, 0.46, 20]} />
            <meshBasicMaterial color={b.color} transparent opacity={0.75} />
          </mesh>
        </group>
      ))}

      {/* Illustrative Comparable Market Markers */}
      {layers.comparables && (
        <group>
          {[
            [-plotDim * 0.85, 0.4, plotDim * 0.35],
            [plotDim * 0.9, 0.4, plotDim * 0.25],
          ].map((pos, idx) => (
            <mesh key={idx} position={pos as [number, number, number]}>
              <octahedronGeometry args={[0.25]} />
              <meshStandardMaterial color="#e5e7eb" metalness={0.5} roughness={0.3} />
            </mesh>
          ))}
        </group>
      )}

      <MeasurementOverlay
        plotW={plotDim}
        plotD={plotDim}
        bldgW={bldgW}
        bldgD={bldgD}
        bldgH={Math.max(totalHeight, 1.0)}
        plotSqft={plotAreaSqft}
        builtSqft={builtupAreaSqft}
        floors={effectiveFloors}
        selectedFloor={selectedFloor}
        visible={layers.measurements}
      />
    </group>
  );
}
