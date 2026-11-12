import React, { useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, OrthographicCamera, PerspectiveCamera } from '@react-three/drei';
import { BuildingModel } from '@/components/visualization/BuildingModel/BuildingModel';
import { FloorSelector, type SceneLayersState } from '@/components/visualization/FloorSelector/FloorSelector';
import { ErrorBoundary } from '@/components/layout/ErrorBoundary';
import type { ZoneAnalysis } from '@/types/api';

interface PropertySceneProps {
  plotAreaSqft: number;
  builtupAreaSqft: number;
  floors: number;
  assetType: 'residential' | 'commercial' | 'land';
  roadWidthFt: string;
  zoneAnalysis?: ZoneAnalysis | null;
  heroMode?: boolean;
  heightClass?: string;
}

function supportsWebGL(): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('webgl2')));
  } catch {
    return false;
  }
}

function IsometricBlueprintFallback({
  plotAreaSqft,
  builtupAreaSqft,
  floors,
  selectedFloor,
}: {
  plotAreaSqft: number;
  builtupAreaSqft: number;
  floors: number;
  selectedFloor: number | null;
}) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center p-6 bg-[var(--bg-input)] border border-[var(--border-hairline)]">
      <svg viewBox="0 0 320 210" className="w-full max-w-[320px] h-auto" aria-label="Architectural isometric wireframe elevation">
        <polygon points="160,185 45,125 160,65 275,125" fill="none" stroke="#c86d3b" strokeWidth="1.5" />
        <polygon points="160,165 85,125 160,85 235,125" fill="#171b22" stroke="#9ba3ae" strokeWidth="1.2" />
        {Array.from({ length: Math.min(Math.max(floors, 1), 6) }, (_, idx) => {
          const yOff = idx * 14;
          const active = selectedFloor === idx + 1;
          return (
            <polygon
              key={idx}
              points={`160,${155 - yOff} 95,${120 - yOff} 160,${85 - yOff} 225,${120 - yOff}`}
              fill={active ? 'rgba(200,109,59,0.35)' : 'rgba(61,69,82,0.45)'}
              stroke={active ? '#c86d3b' : '#cbd5e1'}
              strokeWidth="1"
            />
          );
        })}
      </svg>
      <div className="mt-3 text-center font-mono text-[11px] text-[var(--text-secondary)]">
        2D CAD ELEVATION FALLBACK · PLOT {plotAreaSqft.toLocaleString()} SQ FT · BUILT {builtupAreaSqft.toLocaleString()} SQ FT
      </div>
    </div>
  );
}

export function PropertyScene({
  plotAreaSqft,
  builtupAreaSqft,
  floors,
  assetType,
  roadWidthFt,
  zoneAnalysis,
  heroMode = false,
  heightClass = 'h-[420px]',
}: PropertySceneProps) {
  const [selectedFloor, setSelectedFloor] = useState<number | null>(null);
  const [cameraMode, setCameraMode] = useState<'perspective' | 'orthographic'>('perspective');
  const [layers, setLayers] = useState<SceneLayersState>({
    parcel: true,
    building: true,
    floors: true,
    roads: true,
    nearby: true,
    infrastructure: true,
    comparables: !heroMode,
    measurements: true,
  });

  const hasWebgl = useMemo(() => supportsWebGL(), []);

  const toggleLayer = (key: keyof SceneLayersState) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="space-y-3">
      <div className={`relative w-full ${heightClass} border border-[var(--border-hairline)] bg-[#090b0e] overflow-hidden`}>
        <div className="absolute top-3 left-3 z-10 pointer-events-none space-y-1">
          <span className="inline-block px-2 py-0.5 bg-[#0a0c0f]/90 border border-white/15 font-mono text-[10px] tracking-wider text-[#eceee9]">
            PARAMETRIC ARCHITECTURAL MASSING · {cameraMode.toUpperCase()}
          </span>
          <div className="px-2 py-0.5 bg-[#0a0c0f]/80 border border-white/10 font-mono text-[9px] text-[#9ba3ae] max-w-[320px]">
            Illustrative geometry from plot &amp; built area inputs — drag to orbit, scroll to zoom, click slab to inspect floor.
          </div>
        </div>

        {hasWebgl ? (
          <ErrorBoundary fallbackTitle="3D Scene WebGL Fallback">
            <Canvas shadows dpr={[1, 1.75]}>
              <color attach="background" args={['#090b0e']} />
              {cameraMode === 'perspective' ? (
                <PerspectiveCamera makeDefault position={[12, 9.5, 13]} fov={40} />
              ) : (
                <OrthographicCamera makeDefault position={[14, 14, 14]} zoom={26} />
              )}
              <ambientLight intensity={0.65} />
              <directionalLight position={[12, 18, 10]} intensity={1.35} castShadow />
              <directionalLight position={[-10, 8, -10]} intensity={0.45} color="#c86d3b" />
              <OrbitControls enableDamping dampingFactor={0.07} minDistance={6} maxDistance={34} maxPolarAngle={Math.PI / 2.08} />
              <BuildingModel
                plotAreaSqft={plotAreaSqft}
                builtupAreaSqft={builtupAreaSqft}
                floors={floors}
                assetType={assetType}
                roadWidthFt={roadWidthFt}
                selectedFloor={selectedFloor}
                onSelectFloor={setSelectedFloor}
                layers={layers}
                zoneAnalysis={zoneAnalysis}
                autoRotate={heroMode}
              />
            </Canvas>
          </ErrorBoundary>
        ) : (
          <IsometricBlueprintFallback
            plotAreaSqft={plotAreaSqft}
            builtupAreaSqft={builtupAreaSqft}
            floors={floors}
            selectedFloor={selectedFloor}
          />
        )}
      </div>

      {!heroMode && (
        <FloorSelector
          totalFloors={floors}
          selectedFloor={selectedFloor}
          onSelectFloor={setSelectedFloor}
          layers={layers}
          onToggleLayer={toggleLayer}
          cameraMode={cameraMode}
          onCameraModeChange={setCameraMode}
        />
      )}
    </div>
  );
}
