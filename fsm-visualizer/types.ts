import type * as d3 from 'd3';

export type StateId =
  | 'START'
  | 'ADVIEW_SET'
  | 'NO_ADS_DISPLAYED'
  | 'AD_LOADED'
  | 'IMPRESSION_MADE'
  | 'ENGAGEMENT_MADE'
  | 'ADS_DISPLAYED';

export type EventId =
  | 'attachInfo'
  | 'build'
  | 'initialize'
  | 'onAdLoaded'
  | 'onResume'
  | 'onPause'
  | 'onDestroy'
  | 'onAdImpression';

export interface State {
  id: StateId;
  label: string;
  isStartState?: boolean;
}

export interface Transition {
  event: EventId | string;
  target: StateId;
}

export type FsmDefinition = Record<StateId, {
  state: State;
  transitions: Transition[];
}>;

export interface D3Node extends d3.SimulationNodeDatum {
  id: StateId;
  label: string;
  isStartState?: boolean;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
  layout?: { x: number, y: number }; // Relative position (0-1)
}

// FIX: Corrected typo `d` to `d3` to match the imported namespace.
export interface D3Link extends d3.SimulationLinkDatum<D3Node> {
  source: string | D3Node;
  target: string | D3Node;
  event: EventId | string; // Allow string for violations or combined events
  linkIndex?: number;
  totalInGroup?: number;
  isViolation?: boolean;
  isBidirectional?: boolean;
}
