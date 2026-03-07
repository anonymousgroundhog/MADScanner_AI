
import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { D3Node, D3Link, StateId } from '../types';

interface FsmGraphProps {
  nodes: D3Node[];
  links: D3Link[];
  currentStateId: StateId;
  traversedLinks: Set<string>;
  isSpread?: boolean;
}

const FsmGraph: React.FC<FsmGraphProps> = ({ nodes, links, currentStateId, traversedLinks, isSpread = false }) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const simulationRef = useRef<d3.Simulation<D3Node, D3Link> | null>(null);
  const isSpreadRef = useRef(isSpread);

  // Sync ref with prop for access inside D3 closures
  useEffect(() => {
    isSpreadRef.current = isSpread;
  }, [isSpread]);

  // Initialize graph structure
  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    const width = svg.node()!.getBoundingClientRect().width;
    const height = svg.node()!.getBoundingClientRect().height;

    // Clean up previous elements
    svg.selectAll('*').remove();

    // Initialize positions based on layout if they don't exist yet (first render)
    nodes.forEach(node => {
        if (node.layout && (node.x === undefined || node.x === 0)) {
            node.x = width * node.layout.x;
            node.y = height * node.layout.y;
        }
    });

    // Pre-process links to assign indices for self-loops and multiple links
    const linkGroups: Record<string, number> = {};
    links.forEach(link => {
      const srcId = (typeof link.source === 'object') ? (link.source as D3Node).id : link.source as string;
      const tgtId = (typeof link.target === 'object') ? (link.target as D3Node).id : link.target as string;
      // Sort IDs to create a canonical key for the pair
      const key = [srcId, tgtId].sort().join('-');
      linkGroups[key] = (linkGroups[key] || 0) + 1;
    });

    const linkIndices: Record<string, number> = {};
    links.forEach(link => {
      const srcId = (typeof link.source === 'object') ? (link.source as D3Node).id : link.source as string;
      const tgtId = (typeof link.target === 'object') ? (link.target as D3Node).id : link.target as string;
      const key = [srcId, tgtId].sort().join('-');
      
      link.linkIndex = linkIndices[key] || 0;
      link.totalInGroup = linkGroups[key];
      linkIndices[key] = (linkIndices[key] || 0) + 1;
    });

    const g = svg.append('g');

    // Define markers
    const defs = svg.append('defs');

    // Arrowhead marker (Valid)
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 29) 
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('xoverflow', 'visible')
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#999')
      .style('stroke', 'none');
    
    // Active Arrowhead (Green)
    defs.append('marker')
      .attr('id', 'arrowhead-active')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 29)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('xoverflow', 'visible')
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#10b981') // Green (emerald-500)
      .style('stroke', 'none');
      
    // Violation Arrowhead (Red) - Points forward
    defs.append('marker')
      .attr('id', 'arrowhead-violation')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 29) 
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('xoverflow', 'visible')
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#ef4444') // red-500
      .style('stroke', 'none');

    // Reverse Violation Arrowhead (Red) - Points backward
    defs.append('marker')
      .attr('id', 'arrowhead-violation-reverse')
      .attr('viewBox', '0 -5 40 10')
      .attr('refX', 0) 
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('xoverflow', 'visible')
      .append('svg:path')
      .attr('d', 'M 39,-5 L 29,0 L 39,5') // Arrow pointing left (Back to start)
      .attr('fill', '#ef4444')
      .style('stroke', 'none');

    const link = g.append('g')
      .attr('class', 'links')
      .selectAll('path')
      .data(links)
      .enter().append('path')
      .attr('class', 'link')
      .attr('fill', 'none')
      .attr('stroke', (d: D3Link) => d.isViolation ? '#ef4444' : '#999')
      .attr('stroke-width', 1.5)
      .attr('marker-end', (d: D3Link) => d.isViolation ? 'url(#arrowhead-violation)' : 'url(#arrowhead)')
      .attr('marker-start', (d: D3Link) => d.isBidirectional ? 'url(#arrowhead-violation-reverse)' : null);

    const linkLabelGroup = g.append("g")
      .attr("class", "link-labels")
      .selectAll("text")
      .data(links)
      .enter().append("text")
      .attr('dy', 4) // Centered vertically on the path
      .style('text-anchor', 'middle')
      .style('fill', (d: D3Link) => d.isViolation ? '#ef4444' : '#9ca3af')
      .style('font-size', '10px')
      .style('font-weight', '600')
      .style('paint-order', 'stroke fill')
      .style('stroke', '#111827') 
      .style('stroke-width', '6px')
      .style('stroke-linecap', 'round')
      .style('stroke-linejoin', 'round');

    // Handle multi-line text for sequence events
    linkLabelGroup.each(function(d: D3Link) {
        const el = d3.select(this);
        const lines = d.event.split('\n');
        if (lines.length > 1) {
            const startY = -((lines.length - 1) * 10) / 2;
            el.text(''); // clear existing text
            lines.forEach((line, i) => {
                el.append('tspan')
                  .attr('x', 0)
                  .attr('dy', i === 0 ? `${startY + 4}px` : '10px')
                  .text(line);
            });
        } else {
            el.text(d.event);
        }
    });

    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(nodes)
      .enter().append('g')
      .attr('class', 'node-group');

    node.append('circle')
      .attr('r', 20)
      .attr('stroke', (d: D3Node) => d.isStartState ? '#10b981' : '#6b7280')
      .attr('stroke-width', 3)
      .attr('fill', '#1f2937'); // bg-gray-800
    
    node.append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .style('font-size', '10px')
      .style('font-weight', 'bold')
      .style('fill', 'white')
      .style('pointer-events', 'none')
      .text((d: D3Node) => d.id.split('_').map(w => w[0]).join(''));

    const nodeLabel = g.append("g")
      .attr("class", "node-labels")
      .selectAll("text")
      .data(nodes)
      .enter().append("text")
      .text((d: D3Node) => d.label)
      .attr('dy', 35)
      .attr('text-anchor', 'middle')
      .style('fill', '#e5e7eb')
      .style('font-size', '12px')
      .style('paint-order', 'stroke')
      .style('stroke', '#111827')
      .style('stroke-width', '3px');
    
    const ticked = () => {
        const spread = isSpreadRef.current;
        const curveSpacing = spread ? 100 : 50;
        const loopBase = spread ? 80 : 50;
        const loopStep = spread ? 30 : 15;
        const loopWidth = spread ? 60 : 45;

        link.attr('d', (d: D3Link) => {
            const src = d.source as D3Node;
            const tgt = d.target as D3Node;
            
            if (src.id === tgt.id) {
                // Self-loop
                const idx = d.linkIndex || 0;
                let dir = -1; 
                if (src.layout && src.layout.y > 0.5) dir = 1;
                
                const h = (loopBase + (idx * loopStep)) * dir; 
                return `M ${src.x},${src.y} C ${src.x! - loopWidth},${src.y! + h} ${src.x! + loopWidth},${src.y! + h} ${src.x},${src.y}`;
            } else {
                // Multi-edge Curve
                const isCanonical = src.id < tgt.id;
                const start = isCanonical ? src : tgt;
                const end = isCanonical ? tgt : src;
                
                const dx = end.x! - start.x!;
                const dy = end.y! - start.y!;
                
                const mx = (start.x! + end.x!) / 2;
                const my = (start.y! + end.y!) / 2;
                
                const dr = Math.sqrt(dx * dx + dy * dy) || 1;
                const nx = -dy / dr;
                const ny = dx / dr;
                
                const count = d.totalInGroup || 1;
                const index = d.linkIndex || 0;
                const shift = (index - (count - 1) / 2);
                const curveShift = shift * curveSpacing;

                const cpx = mx + nx * curveShift;
                const cpy = my + ny * curveShift;

                return `M${src.x},${src.y}Q${cpx},${cpy} ${tgt.x},${tgt.y}`;
            }
        });

        node.attr('transform', (d: D3Node) => `translate(${d.x},${d.y})`);
        nodeLabel.attr('x', (d: D3Node) => d.x!).attr('y', (d: D3Node) => d.y!);
        
        linkLabelGroup.attr('transform', function(d: D3Link) {
            const src = d.source as D3Node;
            const tgt = d.target as D3Node;
            
            if (src.id === tgt.id) {
                const idx = d.linkIndex || 0;
                let dir = -1; 
                if (src.layout && src.layout.y > 0.5) dir = 1;
                const h = (loopBase + (idx * loopStep)) * dir;
                const padding = dir === 1 ? 15 : -5;
                return `translate(${src.x}, ${src.y! + h + padding})`;
            }
            
            const isCanonical = src.id < tgt.id;
            const start = isCanonical ? src : tgt;
            const end = isCanonical ? tgt : src;
            
            const count = d.totalInGroup || 1;
            const index = d.linkIndex || 0;
            const shift = (index - (count - 1) / 2);
            const curveShift = shift * curveSpacing;
            
            const dx = end.x! - start.x!;
            const dy = end.y! - start.y!;
            const dr = Math.sqrt(dx * dx + dy * dy) || 1;
            const nx = -dy / dr;
            const ny = dx / dr;
            const mx = (start.x! + end.x!) / 2;
            const my = (start.y! + end.y!) / 2;
            
            const cpx = mx + nx * curveShift;
            const cpy = my + ny * curveShift;
            
            const tx = 0.25 * src.x! + 0.5 * cpx + 0.25 * tgt.x!;
            const ty = 0.25 * src.y! + 0.5 * cpy + 0.25 * tgt.y!;
            
            return `translate(${tx}, ${ty})`;
        });
    };

    // Initialize simulation
    simulationRef.current = d3.forceSimulation<D3Node, D3Link>(nodes)
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('x', d3.forceX())
      .force('y', d3.forceY())
      .on('tick', ticked);
    
    const zoom = d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
           g.attr('transform', event.transform);
        });
    svg.call(zoom as any);

    const drag = d3.drag<SVGGElement, D3Node>()
      .on('start', (event) => {
        if (!event.active) simulationRef.current?.alphaTarget(0.3).restart();
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      })
      .on('drag', (event) => {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      })
      .on('end', (event) => {
        if (!event.active) simulationRef.current?.alphaTarget(0);
        if (!event.subject.layout && isSpreadRef.current) {
            event.subject.fx = null;
            event.subject.fy = null;
        }
      });
      
    node.call(drag as any);

    simulationRef.current.stop();
    for (let i = 0; i < 200; ++i) simulationRef.current.tick();
    ticked();

  }, [nodes, links]);

  // Update simulation forces and Layout Mode
  useEffect(() => {
    if (!simulationRef.current || !svgRef.current) return;
    
    const svg = d3.select(svgRef.current);
    const width = svg.node()!.getBoundingClientRect().width;
    const height = svg.node()!.getBoundingClientRect().height;
    
    const sim = simulationRef.current;

    if (isSpread) {
        // SPREAD MODE
        sim.nodes().forEach(d => { d.fx = null; d.fy = null; });

        sim
          .force('charge', d3.forceManyBody().strength(-3000))
          .force('link', d3.forceLink<D3Node, D3Link>(links).id(d => d.id).distance(300))
          .force('collide', d3.forceCollide(80))
          .force('center', d3.forceCenter(width / 2, height / 2).strength(0.05))
          .force('x', d3.forceX<D3Node>((d) => d.layout ? width * d.layout.x : width/2).strength(0.05))
          .force('y', d3.forceY<D3Node>((d) => d.layout ? height * d.layout.y : height/2).strength(0.05));
    } else {
        // COMPACT MODE
        sim.nodes().forEach(d => {
            if (d.layout) {
                d.fx = width * d.layout.x;
                d.fy = height * d.layout.y;
            }
        });

        sim
          .force('charge', d3.forceManyBody().strength(-500))
          .force('link', d3.forceLink<D3Node, D3Link>(links).id(d => d.id).distance(100))
          .force('collide', d3.forceCollide(50))
          .force('center', null)
          .force('x', null)
          .force('y', null);
    }
    
    sim.alpha(1).restart();
  }, [isSpread, links, nodes]);

  // Update visuals
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);

    svg.selectAll('.node-group circle')
      .transition().duration(300)
      .attr('fill', d => {
        const n = d as D3Node;
        if(n.id === currentStateId) return '#0d9488';
        return '#1f2937';
      })
      .attr('stroke', d => {
          const n = d as D3Node;
          if(n.id === currentStateId) return '#2dd4bf';
          return n.isStartState ? '#10b981' : '#6b7280';
      })
      .attr('r', d => (d as D3Node).id === currentStateId ? 25 : 20);

    svg.selectAll('.link')
      .transition().duration(300)
      .attr('stroke', d => {
        const l = d as D3Link;
        if (l.isViolation) return '#ef4444';
        
        const srcId = (l.source as D3Node).id;
        const tgtId = (l.target as D3Node).id;
        const linkId = `${srcId}-${tgtId}-${l.event}`;
        
        if (traversedLinks.has(linkId)) return '#10b981'; // Green for traversed
        return '#999';
      })
      .attr('stroke-width', d => {
          // Make traversed links slightly thicker for visibility
          const l = d as D3Link;
          const srcId = (l.source as D3Node).id;
          const tgtId = (l.target as D3Node).id;
          const linkId = `${srcId}-${tgtId}-${l.event}`;
          return traversedLinks.has(linkId) ? 2.5 : 1.5;
      })
      .attr('marker-end', d => {
          const l = d as D3Link;
          if (l.isViolation) return 'url(#arrowhead-violation)';
          
          const srcId = (l.source as D3Node).id;
          const tgtId = (l.target as D3Node).id;
          const linkId = `${srcId}-${tgtId}-${l.event}`;
          
          if (traversedLinks.has(linkId)) return 'url(#arrowhead-active)';
          return 'url(#arrowhead)';
      })
      .attr('marker-start', d => (d as D3Link).isBidirectional ? 'url(#arrowhead-violation-reverse)' : null);
      
      svg.selectAll('.link-labels text')
         .style('fill', d => {
            const l = d as D3Link;
            if (l.isViolation) return '#ef4444';
            
            const srcId = (l.source as D3Node).id;
            const tgtId = (l.target as D3Node).id;
            const linkId = `${srcId}-${tgtId}-${l.event}`;
            
            if (traversedLinks.has(linkId)) return '#10b981';
            return '#9ca3af';
         });

  }, [currentStateId, traversedLinks]);

  return <svg ref={svgRef} width="100%" height="100%" className="cursor-move"></svg>;
};

export default FsmGraph;
    