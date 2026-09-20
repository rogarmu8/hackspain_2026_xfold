/* ANIMATION STORYBOARD — milliseconds in a single 4800ms loop.
 *    0 →  350  extended, settle
 *  350 → 1050  right sleeve rotates 0 → π
 * 1050 → 1290  hold the XFOLD mark
 * 1290 → 1910  left sleeve rotates 0 → π
 * 2060 → 2720  hem rotates over the chest
 * 2770 → 3070  flat sleeve enters from below
 * 3130 → 3690  folded garment slides behind the sleeve
 * 3830 → 4200  package leaves through lower edge
 * 4270 → 4800  next shirt rises into initial pose
 */
const TIMING = {
  right: [350, 1050], left: [1290, 1910], hem: [2060, 2720],
  sleeve: [2770, 3070], insert: [3130, 3690], exit: [3830, 4200],
  next: [4270, 4800], duration: 4800,
};
const GARMENT = {
  focal: 190, center: [52, 48], lift: .24, width: 4,
  right: [[72,20],[90,38],[78,50],[72,44]],
  left: [[32,20],[14,38],[26,50],[32,44]],
  hem: [[32,48],[72,48],[72,76],[32,76]],
  insertDistance: 67, nextDistance: 140,
};
const PACKAGING = { top: 84, bottom: 122, x: 30, width: 60, entry: 65, exit: 64 };
const clamp = (v) => Math.min(1, Math.max(0, v));
// Quintic easing has zero velocity and acceleration at both ends, so hinges
// settle without overshooting or changing their physical length.
const ease = (v) => { const p = clamp(v); return p*p*p*(p*(p*6-15)+10); };
const progress = (t, [a,b]) => ease((t-a)/(b-a));
const n = (v) => Number(v.toFixed(3));
const points = (p) => p.map(([x,y]) => `${n(x)},${n(y)}`).join(' ');
const outline = (p) => `M${p.map(([x,y])=>`${n(x)} ${n(y)}`).join('L')}`;
const path = (d, color='var(--stage-ink)', fill='none', extra='') => `<path d="${d}" stroke="${color}" fill="${fill}" stroke-width="${GARMENT.width}" stroke-linejoin="miter" ${extra}/>`;
const project = (x,y,z) => {
  const f = GARMENT.focal / (GARMENT.focal-z);
  return [GARMENT.center[0]+(x-GARMENT.center[0])*f, GARMENT.center[1]+(y-GARMENT.center[1])*f-z*GARMENT.lift];
};
const foldedOutline = (() => {
  const d = 2*Math.SQRT2;
  return `<path fill="var(--stage-fold)" fill-rule="evenodd" d="M${74-d} 18H74V${42+d}L66 ${50+d}L${54-d} 38Z M70 ${22+d}L${54+d} 38L66 ${50-d}L70 ${46-d}Z"/>`;
})();
// Reconstruct the same miter a continuous outline would produce at a hinge.
// Two independently capped strokes share a center point but leave a triangular
// gap on the outside of the turn; these join polygons close that exact gap.
function clipPolygon(vertices, axis, boundary, keepGreater) {
  const inside = point => keepGreater ? point[axis]>=boundary : point[axis]<=boundary;
  const result=[];
  for(let i=0;i<vertices.length;i++) {
    const a=vertices[i], b=vertices[(i+1)%vertices.length];
    if(inside(a)) result.push(a);
    if(inside(a)!==inside(b)) {
      const t=(boundary-a[axis])/(b[axis]-a[axis]);
      result.push([a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]);
    }
  }
  return result;
}
function hingeJoin(a, p, b, color, boundToShoulder=false, miterLimit=4) {
  const unit = ([x,y]) => { const length=Math.hypot(x,y); return [x/length,y/length]; };
  const u=unit([p[0]-a[0],p[1]-a[1]]), v=unit([b[0]-p[0],b[1]-p[1]]);
  const cross=u[0]*v[1]-u[1]*v[0];
  if(Math.abs(cross)<1e-6) return '';
  const half=GARMENT.width/2;
  return [-1,1].map(sign=>{
    const q=[p[0]-u[1]*half*sign,p[1]+u[0]*half*sign];
    const s=[p[0]-v[1]*half*sign,p[1]+v[0]*half*sign];
    const along=((s[0]-q[0])*v[1]-(s[1]-q[1])*v[0])/cross;
    const m=[q[0]+along*u[0],q[1]+along*u[1]];
    // Match SVG's default miter limit for an almost edge-on panel.
    let vertices=Math.hypot(m[0]-p[0],m[1]-p[1])<=half*miterLimit?[p,q,m,s]:[p,q,s];
    // The shoulder belongs to the stationary torso. Its join must stay inside
    // the stroke footprint, even when the turning edge doubles back on itself.
    // Exact polygon clipping retains the connection without an outward spike.
    if(boundToShoulder) {
      for(const axis of [0,1]) {
        vertices=clipPolygon(vertices,axis,p[axis]-half,true);
        vertices=clipPolygon(vertices,axis,p[axis]+half,false);
      }
    }
    return `<polygon points="${points(vertices)}" fill="${color}"/>`;
  }).join('');
}
function sleeve(side, p) {
  const hinge = side==='right' ? 72 : 32;
  const angle = p*Math.PI;
  const pts = GARMENT[side].map(([x,y]) => project(hinge+(x-hinge)*Math.cos(angle), y, Math.abs(x-hinge)*Math.sin(angle)));
  const lift = Math.sin(angle);
  const fill = `color-mix(in srgb, var(--stage-reverse) ${n(lift*75)}%, var(--stage-paper))`;
  const color = `color-mix(in srgb, var(--stage-fold) ${n(clamp(p*5)*100)}%, var(--stage-ink))`;
  const shadow = lift > 0.01 ? `<polygon points="${points(pts.map(([x,y])=>[x+lift*2,y+lift*3]))}" fill="var(--stage-ink)" opacity="${n(lift*.09)}"/>` : '';
  // At rest use the exact approved mark, including its carefully drawn join.
  if(p===1) return `<polygon points="${points(pts)}" fill="var(--stage-paper)"/>${side==='left'?`<g transform="translate(104 0) scale(-1 1)">${foldedOutline}</g>`:foldedOutline}`;
  const openContour=`<polygon points="${points(pts)}" fill="${fill}"/>
    ${path(outline(pts),color,'none','stroke-linecap="butt"')}
    ${path(outline([pts[0],pts[3]]),color,'none',`opacity="${n(clamp(p*5))}" stroke-linecap="butt"`)}
    ${hingeJoin([side==='right'?60:40,20],pts[0],pts[1],color,true)}
    ${hingeJoin(pts[2],pts[3],[hinge,48],color)}`;
  // A moving panel is one opaque face with one closed contour. The hinge edge
  // and the diagonals share true SVG joins, not overlapping capped segments.
  // Clip only the shoulder's top: it is owned by the stationary torso and its
  // acute miter must not protrude above y=18. This converges to foldedOutline.
  // SVG bevels acute miters at its default limit, leaving a moving notch when
  // the sleeve turns edge-on. Calculate just this shoulder join without that
  // limit, then clip it to the fixed 4×4 hinge footprint before drawing it.
  // Other sleeve corners retain their existing joins and animation.
  const shoulder=hingeJoin(pts[3],pts[0],pts[1],color,true,Infinity);
  const joinedContour=path(outline(pts)+'Z',color,fill)+shoulder;
  const joined=ease(p/.18);
  return `${shadow}<svg x="0" y="18" width="104" height="78" viewBox="0 18 104 78" overflow="hidden">
    ${joined<1?`<g opacity="${n(1-joined)}">${openContour}</g>`:''}
    ${joined>0?`<g opacity="${n(joined)}">${joinedContour}</g>`:''}
  </svg>`;
}
function shirt(t) {
  const r = progress(t,TIMING.right), l = progress(t,TIMING.left), h = progress(t,TIMING.hem);
  if(r===0&&l===0&&h===0) return path('M32 76V44L26 50 14 38 32 20H40L45 28H55L60 20H72L90 38 78 50 72 44V76Z','var(--stage-ink)','var(--stage-paper)');
  if(r===1&&l===0&&h===0) return path('M72 76H32V44L26 50 14 38 32 20H40L45 28H55L60 20H72V76Z','var(--stage-ink)','var(--stage-paper)')+foldedOutline;
  const body = 'M32 48V20H40L45 28H55L60 20H72V48Z';
  let markup = `<path d="${body}" fill="var(--stage-paper)"/>
    ${path('M32 48V44M32 20H40L45 28H55L60 20H72M72 44V48')}
    ${sleeve('right',r)}${sleeve('left',l)}`;
  const angle = h*Math.PI;
  const hem = GARMENT.hem.map(([x,y]) => project(x,48+(y-48)*Math.cos(angle),(y-48)*Math.sin(angle)));
  const lift = Math.sin(angle);
  const hemColor=`color-mix(in srgb,var(--stage-fold) ${n(ease(h*5)*100)}%,var(--stage-ink))`;
  // The hinge is not a visible seam across the shirt. Reveal its outline only
  // as it becomes the bottom boundary of the finished packet.
  const closure=ease((h-.85)/.15);
  const hemMarkup = `<polygon points="${points(hem)}" fill="color-mix(in srgb,var(--stage-reverse) ${n(lift*65)}%,var(--stage-paper))"/>
    ${path(outline([hem[0],hem[3],hem[2],hem[1]]),hemColor)}
    ${closure>0?path(outline([hem[0],hem[1]]),'var(--stage-fold)','none',`opacity="${n(closure)}" stroke-linecap="square"`):''}
    ${h>0?hingeJoin([32,44],hem[0],hem[3],hemColor,true)+hingeJoin(hem[2],hem[1],[72,44],hemColor,true):''}`;
  if(h===0) return hemMarkup+markup;
  // Split the artwork at the material crease. The small cuff tips below y=48
  // belong to the lower panel and rotate WITH it, rather than being trimmed
  // away while the panel is still face-up.
  const visibleHeight=48;
  const upper=`<svg x="0" y="0" width="104" height="${n(visibleHeight)}" viewBox="0 0 104 ${n(visibleHeight)}" overflow="hidden">${markup}</svg>`;
  const d=2*Math.SQRT2;
  const rightTip=clipPolygon([[74-d,18],[74,18],[74,42+d],[66,50+d],[54-d,38]],1,48,true);
  const tips=[rightTip,rightTip.map(([x,y])=>[104-x,y])].map(vertices=>{
    const projected=vertices.map(([x,y])=>project(x,48+(y-48)*Math.cos(angle),(y-48)*Math.sin(angle)));
    // The printed tip shrinks to the crease as its face turns away. Once on
    // the underside it is occluded by the opaque, unmarked reverse face.
    const depth=Math.max(...projected.map(([,y])=>y))-48;
    return depth>0?`<polygon points="${points(projected)}" fill="var(--stage-fold)"/>`:'';
  }).join('');
  // Once the face has crossed the hinge, its stroke caps and joins belong to
  // that same visible half-plane. Only the final outline adds half a stroke.
  const frontHeight=48+GARMENT.width/2*closure;
  const front=h>=.5?`<svg x="0" y="0" width="104" height="${n(frontHeight)}" viewBox="0 0 104 ${n(frontHeight)}" overflow="hidden">${hemMarkup}</svg>`:hemMarkup;
  return upper+front+tips;
}
function scene(t) {
  const insert = progress(t,TIMING.insert), exit = progress(t,TIMING.exit), entry = progress(t,TIMING.sleeve);
  const newShirt = t >= TIMING.next[0];
  let markup = '';
  if(newShirt) {
    markup = `<g transform="translate(8 ${n(4+GARMENT.nextDistance*(1-progress(t,TIMING.next)))})">${shirt(0)}</g>`;
  } else if(t<TIMING.exit[1]) {
    markup = `<g transform="translate(8 ${n(4+insert*GARMENT.insertDistance+exit*PACKAGING.exit)})">${shirt(t)}</g>`;
  }
  if(t>=TIMING.sleeve[0]&&t<TIMING.exit[1]) {
    const y=PACKAGING.entry*(1-entry)+exit*PACKAGING.exit;
    markup += `<rect x="${PACKAGING.x}" y="${n(PACKAGING.top+y)}" width="${PACKAGING.width}" height="${PACKAGING.bottom-PACKAGING.top}" fill="var(--stage-sleeve)" stroke="var(--stage-ink)" stroke-width="2"/>`;
  }
  return markup;
}

export const XFOLD_CYCLE_MS = TIMING.duration;
export const XFOLD_REST_FRAME = 1150;
export { scene as renderXFoldFrame, TIMING };
