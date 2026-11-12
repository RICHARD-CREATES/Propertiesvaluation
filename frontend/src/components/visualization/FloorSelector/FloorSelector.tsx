import React from 'react';

export interface SceneLayersState {
  parcel: boolean;
  building: boolean;
  floors: boolean;
  roads: boolean;
  nearby: boolean;
  infrastructure: boolean;
  comparables: boolean;
  measurements: boolean;
}

interface FloorSelectorProps {
  totalFloors: number;
  selectedFloor: number | null;
  onSelectFloor: (floor: number | null) => void;
  layers: SceneLayersState;
  onToggleLayer: (key: keyof SceneLayersState) => void;
  cameraMode: 'perspective' | 'orthographic';
  onCameraModeChange: (mode: 'perspective' | 'orthographic') => void;
}

const LAYER_LABELS: Array<{ key: keyof SceneLayersState; label: string }> = [
  { key: 'parcel', label: 'Land Parcel' },
  { key: 'building', label: 'Building' },
  { key: 'floors', label: 'Floors' },
  { key: 'roads', label: 'Roads' },
  { key: 'nearby', label: 'Nearby Massing' },
  { key: 'infrastructure', label: 'Medical Zones' },
  { key: 'comparables', label: 'Comparables' },
  { key: 'measurements', label: 'Dimensions' },
];

export function FloorSelector({
  totalFloors,
  selectedFloor,
  onSelectFloor,
  layers,
  onToggleLayer,
  cameraMode,
  onCameraModeChange,
}: FloorSelectorProps) {
  const floorList = Array.from({ length: Math.min(Math.max(totalFloors, 1), 16) }, (_, idx) => idx + 1).reverse();

  return (
    <div className="space-y-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="tech-label mr-1">Projection</span>
          {(['perspective', 'orthographic'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onCameraModeChange(m)}
              className={`arch-btn px-2.5 py-1 text-[11px] font-mono border capitalize ${
                cameraMode === m
                  ? 'border-[var(--accent-copper)] bg-[var(--accent-copper)] text-[var(--accent-copper-ink)] font-semibold'
                  : 'border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]'
              }`}
            >
              {m}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {LAYER_LABELS.map((item) => {
            const on = layers[item.key];
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => onToggleLayer(item.key)}
                className={`arch-btn px-2 py-1 text-[10px] font-mono border ${
                  on
                    ? 'border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--text-primary)]'
                    : 'border-transparent bg-transparent text-[var(--text-muted)] line-through'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Floor Stack Selector */}
      <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-[var(--border-hairline)]">
        <span className="tech-label mr-1">Floor Slice</span>
        <button
          type="button"
          onClick={() => onSelectFloor(null)}
          className={`arch-btn px-2 py-0.5 text-[10px] font-mono border ${
            selectedFloor === null
              ? 'border-[var(--accent-copper)] text-[var(--accent-copper)] bg-[var(--bg-elevated)]'
              : 'border-[var(--border-hairline)] text-[var(--text-secondary)]'
          }`}
        >
          All ({totalFloors}F)
        </button>
        {floorList.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => onSelectFloor(selectedFloor === f ? null : f)}
            className={`arch-btn px-2 py-0.5 text-[10px] font-mono border ${
              selectedFloor === f
                ? 'border-[var(--accent-copper)] bg-[var(--accent-copper)] text-[var(--accent-copper-ink)] font-bold'
                : 'border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]'
            }`}
          >
            L{String(f).padStart(2, '0')}
          </button>
        ))}
      </div>
    </div>
  );
}
