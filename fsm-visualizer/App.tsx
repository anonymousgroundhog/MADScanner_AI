
import React, { useState, useCallback, useMemo, useRef } from 'react';
import { FSM_DEFINITION, ALL_EVENTS, NODE_LAYOUT } from './constants';
import { StateId, EventId, D3Node, D3Link } from './types';
import FsmGraph from './components/FsmGraph';
import { UploadIcon, PlayIcon, ResetIcon, CodeIcon, InfoIcon, SmartphoneIcon, ExpandIcon, CloseIcon, AlertIcon, FastForwardIcon } from './components/Icon';

interface AppData {
    events: EventId[];
    logs: string[];
    hasCrash?: boolean;
}

// Limit displayed log lines to prevent browser hang on massive files
const MAX_LOG_LINES = 5000;

// Regex patterns inspired by the Python script
const CRASH_PATTERN = /Process:\s*(.*?),\s*PID:\s*(\d+)/;
const START_PROC_PATTERN = /Start proc (\d+):([a-zA-Z0-9._]+)\//;
const BRACKET_PATTERN = /<(.*?)>/;
// FIX: Changed Python-style named capture group (?P<name>) to JS-style (?<name>)
const PID_RE = /^\s*\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+(?<pid>\d+)\s+(?<tid>\d+)/;


// Define structure for the simulation state stored in ref
interface SimulationRefState {
    step: number;
    currentStateId: StateId;
    traversedLinks: Set<string>;
    violationLinks: D3Link[];
    eventLog: {event: EventId, from: StateId, to: StateId, isViolation?: boolean}[];
    
    // Sequence tracking
    sequenceTargetState: StateId | null;
    sequenceRemainingEvents: string[];
    sequenceLinkId: string | null;
}

const App: React.FC = () => {
  const [logContent, setLogContent] = useState<string>('');
  const [fileName, setFileName] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [processing, setProcessing] = useState<boolean>(false);
  const [simulationRunning, setSimulationRunning] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  const [isSpread, setIsSpread] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'transitions' | 'logs'>('transitions');

  // Multi-app support (Key is Package Name)
  const [apps, setApps] = useState<Record<string, AppData>>({});
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  
  // Crash tracking
  const [crashedApps, setCrashedApps] = useState<string[]>([]);
  const [showCrashModal, setShowCrashModal] = useState<boolean>(false);

  const simulationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startStateId = useMemo(() => 
    Object.values(FSM_DEFINITION).find(def => def.state.isStartState)?.state.id || Object.keys(FSM_DEFINITION)[0] as StateId,
    []
  );

  // React state for rendering
  const [currentStateId, setCurrentStateId] = useState<StateId>(startStateId);
  const [traversedLinks, setTraversedLinks] = useState<Set<string>>(new Set());
  const [violationLinks, setViolationLinks] = useState<D3Link[]>([]);
  const [eventLog, setEventLog] = useState<{event: EventId, from: StateId, to: StateId, isViolation?: boolean}[]>([]);
  const [currentStep, setCurrentStep] = useState<number>(0);

  // Mutable Simulation State (Logic decoupled from Render)
  const simStateRef = useRef<SimulationRefState>({
      step: 0,
      currentStateId: startStateId,
      traversedLinks: new Set(),
      violationLinks: [],
      eventLog: [],
      sequenceTargetState: null,
      sequenceRemainingEvents: [],
      sequenceLinkId: null
  });

  // Compute static links from definition
  const staticLinks = useMemo(() => {
    const d3Links: D3Link[] = [];
    Object.values(FSM_DEFINITION).forEach(def => {
      def.transitions.forEach(transition => {
        d3Links.push({
          source: def.state.id,
          target: transition.target,
          event: transition.event,
        });
      });
    });
    return d3Links;
  }, []);

  const nodes = useMemo(() => {
    return Object.values(FSM_DEFINITION).map(def => ({
      id: def.state.id,
      label: def.state.label,
      isStartState: def.state.isStartState,
      layout: NODE_LAYOUT[def.state.id] // Inject layout coordinates
    }));
  }, []);

  // Merge static links with dynamic violation links
  const graphLinks = useMemo(() => {
    const validLinks = staticLinks; 
    const violationLinksList = violationLinks;

    const violationGroups = new Map<string, D3Link[]>();
    violationLinksList.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source as string;
        const t = typeof l.target === 'object' ? l.target.id : l.target as string;
        const key = [s, t].sort().join('$$');
        if (!violationGroups.has(key)) violationGroups.set(key, []);
        violationGroups.get(key)!.push(l);
    });

    const mergedViolations: D3Link[] = [];

    violationGroups.forEach((group, key) => {
        if (group.length === 0) return;
        
        const [id1, id2] = key.split('$$');
        const forwardLinks = group.filter(l => l.source === id1 && l.target === id2);
        const backwardLinks = group.filter(l => l.source === id2 && l.target === id1);
        const isBidirectional = forwardLinks.length > 0 && backwardLinks.length > 0;

        const events = new Set<string>();
        group.forEach(l => {
            if (typeof l.event === 'string') l.event.split('\n').forEach(e => events.add(e));
        });
        const combinedEvent = Array.from(events).join('\n');

        let source = id1, target = id2;
        if (!isBidirectional) {
            if (forwardLinks.length > 0) { source = id1; target = id2; } 
            else { source = id2; target = id1; }
        }

        mergedViolations.push({ source, target, event: combinedEvent, isViolation: true, isBidirectional });
    });

    return [...validLinks, ...mergedViolations];
  }, [staticLinks, violationLinks]);

  const stopSimulation = useCallback(() => {
    if (simulationIntervalRef.current) {
      clearInterval(simulationIntervalRef.current);
      simulationIntervalRef.current = null;
    }
    setSimulationRunning(false);
  }, []);

  const resetSimulation = useCallback(() => {
    stopSimulation();
    
    setCurrentStateId(startStateId);
    setTraversedLinks(new Set());
    setViolationLinks([]);
    setEventLog([]);
    setCurrentStep(0);
    setError('');

    simStateRef.current = {
      step: 0,
      currentStateId: startStateId,
      traversedLinks: new Set(),
      violationLinks: [],
      eventLog: [],
      sequenceTargetState: null,
      sequenceRemainingEvents: [],
      sequenceLinkId: null
    };
  }, [startStateId, stopSimulation]);

  const resetAll = useCallback(() => {
    resetSimulation();
    setLogContent('');
    setFileName('');
    setApps({});
    setSelectedAppId(null);
    setCrashedApps([]);
    setProcessing(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [resetSimulation]);

  const findLikelyTarget = useCallback((event: EventId): StateId | null => {
      let loopTarget: StateId | null = null;
      for (const stateKey in FSM_DEFINITION) {
          const def = FSM_DEFINITION[stateKey as StateId];
          for (const t of def.transitions) {
              if (t.event === event) {
                  if (t.target !== def.state.id) return t.target; 
                  else loopTarget = t.target;
              }
          }
      }
      return loopTarget;
  }, []);

  const processNextEvent = useCallback((appEvents: EventId[]) => {
      const s = simStateRef.current;
      if (s.step >= appEvents.length) return false;
      const event = appEvents[s.step];
      
      if (event === 'attachInfo') {
        s.currentStateId = 'START';
        s.sequenceRemainingEvents = [];
        s.sequenceTargetState = null;
        s.sequenceLinkId = null;
      }

      if (s.sequenceRemainingEvents.length > 0) {
          const expected = s.sequenceRemainingEvents[0];
          if (event === expected) {
              s.sequenceRemainingEvents.shift();
              if (s.sequenceRemainingEvents.length === 0) {
                  s.eventLog.push({event, from: s.currentStateId, to: s.sequenceTargetState!});
                  s.currentStateId = s.sequenceTargetState!;
                  s.sequenceTargetState = null;
                  s.sequenceLinkId = null;
              } else {
                  s.eventLog.push({event, from: s.currentStateId, to: s.currentStateId}); 
              }
              s.step++;
              return true;
          } else {
              s.sequenceRemainingEvents = [];
              s.sequenceTargetState = null;
              s.sequenceLinkId = null;
          }
      }

      const transitions = FSM_DEFINITION[s.currentStateId]?.transitions || [];
      const transition = transitions.find(t => t.event === event);

      if (transition) {
          const fromState = s.currentStateId;
          const toState = transition.target;
          s.currentStateId = toState;
          const linkId = `${fromState}-${toState}-${transition.event}`;
          s.traversedLinks.add(linkId);
          s.eventLog.push({event, from: fromState, to: toState});
      } else {
          const likelyTarget = findLikelyTarget(event);
          const violationTarget = likelyTarget || s.currentStateId;
          const violationLink: D3Link = { source: s.currentStateId, target: violationTarget, event: event, isViolation: true };
          const exists = s.violationLinks.some(l => l.source === violationLink.source && l.target === violationLink.target && l.event === violationLink.event);
          if (!exists) s.violationLinks.push(violationLink);
          s.traversedLinks.add(`${s.currentStateId}-${violationTarget}-${event}`);
          s.eventLog.push({event, from: s.currentStateId, to: violationTarget, isViolation: true});
          s.currentStateId = violationTarget;
      }
      s.step++;
      return true;
  }, [findLikelyTarget]);

  const syncSimulationState = () => {
      const s = simStateRef.current;
      setCurrentStateId(s.currentStateId);
      setTraversedLinks(new Set(s.traversedLinks));
      setViolationLinks([...s.violationLinks]);
      setEventLog([...s.eventLog]);
      setCurrentStep(s.step);
  };

  const startSimulationForApp = useCallback((appEvents: EventId[]) => {
    resetSimulation();
    if (appEvents.length === 0) return;
    setSimulationRunning(true);
    simulationIntervalRef.current = setInterval(() => {
        const shouldContinue = processNextEvent(appEvents);
        syncSimulationState();
        if (!shouldContinue) stopSimulation();
    }, 1000);
  }, [resetSimulation, processNextEvent, stopSimulation]);

  const skipToEnd = useCallback(() => {
      if (!selectedAppId || !apps[selectedAppId]) return;
      const appEvents = apps[selectedAppId].events;
      if (simStateRef.current.step >= appEvents.length) return;
      stopSimulation();
      while(processNextEvent(appEvents));
      syncSimulationState();
      setSimulationRunning(false);
  }, [selectedAppId, apps, processNextEvent, stopSimulation]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setFileName(file.name);
      const reader = new FileReader();
      reader.onload = (e) => setLogContent(e.target?.result as string);
      reader.readAsText(file);
    }
  };

  const processLog = () => {
    if (!logContent) {
      setError('Please upload a log file.');
      return;
    }
    
    resetSimulation();
    setProcessing(true);
    setApps({});
    setSelectedAppId(null);
    setCrashedApps([]);

    const lines = logContent.split(/\r?\n/);
    const pidToPackageMap = new Map<string, string>();
    const crashedPackageSet = new Set<string>();

    // Pass 1: Build PID -> Package Map
    lines.forEach(line => {
        let match;
        if (line.includes("E AndroidRuntime:") && (match = line.match(CRASH_PATTERN))) {
            const [, pkg, pid] = match;
            pidToPackageMap.set(pid.trim(), pkg.trim());
            crashedPackageSet.add(pkg.trim());
        } else if (line.includes("Start proc") && (match = line.match(START_PROC_PATTERN))) {
            const [, pid, pkg] = match;
            pidToPackageMap.set(pid.trim(), pkg.trim());
        }
    });

    const appsRecord: Record<string, AppData> = {};
    const REQUIRED_PROVIDER = "com.google.android.gms.ads.MobileAdsInitProvider";
    const REQUIRED_HEADER = "SootInjection: Entering method:";

    // Pass 2: Collect Filtered Logs
    lines.forEach(line => {
        if (!line.includes(REQUIRED_HEADER) || !line.includes(REQUIRED_PROVIDER) || !ALL_EVENTS.some(k => line.includes(k))) {
            return;
        }

        const pidMatch = line.match(PID_RE);
        const currentPid = pidMatch?.groups?.pid;
        
        if (currentPid && pidToPackageMap.has(currentPid)) {
            const pkgName = pidToPackageMap.get(currentPid)!;
            
            const bracketMatch = line.match(BRACKET_PATTERN);
            if (bracketMatch) {
                const fullSignature = bracketMatch[1].trim();
                const preParen = fullSignature.split('(')[0];
                const methodName = preParen.split(/\s+/).pop() as EventId;

                if (ALL_EVENTS.includes(methodName)) {
                    if (!appsRecord[pkgName]) {
                        appsRecord[pkgName] = { events: [], logs: [] };
                    }
                    appsRecord[pkgName].events.push(methodName);
                    appsRecord[pkgName].logs.push(line.trim());
                }
            }
        }
    });

    const alivePackageSet = new Set(Object.keys(appsRecord));
    const finalCrashedPackages = Array.from(crashedPackageSet).filter(pkg => !alivePackageSet.has(pkg));
    setCrashedApps(finalCrashedPackages);
    
    Object.keys(appsRecord).forEach(pkg => {
        appsRecord[pkg].hasCrash = finalCrashedPackages.includes(pkg);
    });

    setApps(appsRecord);

    const discoveredApps = Object.keys(appsRecord);
    if (discoveredApps.length === 0) {
      setError('No apps with valid FSM event sequences were discovered in the log file.');
    } else {
      const sortedApps = discoveredApps.sort((a, b) => appsRecord[b].events.length - appsRecord[a].events.length);
      const bestPkg = sortedApps[0];
      setSelectedAppId(bestPkg);
      startSimulationForApp(appsRecord[bestPkg].events);
    }
    
    setProcessing(false);
  };

  const handleAppSelect = (pkg: string) => {
      if (pkg === selectedAppId) return;
      setSelectedAppId(pkg);
      startSimulationForApp(apps[pkg].events);
  };

  const getDisplayedLogs = (pkgId: string) => {
      if (!apps[pkgId]) return '';
      const logs = apps[pkgId].logs;
      if (logs.length > MAX_LOG_LINES) {
          return logs.slice(0, MAX_LOG_LINES).join('\n') + `\n\n... [Truncated: Showing first ${MAX_LOG_LINES} of ${logs.length} lines]`;
      }
      return logs.join('\n');
  };

  return (
    <div className="flex flex-col md:flex-row h-screen font-sans bg-gray-900 text-gray-200 relative">
      {showCrashModal && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-gray-800 border border-gray-600 rounded-lg shadow-2xl w-full max-w-lg p-6 m-4 relative flex flex-col max-h-[80vh]">
                <button onClick={() => setShowCrashModal(false)} className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors">
                    <CloseIcon className="w-6 h-6" />
                </button>
                <header className="flex items-center mb-4 border-b border-gray-700 pb-2">
                    <AlertIcon className="w-6 h-6 text-red-500 mr-3" />
                    <h2 className="text-xl font-bold text-red-400">Crashed Applications</h2>
                </header>
                <div className="flex-grow overflow-y-auto pr-2 space-y-2">
                    {crashedApps.length === 0 ? (
                        <p className="text-gray-400 italic text-center py-4">No exclusive crashes detected.</p>
                    ) : (
                        crashedApps.map((app, idx) => (
                            <div key={idx} className="p-3 bg-gray-900/50 rounded border border-red-900/30 flex items-center justify-between">
                                <span className="font-mono text-sm text-gray-200 break-all">{app}</span>
                                <span className="text-[10px] font-bold bg-red-500/20 text-red-400 px-2 py-1 rounded ml-3 flex-shrink-0">CRASH</span>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
      )}

      <aside className="w-full md:w-1/3 lg:w-1/4 p-4 space-y-4 bg-gray-800/50 border-r border-gray-700 flex flex-col overflow-y-auto">
        <header className="flex items-center space-x-3 pb-2 border-b border-gray-700">
          <CodeIcon className="w-8 h-8 text-cyan-400" />
          <div>
            <h1 className="text-xl font-bold text-white">Android FSM Visualizer</h1>
            <p className="text-xs text-gray-400">Behavioral Model Tracer</p>
          </div>
        </header>

        <section className="space-y-3 flex-grow flex flex-col">
          <h2 className="text-lg font-semibold text-cyan-400">Configuration</h2>
          
          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-400 mb-1">Log File</label>
            <div className="relative">
                <input id="file-upload" type="file" className="hidden" onChange={handleFileChange} accept=".txt,.log" ref={fileInputRef} />
                {!fileName ? (
                     <label htmlFor="file-upload" className="cursor-pointer w-full inline-flex items-center justify-center px-4 py-6 border border-dashed border-gray-500 rounded-md text-sm font-medium text-gray-300 hover:text-white hover:border-cyan-400 transition-colors bg-gray-900/50 group">
                        <div className="flex flex-col items-center">
                        <UploadIcon className="w-6 h-6 mb-2 text-gray-500 group-hover:text-cyan-400 transition-colors"/>
                        <span className="truncate max-w-[200px]">Upload Log Trace</span>
                        </div>
                    </label>
                ) : (
                    <div className="w-full flex items-center justify-between px-3 py-3 border border-gray-600 rounded-md bg-gray-800/50">
                         <label htmlFor="file-upload" className="flex items-center overflow-hidden mr-2 flex-grow cursor-pointer">
                             <div className="p-2 bg-gray-700 rounded-md mr-3"><UploadIcon className="w-4 h-4 text-cyan-400"/></div>
                             <div className="flex flex-col min-w-0">
                                 <span className="truncate text-sm font-medium text-gray-200" title={fileName}>{fileName}</span>
                                 <span className="text-xs text-gray-500">Click to change</span>
                             </div>
                         </label>
                         <button onClick={resetAll} className="p-1.5 rounded-md text-gray-400 hover:text-red-400 hover:bg-gray-700" title="Remove Log"><CloseIcon className="w-4 h-4"/></button>
                    </div>
                )}
            </div>
          </div>

          <div className="flex space-x-2 pt-2">
            <button onClick={processLog} disabled={!logContent || processing || simulationRunning} className="flex-1 inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 disabled:cursor-not-allowed">
              <PlayIcon className="w-5 h-5 mr-2"/>
              {processing ? 'Processing...' : 'Process Log'}
            </button>
             <button onClick={skipToEnd} disabled={!selectedAppId || !apps[selectedAppId]} className="inline-flex items-center justify-center p-2 border border-cyan-700 bg-cyan-900/30 rounded-md text-cyan-300 hover:bg-cyan-800 disabled:bg-gray-800 disabled:border-gray-700 disabled:text-gray-600" title="Skip to End"><FastForwardIcon className="w-5 h-5"/></button>
            <button onClick={resetAll} className="inline-flex items-center justify-center p-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700" title="Reset All"><ResetIcon className="w-5 h-5"/></button>
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          
          {crashedApps.length > 0 && (
            <div className="pt-2"><button onClick={() => setShowCrashModal(true)} className="w-full flex items-center justify-center px-4 py-2.5 bg-red-500/10 border border-red-500/30 rounded-md text-red-400 hover:bg-red-500/20"><AlertIcon className="w-5 h-5 mr-2" /><span className="font-bold">View Crashed Apps ({crashedApps.length})</span></button></div>
          )}

          {Object.keys(apps).length > 0 && (
            <div className="flex-grow-0 pt-2">
                 <h2 className="text-lg font-semibold text-cyan-400 mb-2">Discovered Packages</h2>
                 <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
                     {Object.keys(apps).sort((a, b) => apps[b].events.length - apps[a].events.length).map(pkg => (
                         <button key={pkg} onClick={() => handleAppSelect(pkg)} className={`w-full flex items-center px-3 py-2 text-sm rounded-md transition-colors ${selectedAppId === pkg ? 'bg-cyan-900/50 text-cyan-100 border border-cyan-500/50' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                             <SmartphoneIcon className={`w-4 h-4 mr-2 flex-shrink-0 ${apps[pkg].hasCrash ? 'text-red-400' : 'text-gray-500'}`}/>
                             <div className="flex-grow text-left overflow-hidden"><div className="truncate font-mono text-xs flex items-center" title={pkg}>{pkg}{apps[pkg].hasCrash && (<AlertIcon className="w-3 h-3 ml-2" />)}</div></div>
                             <span className={`ml-2 text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${apps[pkg].events.length > 0 ? 'bg-cyan-800 text-cyan-200' : 'bg-gray-700'}`}>{apps[pkg].events.length}</span>
                         </button>
                     ))}
                 </div>
            </div>
          )}

          <div className="flex-grow pt-4">
             <h2 className="text-lg font-semibold text-cyan-400 mb-2">Simulation Status</h2>
             <div className={`p-3 rounded-lg space-y-2 text-sm ${selectedAppId && apps[selectedAppId]?.hasCrash ? 'bg-red-900/20 border border-red-800' : 'bg-gray-900/70'}`}>
                <div className="flex flex-col"><span className="font-semibold text-gray-400">Current Package:</span><span className={`font-mono text-xs break-all ${selectedAppId && apps[selectedAppId]?.hasCrash ? 'text-red-300' : 'text-cyan-300'}`}>{selectedAppId || '-'}</span></div>
                <p><span className="font-semibold text-gray-400">State:</span> <span className="font-mono text-cyan-300">{FSM_DEFINITION[currentStateId]?.state.label || 'Unknown'}</span></p>
                <p><span className="font-semibold text-gray-400">Step:</span> <span className="font-mono text-white">{currentStep} / {selectedAppId ? apps[selectedAppId]?.events.length : 0}</span></p>
                {selectedAppId && apps[selectedAppId]?.hasCrash && (<div className="flex items-center text-red-400 text-xs font-bold mt-2"><AlertIcon className="w-4 h-4 mr-1.5" />APP CRASH DETECTED</div>)}
             </div>
          </div>

          <div className="flex-grow pt-4 flex flex-col min-h-0">
            <div className="flex border-b border-gray-700 mb-2">
                <button className={`flex-1 py-1 text-sm font-medium ${activeTab === 'transitions' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-400'}`} onClick={() => setActiveTab('transitions')}>Transitions</button>
                <button className={`flex-1 py-1 text-sm font-medium ${activeTab === 'logs' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-400'}`} onClick={() => setActiveTab('logs')}>Raw Logs</button>
            </div>
            <div className="flex-grow bg-gray-900/70 rounded-lg overflow-hidden">
              {activeTab === 'transitions' ? (
                  <div className="h-full overflow-y-auto p-2">
                    {eventLog.length === 0 ? (<div className="flex items-center justify-center h-full text-gray-500"><InfoIcon className="w-4 h-4 mr-2"/><span>Waiting to start...</span></div>) : (
                        <ul className="space-y-1 text-xs">
                        {eventLog.map((log, index) => (
                            <li key={index} className={`p-1.5 rounded ${log.isViolation ? 'bg-red-900/40' : (index === currentStep - 1 ? 'bg-cyan-900/50' : '')}`}>
                            <span className={`font-mono px-1.5 py-0.5 rounded mr-2 ${log.isViolation ? 'bg-red-950 text-red-200' : 'bg-gray-700'}`}>{log.event}</span>
                            <span className="text-gray-400">→</span>
                            <span className={`font-mono ml-2 ${log.isViolation ? 'text-red-400' : 'text-cyan-400'}`}>{FSM_DEFINITION[log.to]?.state.label || 'Unknown'}</span>
                            </li>
                        ))}
                        </ul>
                    )}
                  </div>
              ) : ( selectedAppId && apps[selectedAppId] ? (<pre className="h-full w-full text-[10px] font-mono p-2 overflow-auto">{getDisplayedLogs(selectedAppId)}</pre>) : (<div className="flex items-center justify-center h-full text-gray-500 text-xs">Select an app to view logs</div>))}
            </div>
          </div>
        </section>
      </aside>
      <main className="flex-1 flex items-center justify-center p-4 relative">
        <div className="absolute top-4 right-4 z-10"><button onClick={() => setIsSpread(!isSpread)} className="flex items-center px-3 py-2 bg-gray-800 border border-gray-600 rounded-md shadow-md hover:bg-gray-700 text-xs" title={isSpread ? "Compact View" : "Spread View"}><ExpandIcon className="w-4 h-4 mr-2" />{isSpread ? 'Compact' : 'Spread'}</button></div>
        <FsmGraph nodes={nodes} links={graphLinks} currentStateId={currentStateId} traversedLinks={traversedLinks} isSpread={isSpread} />
      </main>
    </div>
  );
};
export default App;
