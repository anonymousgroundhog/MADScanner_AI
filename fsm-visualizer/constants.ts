
import { FsmDefinition, EventId } from './types';

// FSM Definition based on the Python script's logic
export const FSM_DEFINITION: FsmDefinition = {
  START: {
    state: { id: 'START', label: 'Start', isStartState: true },
    transitions: [
      { event: 'attachInfo', target: 'START' },
      { event: 'build', target: 'ADVIEW_SET' },
      // Alternative path from Python logic (implied)
      { event: 'initialize', target: 'NO_ADS_DISPLAYED' }, 
      { event: 'onAdLoaded', target: 'ADS_DISPLAYED' },
    ],
  },
  ADVIEW_SET: {
    state: { id: 'ADVIEW_SET', label: 'AdViewSet' },
    transitions: [
      { event: 'build', target: 'ADVIEW_SET' },
      { event: 'initialize', target: 'NO_ADS_DISPLAYED' },
    ],
  },
  NO_ADS_DISPLAYED: {
    state: { id: 'NO_ADS_DISPLAYED', label: 'NoAdsDisplayed' },
    transitions: [
      { event: 'initialize', target: 'NO_ADS_DISPLAYED' },
      { event: 'onAdLoaded', target: 'AD_LOADED' },
    ],
  },
  AD_LOADED: {
    state: { id: 'AD_LOADED', label: 'AdLoaded' },
    transitions: [
      { event: 'onAdLoaded', target: 'AD_LOADED' },
      { event: 'onResume', target: 'IMPRESSION_MADE' },
      { event: 'onDestroy', target: 'ADVIEW_SET' },
    ],
  },
  IMPRESSION_MADE: {
    state: { id: 'IMPRESSION_MADE', label: 'ImpressionMade' },
    transitions: [
      { event: 'onResume', target: 'IMPRESSION_MADE' },
      { event: 'onPause', target: 'ENGAGEMENT_MADE' },
      { event: 'onDestroy', target: 'ADVIEW_SET' },
    ],
  },
  ENGAGEMENT_MADE: {
    state: { id: 'ENGAGEMENT_MADE', label: 'EngagementMade' },
    transitions: [
      { event: 'onPause', target: 'ENGAGEMENT_MADE' },
      { event: 'onDestroy', target: 'ADVIEW_SET' },
    ],
  },
  ADS_DISPLAYED: {
    state: { id: 'ADS_DISPLAYED', label: 'AdsDisplayed' },
    transitions: [
      { event: 'onAdLoaded', target: 'ADS_DISPLAYED' },
      { event: 'onAdImpression', target: 'ADS_DISPLAYED' },
      { event: 'onPause', target: 'ENGAGEMENT_MADE' },
    ],
  },
};

// Layout coordinates adapted for the new FSM model
export const NODE_LAYOUT: Record<string, {x: number, y: number}> = {
    AD_LOADED:        { x: 0.15, y: 0.25 },
    NO_ADS_DISPLAYED: { x: 0.38, y: 0.25 },
    ADVIEW_SET:       { x: 0.62, y: 0.25 },
    START:            { x: 0.85, y: 0.25 },
    
    IMPRESSION_MADE:  { x: 0.25, y: 0.75 },
    ENGAGEMENT_MADE:  { x: 0.50, y: 0.75 },
    ADS_DISPLAYED:    { x: 0.75, y: 0.75 },
};

export const ALL_EVENTS: EventId[] = [
    'attachInfo',
    'build',
    'initialize',
    'onAdLoaded',
    'onAdImpression',
    'onResume',
    'onPause',
    'onDestroy'
];
